// SmartCivic AI - Frontend JS Application

const API_BASE = (window.location.origin && (window.location.origin.includes(':5000') || window.location.origin.includes(':5500')))
    ? (window.location.origin.includes(':5500') ? 'http://127.0.0.1:5000' : window.location.origin)
    : 'http://127.0.0.1:5000';

// State management
let activeTab = 'citizen-portal';
let currentUser = null; // Object containing logged in user details

// Automatically attach X-User-Id and credentials to backend requests
const _nativeFetch = window.fetch;
window.fetch = function(url, options = {}) {
    options = options || {};
    const urlStr = typeof url === 'string' ? url : (url.url || '');
    const isBackendCall = urlStr.startsWith('/') || urlStr.startsWith(API_BASE) || (window.location && urlStr.startsWith(window.location.origin));
    
    if (isBackendCall) {
        options.credentials = options.credentials || 'include';
        if (currentUser && currentUser.id) {
            options.headers = options.headers || {};
            if (options.headers instanceof Headers) {
                if (!options.headers.has('X-User-Id')) {
                    options.headers.set('X-User-Id', currentUser.id.toString());
                }
            } else if (Array.isArray(options.headers)) {
                options.headers.push(['X-User-Id', currentUser.id.toString()]);
            } else {
                options.headers['X-User-Id'] = currentUser.id.toString();
            }
        }
    }
    return _nativeFetch(url, options);
};

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
let activeWorkerTasks = [];
let showingHeatmap = false;
let autoRefreshTimer = null;
let currentlyTrackedId = null;
let cachedTrackData = null;
let currentNavData = null;
let cachedCategoriesData = null;
let publishedArticlesList = [];
let cachedHAComplaints = [];
let cachedHALeaderboard = [];
let cachedHALogs = [];
let cachedMyComplaints = [];

