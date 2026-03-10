// API Base URL
const API_BASE = '/api';

// Global state
let tables = [];
let bookings = [];
let queue = [];
let updaterInterval = null;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    loadTables();
    loadBookings();
    loadQueue();
    setupEventListeners();
    startLiveClock();
    
    // Auto-refresh data
    setInterval(() => {
        loadTables();
        loadBookings();
        loadQueue();
    }, 5000);
    
    // UI Visual Updater (progress bars, elapsed times)
    setInterval(updateVisuals, 60000);
});

// Setup event listeners
function setupEventListeners() {
    document.getElementById('bookForm').addEventListener('submit', handleBooking);
    document.getElementById('clearBtn').addEventListener('click', clearForm);
    document.getElementById('resetBtn').addEventListener('click', handleReset);
    
    // Event delegation for checkout buttons
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('btn-checkout')) {
            const bookingId = e.target.getAttribute('data-id');
            if (bookingId) {
                checkoutTable(bookingId);
            }
        }
    });
}

function startLiveClock() {
    const clockEl = document.getElementById('liveClock');
    setInterval(() => {
        const now = new Date();
        clockEl.textContent = now.toLocaleTimeString([], { hour12: false });
    }, 1000);
}

function updateStats() {
    const total = tables.length;
    let available = 0;
    let occupied = 0;
    let openSeats = 0;
    
    tables.forEach(t => {
        if (t.status === 'available') {
            available++;
            openSeats += t.seating_capacity;
        } else {
            occupied++;
        }
    });
    
    document.getElementById('statTotal').textContent = total;
    document.getElementById('statAvailable').textContent = available;
    document.getElementById('statOccupied').textContent = occupied;
    document.getElementById('statSeats').textContent = openSeats;
    
    const floorProgress = document.getElementById('floorProgress');
    const occPercent = total > 0 ? (occupied / total) * 100 : 0;
    floorProgress.style.width = `${occPercent}%`;
    if (occPercent >= 70) {
        floorProgress.classList.add('warning');
    } else {
        floorProgress.classList.remove('warning');
    }
}

// Load endpoints
async function loadTables() {
    try {
        const response = await fetch(`${API_BASE}/tables`);
        const data = await response.json();
        if (data.success) {
            tables = data.tables;
            renderTables();
            updateStats();
        }
    } catch (error) {
        console.error('Error loading tables:', error);
    }
}

async function loadBookings() {
    try {
        const response = await fetch(`${API_BASE}/bookings`);
        const data = await response.json();
        if (data.success) {
            bookings = data.bookings;
            document.getElementById('activeCount').textContent = bookings.length;
            renderBookings();
        }
    } catch (error) {
        console.error('Error loading bookings:', error);
    }
}

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

// Renders
function renderTables() {
    const layout = document.getElementById('tableLayout');
    layout.innerHTML = '';
    
    tables.forEach(table => {
        const orb = document.createElement('div');
        orb.className = `table-orb ${table.status}`;
        
        let guestHtml = '';
        if (table.status === 'booked' && table.booking) {
            guestHtml = `<div class="orb-guest" title="${table.booking.customer_name}">${table.booking.customer_name}</div>`;
        }
        
        orb.innerHTML = `
            <div class="font-serif orb-id">T${table.table_number}</div>
            <div class="font-mono orb-seats">${table.seating_capacity} Seats</div>
            ${guestHtml}
        `;
        
        // Click handler for orbs (toggle)
        orb.addEventListener('click', () => {
            if (table.status === 'booked' && table.booking) {
                // Find corresponding booking to checkout
                const booking = bookings.find(b => b.customer_name === table.booking.customer_name);
                if (booking) {
                    checkoutTable(booking.id.toString());
                }
            } else if (table.status === 'available') {
                // Pre-fill walk-in for this capacity
                document.getElementById('customerName').value = `Walk-in T${table.table_number}`;
                document.getElementById('groupSize').value = table.seating_capacity;
                document.getElementById('customerName').focus();
            }
        });
        
        layout.appendChild(orb);
    });
}

