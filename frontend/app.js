// SmartCivic AI - Frontend JS Application

const API_BASE = window.location.origin;

// State management
let activeTab = 'citizen-portal';
let currentUser = null; // Object containing logged in user details

// Maps
let pickerMap = null;
let pickerMarker = null;
let citizenHeatmapMap = null;
let citizenHeatmapGroup = L.layerGroup();
let authorityHeatmapMap = null;
let authorityHeatmapGroup = L.layerGroup();
let workerRouteMap = null;
let workerRouteLayer = null;
let workerStartMarker = null;
let workerEndMarker = null;


// Charts
let categoriesChart = null;
let wardsChart = null;

// Active state caches
let activeComplaintsList = [];
let activeWorkersList = [];
let activeWorkerTask = null;
let showingHeatmap = false;
let autoRefreshTimer = null;
let currentlyTrackedId = null;

let userCurrentLat = 12.971598;
let userCurrentLng = 77.594562;

if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
        (pos) => {
            userCurrentLat = pos.coords.latitude;
            userCurrentLng = pos.coords.longitude;
        },
        (err) => {
            console.warn("Geolocation query error: using default coords", err);
        }
    );
}

// Default Map Center (Bangalore-like environment)
const DEFAULT_LAT = 12.971598;
const DEFAULT_LNG = 77.594562;

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initMaps();
    initAuth();
    initTabs();
    initForms();
    initJournalistEvents();
    
    // Start auto-refreshing dashboard data every 5 seconds (to fetch new IVR calls & worker assignments too!)
    autoRefreshTimer = setInterval(() => {
        if (currentUser && currentUser.role === 'authority' && activeTab === 'authority-dashboard') {
            loadDashboardData();
        } else if (currentUser && currentUser.role === 'worker' && activeTab === 'worker-module') {
            loadWorkerTasks();
        } else if (activeTab === 'citizen-portal') {
            loadCitizenComplaints();
            if (currentlyTrackedId) {
                trackComplaint(currentlyTrackedId);
            }
        }
    }, 5000);
});

// Theme Management
function initTheme() {
    const themeBtn = document.getElementById('theme-toggle-btn');
    themeBtn.addEventListener('click', () => {
        document.body.classList.toggle('light-theme');
        const icon = themeBtn.querySelector('i');
        if (document.body.classList.contains('light-theme')) {
            icon.className = 'fa-solid fa-sun';
        } else {
            icon.className = 'fa-solid fa-moon';
        }
    });
}

