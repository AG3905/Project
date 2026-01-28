from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

DATABASE = 'dining_system.db'

def get_db_connection():
    """Create a database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with tables schema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tables table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number INTEGER UNIQUE NOT NULL,
            seating_capacity INTEGER NOT NULL,
            status TEXT DEFAULT 'available',
            position_x INTEGER,
            position_y INTEGER
        )
    ''')
    
    # Create bookings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            group_size INTEGER NOT NULL,
            booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (table_id) REFERENCES tables (id)
        )
    ''')
    
    # Create queue table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waiting_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            group_size INTEGER NOT NULL,
            arrival_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'waiting',
            position INTEGER
        )
    ''')
    
    # Check if tables are already populated
    cursor.execute('SELECT COUNT(*) FROM tables')
    if cursor.fetchone()[0] == 0:
        # Insert initial table data
        tables_data = [
            (1, 2, 'available', 100, 100),
            (2, 2, 'available', 250, 100),
            (3, 4, 'available', 100, 250),
            (4, 4, 'available', 250, 250),
            (5, 6, 'available', 100, 400),
            (6, 6, 'available', 250, 400)
        ]
        cursor.executemany('''
            INSERT INTO tables (table_number, seating_capacity, status, position_x, position_y)
            VALUES (?, ?, ?, ?, ?)
        ''', tables_data)
    
    conn.commit()
    conn.close()

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/api/tables', methods=['GET'])
def get_tables():
    """Get all tables with their current status"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get tables with booking information
        cursor.execute('''
            SELECT t.id, t.table_number, t.seating_capacity, t.status, 
                   t.position_x, t.position_y,
                   b.customer_name, b.group_size, b.booking_time
            FROM tables t
            LEFT JOIN bookings b ON t.id = b.table_id AND b.status = 'active'
            ORDER BY t.table_number
        ''')
        
        tables = []
        for row in cursor.fetchall():
            tables.append({
                'id': row['id'],
                'table_number': row['table_number'],
                'seating_capacity': row['seating_capacity'],
                'status': row['status'],
                'position_x': row['position_x'],
                'position_y': row['position_y'],
                'booking': {
                    'customer_name': row['customer_name'],
                    'group_size': row['group_size'],
                    'booking_time': row['booking_time']
                } if row['customer_name'] else None
            })
        
        conn.close()
        return jsonify({'success': True, 'tables': tables})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/book', methods=['POST'])
