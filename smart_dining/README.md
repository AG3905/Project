# Smart Dining System - ASP-BFA Backend

**Adaptive Spatial Priority Best-Fit Allocation Algorithm**

## Project Structure

```
smart_dining/
│
├── app.py                  # Main Flask app (routes only)
├── config.py               # Algorithm configuration constants
├── database.py             # DB connection & initialization
├── models.py               # DB schema-related helpers
├── queue_manager.py        # Queue update & processing logic
│
├── algorithm/
│   ├── __init__.py
│   ├── priority.py         # Priority score logic
│   ├── single_table.py     # Best-fit single allocation
│   ├── merging.py          # Sequential merging logic
│   └── allocator.py        # Main ASP-BFA algorithm
│
├── templates/
│   └── index.html          # Frontend UI
│
└── static/
    ├── script.js           # Frontend JavaScript
    └── style.css           # Frontend styling
```

## How to Run

### Option 1: Run from smart_dining directory
```bash
cd smart_dining
python app.py
```

### Option 2: Run from project root
```bash
python smart_dining/app.py
```

The application will start on: **http://127.0.0.1:5000**

## Features

- ✅ FIFO fairness
- ✅ Best-fit efficiency
- ✅ Starvation prevention (aging)
- ✅ Multi-table merging
- ✅ Sequential/adjacent table merging
- ✅ Large-group starvation avoidance
- ✅ Table wastage minimization
- ✅ Rush-hour balancing

## Algorithm Configuration

Edit `config.py` to adjust algorithm parameters:

- `WEIGHT_WAITING_TIME` - Priority weight for waiting time (default: 3)
- `WEIGHT_GROUP_SIZE` - Priority weight for group size (default: 1)
- `WAIT_THRESHOLD` - Starvation prevention threshold in seconds (default: 300)
- `HIGH_PRIORITY_BONUS` - Bonus points for starving groups (default: 100)
- `RUSH_HOUR_QUEUE_LIMIT` - Queue length to trigger rush hour mode (default: 10)

## API Endpoints

- `GET /` - Main application UI
- `GET /api/health` - Health check
- `GET /api/tables` - Get all tables
- `POST /api/book` - Create new booking
- `DELETE /api/cancel/<booking_id>` - Cancel booking
- `GET /api/bookings` - Get active bookings
- `GET /api/queue` - Get waiting queue
- `DELETE /api/queue/cancel/<queue_id>` - Cancel queue entry
- `POST /api/reset` - Reset system
- `GET /api/algorithm-info` - Get algorithm details

## Database

SQLite database (`dining_system.db`) will be created automatically on first run.

Tables:
- `tables` - Restaurant table information
- `bookings` - Active booking records
- `waiting_queue` - Waiting customer queue
