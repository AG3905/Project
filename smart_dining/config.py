"""
ASP-BFA Algorithm Configuration Constants
==========================================
Contains all configuration parameters for the Adaptive Spatial Priority 
Best-Fit Allocation algorithm.
"""

# ==================== Priority Scoring Weights ====================
WEIGHT_WAITING_TIME = 3  # W1: Aging factor (fairness)
WEIGHT_GROUP_SIZE = 1    # W2: Group size factor (efficiency)

# ==================== Starvation Prevention ====================
WAIT_THRESHOLD = 300  # seconds (5 minutes) - threshold for high priority boost
HIGH_PRIORITY_BONUS = 100  # bonus points when exceeding wait threshold

# ==================== Rush Hour Detection ====================
RUSH_HOUR_QUEUE_LIMIT = 10  # if queue > 10, increase fairness weight
RUSH_HOUR_WEIGHT_MULTIPLIER = 1.5  # increase W1 during rush hours

# ==================== Merging Constraints ====================
MAX_CONSECUTIVE_TABLES = None  # Will be set dynamically based on total restaurant tables
ADJACENCY_ONLY = True  # only merge adjacent tables

# ==================== Database Configuration ====================
DATABASE = 'dining_system.db'