// Authentication & Session Handling
function initAuth() {
    const authModal = document.getElementById('auth-modal');
    const loginPanel = document.getElementById('login-panel');
    const signupPanel = document.getElementById('signup-panel');
    const errorMsg = document.getElementById('auth-error-msg');
    const errorText = document.getElementById('auth-error-text');

    // Switch panels via links
    document.getElementById('link-go-to-login').addEventListener('click', () => {
        loginPanel.classList.remove('hidden');
        signupPanel.classList.add('hidden');
        errorMsg.classList.add('hidden');
    });

    document.getElementById('link-go-to-signup').addEventListener('click', () => {
        signupPanel.classList.remove('hidden');
        loginPanel.classList.add('hidden');
        errorMsg.classList.add('hidden');
    });

    // Close Auth Modal
    document.getElementById('btn-close-auth-modal').addEventListener('click', () => {
        authModal.classList.add('hidden');
    });

    // Open Auth Modal via Header Trigger
    document.getElementById('btn-login-trigger').addEventListener('click', () => {
        authModal.classList.remove('hidden');
    });

    // Role selection cards click logic
    const roleCards = document.querySelectorAll('.role-card');
    const roleInput = document.getElementById('signup-role');
    roleCards.forEach(card => {
        card.addEventListener('click', () => {
            roleCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            roleInput.value = card.getAttribute('data-role');
        });
    });

    // Login Form Submit
    document.getElementById('login-form').addEventListener('submit', (e) => {
        e.preventDefault();
        errorMsg.classList.add('hidden');

        const gmail = document.getElementById('login-gmail').value.trim();
        const password = document.getElementById('login-password').value;

        fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gmail, password })
        })
        .then(res => {
            if (!res.ok) {
                if (res.status === 401) throw new Error('Invalid Gmail address or password.');
                throw new Error('Server connection error.');
            }
            return res.json();
        })
        .then(user => {
            saveSession(user);
            showToast('Welcome Back', `Logged in successfully as ${user.name}`, 'success');
        })
        .catch(err => {
            errorText.textContent = err.message;
            errorMsg.classList.remove('hidden');
        });
    });

    // Signup Form Submit
    document.getElementById('signup-form').addEventListener('submit', (e) => {
        e.preventDefault();
        errorMsg.classList.add('hidden');

        const name = document.getElementById('signup-name').value.trim();
        const gmail = document.getElementById('signup-gmail').value.trim();
        const password = document.getElementById('signup-password').value;
        const role = document.getElementById('signup-role').value;
        const contact = document.getElementById('signup-contact').value.trim();

        fetch(`${API_BASE}/api/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, gmail, password, role, contact })
        })
        .then(res => {
            if (!res.ok) {
                if (res.status === 409) throw new Error('A user with this Gmail already exists.');
                throw new Error('Failed to register account.');
            }
            return res.json();
        })
        .then(user => {
            saveSession(user);
            showToast('Account Created', `Successfully signed up as ${user.name}`, 'success');
        })
        .catch(err => {
            errorText.textContent = err.message;
            errorMsg.classList.remove('hidden');
        });
    });

    // Logout Click
    document.getElementById('btn-logout-session').addEventListener('click', () => {
        clearSession();
        showToast('Logged Out', 'Your session was cleared.', 'info');
    });

    // Load initial session
    checkSession();
}

function checkSession() {
    const sessionData = localStorage.getItem('smartcivic_session');
    const authModal = document.getElementById('auth-modal');
    const banner = document.getElementById('user-profile-banner');
    const loginTriggerBtn = document.getElementById('btn-login-trigger');
    
    if (sessionData) {
        currentUser = JSON.parse(sessionData);
        authModal.classList.add('hidden');
        banner.classList.remove('hidden');
        loginTriggerBtn.classList.add('hidden');

        // Populate banner text
        document.getElementById('lbl-user-name').textContent = currentUser.name;
        document.getElementById('lbl-user-role').textContent = currentUser.role.toUpperCase();

        // Enforce views and tab restrictions based on role
        enforceRoleRestrictions();
        fetchWorkers();
    } else {
        currentUser = null;
        authModal.classList.remove('hidden');
        banner.classList.add('hidden');
        loginTriggerBtn.classList.remove('hidden');
        
        // Show Citizen Portal for Guest access
        document.getElementById('btn-citizen').style.display = 'flex';
        document.getElementById('btn-authority').style.display = 'none';
        document.getElementById('btn-worker').style.display = 'none';
        document.getElementById('btn-journalist').style.display = 'none';
        switchTab('citizen-portal');
    }
}

function saveSession(user) {
    localStorage.setItem('smartcivic_session', JSON.stringify(user));
    checkSession();
}

function clearSession() {
    localStorage.removeItem('smartcivic_session');
    checkSession();
}

function enforceRoleRestrictions() {
    const btnCitizen = document.getElementById('btn-citizen');
    const btnAuthority = document.getElementById('btn-authority');
    const btnWorker = document.getElementById('btn-worker');
    const btnJournalist = document.getElementById('btn-journalist');

    btnCitizen.style.display = 'none';
    btnAuthority.style.display = 'none';
    btnWorker.style.display = 'none';
    btnJournalist.style.display = 'none';

    if (currentUser.role === 'citizen') {
        btnCitizen.style.display = 'flex';
        switchTab('citizen-portal');
    } else if (currentUser.role === 'authority') {
        btnCitizen.style.display = 'flex';
        btnAuthority.style.display = 'flex';
        switchTab('authority-dashboard');
    } else if (currentUser.role === 'worker') {
        btnWorker.style.display = 'flex';
        document.getElementById('val-worker-name').textContent = currentUser.name;
        switchTab('worker-module');
    } else if (currentUser.role === 'journalist') {
        btnJournalist.style.display = 'flex';
        switchTab('journalist-dashboard');
    }
}

// Tab navigation
function initTabs() {
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            switchTab(targetTab);
        });
    });
}

function switchTab(tabId) {
    activeTab = tabId;
    
    // Update nav links active states
    document.querySelectorAll('.nav-btn').forEach(b => {
        if (b.getAttribute('data-tab') === tabId) {
            b.classList.add('active');
        } else {
            b.classList.remove('active');
        }
    });

    // Update tab sections
    document.querySelectorAll('.tab-content').forEach(sect => {
        if (sect.id === tabId) {
            sect.classList.add('active-tab');
        } else {
            sect.classList.remove('active-tab');
        }
    });

    // Refresh leaflet map sizes when tabs switch (crucial for leaflet rendering)
    setTimeout(() => {
        if (tabId === 'citizen-portal') {
            if (pickerMap) pickerMap.invalidateSize();
            if (citizenHeatmapMap) citizenHeatmapMap.invalidateSize();
            loadCitizenComplaints();
            loadHeatmapData();
        } else if (tabId === 'authority-dashboard') {
            if (authorityHeatmapMap) authorityHeatmapMap.invalidateSize();
            loadDashboardData();
            loadHeatmapData();
        } else if (tabId === 'worker-module') {
            if (workerRouteMap) {
                workerRouteMap.invalidateSize();
            }
            loadWorkerTasks();
        } else if (tabId === 'journalist-dashboard') {
            loadJournalistData();
        }
    }, 200);
}

// Initialize Leaflet Maps
function initMaps() {
    // 1. Citizen Picker Map
    pickerMap = L.map('map-picker').setView([DEFAULT_LAT, DEFAULT_LNG], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(pickerMap);

    pickerMarker = L.marker([DEFAULT_LAT, DEFAULT_LNG], { draggable: true }).addTo(pickerMap);
    
    // Set form coordinates on drag end
    pickerMarker.on('dragend', function (event) {
        const marker = event.target;
        const position = marker.getLatLng();
        updateCoordsInForm(position.lat, position.lng);
    });

    // Set form coordinates on map click
    pickerMap.on('click', function (e) {
        pickerMarker.setLatLng(e.latlng);
        updateCoordsInForm(e.latlng.lat, e.latlng.lng);
    });

    // 2. Citizen Heatmap Map
    const citizenElem = document.getElementById('map-citizen-heatmap');
    if (citizenElem) {
        citizenHeatmapMap = L.map('map-citizen-heatmap').setView([DEFAULT_LAT, DEFAULT_LNG], 12);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(citizenHeatmapMap);
    }

    // 3. Authority Heatmap Map
    const authElem = document.getElementById('map-authority-heatmap');
    if (authElem) {
        authorityHeatmapMap = L.map('map-authority-heatmap').setView([DEFAULT_LAT, DEFAULT_LNG], 12);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(authorityHeatmapMap);
    }

    // 4. Worker Route Map
    workerRouteMap = L.map('map-worker-route').setView([DEFAULT_LAT, DEFAULT_LNG], 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(workerRouteMap);

    // Initial heatmap load
    loadHeatmapData();
}

// Fetch & Render Regional Complaint Heatmaps
async function loadHeatmapData() {
    try {
        const res = await fetch(`${API_BASE}/api/heatmap/summary`);
        if (!res.ok) return;
        const data = await res.json();
        
        renderHeatmapOnMap(citizenHeatmapMap, citizenHeatmapGroup, data);
        renderHeatmapOnMap(authorityHeatmapMap, authorityHeatmapGroup, data);
    } catch (err) {
        console.error("Error loading heatmap data:", err);
    }
}

function renderHeatmapOnMap(mapObj, layerGroup, data) {
    if (!mapObj) return;
    layerGroup.clearLayers();

    const regionalSummary = data.regional_summary || [];
    const heatPoints = data.heat_points || [];

    if (regionalSummary.length === 0 && heatPoints.length === 0) return;

    // 1. Draw Regional Density Circles (Red, Yellow, Green based on complaint count)
    regionalSummary.forEach(item => {
        const count = item.count;
        const lat = item.avg_lat;
        const lng = item.avg_lng;
        const ward = item.ward;
        const color = item.color; // #ef4444 (Red > 5), #f59e0b (Yellow 3-5), #10b981 (Green 1-2)
        const severity = item.severity;

        let radius = 600;
        if (severity === 'High') radius = 1000;
        else if (severity === 'Moderate') radius = 750;

        const circle = L.circle([lat, lng], {
            color: color,
            fillColor: color,
            fillOpacity: 0.35,
            radius: radius,
            weight: 2
        });

        const formattedWard = ward.replace('_', ' ').toUpperCase();
        const popupContent = `
            <div class="heatmap-popup-content">
                <h4 style="color: ${color};"><i class="fa-solid fa-fire"></i> ${formattedWard}</h4>
                <p><strong>Density Status:</strong> <span style="color:${color}; font-weight:700;">${severity} Severity (${count} complaints)</span></p>
                <p><strong>High Priority Issues:</strong> ${item.high_priority_count}</p>
                <p style="font-size:0.75rem; color:#64748b; margin-top:4px;">Color: ${severity === 'High' ? '🔴 Red (> 5)' : (severity === 'Moderate' ? '🟡 Yellow (3 - 5)' : '🟢 Green (1 - 2)')}</p>
            </div>
        `;
        circle.bindPopup(popupContent);
        layerGroup.addLayer(circle);

        // Central Badge
        const badgeIcon = L.divIcon({
            className: 'custom-heatmap-badge',
            html: `<div style="background:${color}; color:#fff; font-weight:bold; font-size:11px; padding:3px 8px; border-radius:12px; border:2px solid #fff; box-shadow:0 2px 6px rgba(0,0,0,0.4); text-align:center; white-space:nowrap;">${formattedWard}: ${count} (${severity})</div>`,
            iconSize: [110, 24],
            iconAnchor: [55, 12]
        });
        const marker = L.marker([lat, lng], { icon: badgeIcon });
        marker.bindPopup(popupContent);
        layerGroup.addLayer(marker);
    });

    // 2. Individual Point Markers / Heat Overlay
    heatPoints.forEach(p => {
        let pColor = p.priority === 'High' ? '#ef4444' : (p.priority === 'Medium' ? '#f59e0b' : '#10b981');
        const ptMarker = L.circleMarker([p.lat, p.lng], {
            radius: 7,
            fillColor: pColor,
            color: '#ffffff',
            weight: 1.5,
            fillOpacity: 0.85
        });
        ptMarker.bindPopup(`
            <div class="heatmap-popup-content">
                <b>${p.category ? p.category.toUpperCase() : 'COMPLAINT'}</b><br>
                <span>ID: ${p.complaint_id}</span><br>
                <span>Priority: <strong style="color:${pColor}">${p.priority}</strong></span><br>
                <span>Ward: ${p.ward ? p.ward.replace('_', ' ').toUpperCase() : 'General'}</span>
            </div>
        `);
        layerGroup.addLayer(ptMarker);
    });

    layerGroup.addTo(mapObj);
}


// Helper to fill ward representation based on position coordinates
function getWardByLocation(lat, lng) {
    if (lat > 12.97) {
        return lng < 77.59 ? 'ward_1' : 'ward_2';
    } else {
        return 'ward_3';
    }
}

function updateCoordsInForm(lat, lng) {
    document.getElementById('val-latitude').textContent = lat.toFixed(6);
    document.getElementById('val-longitude').textContent = lng.toFixed(6);
    
    // Smart Ward dynamic preview removed
}

// Forms & Inputs handling
function initForms() {
    // Issue Category Dropdown Quick Select
    const categoryPreset = document.getElementById('form-category-preset');
    const descInput = document.getElementById('form-description');
    if (categoryPreset && descInput) {
        categoryPreset.addEventListener('change', (e) => {
            const selectedVal = e.target.value;
            if (!selectedVal) return;

            const existingText = descInput.value.trim();
            // Clean out any previous category prefix if present
            const cleanText = existingText.replace(/^(1 for Pothole|2 for Drainage|3 for Garbage|4 for Street Light|5 for Footpath|6 for Manhole|Pothole|Drainage|Garbage|Street Light|Footpath|Manhole)(:\s*|\s*-\s*|\s+)?/i, '');

            if (cleanText) {
                descInput.value = `${selectedVal} - ${cleanText}`;
            } else {
                descInput.value = `${selectedVal}: `;
            }
            descInput.focus();
        });
    }

    // Citizen GPS fetch
    const btnGps = document.getElementById('btn-gps-detect');
    btnGps.addEventListener('click', () => {
        if (navigator.geolocation) {
            btnGps.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Locating...';
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const lat = position.coords.latitude;
                    const lng = position.coords.longitude;
                    pickerMarker.setLatLng([lat, lng]);
                    pickerMap.setView([lat, lng], 15);
                    updateCoordsInForm(lat, lng);
                    btnGps.innerHTML = '<i class="fa-solid fa-check"></i> GPS Sync';
                    showToast('Location Detected', 'Set coordinates to your browser location.', 'success');
                },
                (error) => {
                    // Fallback to randomized local area coords
                    const randLat = DEFAULT_LAT + (Math.random() - 0.5) * 0.04;
                    const randLng = DEFAULT_LNG + (Math.random() - 0.5) * 0.04;
                    pickerMarker.setLatLng([randLat, randLng]);
                    pickerMap.setView([randLat, randLng], 14);
                    updateCoordsInForm(randLat, randLng);
                    btnGps.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Mock Location';
                    showToast('GPS Timeout', 'Using local mock coordinates for demo environment.', 'info');
                },
                { timeout: 6000 }
            );
        }
    });

    // Image Upload Previews
    const imageInput = document.getElementById('form-image');
    const dropArea = imageInput.closest('.file-drop-area');
    const previewContainer = document.getElementById('image-preview-container');
    const previewImg = document.getElementById('image-preview');
    const btnRemove = document.getElementById('btn-remove-image');

    imageInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                previewImg.src = e.target.result;
                previewContainer.classList.remove('hidden');
                dropArea.classList.add('hidden');
            }
            reader.readAsDataURL(file);
        }
    });

    btnRemove.addEventListener('click', () => {
        imageInput.value = '';
        previewImg.src = '';
        previewContainer.classList.add('hidden');
        dropArea.classList.remove('hidden');
    });

    // Resolution photo preview
    const resolveImage = document.getElementById('resolve-image');
    const resolveDropArea = resolveImage.closest('.file-drop-area');
    const resolvePreviewContainer = document.getElementById('resolve-preview-container');
    const resolvePreviewImg = document.getElementById('resolve-preview');

    resolveImage.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                resolvePreviewImg.src = e.target.result;
                resolvePreviewContainer.classList.remove('hidden');
                resolveDropArea.classList.add('hidden');
            }
            reader.readAsDataURL(file);
        }
    });

    // Form Submission: Create Complaint
    const reportForm = document.getElementById('report-form');
    reportForm.addEventListener('submit', (e) => {
        e.preventDefault();
        
        const submitBtn = document.getElementById('btn-submit-complaint');
        const btnText = submitBtn.querySelector('.btn-text');
        const spinner = submitBtn.querySelector('.spinner');

        // Toggle loading status
        submitBtn.disabled = true;
        btnText.classList.add('hidden');
        spinner.classList.remove('hidden');

        // Form fields
        const description = document.getElementById('form-description').value;
        const latitude = document.getElementById('val-latitude').textContent;
        const longitude = document.getElementById('val-longitude').textContent;
        const contact = document.getElementById('form-contact').value;
        const image = imageInput.files[0];

        const formData = new FormData();
        formData.append('description', description);
        formData.append('latitude', latitude);
        formData.append('longitude', longitude);
        formData.append('contact', contact);
        if (image) {
            formData.append('image', image);
        }

        // POST request
        fetch(`${API_BASE}/api/complaints`, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) throw new Error('API request failed');
            return response.json();
        })
        .then(data => {
            showToast('Complaint Filed', `ID: ${data.complaint_id} saved successfully!`, 'success');
            
            // Clear Form
            reportForm.reset();
            btnRemove.click();
            
            // If duplicate was detected, render warning card
            const dupWarning = document.getElementById('duplicate-warning');
            if (data.is_duplicate) {
                document.getElementById('dup-linked-id').textContent = data.duplicate_of;
                dupWarning.classList.remove('hidden');
                
                document.getElementById('btn-view-duplicate').onclick = () => {
                    document.getElementById('search-complaint-id').value = data.duplicate_of;
                    trackComplaint(data.duplicate_of);
                    dupWarning.classList.add('hidden');
                };
            } else {
                dupWarning.classList.add('hidden');
            }

            // Immediately select tracker search
            document.getElementById('search-complaint-id').value = data.complaint_id;
            trackComplaint(data.complaint_id);
        })
        .catch(err => {
            console.error(err);
            showToast('Error Submitting', 'Could not establish connection to city servers.', 'error');
        })
        .finally(() => {
            submitBtn.disabled = false;
            btnText.classList.remove('hidden');
            spinner.classList.add('hidden');
        });
    });

    // Tracking search button
    document.getElementById('btn-search-track').addEventListener('click', () => {
        const id = document.getElementById('search-complaint-id').value.trim();
        if (id) {
            trackComplaint(id);
        }
    });

    // Refresh Dashboard Button
    document.getElementById('btn-refresh-dashboard').addEventListener('click', () => {
        loadDashboardData();
        showToast('Database Refreshed', 'Fetched latest city issues.', 'info');
    });

    // Setup filter change listeners
    document.getElementById('filter-status').addEventListener('change', loadDashboardData);
    document.getElementById('filter-priority').addEventListener('change', loadDashboardData);

    // Modal Close
    document.getElementById('btn-close-assignment-modal').addEventListener('click', () => {
        document.getElementById('assignment-modal').classList.add('hidden');
    });

    document.getElementById('btn-close-resolve-modal').addEventListener('click', () => {
        document.getElementById('resolve-modal').classList.add('hidden');
    });

    document.getElementById('btn-close-navigation-modal').addEventListener('click', () => {
        document.getElementById('navigation-modal').classList.add('hidden');
    });

    // Form Assign Submit
    document.getElementById('assign-worker-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const compId = document.getElementById('modal-hidden-complaint-id').value;
        const workerId = document.getElementById('modal-worker-select').value;
        const priority = document.getElementById('modal-priority-select').value;

        fetch(`${API_BASE}/api/complaints/${compId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'Assigned', assigned_to: workerId, priority: priority })
        })
        .then(res => res.json())
        .then(data => {
            showToast('Task Dispatched', `Issue ${compId} assigned successfully.`, 'success');
            document.getElementById('assignment-modal').classList.add('hidden');
            loadDashboardData();
        })
        .catch(err => console.error(err));
    });

    // Form Resolve Submit
    document.getElementById('resolve-task-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const compId = document.getElementById('resolve-hidden-complaint-id').value;
        const notes = document.getElementById('resolve-notes').value;
        const photo = document.getElementById('resolve-image').files[0];

        const formData = new FormData();
        formData.append('status', 'Resolved');
        formData.append('resolution_notes', notes);
        if (photo) {
            formData.append('resolution_image', photo);
        }

        fetch(`${API_BASE}/api/complaints/${compId}`, {
            method: 'PUT',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            showToast('Job Resolved', `Issue ${compId} resolved & closed.`, 'success');
            document.getElementById('resolve-modal').classList.add('hidden');
            document.getElementById('worker-work-area').classList.add('hidden');
            
            // reset file drops
            resolveImage.value = '';
            resolvePreviewImg.src = '';
            resolvePreviewContainer.classList.add('hidden');
            resolveDropArea.classList.remove('hidden');
            document.getElementById('resolve-notes').value = '';

            loadWorkerTasks();
        })
        .catch(err => console.error(err));
    });

    // Back button in worker route details
    document.getElementById('btn-close-work-area').addEventListener('click', () => {
        document.getElementById('worker-work-area').classList.add('hidden');
        activeWorkerTask = null;
    });

    // Worker Site Status Toggle: In Progress
    document.getElementById('btn-toggle-in-progress').addEventListener('click', () => {
        if (!activeWorkerTask) return;
        
        fetch(`${API_BASE}/api/complaints/${activeWorkerTask.complaint_id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'In Progress' })
        })
        .then(res => res.json())
        .then(data => {
            showToast('Status Updated', 'Site work marked In Progress.', 'success');
            activeWorkerTask = data;
            
            const btn = document.getElementById('btn-toggle-in-progress');
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Active on Site';
            btn.classList.add('btn-emerald-submit');
            btn.disabled = true;

            loadWorkerTasks();
        })
        .catch(err => console.error(err));
    });

    // Worker Progress Update Log
    document.getElementById('btn-worker-add-notes').addEventListener('click', () => {
        if (!activeWorkerTask) return;
        const notesInput = document.getElementById('worker-progress-notes');
        const notes = notesInput.value.trim();
        if (!notes) {
            showToast('Empty Update', 'Please type a progress note first.', 'warning');
            return;
        }

        fetch(`${API_BASE}/api/complaints/${activeWorkerTask.complaint_id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'In Progress', notes: notes })
        })
        .then(res => res.json())
        .then(data => {
            showToast('Progress Logged', 'Site update registered successfully.', 'success');
            notesInput.value = '';
            activeWorkerTask = data;
            openWorkerTaskMap(data);
            loadWorkerTasks();
        })
        .catch(err => console.error(err));
    });

    // Resolve Modal Opener
    document.getElementById('btn-open-resolve-modal').addEventListener('click', () => {
        if (!activeWorkerTask) return;
        document.getElementById('resolve-hidden-complaint-id').value = activeWorkerTask.complaint_id;
        document.getElementById('resolve-modal').classList.remove('hidden');
    });
}

