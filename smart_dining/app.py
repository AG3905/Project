"""
Smart Dining System - Main Flask Application
=============================================
ASP-BFA (Adaptive Spatial Priority Best-Fit Allocation) Algorithm
Routes only - business logic is in separate modules.
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime

from database import get_db_connection, init_db
from models import get_total_restaurant_tables, get_max_consecutive_tables
from algorithm.allocator import allocate_table_asp_bfa
from queue_manager import process_queue_asp_bfa
from config import (
    WEIGHT_WAITING_TIME,
    WEIGHT_GROUP_SIZE,
    WAIT_THRESHOLD,
    HIGH_PRIORITY_BONUS,
    RUSH_HOUR_QUEUE_LIMIT,
    RUSH_HOUR_WEIGHT_MULTIPLIER,
    ADJACENCY_ONLY
)

app = Flask(__name__)
CORS(app)


# ==================== Routes ====================

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


# ==================== Application Entry Point ====================

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
