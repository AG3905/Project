"""
Priority Score Calculation Logic
=================================
Handles priority score calculation for ASP-BFA algorithm.
"""

from config import (
    WEIGHT_WAITING_TIME,
    WEIGHT_GROUP_SIZE,
    HIGH_PRIORITY_BONUS,
    WAIT_THRESHOLD,
    RUSH_HOUR_QUEUE_LIMIT,
    RUSH_HOUR_WEIGHT_MULTIPLIER
)


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
