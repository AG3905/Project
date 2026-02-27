"""
Database Schema Helpers
========================
Helper functions for database schema operations and constraints.
"""


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