// Track Complaint Timeline
function trackComplaint(id) {
    currentlyTrackedId = id;
    const searchInput = document.getElementById('search-complaint-id');
    if (searchInput && searchInput.value !== id) {
        searchInput.value = id;
    }

    fetch(`${API_BASE}/api/complaints/${id}`)
    .then(res => {
        if (!res.ok) throw new Error('Not found');
        return res.json();
    })
    .then(data => {
        const trackerResult = document.getElementById('tracker-result');
        trackerResult.classList.remove('hidden');
        
        document.getElementById('track-id').textContent = data.complaint_id;
        document.getElementById('track-description').textContent = data.description;
        
        // Category Badge
        const catBadge = document.getElementById('track-category');
        catBadge.textContent = data.category.replace('_', ' ').toUpperCase();
        
        // Status Badge
        const statusBadge = document.getElementById('track-status-badge');
        const oldStatus = statusBadge.textContent;
        statusBadge.textContent = data.status;
        statusBadge.className = `badge-status badge-${data.status.replace(' ', '')}`;

        if (oldStatus && oldStatus !== 'Resolved' && data.status === 'Resolved') {
            showToast('Issue Resolved', `Your tracked complaint <strong>${data.complaint_id}</strong> has been successfully RESOLVED!`, 'success');
        }

        // Priority
        const prioritySpan = document.getElementById('track-priority');
        prioritySpan.textContent = data.priority;
        prioritySpan.className = `text-priority-${data.priority.toLowerCase()}`;

        // Ward removed

        // Worker
        document.getElementById('track-worker').textContent = data.assigned_to_name || 'Not Assigned Yet';

        // Image & Auto Description Analysis
        const imgContainer = document.getElementById('track-image-container');
        const analysisBox = document.getElementById('track-image-analysis-box');
        const analysisText = document.getElementById('track-image-analysis-text');
        
        if (data.image_path) {
            document.getElementById('track-image').src = `${API_BASE}${data.image_path}`;
            imgContainer.classList.remove('hidden');
            
            if (data.image_analysis) {
                analysisText.textContent = data.image_analysis;
                analysisBox.classList.remove('hidden');
            } else {
                analysisBox.classList.add('hidden');
            }
        } else {
            imgContainer.classList.add('hidden');
        }

        // Escalated flag banner
        const escBanner = document.getElementById('track-escalation-banner');
        if (data.escalation_flag) {
            escBanner.classList.remove('hidden');
        } else {
            escBanner.classList.add('hidden');
        }

        // Reset all steps
        document.querySelectorAll('.timeline-step').forEach(step => {
            step.className = 'timeline-step';
            const sName = step.id.replace('step-', '');
            document.getElementById(`time-${sName}`).textContent = '-';
        });

        // Parse History and Activate steps
        const statusesOrder = ['Submitted', 'Assigned', 'InProgress', 'Resolved'];
        let activeStatusIndex = statusesOrder.indexOf(data.status.replace(' ', ''));
        if (data.status === 'Closed') {
            activeStatusIndex = 3;
        }

        // Populate times and status highlights
        data.history.forEach(log => {
            const stepName = log.status.replace(' ', '');
            const element = document.getElementById(`step-${stepName}`);
            
            if (element) {
                element.classList.add('completed');
                const timeObj = new Date(log.timestamp);
                document.getElementById(`time-${stepName}`).textContent = timeObj.toLocaleString();
            }
        });

        // Set current active status
        const activeElem = document.getElementById(`step-${data.status.replace(' ', '')}`);
        if (activeElem) {
            activeElem.classList.remove('completed');
            activeElem.classList.add('active');
        }
        
        showToast('Complaint Found', `Loaded timeline for ${data.complaint_id}`, 'info');
    })
    .catch(err => {
        showToast('Not Found', `Complaint ID ${id} was not found in city files.`, 'error');
        document.getElementById('tracker-result').classList.add('hidden');
    });
}

