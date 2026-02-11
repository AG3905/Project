from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os
import time

app = Flask(__name__)
CORS(app)

DATABASE = 'dining_system.db'

# ==================== ASP-BFA Algorithm Configuration ====================
# Priority scoring weights
WEIGHT_WAITING_TIME = 3  # W1: Aging factor (fairness)
WEIGHT_GROUP_SIZE = 1    # W2: Group size factor (efficiency)

# Starvation prevention
WAIT_THRESHOLD = 300  # seconds (5 minutes) - threshold for high priority boost
HIGH_PRIORITY_BONUS = 100  # bonus points when exceeding wait threshold

# Rush hour detection
RUSH_HOUR_QUEUE_LIMIT = 10  # if queue > 10, increase fairness weight
RUSH_HOUR_WEIGHT_MULTIPLIER = 1.5  # increase W1 during rush hours

# Merging constraints
MAX_CONSECUTIVE_TABLES = None  # Will be set dynamically based on total restaurant tables
ADJACENCY_ONLY = True  # only merge adjacent tables


def get_total_restaurant_tables(cursor):
    """Get total number of tables in the restaurant"""
    cursor.execute('SELECT COUNT(*) FROM tables')
    return cursor.fetchone()[0]


def get_max_consecutive_tables(cursor):
    """
    Dynamically set MAX_CONSECUTIVE_TABLES based on total restaurant tables
    This prevents memory issues and ensures realistic merging
    
    Logic:
    - If total tables <= 5: can merge all tables
    - If total tables 5-10: can merge up to 80% of tables
    - If total tables > 10: can merge up to 70% of tables
    """
    total_tables = get_total_restaurant_tables(cursor)
    
    if total_tables <= 5:
        return total_tables  # Can merge all small restaurants' tables
    elif total_tables <= 10:
        return max(2, int(total_tables * 0.8))
    else:
        return max(2, int(total_tables * 0.7))