// Hugging Face AI Multilingual Translation Helper
async function translateTextWithHF(text, targetLang, sourceLang = 'auto') {
    if (!text || !text.toString().trim()) {
        return { success: true, translated_text: text, source_lang: targetLang };
    }
    const currentUiLang = targetLang || (window.getCurrentLang ? getCurrentLang() : 'en');
    try {
        const res = await fetch(`${API_BASE}/api/ai/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text.toString().trim(),
                target_lang: currentUiLang,
                source_lang: sourceLang
            })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        return data;
    } catch (err) {
        console.warn('Hugging Face translation notice:', err);
        return { success: false, translated_text: text, source_lang: 'unknown', error: err.message };
    }
}
window.translateTextWithHF = translateTextWithHF;


let userCurrentLat = 12.971598;
let userCurrentLng = 77.594562;
let locationAcquiredFromGps = false;

if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
        (pos) => {
            userCurrentLat = pos.coords.latitude;
            userCurrentLng = pos.coords.longitude;
            locationAcquiredFromGps = true;
            if (pickerMarker && pickerMap) {
                pickerMarker.setLatLng([userCurrentLat, userCurrentLng]);
                pickerMap.setView([userCurrentLat, userCurrentLng], 15);
                updateCoordsInForm(userCurrentLat, userCurrentLng);
            }
        },
        (err) => {
            console.warn("Geolocation query error: using default coords", err);
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
}

// Default Map Center (Bangalore-like environment)
const DEFAULT_LAT = 12.971598;
const DEFAULT_LNG = 77.594562;

// Initialize on load

// Global Language Change Listener - Phase 4 Dynamic Content Re-rendering
window.addEventListener('languageChanged', (e) => {
    const lang = e.detail?.language || (window.getCurrentLang ? getCurrentLang() : 'en');

    // 1. Update user profile banner
    updateUserBanner();

    // 2. Re-render complaints table if on authority tab
    if (activeComplaintsList && activeComplaintsList.length > 0) {
        if (activeTab === 'authority-dashboard') {
            renderComplaintsTable(activeComplaintsList);
        }
        if (activeTab === 'citizen-portal') {
            renderCitizenComplaintsList(activeComplaintsList);
        }
    }

    // 3. Re-render category distribution chart with translated labels
    if (cachedCategoriesData) {
        renderCharts(cachedCategoriesData);
    }

    // 4. Re-render currently tracked complaint timeline
    if (cachedTrackData) {
        renderTrackerDetails(cachedTrackData);
    }

    // 5. Re-render worker tasks and active route
    if (currentUser && currentUser.role === 'worker') {
        if (activeWorkerTasks && activeWorkerTasks.length > 0) {
            renderWorkerJobsList(activeWorkerTasks);
        }
        if (activeWorkerTask) {
            openWorkerTaskMap(activeWorkerTask);
        }
    }

    // 6. Re-render journalist section
    if (currentUser && currentUser.role === 'journalist') {
        if (activeRedirectedComplaints && activeRedirectedComplaints.length > 0) {
            renderRedirectedList(activeRedirectedComplaints);
        }
        if (selectedRedirectedComplaint) {
            inspectRedirectedComplaint(selectedRedirectedComplaint.complaint_id);
        }
        if (publishedArticlesList && publishedArticlesList.length > 0) {
            renderPublishedFeed(publishedArticlesList);
        }
    }

    // 7. Re-render turn-by-turn directions if navigation modal is active
    if (currentNavData) {
        generateTurnByTurnDirections(
            currentNavData.startLat,
            currentNavData.startLng,
            currentNavData.destLat,
            currentNavData.destLng,
            currentNavData.complaintId
        );
    }

    // 8. Re-render Higher Authority oversight table if on HA tab
    if (activeTab === 'higher-authority-dashboard') {
        if (cachedHAComplaints && cachedHAComplaints.length > 0) {
            renderHigherAuthorityTable(cachedHAComplaints);
        } else {
            loadHigherAuthorityData();
        }
    }

    // 9. Re-render citizen personal submitted complaints
    if (currentUser && currentUser.role === 'citizen') {
        loadCitizenMyComplaints();
    }

    // 10. Re-render notifications list if modal is open
    const notifModal = document.getElementById('notification-modal');
    if (notifModal && !notifModal.classList.contains('hidden')) {
        pollNotifications(true);
    }

    // 11. Re-render active public tracker discussion comments if tracked
    if (currentlyTrackedId) {
        loadTrackerComments(currentlyTrackedId);
    }
});

function updateUserBanner() {
    const lblName = document.getElementById('lbl-user-name');
    const lblRole = document.getElementById('lbl-user-role');
    if (lblName) {
        lblName.textContent = currentUser ? currentUser.name : (window.t ? t('guest', 'Guest') : 'Guest');
    }
    if (lblRole) {
        lblRole.textContent = currentUser ? (window.getRoleTranslation ? getRoleTranslation(currentUser.role) : currentUser.role) : (window.t ? t('role_citizen', 'citizen') : 'citizen');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initMaps();
    initAuth();
    initTabs();
    initForms();
    initJournalistEvents();
    initEnhancedCivicFeatures();
    
    // Start auto-refreshing dashboard data every 5 seconds
    autoRefreshTimer = setInterval(() => {
        if (currentUser && currentUser.role === 'authority' && activeTab === 'authority-dashboard') {
            loadDashboardData();
        } else if (currentUser && (currentUser.role === 'higher_authority' || currentUser.role === 'admin') && activeTab === 'higher-authority-dashboard') {
            loadHigherAuthorityData();
        } else if (currentUser && currentUser.role === 'worker' && activeTab === 'worker-module') {
            loadWorkerTasks();
        } else if (activeTab === 'citizen-portal') {
            loadCitizenComplaints();
            if (currentlyTrackedId) {
                trackComplaint(currentlyTrackedId, true); // silent refresh
            }
        }
        if (currentUser) {
            pollNotifications();
        }
    }, 5000);

    // Deep-linking support for Gmail tracking links (?track=COMP-XXXXXX)
    const urlParams = new URLSearchParams(window.location.search);
    const trackParam = urlParams.get('track');
    if (trackParam) {
        switchTab('citizen-portal');
        const searchInput = document.getElementById('search-complaint-id');
        if (searchInput) searchInput.value = trackParam;
        trackComplaint(trackParam);
        setTimeout(() => {
            const trackerSection = document.getElementById('tracker-result') || document.getElementById('search-complaint-id');
            if (trackerSection) {
                trackerSection.scrollIntoView({ behavior: 'smooth' });
            }
        }, 500);
    }
});

// Theme Management
function initTheme() {
    const themeBtn = document.getElementById('theme-toggle-btn');
    const savedTheme = localStorage.getItem('smartcivic_theme') || 'dark';

    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
        if (themeBtn) {
            const icon = themeBtn.querySelector('i');
            if (icon) icon.className = 'fa-solid fa-sun';
        }
    } else {
        document.body.classList.remove('light-theme');
        if (themeBtn) {
            const icon = themeBtn.querySelector('i');
            if (icon) icon.className = 'fa-solid fa-moon';
        }
    }

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            document.body.classList.toggle('light-theme');
            const isLight = document.body.classList.contains('light-theme');
            localStorage.setItem('smartcivic_theme', isLight ? 'light' : 'dark');
            const icon = themeBtn.querySelector('i');
            if (icon) {
                icon.className = isLight ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
            }
            if (typeof renderCharts === 'function' && typeof cachedCategoriesData !== 'undefined' && cachedCategoriesData) {
                renderCharts(cachedCategoriesData);
            }
        });
    }
}

// Authentication & Session Handling
function initAuth() {
    const authModal = document.getElementById('auth-modal');
    const loginPanel = document.getElementById('login-panel');
    const signupPanel = document.getElementById('signup-panel');
    const errorMsg = document.getElementById('auth-error-msg');
    const errorText = document.getElementById('auth-error-text');

    // Switch panels via links
    const linkLogin = document.getElementById('link-go-to-login');
    if (linkLogin) {
        linkLogin.addEventListener('click', () => {
            if (loginPanel) loginPanel.classList.remove('hidden');
            if (signupPanel) signupPanel.classList.add('hidden');
            if (errorMsg) errorMsg.classList.add('hidden');
        });
    }

    const linkSignup = document.getElementById('link-go-to-signup');
    if (linkSignup) {
        linkSignup.addEventListener('click', () => {
            if (signupPanel) signupPanel.classList.remove('hidden');
            if (loginPanel) loginPanel.classList.add('hidden');
            if (errorMsg) errorMsg.classList.add('hidden');
        });
    }

    // Close Auth Modal
    const closeAuthBtn = document.getElementById('btn-close-auth-modal');
    if (closeAuthBtn) {
        closeAuthBtn.addEventListener('click', () => {
            if (authModal) authModal.classList.add('hidden');
        });
    }

    // Continue as Guest Citizen Trigger
    const btnContinueGuest = document.getElementById('btn-continue-guest');
    if (btnContinueGuest) {
        btnContinueGuest.addEventListener('click', () => {
            if (authModal) authModal.classList.add('hidden');
        });
    }

    // Open Auth Modal via Header Trigger
    const loginTriggerBtn = document.getElementById('btn-login-trigger');
    if (loginTriggerBtn) {
        loginTriggerBtn.addEventListener('click', () => {
            if (authModal) authModal.classList.remove('hidden');
        });
    }

    // Signup Role selection cards click logic
    const signupRoleCards = document.querySelectorAll('#signup-panel .role-card');
    const signupRoleInput = document.getElementById('signup-role');
    const authNotice = document.getElementById('signup-authority-notice');
    signupRoleCards.forEach(card => {
        card.addEventListener('click', () => {
            signupRoleCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            const chosenRole = card.getAttribute('data-role');
            if (signupRoleInput) signupRoleInput.value = chosenRole;
            if (authNotice) {
                if (chosenRole === 'authority' || chosenRole === 'higher_authority') {
                    authNotice.classList.remove('hidden');
                } else {
                    authNotice.classList.add('hidden');
                }
            }
        });
    });

    // Login Role selection cards click logic
    const loginRoleCards = document.querySelectorAll('.login-role-selector .role-card');
    const loginRoleInput = document.getElementById('login-role');
    const secretKeyGroup = document.getElementById('login-secret-key-group');
    const secretKeyInput = document.getElementById('login-secret-key');
    const authorityAlert = document.getElementById('login-authority-alert');

    loginRoleCards.forEach(card => {
        card.addEventListener('click', () => {
            loginRoleCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            const role = card.getAttribute('data-login-role');
            if (loginRoleInput) loginRoleInput.value = role;

            if (role === 'authority' || role === 'higher_authority') {
                if (secretKeyGroup) secretKeyGroup.classList.remove('hidden');
                if (authorityAlert) authorityAlert.classList.remove('hidden');
                if (secretKeyInput) {
                    secretKeyInput.required = true;
                    secretKeyInput.focus();
                }
            } else {
                if (secretKeyGroup) secretKeyGroup.classList.add('hidden');
                if (authorityAlert) authorityAlert.classList.add('hidden');
                if (secretKeyInput) {
                    secretKeyInput.required = false;
                    secretKeyInput.value = '';
                }
            }
        });
    });

    // Login Form Submit
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            if (errorMsg) errorMsg.classList.add('hidden');

            const gmailEl = document.getElementById('login-gmail');
            const passEl = document.getElementById('login-password');
            const keyEl = document.getElementById('login-secret-key');
            if (!gmailEl || !passEl) return;

            const gmail = gmailEl.value.trim();
            const password = passEl.value;
            const secret_key = keyEl ? keyEl.value.trim() : '';
            const selectedRole = loginRoleInput ? loginRoleInput.value : 'citizen';

            if ((selectedRole === 'authority' || selectedRole === 'higher_authority') && !secret_key) {
                if (errorText) errorText.textContent = 'Secret Authorization Key is required for Authority login. Please check your Gmail.';
                if (errorMsg) errorMsg.classList.remove('hidden');
                return;
            }

            fetch(`${API_BASE}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gmail, password, secret_key })
            })
            .then(async res => {
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(data.error || 'Invalid credentials or authorization key.');
                }
                return data;
            })
            .then(user => {
                saveSession(user);
                showToast('Welcome Back', `Logged in successfully as ${user.name} (${user.role})`, 'success');
            })
            .catch(err => {
                if (errorText) errorText.textContent = err.message;
                if (errorMsg) errorMsg.classList.remove('hidden');
            });
        });
    }

    // Signup Form Submit
    const signupForm = document.getElementById('signup-form');
    if (signupForm) {
        signupForm.addEventListener('submit', (e) => {
            e.preventDefault();
            if (errorMsg) errorMsg.classList.add('hidden');

            const nameEl = document.getElementById('signup-name');
            const gmailEl = document.getElementById('signup-gmail');
            const passEl = document.getElementById('signup-password');
            const roleEl = document.getElementById('signup-role');
            const contactEl = document.getElementById('signup-contact');

            const name = nameEl ? nameEl.value.trim() : '';
            const gmail = gmailEl ? gmailEl.value.trim() : '';
            const password = passEl ? passEl.value : '';
            const role = roleEl ? roleEl.value : 'citizen';
            const contact = contactEl ? contactEl.value.trim() : '';

            fetch(`${API_BASE}/api/auth/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, gmail, password, role, contact })
            })
            .then(async res => {
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(data.error || 'Failed to register account.');
                }
                return data;
            })
            .then(user => {
                if ((user.role === 'authority' || user.role === 'higher_authority') && user.approval_status === 'pending_approval') {
                    showToast('Application Submitted', 'Authority registration is awaiting Municipal Admin approval. Your Secret Key will be emailed to your Gmail upon approval.', 'info');
                    // Switch to login tab
                    const signupP = document.getElementById('signup-panel');
                    const loginP = document.getElementById('login-panel');
                    if (signupP && loginP) {
                        signupP.classList.add('hidden');
                        loginP.classList.remove('hidden');
                    }
                } else {
                    saveSession(user);
                    showToast('Account Created', `Successfully signed up as ${user.name}`, 'success');
                }
            })
            .catch(err => {
                if (errorText) errorText.textContent = err.message;
                if (errorMsg) errorMsg.classList.remove('hidden');
            });
        });
    }

    // Logout Click
    const logoutBtn = document.getElementById('btn-logout-session');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            clearSession();
            showToast('Logged Out', 'Your session was cleared.', 'info');
        });
    }

    // Load initial session
    checkSession();
}

function checkSession() {
    const sessionData = localStorage.getItem('smartcivic_session');
    const authModal = document.getElementById('auth-modal');
    const loginPanel = document.getElementById('login-panel');
    const signupPanel = document.getElementById('signup-panel');
    const banner = document.getElementById('user-profile-banner');
    const loginTriggerBtn = document.getElementById('btn-login-trigger');
    const closeAuthBtn = document.getElementById('btn-close-auth-modal');
    
    if (sessionData) {
        currentUser = JSON.parse(sessionData);
        document.body.classList.remove('landing-page');
        authModal.classList.add('hidden');
        banner.classList.remove('hidden');
        if (loginTriggerBtn) loginTriggerBtn.classList.add('hidden');
        if (closeAuthBtn) closeAuthBtn.style.display = 'block';

        // Populate banner text with localization
        updateUserBanner();

        // Auto-fill complaint form fields if user is logged in
        if (currentUser.gmail) {
            const formGmail = document.getElementById('form-gmail');
            if (formGmail && !formGmail.value) formGmail.value = currentUser.gmail;
        }
        if (currentUser.contact) {
            const formContact = document.getElementById('form-contact');
            if (formContact && !formContact.value) formContact.value = currentUser.contact;
        }

        // Redirect user to their role dashboard
        enforceRoleRestrictions();
        fetchWorkers();
        pollNotifications();
    } else {
        currentUser = null;
        document.body.classList.remove('landing-page');
        authModal.classList.remove('hidden');
        if (loginPanel) loginPanel.classList.remove('hidden');
        if (signupPanel) signupPanel.classList.add('hidden');
        banner.classList.add('hidden');
        if (loginTriggerBtn) loginTriggerBtn.classList.remove('hidden');
        if (closeAuthBtn) closeAuthBtn.style.display = 'block';
        
        document.getElementById('btn-citizen').style.display = 'flex';
        document.getElementById('btn-authority').style.display = 'none';
        const btnHigherAuth = document.getElementById('btn-higher-authority');
        if (btnHigherAuth) btnHigherAuth.style.display = 'none';
        document.getElementById('btn-worker').style.display = 'none';
        document.getElementById('btn-journalist').style.display = 'none';

        switchTab('citizen-portal');
        loadCitizenComplaints();
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
    const btnHigherAuth = document.getElementById('btn-higher-authority');
    const btnWorker = document.getElementById('btn-worker');
    const btnJournalist = document.getElementById('btn-journalist');

    btnCitizen.style.display = 'none';
    btnAuthority.style.display = 'none';
    if (btnHigherAuth) btnHigherAuth.style.display = 'none';
    btnWorker.style.display = 'none';
    btnJournalist.style.display = 'none';

    if (currentUser.role === 'citizen') {
        btnCitizen.style.display = 'flex';
        switchTab('citizen-portal');
    } else if (currentUser.role === 'authority') {
        btnCitizen.style.display = 'flex';
        btnAuthority.style.display = 'flex';
        switchTab('authority-dashboard');
    } else if (currentUser.role === 'higher_authority' || currentUser.role === 'admin') {
        btnCitizen.style.display = 'flex';
        btnAuthority.style.display = 'flex';
        if (btnHigherAuth) btnHigherAuth.style.display = 'flex';
        switchTab('higher-authority-dashboard');
    } else if (currentUser.role === 'worker') {
        btnWorker.style.display = 'flex';
        const valWorkerName = document.getElementById('val-worker-name');
        if (valWorkerName) valWorkerName.textContent = currentUser.name;
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
            loadCitizenMyComplaints();
            loadHeatmapData();
        } else if (tabId === 'authority-dashboard') {
            if (authorityHeatmapMap) authorityHeatmapMap.invalidateSize();
            loadDashboardData();
            loadCorporatorPerformance();
            loadHeatmapData();
        } else if (tabId === 'higher-authority-dashboard') {
            loadHigherAuthorityData();
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
    const initialLat = locationAcquiredFromGps ? userCurrentLat : DEFAULT_LAT;
    const initialLng = locationAcquiredFromGps ? userCurrentLng : DEFAULT_LNG;
    pickerMap = L.map('map-picker').setView([initialLat, initialLng], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(pickerMap);

    pickerMarker = L.marker([initialLat, initialLng], { draggable: true }).addTo(pickerMap);
    pickerMarker.bindPopup("<strong>Drag pin</strong> or <strong>click map</strong> to set your exact location (e.g. RR Nagar)");
    if (locationAcquiredFromGps) {
        updateCoordsInForm(initialLat, initialLng);
    }
    
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

let reverseGeocodeTimer = null;
function updateCoordsInForm(lat, lng) {
    document.getElementById('val-latitude').textContent = lat.toFixed(6);
    document.getElementById('val-longitude').textContent = lng.toFixed(6);
    
    const lblAddress = document.getElementById('lbl-address-string');
    if (lblAddress) {
        lblAddress.textContent = 'Fetching address...';
        if (reverseGeocodeTimer) clearTimeout(reverseGeocodeTimer);
        reverseGeocodeTimer = setTimeout(() => {
            fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`)
            .then(res => res.json())
            .then(data => {
                if (data && data.display_name) {
                    lblAddress.textContent = data.display_name;
                } else {
                    lblAddress.textContent = `Coordinates: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
                }
            })
            .catch(() => {
                lblAddress.textContent = `Coordinates: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
            });
        }, 400);
    }
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

    // Citizen GPS fetch - Auto Detect Current Location
    const btnGps = document.getElementById('btn-gps-detect');
    btnGps.addEventListener('click', () => {
        if (!navigator.geolocation) {
            showToast('GPS Not Supported', 'Geolocation is not supported by your browser.', 'error');
            return;
        }

        btnGps.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Locating...';
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                userCurrentLat = lat;
                userCurrentLng = lng;
                locationAcquiredFromGps = true;
                if (pickerMarker && pickerMap) {
                    pickerMarker.setLatLng([lat, lng]);
                    pickerMap.setView([lat, lng], 16);
                }
                updateCoordsInForm(lat, lng);
                btnGps.innerHTML = '<i class="fa-solid fa-check"></i> GPS Synced';
                showToast('Location Detected', `Current location acquired!`, 'success');
            },
            (error) => {
                // Fallback attempt without high accuracy constraint
                navigator.geolocation.getCurrentPosition(
                    (pos) => {
                        const lat = pos.coords.latitude;
                        const lng = pos.coords.longitude;
                        userCurrentLat = lat;
                        userCurrentLng = lng;
                        locationAcquiredFromGps = true;
                        if (pickerMarker && pickerMap) {
                            pickerMarker.setLatLng([lat, lng]);
                            pickerMap.setView([lat, lng], 15);
                        }
                        updateCoordsInForm(lat, lng);
                        btnGps.innerHTML = '<i class="fa-solid fa-check"></i> Location Synced';
                        showToast('Location Acquired', `Set to current browser position.`, 'info');
                    },
                    (err2) => {
                        btnGps.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> GPS Error';
                        let msg = 'Could not acquire current location. Tap on the map to place the pin.';
                        if (err2.code === err2.PERMISSION_DENIED) {
                            msg = 'Location permission was denied. Please allow location access in your browser.';
                        }
                        showToast('Location Detection Error', msg, 'warning');
                    },
                    { enableHighAccuracy: false, timeout: 8000 }
                );
            },
            { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
        );
    });

    // Image Upload Previews & EXIF GPS extraction
    const imageInput = document.getElementById('form-image');
    const dropArea = imageInput.closest('.file-drop-area');
    const previewContainer = document.getElementById('image-preview-container');
    const previewImg = document.getElementById('image-preview');
    const btnRemove = document.getElementById('btn-remove-image');

    const parseGeotagRegex = (text) => {
        if (!text) return null;
        const match = text.match(/(?:Lat|Latitude|lat)?\s*[:=]?\s*([+-]?\d{1,2}\.\d+)\D+(?:Long|Longitude|lng|lon)?\s*[:=]?\s*([+-]?\d{1,3}\.\d+)/i);
        if (match) {
            const lat = parseFloat(match[1]);
            const lng = parseFloat(match[2]);
            if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
                return { latitude: lat, longitude: lng };
            }
        }
        return null;
    };

    const descriptionInput = document.getElementById('form-description');
    if (descriptionInput) {
        descriptionInput.addEventListener('input', (e) => {
            const coords = parseGeotagRegex(e.target.value);
            if (coords && pickerMarker && pickerMap) {
                pickerMarker.setLatLng([coords.latitude, coords.longitude]);
                pickerMap.setView([coords.latitude, coords.longitude], 16);
                updateCoordsInForm(coords.latitude, coords.longitude);
                showToast('Geotag Coords Detected', `Geotag GPS location updated: ${coords.latitude}, ${coords.longitude}`, 'info');
            }
        });
    }

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

            // 1. Client-side EXIF GPS Extraction
            if (window.exifr) {
                window.exifr.gps(file).then(coords => {
                    if (coords && coords.latitude && coords.longitude) {
                        const lat = coords.latitude;
                        const lng = coords.longitude;
                        if (pickerMarker && pickerMap) {
                            pickerMarker.setLatLng([lat, lng]);
                            pickerMap.setView([lat, lng], 16);
                            updateCoordsInForm(lat, lng);
                            showToast('GPS Photo Geotag Detected', `Map pinned to exact photo location: ${lat.toFixed(5)}, ${lng.toFixed(5)}`, 'success');
                        }
                    }
                }).catch(err => {
                    console.log("No client EXIF GPS metadata in photo", err);
                });
            }

            // 2. Client-side Tesseract.js OCR Watermark Extraction (reads burned-in GPS Map Camera text)
            if (window.Tesseract) {
                showToast('Scanning Photo', 'AI scanning photo for GPS geotag watermark...', 'info');
                window.Tesseract.recognize(file, 'eng')
                .then(result => {
                    if (result && result.data && result.data.text) {
                        const ocrCoords = parseGeotagRegex(result.data.text);
                        if (ocrCoords && pickerMarker && pickerMap) {
                            pickerMarker.setLatLng([ocrCoords.latitude, ocrCoords.longitude]);
                            pickerMap.setView([ocrCoords.latitude, ocrCoords.longitude], 16);
                            updateCoordsInForm(ocrCoords.latitude, ocrCoords.longitude);
                            showToast('Geotag Photo Processed', `Location automatically pinned on map: ${ocrCoords.latitude}, ${ocrCoords.longitude}`, 'success');
                        }
                    }
                })
                .catch(err => console.log("Client OCR watermark check skipped:", err));
            }

            // 3. Server-side Geotag Preview Parser (handles EXIF + text watermarks)
            const formData = new FormData();
            formData.append('image', file);
            const descVal = document.getElementById('form-description') ? document.getElementById('form-description').value : '';
            if (descVal) formData.append('description', descVal);

            fetch(`${API_BASE}/api/parse-geotag`, {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data && data.found && data.latitude && data.longitude) {
                    const lat = data.latitude;
                    const lng = data.longitude;
                    if (pickerMarker && pickerMap) {
                        pickerMarker.setLatLng([lat, lng]);
                        pickerMap.setView([lat, lng], 16);
                        updateCoordsInForm(lat, lng);
                        showToast('Geotag Photo Processed', `Location automatically pinned on map: ${lat}, ${lng}`, 'success');
                    }
                }
            })
            .catch(err => {
                console.warn("Geotag preview endpoint skipped:", err);
            });
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
        const titleEl = document.getElementById('form-title');
        const title = titleEl ? titleEl.value.trim() : '';
        const catPresetEl = document.getElementById('form-category-preset');
        const categoryPreset = catPresetEl ? catPresetEl.value : '';
        const prioEl = document.getElementById('form-priority-select');
        const priorityPreset = prioEl ? prioEl.value : '';
        const description = document.getElementById('form-description').value;
        const latitude = document.getElementById('val-latitude').textContent;
        const longitude = document.getElementById('val-longitude').textContent;
        const contact = document.getElementById('form-contact').value;
        const formGmailEl = document.getElementById('form-gmail');
        const gmail = formGmailEl ? formGmailEl.value.trim() : '';
        const image = imageInput.files[0];

        const formData = new FormData();
        if (title) formData.append('title', title);
        if (categoryPreset) formData.append('category', categoryPreset);
        if (priorityPreset) formData.append('priority', priorityPreset);
        formData.append('description', description);
        formData.append('latitude', latitude);
        formData.append('longitude', longitude);
        formData.append('contact', contact);
        if (gmail) {
            formData.append('gmail', gmail);
        }
        if (currentUser && currentUser.id) {
            formData.append('citizen_id', currentUser.id);
        }
        if (image) {
            formData.append('image', image);
        }

        // POST request
        fetch(`${API_BASE}/api/complaints`, {
            method: 'POST',
            body: formData
        })
        .then(async response => {
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const errorMsg = data.error || 'Server rejected complaint submission.';
                throw new Error(errorMsg);
            }
            return data;
        })
        .then(data => {
            const toastMsg = gmail ? `ID: ${data.complaint_id} filed! Tracking details dispatched to ${gmail}.` : `ID: ${data.complaint_id} saved successfully!`;
            showToast('Complaint Filed', toastMsg, 'success');
            
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
            showToast('Error Submitting', err.message || 'Could not establish connection to city servers.', 'error');
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
        const deadlineInput = document.getElementById('modal-deadline-input');
        const deadline = deadlineInput && deadlineInput.value ? deadlineInput.value : null;

        const payload = { status: 'Assigned', assigned_to: workerId, priority: priority };
        if (deadline) payload.deadline = deadline;

        fetch(`${API_BASE}/api/complaints/${compId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            showToast('Task Dispatched', `Issue ${compId} assigned successfully with SLA.`, 'success');
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
        formData.append('status', 'Completed');
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
            showToast('Work Completed', `Issue ${compId} marked Completed. Citizen notified to verify resolution.`, 'success');
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
        const oldStatus = cachedTrackData ? cachedTrackData.status : null;
        renderTrackerDetails(data);

        if (oldStatus && oldStatus !== 'Resolved' && data.status === 'Resolved') {
            const resTitle = window.t ? t('toast_issue_resolved', 'Issue Resolved') : 'Issue Resolved';
            const resMsg = window.t ? t('toast_complaint_resolved_msg', 'Your tracked complaint {id} has been successfully RESOLVED!', { id: data.complaint_id }) : `Your tracked complaint ${data.complaint_id} has been successfully RESOLVED!`;
            showToast(resTitle, resMsg, 'success');
        }

        const foundTitle = window.t ? t('toast_complaint_found', 'Complaint Found') : 'Complaint Found';
        const foundMsg = window.t ? t('toast_loaded_timeline', 'Loaded timeline for {id}', { id: data.complaint_id }) : `Loaded timeline for ${data.complaint_id}`;
        showToast(foundTitle, foundMsg, 'info');
    })
    .catch(err => {
        showToast('Not Found', `Complaint ID ${id} was not found in city files.`, 'error');
        document.getElementById('tracker-result').classList.add('hidden');
    });
}

// Load authority dashboard data

// Render tracked complaint details with complete localization
function renderTrackerDetails(data) {
    if (!data) return;
    cachedTrackData = data;
    const trackerResult = document.getElementById('tracker-result');
    if (!trackerResult) return;
    trackerResult.classList.remove('hidden');
    
    document.getElementById('track-id').textContent = data.complaint_id;
    
    // Title
    const titleEl = document.getElementById('track-title');
    if (titleEl) {
        titleEl.textContent = data.title || (data.category ? data.category.replace('_', ' ').toUpperCase() : 'Civic Issue');
    }

    // Set and manage description & HF translation
    const descEl = document.getElementById('track-description');
    if (descEl) {
        descEl.textContent = data._is_translated && data._translated_description ? data._translated_description : data.description;
    }
    if (titleEl && data._is_translated && data._translated_title) {
        titleEl.textContent = data._translated_title;
    }

    // Setup HF On-Demand Translation for Tracker
    const btnTrackTranslate = document.getElementById('btn-track-translate');
    const hfBadge = document.getElementById('track-hf-badge');
    if (btnTrackTranslate) {
        if (!data._original_description || data._last_id !== data.complaint_id) {
            data._original_description = data.description;
            data._original_title = titleEl ? titleEl.textContent : '';
            data._is_translated = false;
            data._last_id = data.complaint_id;
        }

        // Reset display based on current translation state
        if (data._is_translated) {
            if (hfBadge) hfBadge.classList.remove('hidden');
            btnTrackTranslate.innerHTML = `<i class="fa-solid fa-rotate-left"></i> <span>${window.t ? t('btn_show_original', 'Show Original') : 'Show Original'}</span>`;
            btnTrackTranslate.style.background = 'rgba(16, 185, 129, 0.15)';
            btnTrackTranslate.style.borderColor = 'rgba(16, 185, 129, 0.4)';
            btnTrackTranslate.style.color = '#6ee7b7';
        } else {
            if (hfBadge) hfBadge.classList.add('hidden');
            btnTrackTranslate.innerHTML = `<i class="fa-solid fa-language"></i> <span>${window.t ? t('btn_hf_translate', 'Translate (HF AI)') : 'Translate (HF AI)'}</span>`;
            btnTrackTranslate.style.background = 'rgba(99, 102, 241, 0.15)';
            btnTrackTranslate.style.borderColor = 'rgba(99, 102, 241, 0.35)';
            btnTrackTranslate.style.color = '#c7d2fe';
        }

        btnTrackTranslate.onclick = async () => {
            const currentDescEl = document.getElementById('track-description');
            const currentTitleEl = document.getElementById('track-title');
            const currentLang = window.getCurrentLang ? getCurrentLang() : 'en';

            if (!data._is_translated) {
                btnTrackTranslate.disabled = true;
                btnTrackTranslate.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>${window.t ? t('hf_translating', 'Translating with Hugging Face...') : 'Translating...'}</span>`;
                
                let translatedDesc = '';
                let translatedTitle = '';

                if (currentLang === 'en' && data.english_description) {
                    translatedDesc = data.english_description;
                    translatedTitle = data.english_title || data._original_title;
                } else {
                    const descRes = await translateTextWithHF(data._original_description, currentLang);
                    translatedDesc = descRes.translated_text || data._original_description;
                    if (data._original_title) {
                        const titleRes = await translateTextWithHF(data._original_title, currentLang);
                        translatedTitle = titleRes.translated_text || data._original_title;
                    }
                }

                if (currentDescEl) currentDescEl.textContent = translatedDesc;
                if (currentTitleEl && translatedTitle) currentTitleEl.textContent = translatedTitle;

                data._translated_description = translatedDesc;
                data._translated_title = translatedTitle;
                data._is_translated = true;

                if (hfBadge) hfBadge.classList.remove('hidden');
                btnTrackTranslate.innerHTML = `<i class="fa-solid fa-rotate-left"></i> <span>${window.t ? t('btn_show_original', 'Show Original') : 'Show Original'}</span>`;
                btnTrackTranslate.style.background = 'rgba(16, 185, 129, 0.15)';
                btnTrackTranslate.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                btnTrackTranslate.style.color = '#6ee7b7';
                btnTrackTranslate.disabled = false;
            } else {
                if (currentDescEl) currentDescEl.textContent = data._original_description;
                if (currentTitleEl) currentTitleEl.textContent = data._original_title;

                data._is_translated = false;
                if (hfBadge) hfBadge.classList.add('hidden');
                btnTrackTranslate.innerHTML = `<i class="fa-solid fa-language"></i> <span>${window.t ? t('btn_hf_translate', 'Translate (HF AI)') : 'Translate (HF AI)'}</span>`;
                btnTrackTranslate.style.background = 'rgba(99, 102, 241, 0.15)';
                btnTrackTranslate.style.borderColor = 'rgba(99, 102, 241, 0.35)';
                btnTrackTranslate.style.color = '#c7d2fe';
            }
        };
    }

    // SLA Deadline Badge
    const slaEl = document.getElementById('track-sla-deadline') || document.getElementById('track-deadline-text');
    const slaBox = document.getElementById('track-deadline-box');
    if (slaEl) {
        if (data.deadline) {
            const dDate = new Date(data.deadline);
            slaEl.textContent = `SLA: ${dDate.toLocaleString()}`;
            if (data.overdue_flag) {
                if (slaBox) { slaBox.className = 'deadline-badge-box badge-high'; slaBox.classList.remove('hidden'); }
                slaEl.textContent += ' (OVERDUE)';
            } else {
                if (slaBox) { slaBox.className = 'deadline-badge-box'; slaBox.classList.remove('hidden'); }
            }
        } else if (slaBox) {
            slaBox.classList.add('hidden');
        }
    }

    // Rejection Banner
    const rejBanner = document.getElementById('track-rejection-banner');
    const rejReason = document.getElementById('track-rejection-reason') || document.getElementById('track-rejection-text');
    if (data.status === 'Rejected' && data.rejection_reason) {
        if (rejReason) rejReason.textContent = data.rejection_reason;
        if (rejBanner) rejBanner.classList.remove('hidden');
    } else if (rejBanner) {
        rejBanner.classList.add('hidden');
    }

    // Reopened Banner
    const reopBanner = document.getElementById('track-reopened-banner');
    const reopReason = document.getElementById('track-reopened-reason') || document.getElementById('track-reopened-text');
    if (data.reopen_count > 0 || data.status === 'Reopened') {
        if (reopReason) reopReason.textContent = `Issue Reopened (${data.reopen_count || 1}x): ${data.reopened_reason || 'Citizen unsatisfied with previous resolution'}`;
        if (reopBanner) reopBanner.classList.remove('hidden');
    } else if (reopBanner) {
        reopBanner.classList.add('hidden');
    }
    
    // Category Badge
    const catBadge = document.getElementById('track-category');
    if (catBadge) {
        const catText = window.getCategoryTranslation ? getCategoryTranslation(data.category) : data.category;
        catBadge.textContent = catText.toUpperCase();
    }
    
    // Status Badge
    const statusBadge = document.getElementById('track-status-badge');
    if (statusBadge) {
        statusBadge.textContent = window.getStatusTranslation ? getStatusTranslation(data.status) : data.status;
        statusBadge.className = `badge-status badge-${data.status.replace(' ', '')}`;
    }

    // Priority
    const prioritySpan = document.getElementById('track-priority');
    if (prioritySpan) {
        prioritySpan.textContent = window.getPriorityTranslation ? getPriorityTranslation(data.priority) : data.priority;
        prioritySpan.className = `text-priority-${data.priority.toLowerCase()}`;
    }

    // Worker
    const workerEl = document.getElementById('track-worker');
    if (workerEl) {
        workerEl.textContent = data.assigned_to_name || (window.t ? t('not_assigned_yet', 'Not Assigned Yet') : 'Not Assigned Yet');
    }

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

    // Multi-stage Evidence Gallery
    let hasEvidence = false;
    const beforeBox = document.getElementById('evidence-before-box');
    const beforeImg = document.getElementById('evidence-before-img');
    const beforeTime = document.getElementById('evidence-before-time');
    if (data.before_image_path) {
        if (beforeImg) beforeImg.src = `${API_BASE}${data.before_image_path}`;
        if (beforeTime) beforeTime.textContent = 'Uploaded by Worker on Site';
        if (beforeBox) beforeBox.classList.remove('hidden');
        hasEvidence = true;
    } else if (beforeBox) {
        beforeBox.classList.add('hidden');
    }

    const progBox = document.getElementById('evidence-progress-box');
    const progImg = document.getElementById('evidence-progress-img');
    const progTime = document.getElementById('evidence-progress-time');
    if (data.progress_image_path) {
        if (progImg) progImg.src = `${API_BASE}${data.progress_image_path}`;
        if (progTime) progTime.textContent = 'In Progress Work';
        if (progBox) progBox.classList.remove('hidden');
        hasEvidence = true;
    } else if (progBox) {
        progBox.classList.add('hidden');
    }

    const resBox = document.getElementById('evidence-resolved-box');
    const resImg = document.getElementById('evidence-resolved-img');
    const resTime = document.getElementById('evidence-resolved-time');
    if (data.resolved_image_path) {
        if (resImg) resImg.src = `${API_BASE}${data.resolved_image_path}`;
        if (resTime) resTime.textContent = data.completed_at ? new Date(data.completed_at).toLocaleString() : 'Work Completed';
        if (resBox) resBox.classList.remove('hidden');
        hasEvidence = true;
    } else if (resBox) {
        resBox.classList.add('hidden');
    }

    const inspBox = document.getElementById('evidence-inspection-box');
    const inspImg = document.getElementById('evidence-inspection-img');
    const inspTime = document.getElementById('evidence-inspection-time');
    const inspNotes = document.getElementById('evidence-inspection-notes');
    if (data.inspection_image_path || data.inspection_notes) {
        if (inspImg) {
            if (data.inspection_image_path) {
                inspImg.src = `${API_BASE}${data.inspection_image_path}`;
                inspImg.style.display = 'block';
            } else {
                inspImg.style.display = 'none';
            }
        }
        if (inspTime) inspTime.textContent = 'Corporator Site Verification';
        if (inspNotes) inspNotes.textContent = data.inspection_notes || '';
        if (inspBox) inspBox.classList.remove('hidden');
        hasEvidence = true;
    } else if (inspBox) {
        inspBox.classList.add('hidden');
    }

    const evidenceSection = document.getElementById('track-evidence-section');
    if (evidenceSection) {
        if (hasEvidence) evidenceSection.classList.remove('hidden');
        else evidenceSection.classList.add('hidden');
    }

    // Citizen Verification Action Box
    const verifBox = document.getElementById('track-citizen-verification-box') || document.getElementById('track-verification-box');
    const outerVerifBox = document.getElementById('track-verification-box');
    if (verifBox) {
        if (data.status === 'Completed') {
            if (outerVerifBox) outerVerifBox.classList.remove('hidden');
            verifBox.classList.remove('hidden');
            verifBox.innerHTML = `
                <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); padding: 16px; border-radius: 12px;">
                    <h4 style="color: #10b981; margin: 0 0 6px 0; font-size: 1.05rem;"><i class="fa-solid fa-bell"></i> Municipal Work Completed - Citizen Verification Needed</h4>
                    <p style="color: var(--text-secondary); font-size: 0.88rem; margin-bottom: 12px;">The municipal worker has completed the repair and submitted photographic proof above. Please inspect and confirm whether the work meets your satisfaction.</p>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button id="btn-open-verify-accept" class="btn-submit btn-emerald-submit" style="padding: 8px 16px; font-size: 0.85rem;"><i class="fa-solid fa-check"></i> Accept Resolution & Rate</button>
                        <button id="btn-open-verify-reject" class="btn-submit" style="padding: 8px 16px; font-size: 0.85rem; background: rgba(244,63,94,0.2); border-color: #f43f5e; color: #fca5a5;"><i class="fa-solid fa-rotate-left"></i> Reject Resolution & Reopen</button>
                    </div>
                </div>
            `;
            const btnAccept = document.getElementById('btn-open-verify-accept');
            const btnReject = document.getElementById('btn-open-verify-reject');
            if (btnAccept) {
                btnAccept.onclick = () => {
                    document.getElementById('verify-accept-complaint-id').value = data.complaint_id;
                    document.getElementById('verify-accept-modal').classList.remove('hidden');
                };
            }
            if (btnReject) {
                btnReject.onclick = () => {
                    document.getElementById('verify-reject-complaint-id').value = data.complaint_id;
                    document.getElementById('verify-reject-modal').classList.remove('hidden');
                };
            }
        } else if ((data.status === 'Closed' || data.status === 'Resolved') && data.citizen_rating) {
            if (outerVerifBox) outerVerifBox.classList.remove('hidden');
            verifBox.classList.remove('hidden');
            verifBox.innerHTML = `
                <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); padding: 14px; border-radius: 10px;">
                    <h4 style="color: #10b981; margin: 0 0 6px 0; font-size: 0.95rem;"><i class="fa-solid fa-check-circle"></i> Citizen Verified & Closed</h4>
                    <p style="margin: 0; font-size: 0.88rem; color: var(--text-primary);">
                        Rating: <span style="color: #f59e0b; font-size: 1.1rem;">${'★'.repeat(data.citizen_rating)}${'☆'.repeat(5 - data.citizen_rating)}</span> (${data.citizen_rating}/5)
                    </p>
                    ${data.citizen_feedback ? `<p style="margin-top: 6px; font-size: 0.84rem; color: var(--text-secondary); font-style: italic;">"${data.citizen_feedback}"</p>` : ''}
                </div>
            `;
        } else {
            verifBox.classList.add('hidden');
            if (outerVerifBox) outerVerifBox.classList.add('hidden');
        }
    }

    // Escalated flag banner
    const escBanner = document.getElementById('track-escalation-banner');
    if (data.escalation_flag || data.escalation_level > 0) {
        if (escBanner) {
            escBanner.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>Escalated:</strong> Under Tier ${data.escalation_level || 1} supervisory oversight.`;
            escBanner.classList.remove('hidden');
        }
    } else if (escBanner) {
        escBanner.classList.add('hidden');
    }

    // Reset all steps
    document.querySelectorAll('.timeline-step').forEach(step => {
        step.className = 'timeline-step';
        const sName = step.id.replace('step-', '');
        const tEl = document.getElementById(`time-${sName}`);
        if (tEl) tEl.textContent = '-';
    });

    // Populate times and status highlights
    if (data.history && Array.isArray(data.history)) {
        data.history.forEach(log => {
            const stepName = log.status.replace(' ', '');
            const element = document.getElementById(`step-${stepName}`);
            
            if (element) {
                element.classList.add('completed');
                const timeStr = window.formatDate ? formatDate(log.timestamp) : new Date(log.timestamp).toLocaleString();
                const tEl = document.getElementById(`time-${stepName}`);
                if (tEl) tEl.textContent = timeStr;
            }
        });
    }

    // Set current active status
    const activeElem = document.getElementById(`step-${data.status.replace(' ', '')}`);
    if (activeElem) {
        activeElem.classList.remove('completed');
        activeElem.classList.add('active');
    }

    // Load comments thread
    loadTrackerComments(data.complaint_id);
}

function loadDashboardData() {
    // 1. Stats Counter API
    let analyticsUrl = `${API_BASE}/api/analytics`;
    fetch(analyticsUrl)
    .then(res => res.json())
    .then(data => {
        document.getElementById('stat-total-issues').textContent = data.total;
        document.getElementById('stat-pending-issues').textContent = data.pending;
        document.getElementById('stat-resolved-issues').textContent = data.resolved;
        document.getElementById('stat-escalated-issues').textContent = data.escalated;
        const avgEl = document.getElementById('stat-avg-resolution-time');
        if (avgEl) avgEl.textContent = `${data.avg_resolution_hours || 0}h`;
        const overdueEl = document.getElementById('stat-overdue-count');
        if (overdueEl) overdueEl.textContent = data.overdue_count || 0;

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

// Render complaints in table with complete localization and full civic actions
function renderComplaintsTable(complaints) {
    const tbody = document.getElementById('complaints-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    const searchInput = document.getElementById('filter-search-authority');
    const searchVal = searchInput ? searchInput.value.toLowerCase().trim() : '';
    const catInput = document.getElementById('filter-category-authority');
    const catVal = catInput ? catInput.value : '';

    let list = complaints;
    if (searchVal) {
        list = list.filter(c => 
            c.complaint_id.toLowerCase().includes(searchVal) ||
            (c.title && c.title.toLowerCase().includes(searchVal)) ||
            (c.description && c.description.toLowerCase().includes(searchVal))
        );
    }
    if (catVal) {
        list = list.filter(c => c.category === catVal);
    }

    if (list.length === 0) {
        const emptyMsg = window.t ? t('no_matching_complaints', 'No complaints match the active filters.') : 'No complaints match the active filters.';
        tbody.innerHTML = `<tr><td colspan="9" class="empty-table-message"><i class="fa-solid fa-folder-open"></i> ${emptyMsg}</td></tr>`;
        return;
    }

    list.forEach(c => {
        const row = document.createElement('tr');
        
        const formattedDate = window.formatDate ? formatDate(c.created_at) : new Date(c.created_at).toLocaleString();
        const slaDeadline = c.deadline ? (window.formatDate ? formatDate(c.deadline) : new Date(c.deadline).toLocaleDateString()) : '-';

        const prioClass = `badge-${c.priority.toLowerCase()}`;
        const statusClass = `badge-${c.status.replace(' ', '')}`;

        const catText = window.getCategoryTranslation ? getCategoryTranslation(c.category) : c.category.replace('_', ' ');
        const prioText = window.getPriorityTranslation ? getPriorityTranslation(c.priority) : c.priority;
        const statusText = window.getStatusTranslation ? getStatusTranslation(c.status) : c.status;
        const unassignedText = window.t ? t('unassigned', 'Unassigned') : 'Unassigned';

        let navigateHtml = `<button class="btn-action-assign" onclick="triggerNavigation(${c.latitude}, ${c.longitude}, '${c.complaint_id}')" style="background: var(--accent-indigo-glow); color: var(--accent-indigo); padding: 4px 8px; font-size: 0.78rem;" title="Navigate"><i class="fa-solid fa-location-arrow"></i></button>`;

        let actionHtml = '';
        if (c.status === 'Submitted') {
            actionHtml = `
                <button class="btn-action-assign" onclick="verifyComplaint('${c.complaint_id}')" style="background: rgba(16,185,129,0.2); border: 1px solid #10b981; color: #6ee7b7; padding: 4px 8px; font-size: 0.78rem;" title="Verify Report"><i class="fa-solid fa-check"></i> Verify</button>
                <button class="btn-action-assign" onclick="openAuthorityRejectModal('${c.complaint_id}')" style="background: rgba(244,63,94,0.2); border: 1px solid #f43f5e; color: #fca5a5; padding: 4px 8px; font-size: 0.78rem;" title="Reject Report"><i class="fa-solid fa-ban"></i></button>
                <button class="btn-action-assign" onclick="openAssignmentModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.78rem;" title="Assign Worker"><i class="fa-solid fa-user-plus"></i> Assign</button>
            `;
        } else if (c.status === 'Verified') {
            actionHtml = `
                <button class="btn-action-assign" onclick="openAssignmentModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.78rem;" title="Assign Worker"><i class="fa-solid fa-user-plus"></i> Assign</button>
                <button class="btn-action-assign" onclick="openAuthorityRejectModal('${c.complaint_id}')" style="background: rgba(244,63,94,0.2); border: 1px solid #f43f5e; color: #fca5a5; padding: 4px 8px; font-size: 0.78rem;" title="Reject"><i class="fa-solid fa-ban"></i></button>
            `;
        } else if (c.status === 'Reopened') {
            actionHtml = `
                <button class="btn-action-assign" onclick="openAssignmentModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.78rem; background: rgba(245,158,11,0.2); border: 1px solid #f59e0b; color: #fcd34d;" title="Reassign Worker"><i class="fa-solid fa-rotate-left"></i> Reassign</button>
                <button class="btn-action-assign" onclick="openCommentsModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.78rem;" title="Discussion"><i class="fa-solid fa-comments"></i></button>
            `;
        } else if (c.status === 'Completed') {
            actionHtml = `
                <button class="btn-action-assign" onclick="closeComplaint('${c.complaint_id}')" style="background: rgba(16,185,129,0.2); border: 1px solid #10b981; color: #6ee7b7; padding: 4px 8px; font-size: 0.78rem;" title="Verify Completion & Close"><i class="fa-solid fa-check-double"></i> Verify & Close</button>
                <button class="btn-action-assign" onclick="openInspectionModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.78rem; background: rgba(20,184,166,0.2); border: 1px solid #14b8a6; color: #5eead4;" title="Site Inspection"><i class="fa-solid fa-clipboard-check"></i> Inspect</button>
                <button class="btn-action-assign" onclick="openCommentsModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.78rem;" title="Discussion"><i class="fa-solid fa-comments"></i></button>
            `;
        } else {
            actionHtml = `
                <button class="btn-action-assign" onclick="openInspectionModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.78rem; background: rgba(20,184,166,0.2); border: 1px solid #14b8a6; color: #5eead4;" title="Site Inspection"><i class="fa-solid fa-clipboard-check"></i> Inspect</button>
                <button class="btn-action-assign" onclick="openCommentsModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.78rem;" title="Discussion"><i class="fa-solid fa-comments"></i></button>
            `;
        }

        row.innerHTML = `
            <td><strong>${c.complaint_id}</strong></td>
            <td><span class="badge">${catText}</span></td>
            <td style="max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${c.description}">
                ${c.title ? `<strong>${c.title}</strong><br>` : ''}${c.description}
            </td>
            <td><span class="badge ${prioClass}">${prioText}</span></td>
            <td><span class="badge ${statusClass}">${statusText}</span></td>
            <td>${formattedDate}</td>
            <td>${c.overdue_flag ? `<span style="color: #f43f5e; font-weight: 700;">${slaDeadline} (Overdue)</span>` : slaDeadline}</td>
            <td>${c.assigned_to_name || `<i class="text-muted">${unassignedText}</i>`}</td>
            <td><div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">${actionHtml}${navigateHtml}</div></td>
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
    const confirmMsg = window.t ? t('confirm_close_complaint', `Are you sure you want to officially CLOSE complaint ${id}?`, { id }) : `Are you sure you want to officially CLOSE complaint ${id}?`;
    if (!confirm(confirmMsg)) return;

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

// Renders Chart.js Analytics with Localized Category Labels
function renderCharts(categoriesData, wardsData) {
    if (categoriesData) cachedCategoriesData = categoriesData;
    if (!cachedCategoriesData) return;

    const chartCanvas = document.getElementById('chart-categories');
    if (!chartCanvas) return;
    const ctxCat = chartCanvas.getContext('2d');
    if (categoriesChart) {
        categoriesChart.destroy();
    }

    const catLabels = Object.keys(cachedCategoriesData).map(k => {
        return window.getCategoryTranslation ? getCategoryTranslation(k).toUpperCase() : k.replace('_', ' ').toUpperCase();
    });
    const catVals = Object.values(cachedCategoriesData);

    categoriesChart = new Chart(ctxCat, {
        type: 'doughnut',
        data: {
            labels: catLabels,
            datasets: [{
                data: catVals,
                backgroundColor: ['#6366f1', '#14b8a6', '#f59e0b', '#f43f5e', '#10b981', '#8b5cf6'],
                borderColor: document.body.classList.contains('light-theme') ? '#ffffff' : '#0f172a',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { 
                        color: document.body.classList.contains('light-theme') ? '#0f172a' : '#f8fafc',
                        font: { 
                            family: 'Outfit, Inter, Noto Sans Kannada, Noto Sans Devanagari, Noto Sans Telugu, sans-serif',
                            size: 12,
                            weight: '600'
                        }
                    }
                }
            }
        }
    });
}

// WORKER MODULE INTERACTION
function loadWorkerTasks() {
    if (!currentUser || currentUser.role !== 'worker') return;

    let url = `${API_BASE}/api/complaints`;
    fetch(url)
    .then(res => res.json())
    .then(complaints => {
        const myTasks = complaints.filter(c => parseInt(c.assigned_to) === parseInt(currentUser.id));
        renderWorkerJobsList(myTasks);
    })
    .catch(err => console.error(err));
}

let activeWorkerFilter = 'all';

function renderWorkerJobsList(tasks) {
    activeWorkerTasks = tasks;
    const list = document.getElementById('worker-jobs-list');
    if (!list) return;
    list.innerHTML = '';

    let displayTasks = tasks;
    if (activeWorkerFilter !== 'all') {
        if (activeWorkerFilter === 'In Progress') {
            displayTasks = tasks.filter(t => t.status === 'In Progress');
        } else if (activeWorkerFilter === 'Completed') {
            displayTasks = tasks.filter(t => t.status === 'Completed' || t.status === 'Resolved' || t.status === 'Closed');
        } else {
            displayTasks = tasks.filter(t => t.status === activeWorkerFilter);
        }
    }

    if (displayTasks.length === 0) {
        const emptyMsg = window.t ? t('no_worker_tasks', 'No tasks found in this view.') : 'No tasks found in this view.';
        list.innerHTML = `<p class="empty-jobs-message"><i class="fa-solid fa-circle-check text-accent-emerald"></i> ${emptyMsg}</p>`;
        return;
    }

    const catLabel = window.t ? t('category', 'Category') : 'Category';
    const assignedLabel = window.t ? t('assigned_date_label', 'Assigned:') : 'Assigned:';
    const navText = window.t ? t('navigate', 'Navigate') : 'Navigate';

    displayTasks.forEach(task => {
        const card = document.createElement('div');
        card.className = 'job-card';
        if (activeWorkerTask && activeWorkerTask.complaint_id === task.complaint_id) {
            card.classList.add('active-job');
        }

        const formattedDate = window.formatDate ? formatDate(task.created_at, { dateStyle: 'medium' }) : new Date(task.created_at).toLocaleDateString();
        const statusClass = `badge-${task.status.replace(' ', '')}`;

        const catText = window.getCategoryTranslation ? getCategoryTranslation(task.category) : task.category;
        const prioText = window.getPriorityTranslation ? getPriorityTranslation(task.priority) : task.priority;
        const statusText = window.getStatusTranslation ? getStatusTranslation(task.status) : task.status;

        card.innerHTML = `
            <div class="job-card-header">
                <h4>${task.complaint_id}</h4>
                <div style="display: flex; gap: 4px;">
                    <span class="badge badge-${task.priority.toLowerCase()}">${prioText}</span>
                    <span class="badge ${statusClass}">${statusText}</span>
                </div>
            </div>
            <div class="job-card-desc">${task.description}</div>
            <div class="job-card-footer" style="margin-bottom: 8px;">
                <span>${catLabel}: <strong>${catText}</strong></span>
                <span>${assignedLabel} ${formattedDate}</span>
            </div>
            <button class="btn-submit-blue btn-navigate-task" onclick="event.stopPropagation(); triggerNavigation(${task.latitude}, ${task.longitude}, '${task.complaint_id}')" style="margin-top: 4px; padding: 6px 12px; font-size: 0.8rem; width: 100%; border-radius: 8px;">
                <i class="fa-solid fa-location-arrow"></i> ${navText}
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
    
    const catName = window.getCategoryTranslation ? getCategoryTranslation(task.category).toUpperCase() : task.category.replace('_', ' ').toUpperCase();
    const taskSuffix = window.t ? t('task_suffix', 'TASK') : 'TASK';
    document.getElementById('work-active-category').textContent = `${catName} ${taskSuffix}`;

    const btnInProg = document.getElementById('btn-toggle-in-progress');
    const btnResolve = document.getElementById('btn-open-resolve-modal');

    // Reset classes
    btnInProg.classList.remove('btn-emerald-submit');
    btnResolve.classList.remove('btn-emerald-submit');

    const activeSiteText = window.t ? t('active_on_site', 'Active on Site') : 'Active on Site';
    const completedText = window.t ? t('completed', 'Completed') : 'Completed';
    const markInProgText = window.t ? t('btn_mark_in_progress', 'Mark "In Progress"') : 'Mark "In Progress"';
    const resolveTaskText = window.t ? t('btn_resolve_task', 'Resolve Task') : 'Resolve Task';
    const resolvedStatusText = window.getStatusTranslation ? getStatusTranslation('Resolved') : 'Resolved';

    if (task.status === 'In Progress') {
        btnInProg.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${activeSiteText}`;
        btnInProg.classList.add('btn-emerald-submit');
        btnInProg.disabled = true;
        btnResolve.disabled = false;
        btnResolve.innerHTML = resolveTaskText;
    } else if (task.status === 'Completed' || task.status === 'Resolved' || task.status === 'Closed') {
        btnInProg.innerHTML = completedText;
        btnInProg.classList.add('btn-emerald-submit');
        btnInProg.disabled = true;
        btnResolve.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${task.status === 'Completed' ? 'Completed (Awaiting Verification)' : resolvedStatusText}`;
        btnResolve.classList.add('btn-emerald-submit');
        btnResolve.disabled = true;
    } else {
        btnInProg.innerHTML = markInProgText;
        btnInProg.disabled = false;
        btnResolve.disabled = true;
        btnResolve.innerHTML = resolveTaskText;
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

// Toast Notifications Helper with Multilingual Support
function showToast(title, message, type = 'info') {
    const toast = document.getElementById('notification-toast');
    const toastTitle = document.getElementById('toast-title');
    const toastMsg = document.getElementById('toast-message');

    // Auto-translate using dictionary if matching key exists
    const translatedTitle = window.t ? t(title, title) : title;
    const translatedMsg = window.t ? t(message, message) : message;

    toastTitle.textContent = translatedTitle;
    toastMsg.innerHTML = translatedMsg;

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
    activeRedirectedComplaints = complaints;
    const listContainer = document.getElementById('journalist-redirect-list');
    if (!listContainer) return;
    listContainer.innerHTML = '';

    if (complaints.length === 0) {
        const emptyMsg = window.t ? t('no_redirected', 'No complaints currently redirected to press feed.') : 'No complaints currently redirected to press feed.';
        listContainer.innerHTML = `<p class="empty-list-message"><i class="fa-solid fa-face-smile"></i> ${emptyMsg}</p>`;
        return;
    }

    const catLabel = window.t ? t('category', 'Category') : 'Category';
    const inspectBtnText = window.t ? t('inspect_and_write', 'Inspect & Write') : 'Inspect & Write';

    complaints.forEach(c => {
        const card = document.createElement('div');
        card.className = 'job-card';
        const catText = window.getCategoryTranslation ? getCategoryTranslation(c.category).toUpperCase() : c.category.toUpperCase();
        const prioText = window.getPriorityTranslation ? getPriorityTranslation(c.priority) : c.priority;

        card.innerHTML = `
            <div class="job-card-header">
                <h4>${c.complaint_id}</h4>
                <span class="badge badge-${c.priority.toLowerCase()}">${prioText}</span>
            </div>
            <div class="job-card-desc">${c.description}</div>
            <div style="margin-top: 10px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:0.75rem; color:var(--text-muted);">${catLabel}: <strong>${catText}</strong></span>
                <button class="btn-action-assign" onclick="inspectRedirectedComplaint('${c.complaint_id}')" style="padding: 6px 12px; font-size:0.8rem;">
                    <i class="fa-solid fa-magnifying-glass"></i> ${inspectBtnText}
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
    
    const catText = window.getCategoryTranslation ? getCategoryTranslation(complaint.category).toUpperCase() : complaint.category.toUpperCase();
    const prioText = window.getPriorityTranslation ? getPriorityTranslation(complaint.priority) : complaint.priority;
    const descLabel = window.t ? t('description', 'Description') : 'Description';
    const repLabel = window.t ? t('reported_at_label', 'Reported At:') : 'Reported At:';
    const prioLabel = window.t ? t('priority', 'Priority') : 'Priority';
    const gpsLabel = window.t ? t('gps_location_label', 'GPS Location:') : 'GPS Location:';
    const formattedDateStr = window.formatDate ? formatDate(complaint.created_at) : new Date(complaint.created_at).toLocaleString();

    summary.innerHTML = `
        <h4>${complaint.complaint_id} (${catText})</h4>
        <p><strong>${descLabel}:</strong> ${complaint.description}</p>
        <p><strong>${repLabel}</strong> ${formattedDateStr}</p>
        <p><strong>${prioLabel}:</strong> <span class="badge badge-${complaint.priority.toLowerCase()}">${prioText}</span></p>
        <p><strong>${gpsLabel}</strong> ${complaint.latitude.toFixed(5)}, ${complaint.longitude.toFixed(5)}</p>
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
    publishedArticlesList = reports;
    const feed = document.getElementById('published-articles-feed');
    if (!feed) return;
    feed.innerHTML = '';

    if (reports.length === 0) {
        const emptyMsg = window.t ? t('no_published_reports', 'No articles published to press feeds yet.') : 'No articles published to press feeds yet.';
        feed.innerHTML = `<p class="empty-list-message">${emptyMsg}</p>`;
        return;
    }

    const issueLabel = window.t ? t('issue_id_label', 'Issue ID:') : 'Issue ID:';
    const dateLabel = window.t ? t('date_label', 'Date:') : 'Date:';
    const publishedBadge = window.t ? t('badge_published', 'PUBLISHED') : 'PUBLISHED';
    const draftBadge = window.t ? t('badge_draft', 'DRAFT') : 'DRAFT';
    const publishBtnText = window.t ? t('publish_action', 'Publish') : 'Publish';

    reports.forEach(r => {
        const card = document.createElement('div');
        card.className = 'article-feed-card';
        if (!r.published) {
            card.classList.add('draft');
        }

        const dateStr = window.formatDate ? formatDate(r.created_at, { dateStyle: 'medium' }) : new Date(r.created_at).toLocaleDateString();
        const badgeState = r.published ? `<span class="badge badge-resolved">${publishedBadge}</span>` : `<span class="badge badge-low">${draftBadge}</span>`;

        card.innerHTML = `
            <div class="article-meta-row">
                <span>${issueLabel} <strong>${r.complaint_id}</strong></span>
                <span>${dateLabel} ${dateStr}</span>
            </div>
            <h3>${r.title}</h3>
            <div class="article-body-preview">${r.content}</div>
            <div class="article-actions">
                ${badgeState}
                ${!r.published ? `<button class="btn-action-assign" onclick="publishReportFromFeed(${r.id})" style="padding: 6px 12px; font-size: 0.85rem; font-weight: 700;"><i class="fa-solid fa-paper-plane"></i> ${publishBtnText}</button>` : ''}
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
    currentNavData = { startLat, startLng, destLat, destLng, complaintId };
    const list = document.getElementById('navigation-steps-list');
    if (!list) return;
    list.innerHTML = '';

    const latDelta = destLat - startLat;
    const lngDelta = destLng - startLng;

    const northKm = (latDelta * 111).toFixed(1);
    const southKm = (Math.abs(latDelta) * 111).toFixed(1);
    const eastKm = (lngDelta * 111).toFixed(1);
    const westKm = (Math.abs(lngDelta) * 111).toFixed(1);

    const steps = [];
    steps.push({
        icon: 'fa-location-dot',
        text: window.t ? t('nav_depart', 'Depart from your current location.') : 'Depart from your current location.'
    });

    if (latDelta > 0) {
        steps.push({
            icon: 'fa-arrow-up',
            text: window.t ? t('nav_head_north', 'Head north on municipal corridor for {km} km.', { km: northKm }) : `Head north on municipal corridor for ${northKm} km.`
        });
    } else {
        steps.push({
            icon: 'fa-arrow-down',
            text: window.t ? t('nav_head_south', 'Head south on municipal corridor for {km} km.', { km: southKm }) : `Head south on municipal corridor for ${southKm} km.`
        });
    }

    if (lngDelta > 0) {
        steps.push({
            icon: 'fa-arrow-right',
            text: window.t ? t('nav_turn_right', 'Turn right at main intersection, proceed east for {km} km.', { km: eastKm }) : `Turn right at main intersection, proceed east for ${eastKm} km.`
        });
    } else {
        steps.push({
            icon: 'fa-arrow-left',
            text: window.t ? t('nav_turn_left', 'Turn left at main intersection, proceed west for {km} km.', { km: westKm }) : `Turn left at main intersection, proceed west for ${westKm} km.`
        });
    }

    steps.push({
        icon: 'fa-circle-check',
        text: window.t ? t('nav_arrive', 'Arrive at complaint site {id} on the right.', { id: `<strong>${complaintId}</strong>` }) : `Arrive at complaint site <strong>${complaintId}</strong> on the right.`
    });

    const stepLabel = window.t ? t('nav_step', 'Step') : 'Step';
    steps.forEach((step, idx) => {
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.gap = '12px';
        item.style.alignItems = 'flex-start';
        item.innerHTML = `
            <div style="background: var(--accent-indigo-glow); color: var(--accent-indigo); width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; flex-shrink: 0;">
                <i class="fa-solid ${step.icon}"></i>
            </div>
            <div>
                <span style="font-weight: 700; display: block; margin-bottom: 2px;">${stepLabel} ${idx + 1}</span>
                <span>${step.text}</span>
            </div>
        `;
        list.appendChild(item);
    });
}

// CITIZEN PORTAL COMPLAINTS BOARD
function loadCitizenComplaints() {
    let url = `${API_BASE}/api/complaints`;
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
        const emptyMsg = window.t ? t('no_complaints_found', 'No reported city issues found.') : 'No reported city issues found.';
        list.innerHTML = `<p class="empty-list-message">${emptyMsg}</p>`;
        return;
    }

    const catLabel = window.t ? t('category', 'Category') : 'Category';
    const statusLabel = window.t ? t('status', 'Status') : 'Status';
    const workerLabel = window.t ? t('assigned_worker', 'Worker') : 'Worker';
    const notAssignedText = window.t ? t('not_assigned_yet', 'Not Assigned Yet') : 'Not Assigned Yet';
    const viewTimelineText = window.t ? t('view_live_timeline', 'View Live Timeline') : 'View Live Timeline';

    complaints.forEach(c => {
        const card = document.createElement('div');
        card.className = 'job-card';
        
        const prioClass = `badge-${c.priority.toLowerCase()}`;
        const statusClass = `badge-${c.status.replace(' ', '')}`;

        const catText = window.getCategoryTranslation ? getCategoryTranslation(c.category) : c.category;
        const prioText = window.getPriorityTranslation ? getPriorityTranslation(c.priority) : c.priority;
        const statusText = window.getStatusTranslation ? getStatusTranslation(c.status) : c.status;

        const titlePart = c.title ? `<strong style="color: var(--text-primary); display: block; margin-bottom: 2px;">${c.title}</strong>` : '';
        const cardDescId = `card-desc-${c.complaint_id}`;

        card.innerHTML = `
            <div class="job-card-header">
                <h4>${c.complaint_id}</h4>
                <div style="display: flex; gap: 6px; align-items: center;">
                    <button type="button" class="btn-card-translate" data-id="${c.complaint_id}" style="background: none; border: none; color: var(--accent-indigo); font-size: 0.85rem; cursor: pointer; padding: 2px 4px;" title="Translate with Hugging Face AI">
                        <i class="fa-solid fa-language"></i>
                    </button>
                    <span class="badge ${prioClass}">${prioText}</span>
                </div>
            </div>
            <div class="job-card-desc" id="${cardDescId}">${titlePart}${c.description}</div>
            <div class="job-card-footer" style="margin-bottom: 8px; flex-direction: column; align-items: flex-start; gap: 4px;">
                <span>${catLabel}: <strong>${catText.toUpperCase()}</strong></span>
                <span>${statusLabel}: <span class="badge ${statusClass}" style="margin: 0; font-size: 0.8rem; padding: 3px 8px;">${statusText}</span></span>
                <span>${workerLabel}: <strong>${c.assigned_to_name || notAssignedText}</strong></span>
            </div>
            <button class="btn-submit-blue" onclick="trackComplaint('${c.complaint_id}')" style="margin-top: 6px; padding: 10px 14px; font-size: 0.88rem; font-weight: 700; width: 100%; border-radius: 8px;">
                <i class="fa-solid fa-clock-rotate-left"></i> ${viewTimelineText}
            </button>
        `;

        const btnTrans = card.querySelector('.btn-card-translate');
        if (btnTrans) {
            let isTrans = false;
            btnTrans.addEventListener('click', async () => {
                const descEl = document.getElementById(cardDescId);
                const curLang = window.getCurrentLang ? getCurrentLang() : 'en';
                if (!isTrans) {
                    btnTrans.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
                    let transDesc = c.description;
                    if (curLang === 'en' && c.english_description) {
                        transDesc = c.english_description;
                    } else {
                        const res = await translateTextWithHF(c.description, curLang);
                        transDesc = res.translated_text || c.description;
                    }
                    if (descEl) descEl.innerHTML = `${titlePart}${transDesc}`;
                    btnTrans.innerHTML = `<i class="fa-solid fa-rotate-left"></i>`;
                    btnTrans.style.color = '#10b981';
                    isTrans = true;
                } else {
                    if (descEl) descEl.innerHTML = `${titlePart}${c.description}`;
                    btnTrans.innerHTML = `<i class="fa-solid fa-language"></i>`;
                    btnTrans.style.color = 'var(--accent-indigo)';
                    isTrans = false;
                }
            });
        }
        list.appendChild(card);
    });
}

// ==========================================
// ENHANCED CIVIC SYSTEM MANAGEMENT FEATURES
// ==========================================

let activeCitizenFilter = 'all';
let cachedNotifications = [];

function initEnhancedCivicFeatures() {
    // 1. Notifications Center
    const btnNotif = document.getElementById('btn-header-notif') || document.getElementById('btn-open-notifications');
    const notifModal = document.getElementById('notification-modal');
    const btnCloseNotif = document.getElementById('btn-close-notification-modal');
    const btnMarkAllRead = document.getElementById('btn-mark-all-notifications-read');

    if (btnNotif) {
        btnNotif.addEventListener('click', () => {
            if (notifModal) {
                notifModal.classList.remove('hidden');
                pollNotifications(true);
            }
        });
    }
    if (btnCloseNotif && notifModal) {
        btnCloseNotif.addEventListener('click', () => notifModal.classList.add('hidden'));
    }
    if (btnMarkAllRead) {
        btnMarkAllRead.addEventListener('click', () => {
            fetch(`${API_BASE}/api/notifications/read-all`, { method: 'PUT' })
            .then(res => res.json())
            .then(() => {
                showToast('Notifications Cleared', 'Marked all notifications as read.', 'info');
                pollNotifications(true);
            })
            .catch(err => console.error(err));
        });
    }

    // 2. User Profile Modal
    const btnProfile = document.getElementById('btn-header-profile') || document.getElementById('btn-open-profile-modal');
    const profileModal = document.getElementById('profile-modal');
    const btnCloseProfile = document.getElementById('btn-close-profile-modal');
    const profileForm = document.getElementById('profile-form');

    if (btnProfile && profileModal) {
        btnProfile.addEventListener('click', () => {
            profileModal.classList.remove('hidden');
            loadUserProfile();
        });
    }
    if (btnCloseProfile && profileModal) {
        btnCloseProfile.addEventListener('click', () => profileModal.classList.add('hidden'));
    }
    if (profileForm) {
        profileForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const name = document.getElementById('profile-name-input').value.trim();
            const phone = document.getElementById('profile-phone-input').value.trim();
            const password = document.getElementById('profile-password-input').value;

            const payload = { name, phone };
            if (password) payload.password = password;

            fetch(`${API_BASE}/api/users/profile`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(updated => {
                if (updated.error) throw new Error(updated.error);
                showToast('Profile Updated', 'Your profile details have been saved.', 'success');
                if (currentUser) {
                    currentUser.name = updated.name;
                    currentUser.contact = updated.contact;
                    localStorage.setItem('smartcivic_session', JSON.stringify(currentUser));
                    updateUserBanner();
                }
                if (profileModal) profileModal.classList.add('hidden');
            })
            .catch(err => showToast('Error', err.message, 'error'));
        });
    }

    // 3. Citizen Verification Modals & Star Rating
    initStarRatingPicker();

    const verifyAcceptModal = document.getElementById('verify-accept-modal');
    const btnCloseVerifyAccept = document.getElementById('btn-close-verify-accept-modal');
    const verifyAcceptForm = document.getElementById('verify-accept-form');

    if (btnCloseVerifyAccept && verifyAcceptModal) {
        btnCloseVerifyAccept.addEventListener('click', () => verifyAcceptModal.classList.add('hidden'));
    }
    if (verifyAcceptForm) {
        verifyAcceptForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const compId = document.getElementById('verify-accept-complaint-id').value;
            const rating = parseInt(document.getElementById('verify-rating-value').value) || 5;
            const feedback = document.getElementById('verify-feedback-input').value.trim();

            fetch(`${API_BASE}/api/complaints/${compId}/verify-resolution`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'accept', rating, feedback })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                showToast('Resolution Accepted', `Issue ${compId} successfully verified and closed!`, 'success');
                if (verifyAcceptModal) verifyAcceptModal.classList.add('hidden');
                trackComplaint(compId);
                loadCitizenComplaints();
                loadCitizenMyComplaints();
            })
            .catch(err => showToast('Verification Error', err.message, 'error'));
        });
    }

    const verifyRejectModal = document.getElementById('verify-reject-modal');
    const btnCloseVerifyReject = document.getElementById('btn-close-verify-reject-modal');
    const verifyRejectForm = document.getElementById('verify-reject-form');

    if (btnCloseVerifyReject && verifyRejectModal) {
        btnCloseVerifyReject.addEventListener('click', () => verifyRejectModal.classList.add('hidden'));
    }
    if (verifyRejectForm) {
        verifyRejectForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const compId = document.getElementById('verify-reject-complaint-id').value;
            const reason = document.getElementById('reopen-reason-input').value.trim();

            if (!reason) {
                showToast('Reason Required', 'Please provide a clear reason for rejecting the resolution.', 'warning');
                return;
            }

            fetch(`${API_BASE}/api/complaints/${compId}/verify-resolution`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'reject', reason })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                showToast('Issue Reopened', `Issue ${compId} has been reopened and escalated for rectification.`, 'warning');
                if (verifyRejectModal) verifyRejectModal.classList.add('hidden');
                document.getElementById('reopen-reason-input').value = '';
                trackComplaint(compId);
                loadCitizenComplaints();
                loadCitizenMyComplaints();
            })
            .catch(err => showToast('Reopen Error', err.message, 'error'));
        });
    }

    // 4. Authority Rejection Modal
    const authRejectModal = document.getElementById('authority-reject-modal');
    const btnCloseAuthReject = document.getElementById('btn-close-authority-reject-modal');
    const authRejectForm = document.getElementById('authority-reject-form');

    if (btnCloseAuthReject && authRejectModal) {
        btnCloseAuthReject.addEventListener('click', () => authRejectModal.classList.add('hidden'));
    }
    if (authRejectForm) {
        authRejectForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const compId = document.getElementById('authority-reject-complaint-id').value;
            const reason = document.getElementById('authority-reject-reason-input').value.trim();

            if (!reason) {
                showToast('Reason Required', 'Please provide a formal rejection reason.', 'warning');
                return;
            }

            fetch(`${API_BASE}/api/complaints/${compId}/reject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                showToast('Complaint Rejected', `Complaint ${compId} rejected. Citizen notified.`, 'info');
                if (authRejectModal) authRejectModal.classList.add('hidden');
                document.getElementById('authority-reject-reason-input').value = '';
                loadDashboardData();
            })
            .catch(err => showToast('Error', err.message, 'error'));
        });
    }

    // 5. Worker Evidence Photo Upload Modal
    const workerPhotoModal = document.getElementById('worker-photo-modal');
    const btnCloseWorkerPhoto = document.getElementById('btn-close-worker-photo-modal');
    const btnOpenWorkerPhoto = document.getElementById('btn-open-worker-photo');
    const workerPhotoForm = document.getElementById('worker-photo-form');

    window.openWorkerPhotoModal = function(id) {
        const compId = id || (activeWorkerTask ? activeWorkerTask.complaint_id : '');
        if (!compId) {
            showToast('Select Task', 'Select an assigned task first.', 'warning');
            return;
        }
        document.getElementById('worker-photo-complaint-id').value = compId;
        const modal = document.getElementById('worker-photo-modal');
        if (modal) modal.classList.remove('hidden');
    };

    if (btnOpenWorkerPhoto && workerPhotoModal) {
        btnOpenWorkerPhoto.addEventListener('click', () => {
            window.openWorkerPhotoModal();
        });
    }
    if (btnCloseWorkerPhoto && workerPhotoModal) {
        btnCloseWorkerPhoto.addEventListener('click', () => workerPhotoModal.classList.add('hidden'));
    }
    if (workerPhotoForm) {
        workerPhotoForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const compId = document.getElementById('worker-photo-complaint-id').value;
            const stage = document.getElementById('worker-photo-stage').value;
            const file = document.getElementById('worker-photo-file').files[0];
            const caption = document.getElementById('worker-photo-caption').value.trim();

            if (!file) {
                showToast('Photo Required', 'Please choose a photo file.', 'warning');
                return;
            }

            const fd = new FormData();
            fd.append('stage', stage);
            fd.append('image', file);
            if (caption) fd.append('caption', caption);

            fetch(`${API_BASE}/api/complaints/${compId}/evidence`, {
                method: 'POST',
                body: fd
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                showToast('Evidence Uploaded', `${stage.toUpperCase()} photo attached to ${compId}.`, 'success');
                if (workerPhotoModal) workerPhotoModal.classList.add('hidden');
                document.getElementById('worker-photo-file').value = '';
                document.getElementById('worker-photo-caption').value = '';
                loadWorkerTasks();
            })
            .catch(err => showToast('Upload Error', err.message, 'error'));
        });
    }

    // 6. Corporator Site Inspection Modal
    const inspectionModal = document.getElementById('inspection-modal');
    const btnCloseInspection = document.getElementById('btn-close-inspection-modal');
    const inspectionForm = document.getElementById('inspection-form');

    if (btnCloseInspection && inspectionModal) {
        btnCloseInspection.addEventListener('click', () => inspectionModal.classList.add('hidden'));
    }
    if (inspectionForm) {
        inspectionForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const compId = document.getElementById('inspection-complaint-id').value;
            const notes = document.getElementById('inspection-notes-input').value.trim();
            const file = document.getElementById('inspection-image-file').files[0];

            if (!notes) {
                showToast('Notes Required', 'Please enter your inspection observations.', 'warning');
                return;
            }

            const fd = new FormData();
            fd.append('inspection_notes', notes);
            if (file) fd.append('inspection_image', file);

            fetch(`${API_BASE}/api/complaints/${compId}/inspection`, {
                method: 'POST',
                body: fd
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                showToast('Inspection Recorded', `Site visit report saved for ${compId}.`, 'success');
                if (inspectionModal) inspectionModal.classList.add('hidden');
                document.getElementById('inspection-notes-input').value = '';
                document.getElementById('inspection-image-file').value = '';
                loadDashboardData();
            })
            .catch(err => showToast('Inspection Error', err.message, 'error'));
        });
    }

    // 7. Higher Authority Reassign Modal
    const reassignModal = document.getElementById('reassign-modal');
    const btnCloseReassign = document.getElementById('btn-close-reassign-modal');
    const reassignForm = document.getElementById('reassign-form');

    if (btnCloseReassign && reassignModal) {
        btnCloseReassign.addEventListener('click', () => reassignModal.classList.add('hidden'));
    }
    if (reassignForm) {
        reassignForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const compId = document.getElementById('reassign-complaint-id').value;
            const ward = document.getElementById('reassign-ward-select').value;
            const workerId = document.getElementById('reassign-worker-select').value;
            const reason = document.getElementById('reassign-reason-input').value.trim();

            fetch(`${API_BASE}/api/complaints/${compId}/reassign`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ward, assigned_to: workerId, reason })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                showToast('Reassigned', `Issue ${compId} successfully reassigned.`, 'success');
                if (reassignModal) reassignModal.classList.add('hidden');
                loadHigherAuthorityData();
            })
            .catch(err => showToast('Reassign Error', err.message, 'error'));
        });
    }

    // 8. Higher Authority Directive Notice Modal
    const adminNoticeModal = document.getElementById('admin-notice-modal');
    const btnCloseAdminNotice = document.getElementById('btn-close-admin-notice-modal');
    const adminNoticeForm = document.getElementById('admin-notice-form');

    if (btnCloseAdminNotice && adminNoticeModal) {
        btnCloseAdminNotice.addEventListener('click', () => adminNoticeModal.classList.add('hidden'));
    }
    if (adminNoticeForm) {
        adminNoticeForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const compId = document.getElementById('admin-notice-complaint-id').value;
            const notice_type = document.getElementById('admin-notice-type').value;
            const message = document.getElementById('admin-notice-message').value.trim();

            if (!message) {
                showToast('Message Required', 'Please enter the directive notice message.', 'warning');
                return;
            }

            fetch(`${API_BASE}/api/complaints/${compId}/administrative-notice`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ notice_type, message })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                showToast('Directive Issued', `Notice issued for ${compId}.`, 'success');
                if (adminNoticeModal) adminNoticeModal.classList.add('hidden');
                document.getElementById('admin-notice-message').value = '';
                loadHigherAuthorityData();
            })
            .catch(err => showToast('Notice Error', err.message, 'error'));
        });
    }

    // 9. Discussion / Comments Modal
    const commentsModal = document.getElementById('comments-modal');
    const btnCloseComments = document.getElementById('btn-close-comments-modal');
    const modalCommentForm = document.getElementById('modal-new-comment-form');

    if (btnCloseComments && commentsModal) {
        btnCloseComments.addEventListener('click', () => commentsModal.classList.add('hidden'));
    }
    if (modalCommentForm) {
        modalCommentForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const compId = document.getElementById('comments-modal-complaint-id').textContent;
            const input = document.getElementById('modal-new-comment-input');
            const comment = input.value.trim();
            if (!comment) return;

            postComment(compId, comment, () => {
                input.value = '';
                openCommentsModal(compId);
            });
        });
    }

    // 10. Tracker In-Card Discussion Form
    const trackerCommentForm = document.getElementById('form-tracker-add-comment');
    if (trackerCommentForm) {
        trackerCommentForm.addEventListener('submit', (e) => {
            e.preventDefault();
            if (!cachedTrackData) return;
            const input = document.getElementById('tracker-comment-input') || document.getElementById('input-tracker-comment');
            if (!input) return;
            const comment = input.value.trim();
            if (!comment) return;

            postComment(cachedTrackData.complaint_id, comment, () => {
                input.value = '';
                loadTrackerComments(cachedTrackData.complaint_id);
            });
        });
    }

    // 11. CSV Export Handlers
    const btnExportCsv = document.getElementById('btn-export-csv');
    if (btnExportCsv) {
        btnExportCsv.addEventListener('click', () => {
            window.location.href = `${API_BASE}/api/reports/export`;
        });
    }
    const btnHaExportCsv = document.getElementById('btn-ha-export-csv');
    if (btnHaExportCsv) {
        btnHaExportCsv.addEventListener('click', () => {
            window.location.href = `${API_BASE}/api/reports/export`;
        });
    }

    // 12. Search & Filter Listeners for Corporator Table
    const filterSearchAuth = document.getElementById('filter-search-authority');
    if (filterSearchAuth) {
        filterSearchAuth.addEventListener('input', () => {
            if (activeComplaintsList) renderComplaintsTable(activeComplaintsList);
        });
    }
    const filterCatAuth = document.getElementById('filter-category-authority');
    if (filterCatAuth) {
        filterCatAuth.addEventListener('change', () => {
            if (activeComplaintsList) renderComplaintsTable(activeComplaintsList);
        });
    }

    // 13. Higher Authority Filters & Refresh
    const haFilterWard = document.getElementById('ha-filter-ward');
    if (haFilterWard) haFilterWard.addEventListener('change', loadHigherAuthorityData);
    const haFilterStatus = document.getElementById('ha-filter-status');
    if (haFilterStatus) haFilterStatus.addEventListener('change', loadHigherAuthorityData);
    const btnRefreshHa = document.getElementById('btn-refresh-ha-dashboard');
    if (btnRefreshHa) btnRefreshHa.addEventListener('click', loadHigherAuthorityData);

    // 14. Citizen Filter Pills
    document.querySelectorAll('.citizen-filter-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('.citizen-filter-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            activeCitizenFilter = pill.getAttribute('data-filter') || 'all';
            loadCitizenMyComplaints();
        });
    });

    // 15. Citizen "My Submitted Issues" Refresh Button
    const btnRefreshMyComplaints = document.getElementById('btn-refresh-my-complaints');
    if (btnRefreshMyComplaints) {
        btnRefreshMyComplaints.addEventListener('click', () => {
            loadCitizenMyComplaints();
            showToast('Refreshed', 'Updated your personal submitted issues list.', 'info');
        });
    }

    // 16. Worker Tasks Filter Chips
    document.querySelectorAll('.worker-filter-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.worker-filter-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            activeWorkerFilter = chip.getAttribute('data-worker-filter') || 'all';
            if (activeWorkerTasks && activeWorkerTasks.length > 0) {
                renderWorkerJobsList(activeWorkerTasks);
            }
        });
    });

    // 17. Universal Modal Backdrop & Escape Key Dismissal
    initModalBackdropHandling();
}

// Interactive Star Rating Picker
function initStarRatingPicker() {
    const starContainer = document.getElementById('star-rating-picker');
    const ratingInput = document.getElementById('verify-rating-value');
    if (!starContainer || !ratingInput) return;

    const stars = starContainer.querySelectorAll('.star-item');
    stars.forEach(star => {
        star.addEventListener('click', () => {
            const val = parseInt(star.getAttribute('data-value')) || 5;
            ratingInput.value = val;
            stars.forEach(s => {
                const sVal = parseInt(s.getAttribute('data-value')) || 1;
                if (sVal <= val) {
                    s.style.color = '#f59e0b';
                } else {
                    s.style.color = 'var(--text-muted)';
                }
            });
        });
    });
}

// Universal Modal Backdrop Click & Escape Key Dismissal
function initModalBackdropHandling() {
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.add('hidden');
            }
        });
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const openModals = Array.from(document.querySelectorAll('.modal-overlay:not(.hidden)'));
            if (openModals.length > 0) {
                const topModal = openModals[openModals.length - 1];
                topModal.classList.add('hidden');
            }
        }
    });
}

// In-App Notifications Polling & Rendering
function pollNotifications(forceModalRender = false) {
    if (!currentUser) return;
    fetch(`${API_BASE}/api/notifications`)
    .then(res => res.json())
    .then(notifications => {
        cachedNotifications = notifications;
        const unreadCount = notifications.filter(n => !n.is_read).length;
        const badge = document.getElementById('header-notif-badge');
        if (badge) {
            badge.textContent = unreadCount;
            if (unreadCount > 0) {
                badge.classList.remove('hidden');
                badge.style.display = 'inline-block';
            } else {
                badge.classList.add('hidden');
                badge.style.display = 'none';
            }
        }
        if (forceModalRender || !document.getElementById('notification-modal').classList.contains('hidden')) {
            renderNotificationsList(notifications);
        }
    })
    .catch(err => console.error(err));
}

function renderNotificationsList(notifications) {
    const list = document.getElementById('notifications-list');
    if (!list) return;
    list.innerHTML = '';

    if (!notifications || notifications.length === 0) {
        list.innerHTML = '<p class="empty-table-message" style="padding: 24px 0;"><i class="fa-solid fa-bell-slash"></i> No notifications yet.</p>';
        return;
    }

    notifications.forEach(n => {
        const item = document.createElement('div');
        item.style.padding = '12px 14px';
        item.style.borderRadius = '8px';
        item.style.border = '1px solid var(--panel-border)';
        item.style.background = n.is_read ? 'rgba(255,255,255,0.02)' : 'rgba(99,102,241,0.12)';
        item.style.cursor = 'pointer';
        item.style.display = 'flex';
        item.style.flexDirection = 'column';
        item.style.gap = '4px';

        const timeStr = window.formatDate ? formatDate(n.created_at) : new Date(n.created_at).toLocaleString();

        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong style="font-size: 0.88rem; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
                    ${!n.is_read ? '<span style="width: 8px; height: 8px; border-radius: 50%; background: #38bdf8; display: inline-block;"></span>' : ''}
                    ${n.title || 'System Notification'}
                </strong>
                <span style="font-size: 0.75rem; color: var(--text-muted);">${timeStr}</span>
            </div>
            <p style="margin: 0; font-size: 0.82rem; color: var(--text-secondary); line-height: 1.4;">${n.message}</p>
        `;

        item.addEventListener('click', () => {
            if (!n.is_read) {
                fetch(`${API_BASE}/api/notifications/${n.id}/read`, { method: 'PUT' })
                .then(() => pollNotifications(true))
                .catch(err => console.error(err));
            }
            if (n.complaint_id) {
                document.getElementById('notification-modal').classList.add('hidden');
                switchTab('citizen-portal');
                trackComplaint(n.complaint_id);
            }
        });

        list.appendChild(item);
    });
}

