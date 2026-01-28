# 🍽️ Skip the Wait - Smart Dining System
## Table Allocation Prototype

A fully functional single-page web application demonstrating intelligent restaurant table allocation using the **FIFO-Compatible Best-Fit Algorithm**. This prototype combines frontend visualization with backend decision logic to dynamically allocate tables based on seating capacity, availability, and group size.

---

## 📋 Project Overview

### Features
- **Visual Table Layout**: Interactive restaurant floor plan with 6 tables (2-seater, 4-seater, 6-seater)
- **Real-time Status Indicators**: Green (Available) and Red (Booked) visual states
- **Automatic Allocation Only**: Backend algorithm automatically assigns the smallest suitable table
- **Smart Queue System**: When restaurant is full, customers are added to a waiting queue
- **Auto-Processing**: Queue automatically processes when tables become available
- **Booking Management**: View active bookings and cancel them
- **Responsive Design**: Works on desktop and mobile devices

### Technology Stack
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Backend**: Flask (Python)
- **Database**: SQLite
- **Architecture**: RESTful API

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Installation Steps

1. **Clone or Navigate to the Project Directory**
```bash
cd d:\Download\Project
```

2. **Create a Virtual Environment (Recommended)**
```bash
python -m venv venv
```

3. **Activate the Virtual Environment**

**Windows:**
```bash
venv\Scripts\activate
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

4. **Install Dependencies**
```bash
pip install -r requirements.txt
```

5. **Run the Application**
```bash
python app.py
```

6. **Access the Application**
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 📂 Project Structure

```
Project/
│
├── app.py                      # Flask backend application
├── requirements.txt            # Python dependencies
├── dining_system.db           # SQLite database (auto-created)
│
├── templates/
│   └── index.html             # Main HTML page
│
└── static/
    ├── style.css              # CSS styling
    └── script.js              # Frontend JavaScript logic