def book_table():
    """
    Book a table using FIFO-Compatible Best-Fit Algorithm
    If no table available, add to waiting queue
    """
    try:
        data = request.get_json()
        customer_name = data.get('customer_name')
        group_size = data.get('group_size')
        
        if not customer_name or not group_size:
            return jsonify({
                'success': False,
                'error': 'Customer name and group size are required'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Apply Best-Fit Algorithm: Find smallest available table that fits the group
        cursor.execute('''
            SELECT id, table_number, seating_capacity, status
            FROM tables
            WHERE status = 'available' AND seating_capacity >= ?
            ORDER BY seating_capacity ASC
            LIMIT 1
        ''', (group_size,))
        
        allocated_table = cursor.fetchone()
        
        # If no table available, add to queue
        if not allocated_table:
            # Get current queue position
            cursor.execute('SELECT COUNT(*) FROM waiting_queue WHERE status = "waiting"')
            queue_position = cursor.fetchone()[0] + 1
            
            cursor.execute('''
                INSERT INTO waiting_queue (customer_name, group_size, status, position)
                VALUES (?, ?, 'waiting', ?)
            ''', (customer_name, group_size, queue_position))
            
            queue_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'queued': True,
                'message': 'No tables available. Added to waiting queue.',
                'queue': {
                    'id': queue_id,
                    'customer_name': customer_name,
                    'group_size': group_size,
                    'position': queue_position
                }
            })
        
        # Create booking
        cursor.execute('''
            INSERT INTO bookings (table_id, customer_name, group_size, status)
            VALUES (?, ?, ?, 'active')
        ''', (allocated_table['id'], customer_name, group_size))
        
        booking_id = cursor.lastrowid
        
        # Update table status to booked
        cursor.execute('''
            UPDATE tables
            SET status = 'booked'
            WHERE id = ?
        ''', (allocated_table['id'],))
        
        conn.commit()
        
        # Get booking details
        cursor.execute('''
            SELECT b.id, b.customer_name, b.group_size, b.booking_time,
                   t.table_number, t.seating_capacity
            FROM bookings b
            JOIN tables t ON b.table_id = t.id
            WHERE b.id = ?
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        conn.close()
        
        return jsonify({
            'success': True,
            'queued': False,
            'message': 'Table allocated successfully',
            'booking': {
                'id': booking['id'],
                'customer_name': booking['customer_name'],
                'group_size': booking['group_size'],
                'booking_time': booking['booking_time'],
                'table_number': booking['table_number'],
                'seating_capacity': booking['seating_capacity']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cancel/<int:booking_id>', methods=['DELETE'])
def cancel_booking(booking_id):
    """Cancel a booking, free up the table, and process queue"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get booking details
        cursor.execute('''
            SELECT b.table_id, t.seating_capacity
            FROM bookings b
            JOIN tables t ON b.table_id = t.id
            WHERE b.id = ? AND b.status = 'active'
        ''', (booking_id,))
        
        booking = cursor.fetchone()
        
        if not booking:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Booking not found'
            }), 404
        
        table_id = booking['table_id']
        table_capacity = booking['seating_capacity']
        
        # Update booking status
        cursor.execute('''
            UPDATE bookings
            SET status = 'cancelled'
            WHERE id = ?
        ''', (booking_id,))
        
        # Free up the table
        cursor.execute('''
            UPDATE tables
            SET status = 'available'
            WHERE id = ?
        ''', (table_id,))
        
        conn.commit()
        
        # Process queue - allocate to next waiting customer
        result = process_queue(cursor, conn)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Booking cancelled successfully',
            'queue_processed': result
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def process_queue(cursor, conn):
    """Process waiting queue and auto-allocate tables to waiting customers"""
    try:
        # Get all waiting customers in FIFO order
        cursor.execute('''
            SELECT id, customer_name, group_size, position
            FROM waiting_queue
            WHERE status = 'waiting'
            ORDER BY arrival_time ASC
        ''')
        
        waiting_customers = cursor.fetchall()
        allocated_count = 0
        
        for customer in waiting_customers:
            # Find best-fit table for this customer
            cursor.execute('''
                SELECT id, table_number, seating_capacity
                FROM tables
                WHERE status = 'available' AND seating_capacity >= ?
                ORDER BY seating_capacity ASC
                LIMIT 1
            ''', (customer['group_size'],))
            
            available_table = cursor.fetchone()
            
            if available_table:
                # Create booking
                cursor.execute('''
                    INSERT INTO bookings (table_id, customer_name, group_size, status)
                    VALUES (?, ?, ?, 'active')
                ''', (available_table['id'], customer['customer_name'], customer['group_size']))
                
                # Update table status
                cursor.execute('''
                    UPDATE tables
                    SET status = 'booked'
                    WHERE id = ?
                ''', (available_table['id'],))
                
                # Remove from queue
                cursor.execute('''
                    UPDATE waiting_queue
                    SET status = 'allocated'
                    WHERE id = ?
                ''', (customer['id'],))
                
                allocated_count += 1
                conn.commit()
        
        # Update queue positions
        cursor.execute('''
            SELECT id FROM waiting_queue
            WHERE status = 'waiting'
            ORDER BY arrival_time ASC
        ''')
        remaining_queue = cursor.fetchall()
        for idx, item in enumerate(remaining_queue):
            cursor.execute('''
                UPDATE waiting_queue
                SET position = ?
                WHERE id = ?
            ''', (idx + 1, item['id']))
        
        conn.commit()
        return {'allocated': allocated_count}
        
    except Exception as e:
        print(f"Error processing queue: {e}")
        return {'allocated': 0, 'error': str(e)}

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    """Get all active bookings"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.customer_name, b.group_size, b.booking_time,
                   t.table_number, t.seating_capacity
            FROM bookings b
            JOIN tables t ON b.table_id = t.id
            WHERE b.status = 'active'
            ORDER BY b.booking_time DESC
        ''')
        
        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'id': row['id'],
                'customer_name': row['customer_name'],
                'group_size': row['group_size'],
                'booking_time': row['booking_time'],
                'table_number': row['table_number'],
                'seating_capacity': row['seating_capacity']
            })
        
        conn.close()
        return jsonify({'success': True, 'bookings': bookings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/queue', methods=['GET'])
def get_queue():
    """Get all customers in waiting queue"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, customer_name, group_size, arrival_time, position
            FROM waiting_queue
            WHERE status = 'waiting'
            ORDER BY arrival_time ASC
        ''')
        
        queue = []
        for row in cursor.fetchall():
            queue.append({
                'id': row['id'],
                'customer_name': row['customer_name'],
                'group_size': row['group_size'],
                'arrival_time': row['arrival_time'],
                'position': row['position']
            })
        
        conn.close()
        return jsonify({'success': True, 'queue': queue})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reset', methods=['POST'])
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
            SET status = 'available'
        ''')
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'System reset successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize database
    init_db()
    print("Database initialized successfully!")
    print("Starting Smart Dining System...")
    print("Access the application at: http://127.0.0.1:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
