"""
Sequential Table Merging Logic
================================
Handles multi-table merging for large groups.
"""

from config import ADJACENCY_ONLY
from models import get_max_consecutive_tables


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