// Load authority dashboard data
function loadDashboardData() {
    // 1. Stats Counter API
    let analyticsUrl = `${API_BASE}/api/analytics`;
    if (currentUser && currentUser.created_at) {
        analyticsUrl += `?created_after=${currentUser.created_at}`;
    }
    fetch(analyticsUrl)
    .then(res => res.json())
    .then(data => {
        document.getElementById('stat-total-issues').textContent = data.total;
        document.getElementById('stat-pending-issues').textContent = data.pending;
        document.getElementById('stat-resolved-issues').textContent = data.resolved;
        document.getElementById('stat-escalated-issues').textContent = data.escalated;

        renderCharts(data.categories, data.wards);
    })
    .catch(err => console.error(err));

    // 2. Table Complaints List
    const status = document.getElementById('filter-status').value;
    const priority = document.getElementById('filter-priority').value;

    let url = `${API_BASE}/api/complaints`;
    const params = [];
    if (status) params.push(`status=${status}`);
    if (priority) params.push(`priority=${priority}`);
    if (currentUser && currentUser.created_at) params.push(`created_after=${currentUser.created_at}`);
    if (params.length > 0) {
        url += `?${params.join('&')}`;
    }

    fetch(url)
    .then(res => res.json())
    .then(complaints => {
        if (activeComplaintsList && activeComplaintsList.length > 0) {
            complaints.forEach(c => {
                const cached = activeComplaintsList.find(x => x.complaint_id === c.complaint_id);
                if (cached && cached.status !== 'Resolved' && c.status === 'Resolved') {
                    showToast('Task Resolved', `Complaint <strong>${c.complaint_id}</strong> was marked RESOLVED by the worker.`, 'success');
                }
            });
        }
        activeComplaintsList = complaints;
        renderComplaintsTable(complaints);
        renderDashboardMapLayers();
    })
    .catch(err => console.error(err));
}