// User Profile View / Edit
function loadUserProfile() {
    fetch(`${API_BASE}/api/users/profile`)
    .then(res => res.json())
    .then(user => {
        const initial = (user.name || 'U').charAt(0).toUpperCase();
        document.getElementById('profile-avatar-initials').textContent = initial;
        document.getElementById('profile-display-name').textContent = user.name;
        document.getElementById('profile-display-role').textContent = `Role: ${user.role.toUpperCase()}`;
        document.getElementById('profile-name-input').value = user.name;
        document.getElementById('profile-email-input').value = user.gmail;
        document.getElementById('profile-phone-input').value = user.contact || '';
        document.getElementById('profile-ward-input').value = user.ward || 'Central Ward 1';
        document.getElementById('profile-password-input').value = '';
    })
    .catch(err => console.error(err));
}

// Citizen "My Submitted Complaints" Box
function loadCitizenMyComplaints() {
    const box = document.getElementById('citizen-my-complaints-box');
    const list = document.getElementById('citizen-my-complaints-list');
    if (!box || !list) return;

    if (!currentUser || currentUser.role !== 'citizen') {
        box.classList.add('hidden');
        return;
    }
    box.classList.remove('hidden');

    fetch(`${API_BASE}/api/complaints`)
    .then(res => res.json())
    .then(complaints => {
        cachedMyComplaints = complaints;
        renderCitizenMyComplaintsList(complaints);
    })
    .catch(err => console.error(err));
}