```

---

## 🎯 How to Use

### 1. View Table Layout (Left Panel)
- Tables are displayed with their number and seating capacity
- **Green** = Available for booking
- **Red** = Currently booked
- Tables are visual indicators only (no manual selection)

### 2. Make a Booking (Right Panel)

#### Automatic Allocation:
1. Enter customer name
2. Enter number of guests
3. Click "Submit Booking"
4. System automatically:
   - **If tables available**: Allocates the smallest suitable table (Best-Fit Algorithm)
   - **If restaurant full**: Adds customer to waiting queue

### 3. Queue System
- When all tables are full, customers are automatically added to a waiting queue
- Queue displays position, customer name, and group size
- When a table is freed (cancelled), the system automatically:
  - Finds the next customer in queue who fits an available table
  - Allocates the table using Best-Fit Algorithm
  - Removes them from queue and creates a booking

### 4. View Active Bookings & Queue
- Scroll down in the right panel to see:
  - **Active Bookings**: Currently occupied tables
  - **Waiting Queue**: Customers waiting for tables
- Click "Cancel" on bookings to free up tables (triggers auto-queue processing)

### 5. Reset System
- Click "Reset All Tables" in the header to clear all bookings and queue

---

## ⚙️ Backend Logic Explained

### FIFO-Compatible Best-Fit Table Allocation Algorithm with Queue

#### How It Works:
1. **Input Validation**: System checks group size and customer name
2. **Table Availability Check**: System finds available tables that can fit the group
3. **Best-Fit Selection**: Among all suitable tables, select the smallest one
4. **Allocation or Queue**:
   - **If table found**: Allocate immediately and mark table as booked
   - **If no table available**: Add customer to waiting queue (FIFO order)

#### Queue Processing (Automatic):
- Triggered when a table is freed (booking cancelled)
- System iterates through queue in FIFO order
- For each waiting customer, attempts Best-Fit allocation
- Automatically books table and removes customer from queue
- Updates queue positions for remaining customers

#### Example Scenario:
**Initial State:**
- Available Tables: 2-seater, 4-seater, 6-seater

**Booking 1:** Group of 3 people
- **Decision**: Allocates 4-seater (smallest table that fits)
- **Result**: 4-seater marked as booked

**Booking 2:** Group of 5 people  
- **Decision**: Allocates 6-seater
- **Result**: 6-seater marked as booked

**Booking 3:** Group of 2 people
- **Decision**: Allocates 2-seater
- **Result**: 2-seater marked as booked

**Booking 4:** Group of 4 people
- **Decision**: No suitable table available
- **Result**: Added to queue at position #1

**Booking 5:** Group of 2 people
- **Decision**: No suitable table available
- **Result**: Added to queue at position #2

**Cancellation:** Group of 3 cancels (4-seater freed)
- **Auto-Processing**: 
  - Checks queue position #1 (4 people) → Fits in 4-seater → Auto-allocated
  - Queue position #2 (2 people) moves to #1, waits for next cancellation

### Edge Case Handling:
- **Queue member larger than freed table**: Skipped, next customer checked
- **Multiple cancellations**: Queue processed after each cancellation
- **Real-time updates**: Frontend auto-refreshes every 5 seconds

---

## 🔌 API Endpoints

### GET `/api/tables`
Returns all tables with their current status and booking information.

**Response:**
```json
{
  "success": true,
  "tables": [
    {
      "id": 1,
      "table_number": 1,
      "seating_capacity": 2,
      "status": "available",
      "booking": null
    }
  ]
}
```

### POST `/api/book`
Books a table for a customer (automatic allocation only).

**Request Body:**
```json
{
  "customer_name": "John Doe",
  "group_size": 4
}
```

**Response (Table Allocated):**
```json
{
  "success": true,
  "queued": false,
  "message": "Table allocated successfully",
  "booking": {
    "id": 1,
    "customer_name": "John Doe",
    "group_size": 4,
    "table_number": 3,
    "seating_capacity": 4,
    "booking_time": "2026-01-29T10:30:00"
  }
}
```

**Response (Added to Queue):**
```json
{
  "success": true,
  "queued": true,
  "message": "No tables available. Added to waiting queue.",
  "queue": {
    "id": 1,
    "customer_name": "John Doe",
    "group_size": 4,
    "position": 1
  }
}
```

### DELETE `/api/cancel/<booking_id>`
Cancels a booking, frees the table, and processes queue.

**Response:**
```json
{
  "success": true,
  "message": "Booking cancelled successfully",
  "queue_processed": {
    "allocated": 1
  }
}
```

### GET `/api/bookings`
Returns all active bookings.

### GET `/api/queue`
Returns all customers in waiting queue.

**Response:**
```json
{
  "success": true,
  "queue": [
    {
      "id": 1,
      "customer_name": "Jane Smith",
      "group_size": 5,
      "arrival_time": "2026-01-29T10:35:00",
      "position": 1
    }
  ]
}
```

### POST `/api/reset`
Resets the system by cancelling all bookings and clearing the queue.

---

## 🗄️ Database Schema

### Tables Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| table_number | INTEGER | Table identifier (1-6) |
| seating_capacity | INTEGER | Number of seats (2, 4, or 6) |
| status | TEXT | 'available' or 'booked' |
| position_x | INTEGER | X coordinate for layout |
| position_y | INTEGER | Y coordinate for layout |

### Bookings Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| table_id | INTEGER | Foreign key to tables |
| customer_name | TEXT | Customer's name |
| group_size | INTEGER | Number of guests |
| booking_time | TIMESTAMP | When booking was made |
| status | TEXT | 'active' or 'cancelled' |

### Waiting Queue Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| customer_name | TEXT | Customer's name |
| group_size | INTEGER | Number of guests |
| arrival_time | TIMESTAMP | When added to queue |
| status | TEXT | 'waiting' or 'allocated' |
| position | INTEGER | Position in queue |

---

## 🎨 User Interface Features

### Visual Design
- **Split Layout**: Left (Table Layout) + Right (Booking Panel)
- **Color-Coded Status**: Intuitive green/red indicators
- **Interactive Tables**: Clickable, hoverable elements with animations
- **Responsive**: Adapts to different screen sizes

### User Experience
- **Real-time Updates**: Auto-refresh every 5 seconds
- **Toast Notifications**: Instant feedback for actions
- **Form Validation**: Prevents invalid bookings
- **Dual Confirmation**: Different displays for table allocation vs queue addition
- **Queue Visibility**: See your position and estimated wait

---

## 🔮 Future Enhancement Ideas

1. ✅ **Queue Management** - IMPLEMENTED: Automatic waiting queue with FIFO processing
2. **Table Merging**: Combine tables for large groups
3. **QR Code Integration**: Automatic table identification
4. **WebSocket Updates**: Real-time synchronization across devices
5. **Analytics Dashboard**: Track utilization rates and peak hours
6. **Multi-Restaurant Support**: Extend to multiple locations
7. **Customer App**: Allow customers to book directly
8. **Reservation System**: Pre-book tables for future times
9. **SMS Notifications**: Alert customers when their table is ready
10. **Priority Queue**: VIP customers or special handling

---

## 🐛 Troubleshooting

### Port Already in Use
If port 5000 is already in use, modify `app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=5001)
```

### Database Issues
If you encounter database errors, delete `dining_system.db` and restart:
```bash
rm dining_system.db  # macOS/Linux
del dining_system.db  # Windows
python app.py
```

### Module Not Found Errors
Ensure you've activated the virtual environment and installed dependencies:
```bash
pip install -r requirements.txt
```

---

## 📝 License

This is a prototype project for educational and demonstration purposes.

---

## 👨‍💻 Developer Notes

### Key Implementation Details:
- **SQLite**: Chosen for zero-configuration setup (perfect for prototypes)
- **Flask-CORS**: Enabled for potential future API consumption
- **Row Factory**: Used `sqlite3.Row` for dictionary-like access
- **RESTful Design**: Clean API structure for easy frontend integration
- **Best-Fit Algorithm**: Implemented in backend, not frontend
- **Automatic Queue Processing**: Triggered on table cancellation
- **FIFO Queue**: First-in-first-out ensures fairness
- **No Manual Selection**: Ensures optimal table utilization

### Why SQLite?
- No separate database server required
- File-based (portable)
- Perfect for prototypes and small-scale applications
- Supports concurrent reads
- Built into Python

---

## 🎓 Learning Outcomes

This prototype demonstrates:
1. Full-stack web development (Frontend + Backend)
2. RESTful API design and implementation
3. Database schema design and SQL operations
4. Algorithm implementation (Best-Fit + FIFO Queue)
5. Responsive UI/UX design
6. State management in vanilla JavaScript
7. Event-driven architecture
8. Automatic queue processing logic
9. Real-time system updates

---

## 📧 Support

For questions or issues, please review the code comments in:
- [app.py](app.py) - Backend logic and API endpoints
- [script.js](static/script.js) - Frontend interaction logic
- [style.css](static/style.css) - UI styling

---

**Built with ❤️ for the Smart Dining System Project**

*"This prototype combines frontend visualization with backend decision logic to dynamically allocate restaurant tables based on seating capacity and availability. When the restaurant is full, customers are automatically queued and allocated using a FIFO-compatible Best-Fit algorithm."*
