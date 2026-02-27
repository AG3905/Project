"""
Main ASP-BFA Allocation Algorithm
==================================
Main allocation logic combining all algorithm components.
"""

import uuid
from datetime import datetime
from algorithm.single_table import find_best_single_table
from algorithm.merging import find_sequential_table_merging, merge_tables
from queue_manager import update_queue_priority_scores


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