function renderCitizenMyComplaintsList(complaints) {
    const list = document.getElementById('citizen-my-complaints-list');
    if (!list) return;

    if (!complaints) complaints = cachedMyComplaints || [];

    // Filter by user's citizen_id or gmail
    let myIssues = complaints.filter(c => 
        (c.citizen_id && parseInt(c.citizen_id) === parseInt(currentUser.id)) ||
        (c.gmail && currentUser.gmail && c.gmail.toLowerCase() === currentUser.gmail.toLowerCase())
    );

    if (activeCitizenFilter !== 'all') {
        if (activeCitizenFilter === 'Active') {
            myIssues = myIssues.filter(c => c.status === 'Assigned' || c.status === 'In Progress' || c.status === 'Verified');
        } else {
            myIssues = myIssues.filter(c => c.status === activeCitizenFilter);
        }
    }

    list.innerHTML = '';
    if (myIssues.length === 0) {
        const filterName = window.t ? t(`status_${activeCitizenFilter.toLowerCase()}`, activeCitizenFilter) : activeCitizenFilter;
        list.innerHTML = `<p class="empty-table-message" style="padding: 18px 0;"><i class="fa-solid fa-folder-open"></i> ${window.t ? t('no_complaints_found', `No complaints in "${filterName}" category.`) : `No complaints in "${activeCitizenFilter}" category.`}</p>`;
        return;
    }

    const trackLabel = window.t ? t('view_live_timeline', 'Track') : 'Track';

    myIssues.forEach(c => {
        const card = document.createElement('div');
        card.className = 'job-card';
        card.style.padding = '12px 14px';

        const prioClass = `badge-${c.priority.toLowerCase()}`;
        const statusClass = `badge-${c.status.replace(' ', '')}`;
        const catText = window.getCategoryTranslation ? getCategoryTranslation(c.category) : c.category.replace('_', ' ');
        const prioText = window.getPriorityTranslation ? getPriorityTranslation(c.priority) : c.priority;
        const statusText = window.getStatusTranslation ? getStatusTranslation(c.status) : c.status;

        card.innerHTML = `
            <div class="job-card-header" style="margin-bottom: 6px;">
                <strong style="color: var(--text-primary); font-size: 0.92rem;">${c.complaint_id}</strong>
                <div style="display: flex; gap: 4px;">
                    <span class="badge ${prioClass}">${prioText}</span>
                    <span class="badge ${statusClass}">${statusText}</span>
                </div>
            </div>
            <div style="font-size: 0.84rem; color: var(--text-secondary); margin-bottom: 8px;">
                ${c.title ? `<strong>${c.title}</strong> — ` : ''}${c.description}
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 0.78rem; color: var(--text-muted);">${catText}</span>
                <button class="btn-submit-blue" onclick="trackComplaint('${c.complaint_id}')" style="margin: 0; padding: 4px 12px; font-size: 0.78rem; border-radius: 6px;">
                    <i class="fa-solid fa-clock-rotate-left"></i> ${trackLabel}
                </button>
            </div>
        `;
        list.appendChild(card);
    });
}

