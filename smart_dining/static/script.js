// API Base URL
const API_BASE = '/api';

// Global state
let tables = [];
let bookings = [];
let queue = [];

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    loadTables();
    loadBookings();
    loadQueue();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    // Book form submission
    document.getElementById('bookForm').addEventListener('submit', handleBooking);
    
    // Clear form button
    document.getElementById('clearBtn').addEventListener('click', clearForm);
    
    // New booking buttons
    document.getElementById('newBookingBtn').addEventListener('click', showBookingForm);
    document.getElementById('newQueueBookingBtn').addEventListener('click', showBookingForm);
    
    // Reset system button
    document.getElementById('resetBtn').addEventListener('click', handleReset);
}

// Load all tables from backend
async function loadTables() {
    try {
        const response = await fetch(`${API_BASE}/tables`);
        const data = await response.json();
        
        if (data.success) {
            tables = data.tables;
            renderTables();
        } else {
            showToast('Failed to load tables', 'error');
        }
    } catch (error) {
        console.error('Error loading tables:', error);
        showToast('Error connecting to server', 'error');
    }
}

// Render tables in the layout
function renderTables() {
    const tableLayout = document.getElementById('tableLayout');
    tableLayout.innerHTML = '';
    
    tables.forEach(table => {
        const tableElement = document.createElement('div');
        tableElement.className = `restaurant-table ${table.status}`;
        
        tableElement.innerHTML = `
            <div class="table-number">T${table.table_number}</div>
            <div class="table-capacity">${table.seating_capacity} seats</div>
            <div class="table-status">${table.status}</div>
        `;
        
        tableLayout.appendChild(tableElement);
    });
}

