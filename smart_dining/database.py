"""
Database Connection and Initialization
======================================
Handles SQLite database connection and table initialization for ASP-BFA system.
"""

import sqlite3
from config import DATABASE


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