// Corporator Actions: Verify, Reject, Inspect
window.verifyComplaint = function(id) {
    fetch(`${API_BASE}/api/complaints/${id}/verify`, { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        if (data.error) throw new Error(data.error);
        showToast('Complaint Verified', `Report ${id} verified. Ready for worker dispatch.`, 'success');
        loadDashboardData();
    })
    .catch(err => showToast('Error', err.message, 'error'));
};

window.openAuthorityRejectModal = function(id) {
    document.getElementById('authority-reject-complaint-id').value = id;
    document.getElementById('authority-reject-modal').classList.remove('hidden');
};

window.openInspectionModal = function(id) {
    document.getElementById('inspection-complaint-id').value = id;
    document.getElementById('inspection-modal').classList.remove('hidden');
};

// Comments & Discussion Thread
window.openCommentsModal = function(id) {
    document.getElementById('comments-modal-complaint-id').textContent = id;
    document.getElementById('comments-modal').classList.remove('hidden');

    const list = document.getElementById('modal-comments-list');
    list.innerHTML = '<p class="empty-table-message"><i class="fa-solid fa-spinner fa-spin"></i> Loading discussion...</p>';

    fetch(`${API_BASE}/api/complaints/${id}/comments`)
    .then(res => res.json())
    .then(comments => {
        renderCommentsList(comments, list);
    })
    .catch(err => console.error(err));
};