function renderBookings() {
    const list = document.getElementById('bookingsList');
    if (bookings.length === 0) {
        list.innerHTML = '<div class="empty-state">No active bookings</div>';
        return;
    }
    
    let html = '';
    const now = new Date();
    
    bookings.forEach(b => {
        // b.table_ids is array of DB ids. Map to table_number.
        const tableNums = b.table_ids.map(tid => {
            const table = tables.find(t => t.id === tid);
            return table ? table.table_number : tid;
        });
        const tableStr = tableNums.join(',');
        
        const bTime = new Date(b.booking_time);
        const timeStr = bTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        const elapsedMins = Math.max(0, Math.floor((now - bTime) / 60000));
        const progressPercent = Math.min(100, (elapsedMins / 90) * 100);
        const warningClass = progressPercent >= 70 ? 'warning' : '';
        
        html += `
            <div class="booking-card">
                <div class="card-top">
                    <div class="card-mini-orb">
                        <div class="card-mini-id">T${tableStr}</div>
                        <div class="font-mono card-mini-seats">${b.group_size}P</div>
                    </div>
                    <div class="card-guest-info">
                        <div class="card-guest-name">${b.customer_name}</div>
                        <div class="font-mono card-meta">
                            <span>🕒 ${timeStr}</span>
                            <span class="card-time-pill elapsed-time" data-time="${b.booking_time}">${elapsedMins}m</span>
                        </div>
                    </div>
                </div>
                <div class="card-progress-container">
                    <div class="card-progress-fill progress-dynamic ${warningClass}" data-time="${b.booking_time}" style="width: ${progressPercent}%"></div>
                </div>
                <div class="card-bottom">
                    <span>Seated at ${timeStr}</span>
                    <button class="btn-checkout" data-id="${b.id}">Checkout</button>
                </div>
            </div>
        `;
    });
    
    list.innerHTML = html;
}

function updateVisuals() {
    const now = new Date();
    
    document.querySelectorAll('.elapsed-time').forEach(el => {
        const bTime = new Date(el.getAttribute('data-time'));
        const elapsedMins = Math.max(0, Math.floor((now - bTime) / 60000));
        el.textContent = `${elapsedMins}m`;
    });
    
    document.querySelectorAll('.progress-dynamic').forEach(el => {
        const bTime = new Date(el.getAttribute('data-time'));
        const elapsedMins = Math.max(0, Math.floor((now - bTime) / 60000));
        const progressPercent = Math.min(100, (elapsedMins / 90) * 100);
        el.style.width = `${progressPercent}%`;
        if (progressPercent >= 70) {
            el.classList.add('warning');
        } else {
            el.classList.remove('warning');
        }
    });
}

function renderQueue() {
    const list = document.getElementById('queueList');
    if (queue.length === 0) {
        list.innerHTML = '<div class="empty-state">Queue is empty</div>';
        return;
    }
    
    let html = '';
    queue.forEach(q => {
        const initial = q.customer_name.charAt(0).toUpperCase();
        html += `
            <div class="queue-item">
                <div class="avatar">${initial}</div>
                <div class="queue-info">
                    <div class="queue-name">${q.customer_name}</div>
                    <div class="font-mono queue-meta">Party of ${q.group_size}</div>
                </div>
                <div class="queue-position">#${q.position}</div>
            </div>
        `;
    });
    list.innerHTML = html;
}

// Handlers
async function handleBooking(e) {
    e.preventDefault();
    const name = document.getElementById('customerName').value.trim();
    const size = parseInt(document.getElementById('groupSize').value);
    
    if (!name || !size) return;
    
    try {
        const response = await fetch(`${API_BASE}/book`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ customer_name: name, group_size: size })
        });
        
        const data = await response.json();
        if (data.success) {
            if (data.queued) {
                showToast(`Added ${name} to queue at position #${data.queue_position}`, 'info');
            } else {
                const tablesArray = Array.isArray(data.allocated_tables) ? data.allocated_tables.join(', ') : data.allocated_tables;
                showToast(`Seated ${name} at Table ${tablesArray}`, 'success');
            }
            clearForm();
            loadTables();
            loadBookings();
            loadQueue();
        } else {
            showToast(data.error || 'Booking failed', 'error');
        }
    } catch (error) {
        showToast('Connection error', 'error');
    }
}

async function checkoutTable(bookingId) {
    try {
        const response = await fetch(`${API_BASE}/cancel/${bookingId}`, { method: 'DELETE' });
        const data = await response.json();
        
        if (data.success) {
            showToast('Table freed and checkout complete', 'success');
            if (data.queue_processed && data.queue_processed.allocated > 0) {
                setTimeout(() => {
                    showToast(`Auto-seated ${data.queue_processed.allocated} group(s) from queue`, 'info');
                }, 500);
            }
            loadTables();
            loadBookings();
            loadQueue();
        } else {
            showToast(data.error || 'Checkout failed', 'error');
        }
    } catch (error) {
        showToast('Connection error', 'error');
    }
}

async function handleReset() {
    if (!confirm('Reset entire system?')) return;
    try {
        const response = await fetch(`${API_BASE}/reset`, { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            showToast('System reset complete', 'success');
            loadTables();
            loadBookings();
            loadQueue();
        }
    } catch (error) {
        showToast('Connection error', 'error');
    }
}

function clearForm() {
    document.getElementById('bookForm').reset();
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = '✅';
    if (type === 'error') icon = '❌';
    if (type === 'info') icon = 'ℹ️';
    
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