def get_db_connection():
    """Create a database connection with error handling"""
    try:
        conn = sqlite3.connect(DATABASE, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Enable foreign keys
        conn.execute('PRAGMA foreign_keys = ON')
        return conn
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        raise

def init_db():
    """Initialize the database with ASP-BFA schema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create enhanced tables table with position_index and merge_group_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number INTEGER UNIQUE NOT NULL,
            seating_capacity INTEGER NOT NULL,
            status TEXT DEFAULT 'available',
            position_x INTEGER,
            position_y INTEGER,
            position_index INTEGER,
            merge_group_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create bookings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT UNIQUE NOT NULL,
            table_ids TEXT,
            customer_name TEXT NOT NULL,
            group_size INTEGER NOT NULL,
            booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            merge_count INTEGER DEFAULT 0,
            priority_score REAL DEFAULT 0.0
        )
    ''')
    
    # Create enhanced waiting queue table for ASP-BFA
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waiting_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            group_size INTEGER NOT NULL,
            arrival_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            waiting_time REAL DEFAULT 0,
            priority_score REAL DEFAULT 0,
            status TEXT DEFAULT 'waiting',
            position INTEGER,
            starvation_flag INTEGER DEFAULT 0
        )
    ''')
    
    # CLEAR ALL BOOKINGS AND QUEUE ON RESTART
    cursor.execute('DELETE FROM bookings')
    cursor.execute('DELETE FROM waiting_queue')
    
    # Reset all tables to available status and remove merge groups
    cursor.execute('''
        UPDATE tables
        SET status = 'available', merge_group_id = NULL
    ''')
    
    # Check if tables are already populated
    cursor.execute('SELECT COUNT(*) FROM tables')
    if cursor.fetchone()[0] == 0:
        # Insert initial table data with position_index for sequential merging
        tables_data = [
            (1, 2, 'available', 100, 100, 0, None),
            (2, 2, 'available', 250, 100, 1, None),
            (3, 4, 'available', 100, 250, 2, None),
            (4, 4, 'available', 250, 250, 3, None),
            (5, 6, 'available', 100, 400, 4, None),
            (6, 6, 'available', 250, 400, 5, None)
        ]
        cursor.executemany('''
            INSERT INTO tables (table_number, seating_capacity, status, position_x, position_y, position_index, merge_group_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', tables_data)
    
    conn.commit()
    conn.close()

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify server is running"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM tables')
        table_count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'success': True,
            'status': 'healthy',
            'tables_count': table_count,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'unhealthy',
            'error': str(e)
        }), 500



# ==================== ASP-BFA Core Algorithm Functions ====================

def get_waiting_queue(cursor):
    """Retrieve all waiting groups with current waiting time"""
    cursor.execute('''
        SELECT id, group_id, customer_name, group_size, arrival_time, 
               priority_score, starvation_flag
        FROM waiting_queue
        WHERE status = 'waiting'
        ORDER BY priority_score DESC, arrival_time ASC
    ''')
    return cursor.fetchall()


def calculate_priority_score(group_size, waiting_time_seconds, is_starving=False):
    """
    Calculate ASP-BFA priority score
    
    Formula:
    priority_score = (waiting_time × W1) + (group_size × W2)
    if starving: priority_score += HIGH_PRIORITY_BONUS
    """
    base_score = (waiting_time_seconds * WEIGHT_WAITING_TIME) + (group_size * WEIGHT_GROUP_SIZE)
    
    if is_starving:
        base_score += HIGH_PRIORITY_BONUS
    
    return base_score


def detect_rush_hour(cursor):
    """
    Detect if system is in rush hour based on queue length
    Returns adjusted weight_waiting_time
    """
    cursor.execute('SELECT COUNT(*) FROM waiting_queue WHERE status = "waiting"')
    queue_length = cursor.fetchone()[0]
    
    if queue_length > RUSH_HOUR_QUEUE_LIMIT:
        return WEIGHT_WAITING_TIME * RUSH_HOUR_WEIGHT_MULTIPLIER
    
    return WEIGHT_WAITING_TIME


def update_queue_priority_scores(cursor, conn):
    """Update waiting times and priority scores for all groups in queue"""
    current_time = datetime.now()
    
    cursor.execute('''
        SELECT id, group_id, group_size, arrival_time, waiting_time
        FROM waiting_queue
        WHERE status = 'waiting'
    ''')
    
    queue_groups = cursor.fetchall()
    w1 = detect_rush_hour(cursor)
    
    for group in queue_groups:
        arrival = datetime.fromisoformat(group['arrival_time'])
        waiting_seconds = (current_time - arrival).total_seconds()
        
        # Check if group is starving (exceeds wait threshold)
        is_starving = waiting_seconds >= WAIT_THRESHOLD
        
        # Calculate new priority score
        priority_score = calculate_priority_score(
            group['group_size'],
            waiting_seconds,
            is_starving
        )
        
        # Update the queue entry
        cursor.execute('''
            UPDATE waiting_queue
            SET waiting_time = ?, priority_score = ?, starvation_flag = ?
            WHERE id = ?
        ''', (waiting_seconds, priority_score, 1 if is_starving else 0, group['id']))
    
    conn.commit()


def find_best_single_table(cursor, group_size):
    """
    Step 5: Find best single table for group (Best-Fit)
    
    Returns:
        Tuple (table_id, table_number, capacity, wasted_seats)
        or None if no suitable table found
    """
    cursor.execute('''
        SELECT id, table_number, seating_capacity
        FROM tables
        WHERE status = 'available' AND seating_capacity >= ?
        ORDER BY seating_capacity ASC
        LIMIT 1
    ''', (group_size,))
    
    table = cursor.fetchone()
    
    if table:
        wasted_seats = table['seating_capacity'] - group_size
        return (table['id'], table['table_number'], table['seating_capacity'], wasted_seats)
    
    return None


def find_sequential_table_merging(cursor, group_size):
    """
    Step 6: Find sequential table merging solution
    
    Dynamically limits merging based on total restaurant tables
    Returns:
        Tuple (table_list, table_numbers, total_capacity, wasted_seats, merge_count)
        or None if no valid merge sequence found
    """
    # Get the maximum consecutive tables allowed (dynamic based on restaurant size)
    max_merge = get_max_consecutive_tables(cursor)
    
    # Get all available tables sorted by position_index
    cursor.execute('''
        SELECT id, table_number, seating_capacity, position_index
        FROM tables
        WHERE status = 'available' AND merge_group_id IS NULL
        ORDER BY position_index ASC
    ''')
    
    available_tables = cursor.fetchall()
    
    if len(available_tables) < 2:
        return None  # Need at least 2 tables to merge
    
    best_solution = None
    best_wasted_seats = float('inf')
    
    # Try all possible contiguous sequences (limited by max_merge and restaurant table count)
    for start_idx in range(len(available_tables)):
        for end_idx in range(start_idx + 1, min(start_idx + max_merge + 1, len(available_tables) + 1)):
            sequence = available_tables[start_idx:end_idx]
            
            # Calculate total capacity
            total_capacity = sum(table['seating_capacity'] for table in sequence)
            
            if total_capacity >= group_size:
                wasted_seats = total_capacity - group_size
                merge_count = len(sequence)
                
                # Check adjacency constraint
                if ADJACENCY_ONLY:
                    positions = [table['position_index'] for table in sequence]
                    is_adjacent = all(positions[i+1] - positions[i] == 1 for i in range(len(positions)-1))
                    if not is_adjacent:
                        continue
                
                # Update best solution if this is better
                # Priority: minimize wasted seats, then minimize table count, then shortest physical distance
                if (wasted_seats < best_wasted_seats or 
                    (wasted_seats == best_wasted_seats and merge_count < best_solution[4] if best_solution else True)):
                    
                    table_ids = [table['id'] for table in sequence]
                    table_numbers = [table['table_number'] for table in sequence]
                    
                    best_solution = (table_ids, table_numbers, total_capacity, wasted_seats, merge_count)
                    best_wasted_seats = wasted_seats
    
    return best_solution


def merge_tables(cursor, conn, table_ids, merge_group_id):
    """
    Create a merged table group
    
    Sets the merge_group_id for all tables in the merge
    """
    for table_id in table_ids:
        cursor.execute('''
            UPDATE tables
            SET status = 'booked', merge_group_id = ?
            WHERE id = ?
        ''', (merge_group_id, table_id))
    
    conn.commit()


def unmerge_tables(cursor, conn, table_ids):
    """
    Release tables from a merged group
    """
    for table_id in table_ids:
        cursor.execute('''
            UPDATE tables
            SET status = 'available', merge_group_id = NULL
            WHERE id = ?
        ''', (table_id,))
    
    conn.commit()


def allocate_table_asp_bfa(cursor, conn, customer_name, group_size):
    """
    Main ASP-BFA Allocation Algorithm
    
    Steps:
    1. Generate unique group_id
    2. Add to waiting queue
    3. Update priority scores for all groups
    4. Try best-fit single table allocation
    5. If fails, try sequential table merging
    6. If still fails, keep waiting (return queued=True)
    
    Returns:
        Dictionary with allocation result
    """
    import uuid
    
    # Step 1: Generate unique group_id
    group_id = str(uuid.uuid4())[:8]
    
    # Step 2: Add initial queue entry
    current_time = datetime.now()
    cursor.execute('''
        INSERT INTO waiting_queue (group_id, customer_name, group_size, arrival_time, 
                                   waiting_time, priority_score, status, position)
        VALUES (?, ?, ?, ?, ?, ?, 'waiting', 1)
    ''', (group_id, customer_name, group_size, current_time, 0, 0))
    
    conn.commit()
    queue_entry_id = cursor.lastrowid
    
    # Step 3: Update priority scores for all waiting groups
    update_queue_priority_scores(cursor, conn)
    
    # Step 4: Try best-fit single table allocation
    single_table = find_best_single_table(cursor, group_size)
    
    if single_table:
        table_id, table_number, capacity, wasted = single_table
        
        # Allocate the table
        cursor.execute('''
            UPDATE tables
            SET status = 'booked'
            WHERE id = ?
        ''', (table_id,))
        
        # Create booking
        cursor.execute('''
            INSERT INTO bookings (group_id, table_ids, customer_name, group_size, 
                                 status, merge_count, priority_score)
            VALUES (?, ?, ?, ?, 'active', 0, ?)
        ''', (group_id, str(table_id), customer_name, group_size, 0))
        
        # Remove from queue
        cursor.execute('''
            UPDATE waiting_queue
            SET status = 'allocated'
            WHERE group_id = ?
        ''', (group_id,))
        
        conn.commit()
        booking_id = cursor.lastrowid
        
        return {
            'success': True,
            'queued': False,
            'booking_id': booking_id,
            'group_id': group_id,
            'allocated_tables': [table_number],
            'merge_count': 0,
            'table_capacity': capacity,
            'wasted_seats': wasted,
            'message': f'Table {table_number} allocated to {customer_name}'
        }
    
    # Step 5: Try sequential table merging
    merge_solution = find_sequential_table_merging(cursor, group_size)
    
    if merge_solution:
        table_ids, table_numbers, total_capacity, wasted, merge_count = merge_solution
        
        # Merge tables
        merge_tables(cursor, conn, table_ids, queue_entry_id)
        
        # Create booking
        cursor.execute('''
            INSERT INTO bookings (group_id, table_ids, customer_name, group_size, 
                                 status, merge_count, priority_score)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
        ''', (group_id, ','.join(map(str, table_ids)), customer_name, group_size, merge_count, 0))
        
        # Remove from queue
        cursor.execute('''
            UPDATE waiting_queue
            SET status = 'allocated'
            WHERE group_id = ?
        ''', (group_id,))
        
        conn.commit()
        booking_id = cursor.lastrowid
        
        return {
            'success': True,
            'queued': False,
            'booking_id': booking_id,
            'group_id': group_id,
            'allocated_tables': table_numbers,
            'merge_count': merge_count,
            'table_capacity': total_capacity,
            'wasted_seats': wasted,
            'message': f'Merged {merge_count} tables ({table_numbers}) for {customer_name}'
        }
    
    # Step 6: No allocation possible - add to waiting queue
    cursor.execute('''
        SELECT COUNT(*) FROM waiting_queue WHERE status = 'waiting'
    ''')
    queue_position = cursor.fetchone()[0]
    
    cursor.execute('''
        UPDATE waiting_queue
        SET position = ?
        WHERE group_id = ?
    ''', (queue_position, group_id))
    
    conn.commit()
    
    return {
        'success': True,
        'queued': True,
        'group_id': group_id,
        'customer_name': customer_name,
        'group_size': group_size,
        'queue_position': queue_position,
        'message': f'{customer_name} added to waiting queue at position {queue_position}'
    }


def process_queue_asp_bfa(cursor, conn):
    """
    Process waiting queue with ASP-BFA algorithm
    
    Called whenever a table is freed up
    Attempts to allocate tables to high-priority waiting groups
    """
    update_queue_priority_scores(cursor, conn)
    
    # Get waiting groups sorted by priority
    waiting_groups = get_waiting_queue(cursor)
    allocated_count = 0
    
    for group in waiting_groups:
        group_id = group['group_id']
        customer_name = group['customer_name']
        group_size = group['group_size']
        
        # Try best-fit single table
        single_table = find_best_single_table(cursor, group_size)
        
        if single_table:
            table_id, table_number, capacity, wasted = single_table
            
            # Allocate
            cursor.execute('''
                UPDATE tables
                SET status = 'booked'
                WHERE id = ?
            ''', (table_id,))
            
            # Create booking
            cursor.execute('''
                INSERT INTO bookings (group_id, table_ids, customer_name, group_size, 
                                     status, merge_count, priority_score)
                VALUES (?, ?, ?, ?, 'active', 0, ?)
            ''', (group_id, str(table_id), customer_name, group_size, group['priority_score']))
            
            # Update queue
            cursor.execute('''
                UPDATE waiting_queue
                SET status = 'allocated'
                WHERE group_id = ?
            ''', (group_id,))
            
            conn.commit()
            allocated_count += 1
            continue
        
        # Try sequential merging
        merge_solution = find_sequential_table_merging(cursor, group_size)
        
        if merge_solution:
            table_ids, table_numbers, total_capacity, wasted, merge_count = merge_solution
            
            merge_tables(cursor, conn, table_ids, group['id'])
            
            cursor.execute('''
                INSERT INTO bookings (group_id, table_ids, customer_name, group_size, 
                                     status, merge_count, priority_score)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
            ''', (group_id, ','.join(map(str, table_ids)), customer_name, group_size, merge_count, group['priority_score']))
            
            cursor.execute('''
                UPDATE waiting_queue
                SET status = 'allocated'
                WHERE group_id = ?
            ''', (group_id,))
            
            conn.commit()
            allocated_count += 1
    
    # Update queue positions for remaining groups
    cursor.execute('''
        SELECT id FROM waiting_queue
        WHERE status = 'waiting'
        ORDER BY priority_score DESC, arrival_time ASC
    ''')
    
    remaining = cursor.fetchall()
    for idx, item in enumerate(remaining):
        cursor.execute('''
            UPDATE waiting_queue
            SET position = ?
            WHERE id = ?
        ''', (idx + 1, item['id']))
    
    conn.commit()
    return {'allocated': allocated_count}


@app.route('/api/tables', methods=['GET'])
def get_tables():
    """Get all tables with their current status"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute('''
            SELECT id, table_number, seating_capacity, status, 
                   position_x, position_y, position_index, merge_group_id
            FROM tables
            ORDER BY position_index ASC
        ''')
        
        tables = []
        table_rows = cursor.fetchall()
        
        for table_row in table_rows:
            table_id = table_row['id']
            
            # Get booking for this table (if exists)
            cursor.execute('''
                SELECT b.customer_name, b.group_size, b.booking_time, b.merge_count
                FROM bookings b
                WHERE b.status = 'active' AND b.table_ids LIKE ?
            ''', (f'%{table_id}%',))
            
            booking_row = cursor.fetchone()
            
            tables.append({
                'id': table_row['id'],
                'table_number': table_row['table_number'],
                'seating_capacity': table_row['seating_capacity'],
                'status': table_row['status'],
                'position_x': table_row['position_x'],
                'position_y': table_row['position_y'],
                'position_index': table_row['position_index'],
                'is_merged': table_row['merge_group_id'] is not None,
                'merge_group_id': table_row['merge_group_id'],
                'booking': {
                    'customer_name': booking_row['customer_name'],
                    'group_size': booking_row['group_size'],
                    'booking_time': booking_row['booking_time'],
                    'merge_count': booking_row['merge_count']
                } if booking_row else None
            })
        
        conn.close()
        return jsonify({'success': True, 'tables': tables})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/book', methods=['POST'])
def book_table():
    """
    Book a table using ASP-BFA (Adaptive Spatial Priority Best-Fit Allocation) Algorithm
    
    Handles:
    - FIFO fairness
    - Starvation prevention (aging)
    - Best-fit efficiency
    - Sequential table merging
    - Rush hour balancing
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        customer_name = data.get('customer_name', '').strip()
        group_size = data.get('group_size')
        
        # Validation
        if not customer_name:
            return jsonify({
                'success': False,
                'error': 'Customer name is required'
            }), 400
        
        if group_size is None:
            return jsonify({
                'success': False,
                'error': 'Group size is required'
            }), 400
        
        if not isinstance(group_size, int):
            return jsonify({
                'success': False,
                'error': 'Group size must be a number'
            }), 400
        
        if group_size <= 0 or group_size > 1000:
            return jsonify({
                'success': False,
                'error': 'Group size must be between 1 and 1000'
            }), 400
        
        if len(customer_name) > 100:
            return jsonify({
                'success': False,
                'error': 'Customer name is too long (max 100 characters)'
            }), 400
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Use ASP-BFA algorithm
            result = allocate_table_asp_bfa(cursor, conn, customer_name, group_size)
            
            if result['queued']:
                return jsonify({
                    'success': result['success'],
                    'queued': True,
                    'message': result['message'],
                    'group_id': result['group_id'],
                    'queue_position': result['queue_position']
                })
            else:
                return jsonify({
                    'success': result['success'],
                    'queued': False,
                    'message': result['message'],
                    'group_id': result['group_id'],
                    'booking_id': result['booking_id'],
                    'allocated_tables': result['allocated_tables'],
                    'merge_count': result['merge_count'],
                    'table_capacity': result['table_capacity'],
                    'wasted_seats': result['wasted_seats']
                })
        finally:
            if conn:
                conn.close()
    except Exception as e:
        print(f"[ERROR] Booking error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cancel/<booking_id>', methods=['DELETE'])
def cancel_booking(booking_id):
    """
    Cancel a booking and free up the allocated tables
    Automatically processes waiting queue using ASP-BFA
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Validate booking_id
        try:
            booking_id_int = int(booking_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid booking ID'
            }), 400
        
        # Get booking details
        cursor.execute('''
            SELECT group_id, table_ids, status
            FROM bookings
            WHERE id = ? AND status = 'active'
        ''', (booking_id_int,))
        
        booking = cursor.fetchone()
        
        if not booking:
            return jsonify({
                'success': False,
                'error': 'Booking not found or already cancelled'
            }), 404
        
        # Parse table IDs
        table_ids = list(map(int, booking['table_ids'].split(','))) if ',' in booking['table_ids'] else [int(booking['table_ids'])]
        
        # Mark booking as cancelled
        cursor.execute('''
            UPDATE bookings
            SET status = 'cancelled'
            WHERE id = ?
        ''', (booking_id_int,))
        
        # Free up the tables
        for table_id in table_ids:
            cursor.execute('''
                UPDATE tables
                SET status = 'available', merge_group_id = NULL
                WHERE id = ?
            ''', (table_id,))
        
        conn.commit()
        
        # Process queue with ASP-BFA algorithm
        result = process_queue_asp_bfa(cursor, conn)
        
        return jsonify({
            'success': True,
            'message': 'Booking cancelled successfully',
            'tables_freed': len(table_ids),
            'queue_processed': result
        })
    except ValueError:
        return jsonify({
            'success': False,
            'error': 'Invalid booking ID format'
        }), 400
    except Exception as e:
        print(f"[ERROR] Cancel booking error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    """Get all active bookings with ASP-BFA details"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.group_id, b.customer_name, b.group_size, b.booking_time,
                   b.table_ids, b.merge_count, b.priority_score
            FROM bookings b
            WHERE b.status = 'active'
            ORDER BY b.booking_time DESC
        ''')
        
        bookings = []
        for row in cursor.fetchall():
            table_ids = list(map(int, row['table_ids'].split(','))) if ',' in row['table_ids'] else [int(row['table_ids'])]
            
            bookings.append({
                'id': row['id'],
                'group_id': row['group_id'],
                'customer_name': row['customer_name'],
                'group_size': row['group_size'],
                'booking_time': row['booking_time'],
                'table_ids': table_ids,
                'merge_count': row['merge_count'],
                'priority_score': row['priority_score']
            })
        
        conn.close()
        return jsonify({'success': True, 'bookings': bookings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/queue', methods=['GET'])
def get_queue():
    """Get all customers in waiting queue with ASP-BFA priority info"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, group_id, customer_name, group_size, arrival_time, 
                   waiting_time, priority_score, position, starvation_flag
            FROM waiting_queue
            WHERE status = 'waiting'
            ORDER BY priority_score DESC, arrival_time ASC
        ''')
        
        queue = []
        for row in cursor.fetchall():
            queue.append({
                'id': row['id'],
                'group_id': row['group_id'],
                'customer_name': row['customer_name'],
                'group_size': row['group_size'],
                'arrival_time': row['arrival_time'],
                'waiting_time': row['waiting_time'],
                'priority_score': row['priority_score'],
                'position': row['position'],
                'is_starving': bool(row['starvation_flag'])
            })
        
        conn.close()
        return jsonify({'success': True, 'queue': queue})
    except Exception as e:
        print(f"[ERROR] Get queue error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/queue/cancel/<queue_entry_id>', methods=['DELETE'])
def cancel_queue_entry(queue_entry_id):
    """
    Cancel a waiting queue entry
    Removes the group from the queue and updates positions
    """
    conn = None
    try:
        # Validate queue_entry_id
        try:
            queue_id_int = int(queue_entry_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid queue entry ID'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get queue entry details
        cursor.execute('''
            SELECT id, group_id, customer_name, group_size, position, status
            FROM waiting_queue
            WHERE id = ? AND status = 'waiting'
        ''', (queue_id_int,))
        
        queue_entry = cursor.fetchone()
        
        if not queue_entry:
            return jsonify({
                'success': False,
                'error': 'Queue entry not found or already cancelled'
            }), 404
        
        # Remove from queue
        cursor.execute('''
            UPDATE waiting_queue
            SET status = 'cancelled'
            WHERE id = ?
        ''', (queue_id_int,))
        
        conn.commit()
        
        # Update queue positions for remaining entries
        cursor.execute('''
            SELECT id FROM waiting_queue
            WHERE status = 'waiting'
            ORDER BY priority_score DESC, arrival_time ASC
        ''')
        
        remaining = cursor.fetchall()
        for idx, item in enumerate(remaining):
            cursor.execute('''
                UPDATE waiting_queue
                SET position = ?
                WHERE id = ?
            ''', (idx + 1, item['id']))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Queue entry for {queue_entry["customer_name"]} (Group size: {queue_entry["group_size"]}) has been cancelled',
            'cancelled_group_id': queue_entry['group_id'],
            'queue_positions_updated': len(remaining)
        })
    except Exception as e:
        print(f"[ERROR] Cancel queue entry error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/queue/cancel-by-group/<group_id>', methods=['DELETE'])
def cancel_queue_by_group_id(group_id):
    """
    Cancel a waiting queue entry by group_id
    Removes the group from the queue and updates positions
    """
    conn = None
    try:
        # Validate group_id
        if not group_id or len(group_id) == 0:
            return jsonify({
                'success': False,
                'error': 'Invalid group ID'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get queue entry details by group_id
        cursor.execute('''
            SELECT id, group_id, customer_name, group_size, position, status
            FROM waiting_queue
            WHERE group_id = ? AND status = 'waiting'
        ''', (group_id,))
        
        queue_entry = cursor.fetchone()
        
        if not queue_entry:
            return jsonify({
                'success': False,
                'error': 'Queue entry not found or already cancelled'
            }), 404
        
        queue_id = queue_entry['id']
        
        # Remove from queue
        cursor.execute('''
            UPDATE waiting_queue
            SET status = 'cancelled'
            WHERE id = ?
        ''', (queue_id,))
        
        conn.commit()
        
        # Update queue positions for remaining entries
        cursor.execute('''
            SELECT id FROM waiting_queue
            WHERE status = 'waiting'
            ORDER BY priority_score DESC, arrival_time ASC
        ''')
        
        remaining = cursor.fetchall()
        for idx, item in enumerate(remaining):
            cursor.execute('''
                UPDATE waiting_queue
                SET position = ?
                WHERE id = ?
            ''', (idx + 1, item['id']))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Queue entry for {queue_entry["customer_name"]} (Group size: {queue_entry["group_size"]}) has been cancelled',
            'cancelled_group_id': queue_entry['group_id'],
            'queue_positions_updated': len(remaining)
        })
    except Exception as e:
        print(f"[ERROR] Cancel queue by group error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

def reset_system():
    """Reset all bookings, queue and make all tables available"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Cancel all active bookings
        cursor.execute('''
            UPDATE bookings
            SET status = 'cancelled'
            WHERE status = 'active'
        ''')
        
        # Clear waiting queue
        cursor.execute('''
            DELETE FROM waiting_queue
        ''')
        
        # Make all tables available
        cursor.execute('''
            UPDATE tables
            SET status = 'available', merge_group_id = NULL
        ''')
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'System reset successfully. All tables available.'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/algorithm-info', methods=['GET'])
def get_algorithm_info():
    """Get comprehensive information about ASP-BFA algorithm and all API endpoints"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        total_tables = get_total_restaurant_tables(cursor)
        max_merge = get_max_consecutive_tables(cursor)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'system': 'SMART DINING SYSTEM',
            'algorithm': 'ASP-BFA',
            'full_name': 'Adaptive Spatial Priority Best-Fit Allocation Algorithm',
            'version': '1.0.0',
            
            'core_features': [
                'FIFO fairness - First-come, first-served queue processing',
                'Best-fit efficiency - Allocates smallest suitable table to minimize wastage',
                'Starvation prevention (aging) - Boosts priority for groups waiting > 5 min',
                'Multi-table merging - Combines adjacent tables for large groups',
                'Sequential/adjacent table merging - Only merges physically adjacent tables',
                'Large-group starvation avoidance - Ensures big groups eventually get seated',
                'Table wastage minimization - Optimizes seating to minimize empty seats',
                'Rush-hour balancing - Adjusts priorities when queue > 10 groups'
            ],
            
            'configuration': {
                'weight_waiting_time': WEIGHT_WAITING_TIME,
                'weight_group_size': WEIGHT_GROUP_SIZE,
                'wait_threshold_seconds': WAIT_THRESHOLD,
                'high_priority_bonus': HIGH_PRIORITY_BONUS,
                'rush_hour_queue_limit': RUSH_HOUR_QUEUE_LIMIT,
                'rush_hour_weight_multiplier': RUSH_HOUR_WEIGHT_MULTIPLIER,
                'adjacency_only': ADJACENCY_ONLY,
                'total_restaurant_tables': total_tables,
                'max_consecutive_tables_allowed': max_merge,
                'max_merge_logic': 'Dynamic: All tables if ≤5, 80% if 5-10, 70% if >10'
            },
            
            'api_endpoints': {
                'booking_management': [
                    {
                        'method': 'POST',
                        'endpoint': '/api/book',
                        'description': 'Create new booking using ASP-BFA algorithm',
                        'request_body': {'customer_name': 'string', 'group_size': 'integer'},
                        'response': {'success': 'boolean', 'queued': 'boolean', 'group_id': 'string', 'allocated_tables': 'array'}
                    },
                    {
                        'method': 'DELETE',
                        'endpoint': '/api/cancel/<booking_id>',
                        'description': 'Cancel an active booking and process queue',
                        'parameters': {'booking_id': 'integer (database ID)'},
                        'response': {'success': 'boolean', 'tables_freed': 'integer', 'queue_processed': 'object'}
                    }
                ],
                'table_management': [
                    {
                        'method': 'GET',
                        'endpoint': '/api/tables',
                        'description': 'Get all tables with their current status and booking info',
                        'response': {'success': 'boolean', 'tables': 'array'}
                    },
                    {
                        'method': 'GET',
                        'endpoint': '/api/bookings',
                        'description': 'Get all active bookings with merge info',
                        'response': {'success': 'boolean', 'bookings': 'array'}
                    }
                ],
                'queue_management': [
                    {
                        'method': 'GET',
                        'endpoint': '/api/queue',
                        'description': 'Get all waiting groups in queue with priority scores',
                        'response': {'success': 'boolean', 'queue': 'array with position, priority_score, is_starving'}
                    },
                    {
                        'method': 'DELETE',
                        'endpoint': '/api/queue/cancel/<queue_entry_id>',
                        'description': 'Cancel a waiting queue entry by database ID',
                        'parameters': {'queue_entry_id': 'integer (database ID)'},
                        'response': {'success': 'boolean', 'message': 'string', 'queue_positions_updated': 'integer'}
                    },
                    {
                        'method': 'DELETE',
                        'endpoint': '/api/queue/cancel-by-group/<group_id>',
                        'description': 'Cancel a waiting queue entry by group_id',
                        'parameters': {'group_id': 'string (UUID)'},
                        'response': {'success': 'boolean', 'message': 'string', 'queue_positions_updated': 'integer'}
                    }
                ],
                'system_management': [
                    {
                        'method': 'POST',
                        'endpoint': '/api/reset',
                        'description': 'Reset entire system - clear all bookings and queue',
                        'response': {'success': 'boolean', 'message': 'string'}
                    },
                    {
                        'method': 'GET',
                        'endpoint': '/api/health',
                        'description': 'Health check endpoint - verify server is running',
                        'response': {'success': 'boolean', 'status': 'string', 'tables_count': 'integer'}
                    },
                    {
                        'method': 'GET',
                        'endpoint': '/api/algorithm-info',
                        'description': 'Get complete backend logic information (this endpoint)',
                        'response': {'success': 'boolean', 'algorithm': 'object with detailed info'}
                    }
                ]
            },
            
            'priority_score_formula': {
                'description': 'Calculates group priority for queue processing',
                'formula': 'priority_score = (waiting_time × W1) + (group_size × W2) [+ starvation_bonus if waiting > threshold]',
                'variables': {
                    'W1': f'{WEIGHT_WAITING_TIME} (waiting time weight - fairness)',
                    'W2': f'{WEIGHT_GROUP_SIZE} (group size weight - efficiency)',
                    'starvation_bonus': f'+{HIGH_PRIORITY_BONUS} points when waiting > {WAIT_THRESHOLD}s'
                }
            },
            
            'allocation_algorithm_flow': {
                'step_1': 'Customer arrival - Add to waiting queue with unique group_id',
                'step_2': 'Priority update - Recalculate waiting times and scores for all groups',
                'step_3': 'Starvation check - Detect if group exceeds wait threshold and apply boost',
                'step_4': 'Single table check - Try best-fit allocation from available tables',
                'step_5': 'Multi-table merge - If single table fails, find adjacent table sequences',
                'step_6': 'Queue waiting - If no allocation possible, group waits in queue',
                'step_7': 'Auto-process - When table frees up, process queue and allocate to next groups'
            },
            
            'data_structures': {
                'tables': {
                    'fields': ['id', 'table_number', 'seating_capacity', 'status', 'position_index', 'merge_group_id'],
                    'status_values': ['available', 'booked'],
                    'position_index': 'Used for sequential/adjacent table merging'
                },
                'bookings': {
                    'fields': ['id', 'group_id', 'table_ids', 'customer_name', 'group_size', 'status', 'merge_count', 'priority_score'],
                    'status_values': ['active', 'cancelled'],
                    'table_ids': 'Comma-separated list for merged tables'
                },
                'waiting_queue': {
                    'fields': ['id', 'group_id', 'customer_name', 'group_size', 'priority_score', 'waiting_time', 'status', 'starvation_flag'],
                    'status_values': ['waiting', 'allocated', 'cancelled'],
                    'starvation_flag': '1 if waiting > threshold, 0 otherwise'
                }
            },
            
            'edge_cases_handled': [
                'Large group first, small groups later -> Aging priority handles this',
                'Many small tables sum to large capacity -> Sequential merging combines them',
                'Small groups constantly blocking medium groups -> Priority formula prevents this',
                'Tables remain idle due to incompatible front group -> Algorithm scans all groups',
                'Large group starving forever -> Starvation threshold boost prevents this',
                'Random scattered merging -> Adjacency constraint ensures logical grouping',
                'Rush hour overload -> Dynamic weight adjustment increases fairness'
            ]
        })
    except Exception as e:
        print(f"[ERROR] Algorithm info error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== Global Error Handlers ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'message': 'The requested URL was not found on the server'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    print(f"[ERROR] Internal server error: {error}")
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'message': 'An unexpected error occurred on the server'
    }), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all uncaught exceptions"""
    print(f"[ERROR] Uncaught exception: {type(e).__name__}: {e}")
    return jsonify({
        'success': False,
        'error': 'Server error',
        'message': str(e)
    }), 500



if __name__ == '__main__':
    # Initialize database with ASP-BFA schema
    init_db()
    
    # Get restaurant info
    conn = get_db_connection()
    cursor = conn.cursor()
    total_tables = get_total_restaurant_tables(cursor)
    max_merge = get_max_consecutive_tables(cursor)
    conn.close()
    
    print("=" * 70)
    print("[*] SMART DINING SYSTEM - ASP-BFA BACKEND")
    print("=" * 70)
    print("\n[OK] Algorithm: Adaptive Spatial Priority Best-Fit Allocation (ASP-BFA)")
    print("\n[FEATURES]")
    print("   [+] FIFO fairness")
    print("   [+] Best-fit efficiency")
    print("   [+] Starvation prevention (aging)")
    print("   [+] Multi-table merging")
    print("   [+] Sequential/adjacent table merging")
    print("   [+] Large-group starvation avoidance")
    print("   [+] Table wastage minimization")
    print("   [+] Rush-hour balancing")
    print("\n[CONFIG]")
    print(f"   . Weight (Waiting Time): {WEIGHT_WAITING_TIME}")
    print(f"   . Weight (Group Size): {WEIGHT_GROUP_SIZE}")
    print(f"   . Starvation Threshold: {WAIT_THRESHOLD}s")
    print(f"   . Starvation Bonus: +{HIGH_PRIORITY_BONUS} points")
    print(f"   . Rush Hour Queue Limit: {RUSH_HOUR_QUEUE_LIMIT} groups")
    print(f"   . Adjacency Required: {ADJACENCY_ONLY}")
    print("\n[RESTAURANT]")
    print(f"   . Total Tables: {total_tables}")
    print(f"   . Max Consecutive Merge: {max_merge} tables")
    print(f"   . Merge Logic: Dynamic (All if <=5, 80% if 5-10, 70% if >10)")
    print("\n[DATABASE]")
    print("   . All bookings and queue cleared!")
    print("   . All tables reset to AVAILABLE status")
    print("   . Database initialized successfully!")
    print("   . Access the application at: http://127.0.0.1:5000")
    print("=" * 70)
    print()
    app.run(debug=True, host='0.0.0.0', port=5000)