function loadTrackerComments(id) {
    const list = document.getElementById('tracker-comments-list');
    if (!list) return;
    fetch(`${API_BASE}/api/complaints/${id}/comments`)
    .then(res => res.json())
    .then(comments => {
        renderCommentsList(comments, list);
    })
    .catch(err => console.error(err));
}

function renderCommentsList(comments, container) {
    if (!container) return;
    container.innerHTML = '';

    if (!comments || comments.length === 0) {
        container.innerHTML = '<p class="empty-table-message" style="padding: 12px 0;"><i class="fa-solid fa-comment-slash"></i> No official notes or comments posted yet.</p>';
        return;
    }

    comments.forEach(c => {
        const item = document.createElement('div');
        item.style.padding = '8px 12px';
        item.style.borderRadius = '8px';
        item.style.background = 'rgba(255,255,255,0.03)';
        item.style.border = '1px solid var(--panel-border)';
        item.style.display = 'flex';
        item.style.flexDirection = 'column';
        item.style.gap = '2px';

        const timeStr = window.formatDate ? formatDate(c.created_at) : new Date(c.created_at).toLocaleString();
        const roleLabel = window.getRoleTranslation ? getRoleTranslation(c.user_role) : c.user_role;
        const roleBadge = `<span class="badge" style="font-size: 0.7rem; padding: 2px 6px; text-transform: uppercase;">${roleLabel}</span>`;

        const commentId = `comment-text-${c.id || Math.random().toString(36).substr(2, 9)}`;
        const translateBtnText = window.t ? t('btn_hf_translate', 'Translate (HF AI)') : 'Translate (HF AI)';
        const originalBtnText = window.t ? t('btn_show_original', 'Show Original') : 'Original';

        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 700; font-size: 0.85rem; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
                    ${c.user_name} ${roleBadge}
                </span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <button type="button" class="btn-comment-translate" style="background: none; border: none; color: var(--accent-indigo); font-size: 0.74rem; cursor: pointer; padding: 2px 4px; display: inline-flex; align-items: center; gap: 4px;" title="Translate with Hugging Face AI">
                        <i class="fa-solid fa-language"></i> <span>${translateBtnText}</span>
                    </button>
                    <span style="font-size: 0.72rem; color: var(--text-muted);">${timeStr}</span>
                </div>
            </div>
            <p id="${commentId}" style="margin: 0; font-size: 0.84rem; color: var(--text-secondary);">${c.comment}</p>
        `;

        const btnTranslate = item.querySelector('.btn-comment-translate');
        let isCommentTranslated = false;
        const origText = c.comment;

        if (btnTranslate) {
            btnTranslate.addEventListener('click', async () => {
                const textEl = document.getElementById(commentId);
                const currentLang = window.getCurrentLang ? getCurrentLang() : 'en';

                if (!isCommentTranslated) {
                    btnTranslate.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
                    const res = await translateTextWithHF(origText, currentLang);
                    if (textEl) textEl.textContent = res.translated_text || origText;
                    btnTranslate.innerHTML = `<i class="fa-solid fa-rotate-left"></i> <span>${originalBtnText}</span>`;
                    btnTranslate.style.color = '#10b981';
                    isCommentTranslated = true;
                } else {
                    if (textEl) textEl.textContent = origText;
                    btnTranslate.innerHTML = `<i class="fa-solid fa-language"></i> <span>${translateBtnText}</span>`;
                    btnTranslate.style.color = 'var(--accent-indigo)';
                    isCommentTranslated = false;
                }
            });
        }

        container.appendChild(item);
    });
}

function postComment(complaintId, comment, onSuccess) {
    fetch(`${API_BASE}/api/complaints/${complaintId}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) throw new Error(data.error);
        showToast('Comment Posted', 'Your note has been added to the discussion.', 'success');
        if (onSuccess) onSuccess();
    })
    .catch(err => showToast('Error', err.message, 'error'));
}