// Handle booking form submission (Auto-allocate only)
async function handleBooking(e) {
    e.preventDefault();
    
    const customerName = document.getElementById('customerName').value.trim();
    const groupSize = parseInt(document.getElementById('groupSize').value);
    
    if (!customerName || !groupSize) {
        showToast('Please fill in all required fields', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/book`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                customer_name: customerName,
                group_size: groupSize
                // No table_id - automatic allocation only
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (data.queued) {
                // Customer added to queue
                showToast('Added to waiting queue!', 'warning');
                showQueueConfirmation(data.queue);
            } else {
                // Table allocated
                showToast(`Table ${data.booking.table_number} allocated!`, 'success');
                showBookingConfirmation(data.booking);
            }
            clearForm();
            loadTables();
            loadBookings();
            loadQueue();
        } else {
            showToast(data.error || 'Booking failed', 'error');
        }
    } catch (error) {
        console.error('Error booking table:', error);
        showToast('Error connecting to server', 'error');
    }
}

// Show booking confirmation
function showBookingConfirmation(booking) {
    const bookingForm = document.getElementById('bookingForm');
    const bookingStatus = document.getElementById('bookingStatus');
    const queueStatus = document.getElementById('queueStatus');
    const confirmationDetails = document.getElementById('confirmationDetails');
    
    bookingForm.classList.add('hidden');
    bookingStatus.classList.remove('hidden');
    queueStatus.classList.add('hidden');
    
    const bookingTime = new Date(booking.booking_time).toLocaleString();
    
    confirmationDetails.innerHTML = `
        <p><strong>Customer Name:</strong> ${booking.customer_name}</p>
        <p><strong>Group Size:</strong> ${booking.group_size} guests</p>
        <p><strong>Table Number:</strong> ${booking.table_number}</p>
        <p><strong>Table Capacity:</strong> ${booking.seating_capacity} seats</p>
        <p><strong>Booking Time:</strong> ${bookingTime}</p>
        <p><strong>Booking ID:</strong> #${booking.id}</p>
    `;
}

// Show queue confirmation
function showQueueConfirmation(queueData) {
    const bookingForm = document.getElementById('bookingForm');
    const bookingStatus = document.getElementById('bookingStatus');
    const queueStatus = document.getElementById('queueStatus');
    const queueDetails = document.getElementById('queueDetails');
    
    bookingForm.classList.add('hidden');
    bookingStatus.classList.add('hidden');
    queueStatus.classList.remove('hidden');
    
    queueDetails.innerHTML = `
        <p><strong>Customer Name:</strong> ${queueData.customer_name}</p>
        <p><strong>Group Size:</strong> ${queueData.group_size} guests</p>
        <p><strong>Queue Position:</strong> #${queueData.position}</p>
        <p><strong>Status:</strong> Waiting for table</p>
        <p style="color: #856404; margin-top: 15px;">
            <strong>ℹ️ You will be automatically allocated when a suitable table becomes available</strong>
        </p>
    `;
}

// Show booking form (hide confirmations)
function showBookingForm() {
    document.getElementById('bookingForm').classList.remove('hidden');
    document.getElementById('bookingStatus').classList.add('hidden');
    document.getElementById('queueStatus').classList.add('hidden');
}

// Clear form
function clearForm() {
    document.getElementById('bookForm').reset();
}

// Load waiting queue
async function loadQueue() {
    try {
        const response = await fetch(`${API_BASE}/queue`);
        const data = await response.json();
        
        if (data.success) {
            queue = data.queue;
            renderQueue();
        }
    } catch (error) {
        console.error('Error loading queue:', error);
    }
}

// Render queue list
function renderQueue() {
    const queueList = document.getElementById('queueList');
    
    if (queue.length === 0) {
        queueList.innerHTML = '<div class="no-bookings">No customers in queue</div>';
        return;
    }
    
    queueList.innerHTML = queue.map(item => {
        const arrivalTime = new Date(item.arrival_time).toLocaleTimeString();
        return `
            <div class="queue-item">
                <div class="queue-info">
                    <p><strong>${item.customer_name}</strong> - ${item.group_size} guests</p>
                    <p>Arrived at: ${arrivalTime}</p>
                </div>
                <div class="queue-position">#${item.position}</div>
            </div>
        `;
    }).join('');
}

// Load active bookings
async function loadBookings() {
    try {
        const response = await fetch(`${API_BASE}/bookings`);
        const data = await response.json();
        
        if (data.success) {
            bookings = data.bookings;
            renderBookings();
        }
    } catch (error) {
        console.error('Error loading bookings:', error);
    }
}

// Render bookings list
function renderBookings() {
    const bookingsList = document.getElementById('bookingsList');
    
    if (bookings.length === 0) {
        bookingsList.innerHTML = '<div class="no-bookings">No active bookings</div>';
        return;
    }
    
    bookingsList.innerHTML = bookings.map(booking => {
        const bookingTime = new Date(booking.booking_time).toLocaleTimeString();
        return `
            <div class="booking-item">
                <div class="booking-info">
                    <p><strong>${booking.customer_name}</strong> - ${booking.group_size} guests</p>
                    <p>Table ${booking.table_number} (${booking.seating_capacity} seats) - ${bookingTime}</p>
                </div>
                <div class="booking-actions">
                    <button class="btn btn-small btn-danger" onclick="cancelBooking(${booking.id})">
                        Cancel
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Cancel booking
async function cancelBooking(bookingId) {
    if (!confirm('Are you sure you want to cancel this booking?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/cancel/${bookingId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Booking cancelled successfully', 'success');
            loadTables();
            loadBookings();
        } else {
            showToast(data.error || 'Failed to cancel booking', 'error');
        }
    } catch (error) {
        console.error('Error cancelling booking:', error);
        showToast('Error connecting to server', 'error');
    }
}

// Reset system
async function handleReset() {
    if (!confirm('Are you sure you want to reset all bookings and queue? This will make all tables available.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/reset`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('System reset successfully', 'success');
            clearForm();
            showBookingForm();
            loadTables();
            loadBookings();
            loadQueue();
        } else {
            showToast(data.error || 'Reset failed', 'error');
        }
    } catch (error) {
        console.error('Error resetting system:', error);
        showToast('Error connecting to server', 'error');
    }
}

// Show toast notification
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toastMessage');
    
    toastMessage.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove('hidden');
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

// Auto-refresh tables, bookings, and queue every 5 seconds
setInterval(() => {
    loadTables();
    loadBookings();
    loadQueue();
}, 5000);