// Render complaints in table
function renderComplaintsTable(complaints) {
    const tbody = document.getElementById('complaints-table-body');
    tbody.innerHTML = '';

    if (complaints.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-table-message"><i class="fa-solid fa-folder-open"></i> No complaints match the active filters.</td></tr>';
        return;
    }

    complaints.forEach(c => {
        const row = document.createElement('tr');
        
        const rDate = new Date(c.created_at);
        const formattedDate = rDate.toLocaleDateString() + ' ' + rDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        const prioClass = `badge-${c.priority.toLowerCase()}`;
        const statusClass = `badge-${c.status.replace(' ', '')}`;

        let navigateHtml = `<button class="btn-action-assign" onclick="triggerNavigation(${c.latitude}, ${c.longitude}, '${c.complaint_id}')" style="background: var(--accent-indigo-glow); color: var(--accent-indigo);"><i class="fa-solid fa-location-arrow"></i> Navigate</button>`;

        let actionHtml = '';
        if (c.status === 'Submitted') {
            actionHtml = `<button class="btn-action-assign" onclick="openAssignmentModal('${c.complaint_id}')"><i class="fa-solid fa-user-plus"></i> Assign</button>`;
        } else if (c.status === 'Resolved') {
            actionHtml = `<button class="btn-action-close" onclick="closeComplaint('${c.complaint_id}')"><i class="fa-solid fa-lock"></i> Close</button>`;
        } else {
            actionHtml = `<span class="text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Dispatched</span>`;
        }

        row.innerHTML = `
            <td><strong>${c.complaint_id}</strong></td>
            <td><span class="badge">${c.category.replace('_', ' ')}</span></td>
            <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${c.description}</td>
            <td><span class="badge ${prioClass}">${c.priority}</span></td>
            <td><span class="badge ${statusClass}">${c.status}</span></td>
            <td>${formattedDate}</td>
            <td>${c.assigned_to_name || '<i class="text-muted">Unassigned</i>'}</td>
            <td><div style="display: flex; gap: 6px; align-items: center;">${actionHtml}${navigateHtml}</div></td>
        `;
        tbody.appendChild(row);
    });
}

// Render Dashboard Leaflet Markers or Heatmaps (removed)
function renderDashboardMapLayers() {
    // Map was removed from authority dashboard
}

// Fetch all registered workers
function fetchWorkers() {
    fetch(`${API_BASE}/api/users?role=worker`)
    .then(res => res.json())
    .then(workers => {
        activeWorkersList = workers;
    })
    .catch(err => console.error(err));
}

// Open assignment dialog modal
window.openAssignmentModal = function(id) {
    const comp = activeComplaintsList.find(c => c.complaint_id === id);
    if (!comp) return;

    document.getElementById('modal-complaint-id').textContent = comp.complaint_id;
    document.getElementById('modal-hidden-complaint-id').value = comp.complaint_id;
    document.getElementById('modal-complaint-category').textContent = comp.category.replace('_', ' ').toUpperCase();
    document.getElementById('modal-complaint-desc').textContent = comp.description;
    document.getElementById('modal-priority-select').value = comp.priority;

    const select = document.getElementById('modal-worker-select');
    select.innerHTML = '<option value="">-- Loading Workers... --</option>';

    fetch(`${API_BASE}/api/users?role=worker`)
    .then(res => res.json())
    .then(workers => {
        activeWorkersList = workers;
        select.innerHTML = '<option value="">-- Choose Worker --</option>';
        workers.forEach(w => {
            const opt = document.createElement('option');
            opt.value = w.id;
            opt.textContent = `${w.name} (${w.gmail})`;
            select.appendChild(opt);
        });
    })
    .catch(err => {
        console.error(err);
        select.innerHTML = '<option value="">-- Choose Worker --</option>';
    });

    document.getElementById('assignment-modal').classList.remove('hidden');
};