// Corporator Performance Leaderboard
function loadCorporatorPerformance() {
    const tbody = document.getElementById('authority-performance-table-body');
    if (!tbody) return;

    fetch(`${API_BASE}/api/corporator/performance`)
    .then(res => res.json())
    .then(data => {
        tbody.innerHTML = '';
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-table-message">No ward data available.</td></tr>';
            return;
        }

        data.forEach(item => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${item.ward.toUpperCase()}</strong></td>
                <td>${item.total_complaints}</td>
                <td><span style="color: #10b981; font-weight: 700;">${item.resolved_complaints}</span></td>
                <td><span class="badge badge-emerald">${item.resolution_rate}%</span></td>
                <td>${item.avg_resolution_hours}h</td>
                <td><span style="color: #f59e0b; font-weight: 700;">${item.citizen_rating} ★</span></td>
                <td><span style="color: ${item.overdue_complaints > 0 ? '#f43f5e' : 'var(--text-muted)'}; font-weight: 700;">${item.overdue_complaints}</span></td>
            `;
            tbody.appendChild(row);
        });
    })
    .catch(err => console.error(err));
}

// HIGHER AUTHORITY COMMAND CENTER MODULE
function loadHigherAuthorityData() {
    // 1. Citywide KPIs
    fetch(`${API_BASE}/api/analytics`)
    .then(res => res.json())
    .then(data => {
        const haTotal = document.getElementById('stat-ha-total');
        if (haTotal) haTotal.textContent = data.total;
        const haEsc = document.getElementById('stat-ha-escalated');
        if (haEsc) haEsc.textContent = data.escalated;
        const haOver = document.getElementById('stat-ha-overdue');
        if (haOver) haOver.textContent = data.overdue_count || 0;
        const haRate = document.getElementById('stat-ha-res-rate');
        if (haRate) haRate.textContent = `${data.resolution_rate || 0}%`;
    })
    .catch(err => console.error(err));

    // 2. Citywide Complaints Registry
    const wardFilter = document.getElementById('ha-filter-ward') ? document.getElementById('ha-filter-ward').value : '';
    const statusFilter = document.getElementById('ha-filter-status') ? document.getElementById('ha-filter-status').value : '';

    let url = `${API_BASE}/api/complaints`;
    const params = [];
    if (wardFilter) params.push(`ward=${wardFilter}`);
    if (statusFilter) params.push(`status=${statusFilter}`);
    if (params.length > 0) url += `?${params.join('&')}`;

    fetch(url)
    .then(res => res.json())
    .then(complaints => {
        cachedHAComplaints = complaints;
        renderHigherAuthorityTable(complaints);
    })
    .catch(err => console.error(err));

    // 3. Multi-ward Leaderboard
    const haLbBody = document.getElementById('ha-leaderboard-table-body');
    if (haLbBody) {
        fetch(`${API_BASE}/api/corporator/performance`)
        .then(res => res.json())
        .then(leaderboard => {
            cachedHALeaderboard = leaderboard;
            haLbBody.innerHTML = '';
            if (!leaderboard || leaderboard.length === 0) {
                haLbBody.innerHTML = '<tr><td colspan="9" class="empty-table-message">No leaderboard data found.</td></tr>';
                return;
            }
            leaderboard.forEach((lb, idx) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>#${idx + 1}</strong></td>
                    <td><span class="badge">${lb.ward.toUpperCase()}</span></td>
                    <td>${lb.corporator_name}</td>
                    <td>${lb.total_complaints}</td>
                    <td><strong style="color: #10b981;">${lb.resolved_complaints}</strong></td>
                    <td><span class="badge badge-emerald">${lb.resolution_rate}%</span></td>
                    <td>${lb.avg_resolution_hours}h</td>
                    <td><span style="color: #f59e0b; font-weight: 700;">${lb.citizen_rating} ★</span></td>
                    <td><strong style="color: ${lb.overdue_complaints > 0 ? '#f43f5e' : 'var(--text-muted)'};">${lb.overdue_complaints}</strong></td>
                `;
                haLbBody.appendChild(tr);
            });
        })
        .catch(err => console.error(err));
    }

    // 4. System Audit Trail Live Log
    const haAuditBody = document.getElementById('ha-audit-table-body');
    if (haAuditBody) {
        fetch(`${API_BASE}/api/audit-logs`)
        .then(res => res.json())
        .then(logs => {
            cachedHALogs = logs;
            haAuditBody.innerHTML = '';
            if (!logs || logs.length === 0) {
                haAuditBody.innerHTML = '<tr><td colspan="6" class="empty-table-message">No audit log entries recorded.</td></tr>';
                return;
            }
            logs.slice(0, 50).forEach(entry => {
                const tr = document.createElement('tr');
                const timeStr = window.formatDate ? formatDate(entry.created_at) : new Date(entry.created_at).toLocaleString();
                const roleLabel = window.getRoleTranslation ? getRoleTranslation(entry.user_role) : entry.user_role;
                tr.innerHTML = `
                    <td style="font-size: 0.8rem; color: var(--text-muted);">${timeStr}</td>
                    <td><span class="badge" style="font-family: monospace; font-size: 0.75rem;">${entry.action}</span></td>
                    <td><strong>${entry.user_name}</strong></td>
                    <td><span class="badge">${roleLabel}</span></td>
                    <td>${entry.complaint_id || '-'}</td>
                    <td style="font-size: 0.82rem; color: var(--text-secondary);">${entry.details || ''}</td>
                `;
                haAuditBody.appendChild(tr);
            });
        })
        .catch(err => console.error(err));
    }
}

