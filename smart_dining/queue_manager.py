"""
Queue Update and Processing Logic
==================================
Handles queue priority updates and automatic processing.
"""

from datetime import datetime
from config import WAIT_THRESHOLD
from models import get_waiting_queue
from algorithm.priority import calculate_priority_score, detect_rush_hour
from algorithm.single_table import find_best_single_table
from algorithm.merging import find_sequential_table_merging, merge_tables


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