// Directly close resolving task
window.closeComplaint = function(id) {
    if (!confirm(`Are you sure you want to officially CLOSE complaint ${id}?`)) return;

    fetch(`${API_BASE}/api/complaints/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'Closed' })
    })
    .then(res => res.json())
    .then(() => {
        showToast('Complaint Closed', `Issue ${id} has been archived.`, 'success');
        loadDashboardData();
    })
    .catch(err => console.error(err));
};

// Renders Chart.js Analytics
function renderCharts(categoriesData, wardsData) {
    const ctxCat = document.getElementById('chart-categories').getContext('2d');
    if (categoriesChart) {
        categoriesChart.destroy();
    }

    const catLabels = Object.keys(categoriesData).map(k => k.replace('_', ' ').toUpperCase());
    const catVals = Object.values(categoriesData);

    categoriesChart = new Chart(ctxCat, {
        type: 'doughnut',
        data: {
            labels: catLabels,
            datasets: [{
                data: catVals,
                backgroundColor: ['#6366f1', '#14b8a6', '#f59e0b', '#f43f5e', '#64748b'],
                borderColor: 'rgba(30, 41, 59, 0.4)',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: document.body.classList.contains('light-theme') ? '#0f172a' : '#f8fafc', font: { family: 'Inter' } }
                }
            }
        }
    });

    // Wards density bar chart removed
}

// WORKER MODULE INTERACTION
function loadWorkerTasks() {
    if (!currentUser || currentUser.role !== 'worker') return;

    let url = `${API_BASE}/api/complaints`;
    if (currentUser && currentUser.created_at) {
        url += `?created_after=${currentUser.created_at}`;
    }

    fetch(url)
    .then(res => res.json())
    .then(complaints => {
        const myTasks = complaints.filter(c => parseInt(c.assigned_to) === parseInt(currentUser.id));
        renderWorkerJobsList(myTasks);
    })
    .catch(err => console.error(err));
}

function renderWorkerJobsList(tasks) {
    const list = document.getElementById('worker-jobs-list');
    list.innerHTML = '';

    if (tasks.length === 0) {
        list.innerHTML = '<p class="empty-jobs-message"><i class="fa-solid fa-circle-check text-accent-emerald"></i> You have no assigned tasks in your queue!</p>';
        return;
    }

    tasks.forEach(task => {
        const card = document.createElement('div');
        card.className = 'job-card';
        if (activeWorkerTask && activeWorkerTask.complaint_id === task.complaint_id) {
            card.classList.add('active-job');
        }

        const formattedDate = new Date(task.created_at).toLocaleDateString();
        const statusClass = `badge-${task.status.replace(' ', '')}`;

        card.innerHTML = `
            <div class="job-card-header">
                <h4>${task.complaint_id}</h4>
                <div style="display: flex; gap: 4px;">
                    <span class="badge badge-${task.priority.toLowerCase()}">${task.priority}</span>
                    <span class="badge ${statusClass}">${task.status}</span>
                </div>
            </div>
            <div class="job-card-desc">${task.description}</div>
            <div class="job-card-footer" style="margin-bottom: 8px;">
                <span>Category: <strong>${task.category}</strong></span>
                <span>Assigned: ${formattedDate}</span>
            </div>
            <button class="btn-submit-blue btn-navigate-task" onclick="event.stopPropagation(); triggerNavigation(${task.latitude}, ${task.longitude}, '${task.complaint_id}')" style="margin-top: 4px; padding: 6px 12px; font-size: 0.8rem; width: 100%; border-radius: 8px;">
                <i class="fa-solid fa-location-arrow"></i> Navigate
            </button>
        `;

        card.addEventListener('click', () => {
            openWorkerTaskMap(task);
            
            document.querySelectorAll('.job-card').forEach(c => c.classList.remove('active-job'));
            card.classList.add('active-job');
        });

        list.appendChild(card);
    });
}

function openWorkerTaskMap(task) {
    activeWorkerTask = task;
    document.getElementById('worker-work-area').classList.remove('hidden');
    document.getElementById('work-active-id').textContent = task.complaint_id;
    document.getElementById('work-active-category').textContent = task.category.replace('_', ' ').toUpperCase() + ' TASK';

    const btnInProg = document.getElementById('btn-toggle-in-progress');
    const btnResolve = document.getElementById('btn-open-resolve-modal');

    // Reset classes
    btnInProg.classList.remove('btn-emerald-submit');
    btnResolve.classList.remove('btn-emerald-submit');

    if (task.status === 'In Progress') {
        btnInProg.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Active on Site';
        btnInProg.classList.add('btn-emerald-submit');
        btnInProg.disabled = true;
        btnResolve.disabled = false;
        btnResolve.innerHTML = 'Resolve Task';
    } else if (task.status === 'Resolved' || task.status === 'Closed') {
        btnInProg.innerHTML = 'Completed';
        btnInProg.classList.add('btn-emerald-submit');
        btnInProg.disabled = true;
        btnResolve.innerHTML = '<i class="fa-solid fa-circle-check"></i> Resolved';
        btnResolve.classList.add('btn-emerald-submit');
        btnResolve.disabled = true;
    } else {
        btnInProg.innerHTML = 'Mark "In Progress"';
        btnInProg.disabled = false;
        btnResolve.disabled = true; // Cannot resolve until in progress!
        btnResolve.innerHTML = 'Resolve Task';
    }

    const logGroup = document.getElementById('worker-log-input-group');
    if (task.status === 'In Progress') {
        logGroup.classList.remove('hidden');
    } else {
        logGroup.classList.add('hidden');
    }

    // Set starting worker lat/lng coordinates near the ward center
    let workerLat = DEFAULT_LAT;
    let workerLng = DEFAULT_LNG;

    if (task.ward === 'ward_1') {
        workerLat = DEFAULT_LAT + 0.015;
        workerLng = DEFAULT_LNG - 0.015;
    } else if (task.ward === 'ward_2') {
        workerLat = DEFAULT_LAT + 0.015;
        workerLng = DEFAULT_LNG + 0.015;
    } else {
        workerLat = DEFAULT_LAT - 0.015;
        workerLng = DEFAULT_LNG;
    }

    const issueLat = task.latitude;
    const issueLng = task.longitude;

    workerRouteMap.setView([workerLat, workerLng], 14);
    workerRouteMap.invalidateSize();

    if (workerStartMarker) workerRouteMap.removeLayer(workerStartMarker);
    if (workerEndMarker) workerRouteMap.removeLayer(workerEndMarker);
    if (workerRouteLayer) workerRouteMap.removeLayer(workerRouteLayer);

    const startIcon = L.divIcon({
        html: `<div style="background-color: #14b8a6; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(20, 184, 166, 0.8);"></div>`,
        className: 'worker-marker-icon',
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });
    
    const endIcon = L.divIcon({
        html: `<div style="background-color: #f59e0b; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(245, 158, 11, 0.8);"></div>`,
        className: 'issue-marker-icon',
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });

    workerStartMarker = L.marker([workerLat, workerLng], { icon: startIcon }).bindPopup('Your Current Location').addTo(workerRouteMap);
    workerEndMarker = L.marker([issueLat, issueLng], { icon: endIcon }).bindPopup(`Issue site: ${task.complaint_id}`).addTo(workerRouteMap);

    // Curved routing path for visual realism
    const pathCoordinates = [
        [workerLat, workerLng],
        [(workerLat + issueLat)/2 + 0.001, (workerLng + issueLng)/2 - 0.001],
        [issueLat, issueLng]
    ];

    workerRouteLayer = L.polyline(pathCoordinates, {
        color: '#6366f1',
        weight: 6,
        opacity: 0.75,
        dashArray: '8, 8',
        lineJoin: 'round'
    }).addTo(workerRouteMap);

    workerRouteMap.fitBounds(workerRouteLayer.getBounds(), { padding: [40, 40] });
    showToast('Route Loaded', 'Calculated optimized ward dispatch route.', 'info');
}

// Toast Notifications Helper
function showToast(title, message, type = 'info') {
    const toast = document.getElementById('notification-toast');
    const toastTitle = document.getElementById('toast-title');
    const toastMsg = document.getElementById('toast-message');

    toastTitle.textContent = title;
    toastMsg.textContent = message;

    if (type === 'success') {
        toast.style.borderLeftColor = 'var(--accent-emerald)';
        toast.querySelector('.toast-icon i').className = 'fa-solid fa-circle-check text-accent-emerald';
    } else if (type === 'error') {
        toast.style.borderLeftColor = 'var(--priority-high)';
        toast.querySelector('.toast-icon i').className = 'fa-solid fa-circle-exclamation text-priority-high';
    } else if (type === 'info') {
        toast.style.borderLeftColor = 'var(--accent-indigo)';
        toast.querySelector('.toast-icon i').className = 'fa-solid fa-circle-info text-accent-indigo';
    }

    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4500);

    document.getElementById('btn-close-toast').onclick = () => {
        toast.classList.add('hidden');
    };
}

// JOURNALIST DASHBOARD CONTROLLER & LOGIC
let activeRedirectedComplaints = [];
let selectedRedirectedComplaint = null;

function loadJournalistData() {
    if (!currentUser || currentUser.role !== 'journalist') return;

    // 1. Fetch redirected complaints (5-min rule unopened ones)
    let complaintsUrl = `${API_BASE}/api/complaints?redirected_to_journalist=true`;
    if (currentUser && currentUser.created_at) {
        complaintsUrl += `&created_after=${currentUser.created_at}`;
    }
    fetch(complaintsUrl)
    .then(res => res.json())
    .then(complaints => {
        activeRedirectedComplaints = complaints;
        renderRedirectedList(complaints);
    })
    .catch(err => console.error(err));

    // 2. Fetch published reports
    fetch(`${API_BASE}/api/journalist/reports`)
    .then(res => res.json())
    .then(reports => {
        renderPublishedFeed(reports);
    })
    .catch(err => console.error(err));
}

function renderRedirectedList(complaints) {
    const listContainer = document.getElementById('journalist-redirect-list');
    listContainer.innerHTML = '';

    if (complaints.length === 0) {
        listContainer.innerHTML = '<p class="empty-list-message"><i class="fa-solid fa-face-smile"></i> No complaints currently redirected to press feed.</p>';
        return;
    }

    complaints.forEach(c => {
        const card = document.createElement('div');
        card.className = 'job-card'; // Reuse worker card styling since it looks great
        
        card.innerHTML = `
            <div class="job-card-header">
                <h4>${c.complaint_id}</h4>
                <span class="badge badge-${c.priority.toLowerCase()}">${c.priority}</span>
            </div>
            <div class="job-card-desc">${c.description}</div>
            <div style="margin-top: 10px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:0.75rem; color:var(--text-muted);">Category: <strong>${c.category.toUpperCase()}</strong></span>
                <button class="btn-action-assign" onclick="inspectRedirectedComplaint('${c.complaint_id}')" style="padding: 6px 12px; font-size:0.8rem;">
                    <i class="fa-solid fa-magnifying-glass"></i> Inspect & Write
                </button>
            </div>
        `;
        listContainer.appendChild(card);
    });
}

window.inspectRedirectedComplaint = function(compId) {
    const complaint = activeRedirectedComplaints.find(c => c.complaint_id === compId);
    if (!complaint) return;

    selectedRedirectedComplaint = complaint;

    // Reveal Station Panel
    const station = document.getElementById('journalist-station');
    station.classList.remove('hidden');

    // Reset AI Report Editor & loaders
    document.getElementById('ai-report-editor').classList.add('hidden');
    document.getElementById('ai-agent-loader').classList.add('hidden');
    document.getElementById('btn-trigger-ai-agent').disabled = false;

    // Load complaint metadata
    const summary = document.getElementById('station-complaint-summary');
    const formattedDate = new Date(complaint.created_at).toLocaleString();
    
    summary.innerHTML = `
        <h4>${complaint.complaint_id} (${complaint.category.toUpperCase()})</h4>
        <p><strong>Description:</strong> ${complaint.description}</p>
        <p><strong>Reported At:</strong> ${formattedDate}</p>
        <p><strong>Priority:</strong> <span class="badge badge-${complaint.priority.toLowerCase()}">${complaint.priority}</span></p>
        <p><strong>GPS Location:</strong> ${complaint.latitude.toFixed(5)}, ${complaint.longitude.toFixed(5)}</p>
    `;

    document.getElementById('report-hidden-complaint-id').value = compId;
};

function initJournalistEvents() {
    // 1. Close Station Panel button
    document.getElementById('btn-close-journalist-station').addEventListener('click', () => {
        document.getElementById('journalist-station').classList.add('hidden');
        selectedRedirectedComplaint = null;
    });

    // 2. Trigger AI Agent report generation
    document.getElementById('btn-trigger-ai-agent').addEventListener('click', () => {
        if (!selectedRedirectedComplaint) return;

        const triggerBtn = document.getElementById('btn-trigger-ai-agent');
        const loader = document.getElementById('ai-agent-loader');
        const editor = document.getElementById('ai-report-editor');

        triggerBtn.disabled = true;
        loader.classList.remove('hidden');
        editor.classList.add('hidden');

        fetch(`${API_BASE}/api/journalist/reports/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ complaint_id: selectedRedirectedComplaint.complaint_id })
        })
        .then(res => {
            if (!res.ok) throw new Error("Generation failed");
            return res.json();
        })
        .then(data => {
            // Fake an AI delay of 1.5 seconds for visual premium polish effect!
            setTimeout(() => {
                loader.classList.add('hidden');
                editor.classList.remove('hidden');
                
                document.getElementById('report-title-input').value = data.title;
                document.getElementById('report-content-input').value = data.content;
                showToast('AI Generation Done', 'AI agent drafted investigative report.', 'success');
            }, 1500);
        })
        .catch(err => {
            console.error(err);
            loader.classList.add('hidden');
            triggerBtn.disabled = false;
            showToast('Generation Error', 'AI Agent encountered a scanning error.', 'error');
        });
    });

    // 3. Save Draft (Local state / unpublished)
    document.getElementById('btn-save-draft').addEventListener('click', () => {
        submitJournalistReport(false);
    });

    // 4. Publish Report submit listener
    document.getElementById('journalist-report-form').addEventListener('submit', (e) => {
        e.preventDefault();
        submitJournalistReport(true);
    });
}