function renderHigherAuthorityTable(complaints) {
    const tbody = document.getElementById('ha-complaints-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!complaints) complaints = cachedHAComplaints || [];

    if (complaints.length === 0) {
        const emptyMsg = window.t ? t('no_complaints_found', 'No complaints matching oversight filters.') : 'No complaints matching oversight filters.';
        tbody.innerHTML = `<tr><td colspan="9" class="empty-table-message"><i class="fa-solid fa-folder-open"></i> ${emptyMsg}</td></tr>`;
        return;
    }

    const unassignedText = window.t ? t('unassigned', 'Unassigned') : 'Unassigned';
    const reassignText = window.t ? t('reassign_title', 'Reassign') : 'Reassign';
    const directiveText = window.t ? t('opt_immediate_directive', 'Directive') : 'Directive';
    const discTitle = window.t ? t('discussion_title', 'Discussion') : 'Discussion';
    const overdueLabel = window.t ? t('stat_overdue_count', 'OVERDUE') : 'OVERDUE';
    const onScheduleLabel = window.t ? t('status_active', 'On Schedule') : 'On Schedule';

    complaints.forEach(c => {
        const tr = document.createElement('tr');
        const prioClass = `badge-${c.priority.toLowerCase()}`;
        const statusClass = `badge-${c.status.replace(' ', '')}`;
        const prioText = window.getPriorityTranslation ? getPriorityTranslation(c.priority) : c.priority;
        const statusText = window.getStatusTranslation ? getStatusTranslation(c.status) : c.status;
        const escBadge = c.escalation_level > 0 ? `<span class="badge badge-high">Tier ${c.escalation_level}</span>` : '<span class="text-muted">-</span>';
        const slaStatus = c.overdue_flag ? `<span style="color: #f43f5e; font-weight: 700;"><i class="fa-solid fa-triangle-exclamation"></i> ${overdueLabel}</span>` : `<span style="color: #10b981;">${onScheduleLabel}</span>`;
        const assignedName = c.assigned_to_name || `<i class="text-muted">${unassignedText}</i>`;

        const titleText = c.title || (window.getCategoryTranslation ? getCategoryTranslation(c.category).toUpperCase() : c.category.toUpperCase());
        const cellId = `ha-desc-${c.complaint_id}`;

        tr.innerHTML = `
            <td><strong>${c.complaint_id}</strong></td>
            <td style="max-width: 240px;">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                    <strong style="font-size: 0.88rem; color: var(--text-primary);">${titleText}</strong>
                    <button type="button" class="btn-ha-translate" data-id="${c.complaint_id}" style="background: none; border: none; color: var(--accent-indigo); font-size: 0.76rem; cursor: pointer; padding: 2px 4px;" title="Translate text (Hugging Face AI)">
                        <i class="fa-solid fa-language"></i>
                    </button>
                </div>
                <span id="${cellId}" style="font-size: 0.8rem; color: var(--text-secondary); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${c.description}</span>
            </td>
            <td><span class="badge">${c.ward.toUpperCase()}</span></td>
            <td><span class="badge ${prioClass}">${prioText}</span></td>
            <td><span class="badge ${statusClass}">${statusText}</span></td>
            <td>${escBadge}</td>
            <td>${slaStatus}</td>
            <td>${assignedName}</td>
            <td>
                <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                    <button class="btn-action-assign" onclick="openReassignModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.75rem;" title="${reassignText}"><i class="fa-solid fa-arrows-split-up-and-left"></i> ${reassignText}</button>
                    <button class="btn-action-assign" onclick="openAdminNoticeModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.75rem; background: rgba(245,158,11,0.2); border: 1px solid #f59e0b; color: #fcd34d;" title="${directiveText}"><i class="fa-solid fa-file-signature"></i> ${directiveText}</button>
                    <button class="btn-action-assign" onclick="openCommentsModal('${c.complaint_id}')" style="padding: 4px 8px; font-size: 0.75rem;" title="${discTitle}"><i class="fa-solid fa-comments"></i></button>
                </div>
            </td>
        `;

        const btnTrans = tr.querySelector('.btn-ha-translate');
        if (btnTrans) {
            let isTrans = false;
            btnTrans.addEventListener('click', async () => {
                const descSpan = document.getElementById(cellId);
                const curLang = window.getCurrentLang ? getCurrentLang() : 'en';
                if (!isTrans) {
                    btnTrans.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
                    let transDesc = c.description;
                    if (curLang === 'en' && c.english_description) {
                        transDesc = c.english_description;
                    } else {
                        const res = await translateTextWithHF(c.description, curLang);
                        transDesc = res.translated_text || c.description;
                    }
                    if (descSpan) descSpan.textContent = transDesc;
                    btnTrans.innerHTML = `<i class="fa-solid fa-rotate-left"></i>`;
                    btnTrans.style.color = '#10b981';
                    isTrans = true;
                } else {
                    if (descSpan) descSpan.textContent = c.description;
                    btnTrans.innerHTML = `<i class="fa-solid fa-language"></i>`;
                    btnTrans.style.color = 'var(--accent-indigo)';
                    isTrans = false;
                }
            });
        }

        tbody.appendChild(tr);
    });
}

window.openReassignModal = function(id) {
    document.getElementById('reassign-complaint-id').value = id;
    const workerSelect = document.getElementById('reassign-worker-select');
    workerSelect.innerHTML = '<option value="">-- Choose Dispatch Worker --</option>';

    if (activeWorkersList && activeWorkersList.length > 0) {
        activeWorkersList.forEach(w => {
            const opt = document.createElement('option');
            opt.value = w.id;
            opt.textContent = `${w.name} (${w.ward || 'Central'})`;
            workerSelect.appendChild(opt);
        });
    } else {
        fetch(`${API_BASE}/api/users?role=worker`)
        .then(res => res.json())
        .then(workers => {
            activeWorkersList = workers;
            workers.forEach(w => {
                const opt = document.createElement('option');
                opt.value = w.id;
                opt.textContent = `${w.name} (${w.ward || 'Central'})`;
                workerSelect.appendChild(opt);
            });
        });
    }

    document.getElementById('reassign-modal').classList.remove('hidden');
};

window.openAdminNoticeModal = function(id) {
    document.getElementById('admin-notice-complaint-id').value = id;
    document.getElementById('admin-notice-modal').classList.remove('hidden');
};

