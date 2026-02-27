"""
Best-Fit Single Table Allocation
=================================
Handles best-fit allocation for single table scenarios.
"""


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