function submitJournalistReport(publishState) {
    const compId = document.getElementById('report-hidden-complaint-id').value;
    const title = document.getElementById('report-title-input').value.trim();
    const content = document.getElementById('report-content-input').value.trim();

    if (!compId || !title || !content) {
        showToast('Missing Fields', 'Title and Content are required to submit reports.', 'error');
        return;
    }

    fetch(`${API_BASE}/api/journalist/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            complaint_id: compId,
            title: title,
            content: content,
            published: publishState
        })
    })
    .then(res => {
        if (!res.ok) throw new Error("Failed to save report");
        return res.json();
    })
    .then(data => {
        const actionText = publishState ? 'published & broadcasted' : 'saved as draft';
        showToast('Report Saved', `Article was successfully ${actionText}!`, 'success');
        
        // Hide Station Panel
        document.getElementById('journalist-station').classList.add('hidden');
        
        // Refresh data
        loadJournalistData();
    })
    .catch(err => {
        console.error(err);
        showToast('Submission Error', 'Failed to store article details on municipal servers.', 'error');
    });
}

function renderPublishedFeed(reports) {
    const feed = document.getElementById('published-articles-feed');
    feed.innerHTML = '';

    if (reports.length === 0) {
        feed.innerHTML = '<p class="empty-list-message">No articles published to press feeds yet.</p>';
        return;
    }

    reports.forEach(r => {
        const card = document.createElement('div');
        card.className = 'article-feed-card';
        if (!r.published) {
            card.classList.add('draft');
        }

        const dateStr = new Date(r.created_at).toLocaleDateString();
        const badgeState = r.published ? '<span class="badge badge-resolved">PUBLISHED</span>' : '<span class="badge badge-low">DRAFT</span>';

        card.innerHTML = `
            <div class="article-meta-row">
                <span>Issue ID: <strong>${r.complaint_id}</strong></span>
                <span>Date: ${dateStr}</span>
            </div>
            <h3>${r.title}</h3>
            <div class="article-body-preview">${r.content}</div>
            <div class="article-actions">
                ${badgeState}
                ${!r.published ? `<button class="btn-action-assign" onclick="publishReportFromFeed(${r.id})" style="padding: 4px 8px; font-size: 0.72rem;"><i class="fa-solid fa-paper-plane"></i> Publish</button>` : ''}
            </div>
        `;
        feed.appendChild(card);
    });
}

window.publishReportFromFeed = function(reportId) {
    fetch(`${API_BASE}/api/journalist/reports/${reportId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ published: true })
    })
    .then(res => {
        if (!res.ok) throw new Error("Failed to publish report");
        return res.json();
    })
    .then(() => {
        showToast('Article Published', 'Watchdog news article is now live!', 'success');
        loadJournalistData();
    })
    .catch(err => {
        console.error(err);
        showToast('Publish Error', 'Could not establish connection to live feeds.', 'error');
    });
};

