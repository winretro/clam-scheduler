// --- GLOBAL FETCH INTERCEPTOR ---
// Add this to the very first line of your app.js
const originalFetch = window.fetch;
window.fetch = async function (url, options = {}) {
    if (!options.headers) { options.headers = {}; }

    // Intercept API calls to attach the Bearer token
    if (typeof url === 'string' && url.startsWith('/api/') && !['/api/login', '/api/setup', '/api/setup/status', '/api/version'].includes(url)) {
        const sid = sessionStorage.getItem('auth_sid');
        if (sid) {
            options.headers['Authorization'] = 'Bearer ' + sid;
        }
    }

    const response = await originalFetch(url, options);

    // Global 401 handler
    if (response.status === 401) {
        sessionStorage.removeItem('auth_sid');
        document.getElementById('login-overlay').classList.remove('hidden');
    }
    return response;
};

async function apiFetch(url, options = {}) {
    if (!options.headers) {
        options.headers = {};
    }

    // Only attach if it's an API route and not public
    if (typeof url === 'string' && url.startsWith('/api/') && !['/api/login', '/api/setup', '/api/setup/status', '/api/version'].includes(url)) {
        const sid = sessionStorage.getItem('auth_sid');
        if (sid) {
            // This now sends 'Bearer <your_actual_token>'
            options.headers['Authorization'] = 'Bearer ' + sid;
        }
    }

    // DEBUG: Log exactly what is being sent
    console.log(`[API CALL] URL: ${url} | Headers:`, options.headers);

    const response = await fetch(url, options);

    if (response.status === 401) {
        try {
            const statusRes = await fetch('/api/setup/status');
            const data = await statusRes.json();
            if (data.is_setup) {
                sessionStorage.removeItem('auth_sid');
                app.currentSID = null;
                const overlay = document.getElementById('login-overlay');
                if (overlay) overlay.classList.remove('hidden');
            } else {
                window.location.href = '/setup';
            }
        } catch (e) {
            console.error("Failed to check setup status");
        }
    }
    return response;
}