// GLOBAL NAVIGATION MAP & TURN-BY-TURN DIRECTIONS
let navigationMap = null;
let navigationStartMarker = null;
let navigationEndMarker = null;
let navigationRouteLayer = null;

window.triggerNavigation = function(destLat, destLng, complaintId) {
    const modal = document.getElementById('navigation-modal');
    modal.classList.remove('hidden');

    let startLat = userCurrentLat;
    let startLng = userCurrentLng;

    // Initialize Map if not already initialized
    setTimeout(() => {
        if (!navigationMap) {
            navigationMap = L.map('map-modal-navigation').setView([startLat, startLng], 14);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(navigationMap);
        } else {
            navigationMap.setView([startLat, startLng], 14);
        }

        // Invalidate map size so it renders fully in the modal
        navigationMap.invalidateSize();

        // Clear existing layers
        if (navigationStartMarker) navigationMap.removeLayer(navigationStartMarker);
        if (navigationEndMarker) navigationMap.removeLayer(navigationEndMarker);
        if (navigationRouteLayer) navigationMap.removeLayer(navigationRouteLayer);

        // Add Markers
        const startIcon = L.divIcon({
            html: `<div style="background-color: #14b8a6; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(20, 184, 166, 0.8);"></div>`,
            className: 'nav-marker-start',
            iconSize: [16, 16],
            iconAnchor: [8, 8]
        });
        
        const endIcon = L.divIcon({
            html: `<div style="background-color: #ef4444; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(239, 68, 68, 0.8);"></div>`,
            className: 'nav-marker-end',
            iconSize: [16, 16],
            iconAnchor: [8, 8]
        });

        navigationStartMarker = L.marker([startLat, startLng], { icon: startIcon }).bindPopup('Your Current Location').addTo(navigationMap);
        navigationEndMarker = L.marker([destLat, destLng], { icon: endIcon }).bindPopup(`Target Issue: ${complaintId}`).addTo(navigationMap);

        // Draw Route (polyline)
        const path = [
            [startLat, startLng],
            [(startLat + destLat)/2 + 0.001, (startLng + destLng)/2 - 0.001],
            [destLat, destLng]
        ];

        navigationRouteLayer = L.polyline(path, {
            color: '#6366f1',
            weight: 6,
            opacity: 0.85,
            dashArray: '6, 6'
        }).addTo(navigationMap);

        navigationMap.fitBounds(navigationRouteLayer.getBounds(), { padding: [50, 50] });

        // Generate Turn-by-Turn Directions
        generateTurnByTurnDirections(startLat, startLng, destLat, destLng, complaintId);

        // Hook up external Google Maps redirect button
        document.getElementById('btn-open-real-google-maps').onclick = () => {
            const url = `https://www.google.com/maps/dir/?api=1&origin=${startLat},${startLng}&destination=${destLat},${destLng}&travelmode=driving`;
            window.open(url, '_blank');
        };
    }, 150);
};

function generateTurnByTurnDirections(startLat, startLng, destLat, destLng, complaintId) {
    const list = document.getElementById('navigation-steps-list');
    list.innerHTML = '';

    const latDelta = destLat - startLat;
    const lngDelta = destLng - startLng;

    const steps = [];
    steps.push({
        icon: 'fa-location-dot',
        text: 'Depart from your current location.'
    });

    if (latDelta > 0) {
        steps.push({
            icon: 'fa-arrow-up',
            text: `Head north on municipal corridor for ${(latDelta * 111).toFixed(1)} km.`
        });
    } else {
        steps.push({
            icon: 'fa-arrow-down',
            text: `Head south on municipal corridor for ${(Math.abs(latDelta) * 111).toFixed(1)} km.`
        });
    }

    if (lngDelta > 0) {
        steps.push({
            icon: 'fa-arrow-right',
            text: `Turn right at main intersection, proceed east for ${(lngDelta * 111).toFixed(1)} km.`
        });
    } else {
        steps.push({
            icon: 'fa-arrow-left',
            text: `Turn left at main intersection, proceed west for ${(Math.abs(lngDelta) * 111).toFixed(1)} km.`
        });
    }

    steps.push({
        icon: 'fa-circle-check',
        text: `Arrive at complaint site <strong>${complaintId}</strong> on the right.`
    });

    steps.forEach((step, idx) => {
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.gap = '12px';
        item.style.alignItems = 'flex-start';
        item.innerHTML = `
            <div style="background: rgba(99, 102, 241, 0.1); color: var(--accent-indigo); width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; flex-shrink: 0;">
                <i class="fa-solid ${step.icon}"></i>
            </div>
            <div>
                <span style="font-weight: 700; display: block; margin-bottom: 2px;">Step ${idx + 1}</span>
                <span>${step.text}</span>
            </div>
        `;
        list.appendChild(item);
    });
}

// CITIZEN PORTAL COMPLAINTS BOARD
function loadCitizenComplaints() {
    let url = `${API_BASE}/api/complaints`;
    if (currentUser && currentUser.created_at) {
        url += `?created_after=${currentUser.created_at}`;
    }
    fetch(url)
    .then(res => res.json())
    .then(complaints => {
        renderCitizenComplaintsList(complaints);
    })
    .catch(err => console.error(err));
}

function renderCitizenComplaintsList(complaints) {
    const list = document.getElementById('citizen-complaints-list');
    if (!list) return;

    list.innerHTML = '';
    if (complaints.length === 0) {
        list.innerHTML = '<p class="empty-list-message">No reported city issues found.</p>';
        return;
    }

    complaints.forEach(c => {
        const card = document.createElement('div');
        card.className = 'job-card'; // Reuse styled job-card from CSS
        
        const prioClass = `badge-${c.priority.toLowerCase()}`;
        const statusClass = `badge-${c.status.replace(' ', '')}`;

        card.innerHTML = `
            <div class="job-card-header">
                <h4>${c.complaint_id}</h4>
                <span class="badge ${prioClass}">${c.priority}</span>
            </div>
            <div class="job-card-desc">${c.description}</div>
            <div class="job-card-footer" style="margin-bottom: 8px; flex-direction: column; align-items: flex-start; gap: 4px;">
                <span>Category: <strong>${c.category.replace('_', ' ').toUpperCase()}</strong></span>
                <span>Status: <span class="badge ${statusClass}" style="margin: 0; font-size: 0.7rem; padding: 2px 6px;">${c.status}</span></span>
                <span>Worker: <strong>${c.assigned_to_name || 'Not Assigned Yet'}</strong></span>
            </div>
            <button class="btn-submit-blue" onclick="trackComplaint('${c.complaint_id}')" style="margin-top: 4px; padding: 6px 12px; font-size: 0.8rem; width: 100%; border-radius: 8px;">
                <i class="fa-solid fa-clock-rotate-left"></i> View Live Timeline
            </button>
        `;
        list.appendChild(card);
    });
}