const app = {
    currentSID: null,
    isScanning: false,
    selectedPath: null,
    eventSource: null,
    historyLimit: parseInt(localStorage.getItem('historyLimit')) || 20,
    inactivityTimer: null,
    inactivityTimeoutMinutes: 5,

    // --- INIT & AUTH ---
    init() {
        // Explicitly load session inside DOMContentLoaded
        this.currentSID = sessionStorage.getItem('auth_sid');

        if (!this.currentSID) {
            document.getElementById('login-overlay').classList.remove('hidden');
        } else {
            document.getElementById('login-overlay').classList.add('hidden');
            document.getElementById('main-dashboard').classList.remove('hidden');
            const displayUser = sessionStorage.getItem('auth_user') || 'Admin';
            document.getElementById('display-user').innerText = displayUser;

            this.loadSharedFolders();
            this.loadSchedules();
            this.loadHistory();
            this.startStatusStream();
            this.refreshSigStatus();
            this.loadVersion();
            
            this.fetchSettings();
            this.setupInactivityListener();
            this.updateLimitUI();

            // Poll signature status every hour
            setInterval(() => this.refreshSigStatus(), 3600000);

            // Global listener to close overflow menus when clicking outside
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.overflow-menu-container')) {
                    document.querySelectorAll('.overflow-menu-content').forEach(el => el.classList.add('hidden'));
                }
            });
        }
    },

    async fetchSettings() {
        try {
            const res = await apiFetch('/api/settings');
            const data = await res.json();
            if (data.theme) {
                this.setTheme(data.theme);
                document.getElementById('setting-theme').value = data.theme;
            }
            if (data.log_retention !== undefined) {
                document.getElementById('setting-retention').value = data.log_retention;
            }
            if (data.inactivity_timeout !== undefined) {
                this.inactivityTimeoutMinutes = data.inactivity_timeout;
                document.getElementById('setting-timeout').value = data.inactivity_timeout;
                this.resetInactivityTimer();
            }
        } catch (e) {
            console.error("Failed to load settings", e);
        }
    },

    showSettings() {
        document.querySelectorAll('.overflow-menu-content').forEach(el => el.classList.add('hidden'));
        document.getElementById('settings-modal').classList.remove('hidden');
    },

    async saveSettings() {
        const theme = document.getElementById('setting-theme').value;
        const retention = document.getElementById('setting-retention').value;
        const timeout = document.getElementById('setting-timeout').value;

        try {
            const res = await apiFetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    theme: theme,
                    log_retention: parseInt(retention),
                    inactivity_timeout: parseInt(timeout)
                })
            });
            if (res.ok) {
                this.setTheme(theme);
                this.inactivityTimeoutMinutes = parseInt(timeout);
                this.resetInactivityTimer();
            } else {
                alert("Failed to save settings.");
            }
        } catch (e) {
            alert("Error saving settings.");
        }
    },

    showAbout() {
        document.querySelectorAll('.overflow-menu-content').forEach(el => el.classList.add('hidden'));
        document.getElementById('about-modal').classList.remove('hidden');
    },

    setupInactivityListener() {
        const reset = () => this.resetInactivityTimer();
        window.addEventListener('mousemove', reset);
        window.addEventListener('keydown', reset);
        window.addEventListener('scroll', reset);
        window.addEventListener('click', reset);
        this.resetInactivityTimer();
    },

    resetInactivityTimer() {
        if (this.inactivityTimer) clearTimeout(this.inactivityTimer);
        if (this.inactivityTimeoutMinutes > 0) {
            this.inactivityTimer = setTimeout(() => {
                this.logout();
            }, this.inactivityTimeoutMinutes * 60 * 1000);
        }
    },

    setHistoryLimit(limit) {
        this.historyLimit = limit;
        localStorage.setItem('historyLimit', limit);
        this.updateLimitUI();
        this.loadHistory();
    },

    updateLimitUI() {
        document.querySelectorAll('.limit-link').forEach(link => {
            if (parseInt(link.dataset.limit) === this.historyLimit) {
                link.style.fontWeight = 'normal';
                link.style.color = '#3498db'; // Active blue
                link.style.textDecoration = 'none';
            } else {
                link.style.fontWeight = 'normal';
                link.style.color = 'var(--text-main)'; // Standard color
                link.style.textDecoration = 'none';
            }
        });
    },

    setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        
        // Hide the overflow menus
        document.querySelectorAll('.overflow-menu-content').forEach(el => el.classList.add('hidden'));
    },

    async handleLogin() {
        const user = document.getElementById('username').value;
        const pass = document.getElementById('password').value;
        const errElem = document.getElementById('login-error');

        try {
            const response = await apiFetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user, pass })
            });
            const data = await response.json();

            if (data.auth && data.isAdmin) {
                sessionStorage.setItem('auth_sid', data.SID);
                sessionStorage.setItem('auth_user', user);
                window.location.reload();
            } else {
                errElem.innerText = "Login failed or not an administrator.";
            }
        } catch (err) {
            errElem.innerText = "Connection error.";
        }
    },

    async loadVersion() {
        try {
            const res = await apiFetch('/api/version');
            const data = await res.json();
            const elem = document.getElementById('app-version-display');
            if (elem) elem.innerText = data.version;
        } catch (e) { console.error("Failed to load version", e); }
    },

    // --- FILE EXPLORER ---
    async loadSharedFolders(targetPath = '/share') {
        try {
            const response = await apiFetch('/api/folders?path=' + encodeURIComponent(targetPath));
            const data = await response.json();
            const list = document.getElementById('folder-list');
            if (list.parentElement) list.parentElement.scrollTop = 0;
            list.innerHTML = '';

            if (data.parent_path) {
                const clone = document.getElementById('folder-item-template').content.cloneNode(true);
                const li = clone.querySelector('li');
                li.textContent = '📁 .. (Back)';
                li.onclick = () => this.loadSharedFolders(data.parent_path);
                list.appendChild(clone);
            }

            data.folders.forEach(f => {
                const clone = document.getElementById('folder-item-template').content.cloneNode(true);
                const li = clone.querySelector('li');
                const fullPath = (data.current_path + '/' + f).replace(/\/+/g, '/');
                li.textContent = '📁 ' + f;
                li.onclick = (e) => { e.stopPropagation(); this.selectTarget(li, fullPath); };
                li.ondblclick = (e) => { e.stopPropagation(); this.loadSharedFolders(fullPath); };
                list.appendChild(clone);
            });

            data.files.forEach(f => {
                const clone = document.getElementById('file-item-template').content.cloneNode(true);
                const li = clone.querySelector('li');
                const fullPath = (data.current_path + '/' + f).replace(/\/+/g, '/');
                li.textContent = '📄 ' + f;
                li.onclick = (e) => { e.stopPropagation(); this.selectTarget(li, fullPath); };
                list.appendChild(clone);
            });

            this.selectedPath = data.current_path;
        } catch (e) { console.error("Navigation error:", e); }
    },

    selectTarget(element, fullPath) {
        this.selectedPath = fullPath;
        document.querySelectorAll('#folder-list li').forEach(el => el.classList.remove('selected'));
        element.classList.add('selected');

        document.getElementById('start-scan-btn').disabled = this.isScanning;

        const targetLabel = document.getElementById('current-target-label');
        if (targetLabel) targetLabel.innerText = 'Target: ' + fullPath;

        if (!this.isScanning) {
            const progressBar = document.getElementById('progress-bar');
            const statusText = document.getElementById('status-text');
            if (progressBar) progressBar.style.width = '0%';
            if (statusText) statusText.innerText = 'Ready to scan';
        }
    },

    // --- REACTIVE STATUS STREAM ---
    startStatusStream() {
        if (this.eventSource) this.eventSource.close();

        const progressBar = document.getElementById('progress-bar');
        const statusText = document.getElementById('status-text');
        const targetLabel = document.getElementById('current-target-label');
        const startBtn = document.getElementById('start-scan-btn');

        this.eventSource = new EventSource('/api/scan/stream');

        this.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            const wasScanning = this.isScanning;
            this.isScanning = data.is_running;

            if (this.isScanning) {
                startBtn.disabled = true;
                if (targetLabel) targetLabel.innerText = 'Target: ' + (data.target || 'Processing...');
                progressBar.style.width = data.progress + '%';
                statusText.innerText = 'Scanning: ' + (data.current_file || 'In progress...');
            } else {
                if (wasScanning) {
                    if (app.isManualScan) {
                        progressBar.style.width = "100%";
                        if (data.found_count > 0) {
                            statusText.innerHTML = `<span class="text-danger font-bold">Scan Complete. ${data.found_count} Infection(s) Found!</span>`;
                        } else {
                            statusText.innerText = "Scan Complete. No threats detected.";
                        }
                    } else {
                        progressBar.style.width = "0%";
                        statusText.innerText = "Ready to scan...";
                        if (targetLabel) targetLabel.innerText = "Target: Idle";
                    }
                    startBtn.disabled = false;
                    this.loadHistory();
                    this.refreshSigStatus();
                    app.isManualScan = false;
                }
            }
        };

        this.eventSource.onerror = () => {
            console.warn("Status stream disconnected.");
        };
    },

    // --- SCAN ENGINE CONTROL ---
    async initiateScan() {
        if (this.isScanning) return;
        document.getElementById('start-scan-btn').disabled = true;
        this.isManualScan = true;

        try {
            const response = await apiFetch('/api/scan/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ path: this.selectedPath })
            });

            if (!response.ok) {
                const data = await response.json();
                alert(data.detail || "Scan failed to start.");
                document.getElementById('start-scan-btn').disabled = false;
            }
        } catch (e) {
            alert("Network error starting scan.");
            document.getElementById('start-scan-btn').disabled = false;
        }
    },

    // --- SCHEDULING ---
    clearTaskConfig() {
        document.getElementById('edit-sched-id').value = '';
        document.getElementById('sched-name').value = '';
        document.getElementById('cron-min').value = '0';
        document.getElementById('cron-hour').value = '0';
        document.getElementById('cron-dom').value = '*';
        document.getElementById('cron-month').value = '*';
        document.getElementById('cron-dow').value = '*';
        document.getElementById('task-list-body').innerHTML = '';
        const saveBtn = document.querySelector('button[onclick*="saveSequencedSchedule"]');
        if (saveBtn) saveBtn.innerText = "Save";
    },

    addTaskRow(action = 'start_scan', payload = null) {
        let finalPayload = payload !== null ? payload : (this.selectedPath || '');
        if (finalPayload.startsWith('/data/')) {
            finalPayload = finalPayload.replace('/data/', '/');
        } else if (finalPayload === '/data') {
            finalPayload = '/';
        }
        const tbody = document.getElementById('task-list-body');
        const rowId = 'row-' + Date.now();

        const template = document.getElementById('task-row-template');
        const clone = template.content.cloneNode(true);

        const tr = clone.querySelector('tr');
        tr.id = rowId;

        const select = clone.querySelector('.task-action-select');
        select.value = action;

        const input = clone.querySelector('.task-payload-input');
        const valDiv = clone.querySelector('.validation-feedback');
        valDiv.id = 'val-' + rowId;

        const togglePayloadInput = () => {
            if (select.value === 'update_defs') {
                input.style.display = 'none';
                valDiv.style.display = 'none';
                input.value = '';
            } else {
                input.style.display = 'block';
                valDiv.style.display = 'block';
            }
        };

        select.addEventListener('change', () => {
            togglePayloadInput();
            if (select.value === 'start_scan' && input.value) {
                app.validatePath(input.value, 'val-' + rowId);
            }
        });
        
        togglePayloadInput();

        // Only set value if it's a scan action
        if (action === 'start_scan') {
            input.value = finalPayload;
        }
        
        input.onchange = (e) => app.validatePath(e.target.value, 'val-' + rowId);

        const removeBtn = clone.querySelector('.btn-remove');
        removeBtn.onclick = function () { this.closest('tr').remove(); };

        tbody.appendChild(clone);

        if (finalPayload && action === 'start_scan') {
            this.validatePath(finalPayload, 'val-' + rowId);
        }
    },

    async validatePath(path, feedbackElementId) {
        const feedback = document.getElementById(feedbackElementId);
        if (!path || path.trim() === "") {
            feedback.innerHTML = "";
            return;
        }

        try {
            const response = await apiFetch('/api/folders/validate?path=' + encodeURIComponent(path));
            const data = await response.json();

            feedback.innerHTML = '';
            if (data.valid) {
                const tmpl = document.getElementById('val-valid-template').content.cloneNode(true);
                tmpl.querySelector('.val-text').textContent = 'Valid';
                feedback.appendChild(tmpl);
            } else {
                const tmpl = document.getElementById('val-invalid-template').content.cloneNode(true);
                tmpl.querySelector('.val-text').textContent = data.reason;
                feedback.appendChild(tmpl);
            }
        } catch (err) {
            feedback.innerHTML = '';
            const tmpl = document.getElementById('val-unavail-template').content.cloneNode(true);
            feedback.appendChild(tmpl);
        }
    },

    async saveSequencedSchedule() {
        const schedId = document.getElementById('edit-sched-id').value;
        const name = document.getElementById('sched-name').value;
        const taskRows = document.querySelectorAll('.task-row');

        if (!name || taskRows.length === 0) {
            return alert("Please provide a schedule name and at least one task.");
        }

        const tasks = Array.from(taskRows).map(row => ({
            action: row.querySelector('.task-action-select').value,
            payload: row.querySelector('.task-payload-input').value
        }));

        // Validate all target paths before saving
        for (const task of tasks) {
            if (task.action === 'start_scan') {
                try {
                    const response = await apiFetch('/api/folders/validate?path=' + encodeURIComponent(task.payload));
                    const data = await response.json();
                    if (!data.valid) {
                        return alert(`Cannot save schedule.\nValidation failed for target: ${task.payload}\nReason: ${data.reason}`);
                    }
                } catch (err) {
                    return alert(`Cannot save schedule.\nCould not communicate with validation server for target: ${task.payload}`);
                }
            }
        }

        const cronStr = [
            document.getElementById('cron-min').value || '*',
            document.getElementById('cron-hour').value || '*',
            document.getElementById('cron-dom').value || '*',
            document.getElementById('cron-month').value || '*',
            document.getElementById('cron-dow').value || '*'
        ].join(' ');

        const payload = { id: schedId || null, name: name, cron: cronStr, tasks: tasks };

        try {
            const response = await apiFetch('/api/schedules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                this.clearTaskConfig();
                this.loadSchedules();
                alert("Schedule saved successfully!");
            } else {
                alert("Failed to save schedule.");
            }
        } catch (err) { alert("Save error."); }
    },

    async loadSchedules() {
        try {
            const response = await apiFetch('/api/schedules');
            const schedules = await response.json();
            const container = document.getElementById('schedule-list');

            if (schedules.length === 0) {
                container.innerHTML = '';
                const emptyClone = document.getElementById('sched-empty-template').content.cloneNode(true);
                container.appendChild(emptyClone);
                return;
            }

            container.innerHTML = '';

            schedules.forEach(sched => {
                const template = document.getElementById('schedule-card-template');
                const clone = template.content.cloneNode(true);

                const card = clone.querySelector('.schedule-card');
                card.id = 'sched-row-' + sched.id;

                clone.querySelector('.sched-title').textContent = sched.name;
                clone.querySelector('.sched-cron').textContent = 'Cron: ' + sched.cron_spec;

                const tasksContainer = clone.querySelector('.sched-tasks-container');
                if (sched.tasks && sched.tasks.length > 0) {
                    sched.tasks.forEach(t => {
                        const taskTmpl = document.getElementById('schedule-task-row-template').content.cloneNode(true);
                        
                        let displayAction = t.action;
                        if (t.action === 'start_scan') displayAction = 'Target';
                        else if (t.action === 'update_defs') displayAction = 'Update';
                        
                        taskTmpl.querySelector('.sched-task-action').textContent = displayAction + ':';
                        
                        let cleanPayload = t.payload || '';
                        if (t.action === 'update_defs') {
                            cleanPayload = 'Fetch current signatures';
                        } else {
                            if (cleanPayload.startsWith('/data/')) {
                                cleanPayload = cleanPayload.replace('/data/', '/');
                            } else if (cleanPayload === '/data') {
                                cleanPayload = '/';
                            }
                        }
                        
                        taskTmpl.querySelector('.sched-task-payload').textContent = cleanPayload;
                        tasksContainer.appendChild(taskTmpl);
                    });
                } else {
                    const noTasksClone = document.getElementById('sched-no-tasks-template').content.cloneNode(true);
                    tasksContainer.appendChild(noTasksClone);
                }

                // Toggle Logic
                const toggleBtn = clone.querySelector('.sched-toggle');
                if (toggleBtn) {
                    toggleBtn.checked = (sched.enabled === 1);
                    toggleBtn.addEventListener('change', async (e) => {
                        try {
                            const res = await apiFetch(`/api/schedules/${sched.id}/toggle`, {
                                method: 'PUT',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ enabled: e.target.checked ? 1 : 0 })
                            });
                            if (!res.ok) throw new Error();
                        } catch(err) { 
                            e.target.checked = !e.target.checked; 
                            alert("Failed to toggle task."); 
                        }
                    });
                }

                // Overflow Menu Logic
                const overflowBtn = clone.querySelector('.btn-overflow');
                const overflowContent = clone.querySelector('.overflow-menu-content');
                if (overflowBtn && overflowContent) {
                    overflowContent.classList.add('hidden');
                    overflowBtn.onclick = (e) => {
                        e.stopPropagation();
                        // Close all others first
                        document.querySelectorAll('.overflow-menu-content').forEach(el => {
                            if (el !== overflowContent) el.classList.add('hidden');
                        });
                        overflowContent.classList.toggle('hidden');
                    };
                    clone.querySelector('.btn-menu-edit').onclick = () => { overflowContent.classList.add('hidden'); app.editSchedule(sched.id); };
                    clone.querySelector('.btn-menu-run').onclick = () => { overflowContent.classList.add('hidden'); app.runSchedule(sched.id); };
                    clone.querySelector('.btn-menu-del').onclick = () => { overflowContent.classList.add('hidden'); app.deleteSchedule(sched.id); };
                }

                container.appendChild(clone);
            });
        } catch (err) { console.error("Load error:", err); }
    },

    async deleteSchedule(id) {
        if (!confirm("Delete this schedule?")) return;
        try {
            const response = await apiFetch('/api/schedules/' + id, { method: 'DELETE' });
            if (response.ok) document.getElementById('sched-row-' + id).remove();
        } catch (err) { alert("Delete failed."); }
    },

    async runSchedule(id) {
        try {
            const response = await apiFetch(`/api/schedules/${id}/run`, { method: 'POST' });
            if (!response.ok) {
                const data = await response.json();
                alert(data.detail || "Failed to run schedule.");
            } else {
                alert("Task execution initiated.");
            }
        } catch (err) { alert("Network error running task."); }
    },

    async editSchedule(id) {
        try {
            const response = await apiFetch('/api/schedules/' + id);
            const sched = await response.json();

            document.getElementById('edit-sched-id').value = sched.id;
            document.getElementById('sched-name').value = sched.name;

            const parts = sched.cron_spec.split(' ');
            
            document.getElementById('cron-min').value = parts[0] === '*' ? '' : parts[0];
            document.getElementById('cron-hour').value = parts[1] === '*' ? '' : parts[1];

            document.getElementById('cron-dom').value = parts[2];
            document.getElementById('cron-month').value = parts[3];
            document.getElementById('cron-dow').value = parts[4];

            const tbody = document.getElementById('task-list-body');
            tbody.innerHTML = '';
            sched.tasks.forEach(t => {
                this.addTaskRow(t.action || t.action_type, t.payload);
            });

            const saveBtn = document.querySelector('button[onclick*="saveSequencedSchedule"]');
            if (saveBtn) saveBtn.innerText = "Update";

            document.querySelector('.schedule-section').scrollIntoView({ behavior: 'smooth' });

        } catch (err) {
            console.error("Edit load error:", err);
            alert("Could not load schedule.");
        }
    },

    // --- HISTORY & MISC ---
    async loadHistory() {
        try {
            const response = await apiFetch('/api/history');
            let history = await response.json();
            const body = document.getElementById('history-body');

            if (this.historyLimit > 0) {
                history = history.slice(0, this.historyLimit);
            }

            body.innerHTML = '';
            history.forEach(entry => {
                const template = document.getElementById('history-row-template');
                const clone = template.content.cloneNode(true);

                let cleanPath = entry.target_path || '';
                if (cleanPath.startsWith('/data/')) {
                    cleanPath = cleanPath.replace('/data/', '/');
                } else if (cleanPath === '/data') {
                    cleanPath = '/';
                }

                clone.querySelector('.h-date').textContent = this.formatDate(entry.start_time);
                clone.querySelector('.h-path').textContent = cleanPath;
                
                const btn = clone.querySelector('.btn-logs');
                if (entry.status !== 'Completed') {
                    clone.querySelector('.h-files').textContent = '...';
                    clone.querySelector('.h-infected').textContent = '...';
                    btn.textContent = 'Scanning...';
                    btn.classList.add('btn-disabled');
                } else {
                    clone.querySelector('.h-files').textContent = entry.files_scanned;
                    clone.querySelector('.h-infected').textContent = entry.infections_found || 0;
                    btn.onclick = () => app.showDetails(entry, cleanPath);
                }

                body.appendChild(clone);
            });
        } catch (e) { console.error("History failed"); }
    },

    // --- SHOW SCAN LOGS ---
    async showDetails(entry, cleanPath) {
        try {
            const response = await apiFetch('/api/scan/details/' + entry.id);
            if (!response.ok) throw new Error("Could not fetch log details.");

            const infections = await response.json();

            let logMsg = `[ Scan Job #${entry.id} ]\n`;
            logMsg += `Target: ${cleanPath}\n`;
            logMsg += `Files Scanned: ${entry.files_scanned}\n`;
            logMsg += `Hits Found: ${entry.infections_found || 0}\n\n`;

            if (infections.length === 0) {
                logMsg += "Result: Clean Scan. No threats were detected.";
            } else {
                logMsg += '--- INFECTED FILES ---\n';
                infections.forEach(inf => {
                    let cleanInfPath = inf.file_path || '';
                    if (cleanInfPath.startsWith('/data/')) {
                        cleanInfPath = cleanInfPath.replace('/data/', '/');
                    } else if (cleanInfPath === '/data') {
                        cleanInfPath = '/';
                    }
                    logMsg += `File: ${cleanInfPath}\nThreat: ${inf.virus_name}\n\n`;
                });
            }
            alert(logMsg);
        } catch (e) {
            console.error("Log fetch error:", e);
            alert("Failed to retrieve scan logs from database.");
        }
    },

    // --- DELETE LOGS ---
    async deleteHistory(id) {
        if (!confirm("Delete this scan record?")) return;
        try {
            const response = await apiFetch('/api/history/' + id, { method: 'DELETE' });
            if (response.ok) this.loadHistory();
        } catch (err) {
            alert("Delete failed.");
        }
    },

    async clearAllHistory() {
        if (!confirm("Are you sure you want to wipe ALL scan logs? This cannot be undone.")) return;
        try {
            const response = await apiFetch('/api/history/clear', { method: 'DELETE' });
            if (response.ok) this.loadHistory();
        } catch (err) {
            alert("Clear failed.");
        }
    },

    logout() {
        if (this.eventSource) this.eventSource.close();
        sessionStorage.removeItem('auth_sid');
        window.location.reload();
    },

    // --- SIGNATURE STATUS ---
    refreshSigStatus: async function () {
        try {
            const response = await apiFetch('/api/signatures/status');
            const data = await response.json();

            const sigDateElem = document.getElementById('sig-date');
            const sigInfoWrapper = document.getElementById('sig-info');

            if (data.version && sigDateElem) {
                sigDateElem.innerText = 'v' + data.version + ' (' + (data.sig_date || data.date) + ')';

                if (data.is_current) {
                    sigInfoWrapper.className = "sig-ok";
                    sigInfoWrapper.title = "Signatures are current";
                } else {
                    sigInfoWrapper.className = "sig-err";
                    sigInfoWrapper.title = 'Update Available: v' + (data.remote_version || "unknown");
                }
            }
        } catch (err) {
            console.error("Signature check failed:", err);
        }
    },

    formatDate(dateStr) {
        if (!dateStr) return '';
        const d = new Date(dateStr.replace(' ', 'T') + 'Z');
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        return `${yyyy}/${mm}/${dd} ${hh}:${min}`;
    }
};

document.addEventListener('DOMContentLoaded', () => app.init());