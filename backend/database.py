import sqlite3
import os
from .logger import logger

class DatabaseManager:
    def __init__(self):
        # 1. Get location of database.py (/.../backend/database.py)
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. Get the project directory (/.../)
        project_root = os.path.dirname(backend_dir)
        
        # 3. Target the 'data' folder inside root
        self.db_path = os.path.join(project_root, "data", "scans.db")
        
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            logger.info(f"--- DB ATTACHED: {self.db_path} ---")
        except Exception as e:
            logger.error(f"Directory Error: {e}")

        self._bootstrap()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row 
        return conn

    def _bootstrap(self):
        """Initializes the database schema."""
        with self._get_connection() as conn:
            # 1. Main Scan History
            conn.execute('''
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_path TEXT NOT NULL,
                    status TEXT DEFAULT 'In Progress',
                    trigger_source TEXT DEFAULT 'Manual',
                    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    end_time DATETIME,
                    dirs_scanned INTEGER DEFAULT 0,
                    files_scanned INTEGER DEFAULT 0,
                    data_size_mb REAL DEFAULT 0.0,
                    infections_found INTEGER DEFAULT 0
                )
            ''')
            
            # 2. Permanent Threat Archive
            conn.execute('''
                CREATE TABLE IF NOT EXISTS threats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id INTEGER,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    infection_type TEXT NOT NULL,
                    found_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(scan_id) REFERENCES scans(id)
                )
            ''')
            
            # 3. Volatile Live Results
            conn.execute('''
                CREATE TABLE IF NOT EXISTS live_results (
                    file_path TEXT PRIMARY KEY,
                    infection_type TEXT,
                    found_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 4. Master Schedules
            conn.execute('''
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    cron_spec TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 5. Schedule Tasks (The Sequence)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS schedule_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule_id INTEGER,
                    action_type TEXT NOT NULL,
                    payload TEXT,
                    task_order INTEGER,
                    FOREIGN KEY(schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
                )
            ''')

    # --- SCHEDULING METHODS (Sequence-Based) ---

    def save_master_schedule(self, name, cron):
        """Creates a master schedule entry and returns the ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO schedules (name, cron_spec) VALUES (?, ?)
            ''', (name, cron))
            return cursor.lastrowid

    def add_task_to_schedule(self, sched_id, action, payload):
        """Adds a specific task action to a schedule sequence."""
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO schedule_tasks (schedule_id, action_type, payload)
                VALUES (?, ?, ?)
            ''', (sched_id, action, payload))

    def get_schedules(self):
        """Returns all schedules with task counts for the UI list."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.id, s.name, s.cron_spec, s.enabled, COUNT(t.id) as task_count
                FROM schedules s
                LEFT JOIN schedule_tasks t ON s.id = t.schedule_id
                GROUP BY s.id
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_schedule_tasks(self, schedule_id):
        """Returns the specific tasks for a given schedule."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT action_type, payload FROM schedule_tasks 
                WHERE schedule_id = ? 
                ORDER BY id ASC
            ''', (schedule_id,))
            return [dict(row) for row in cursor.fetchall()]

    def delete_schedule(self, schedule_id):
        """Removes a schedule and all its associated tasks."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM schedule_tasks WHERE schedule_id = ?", (schedule_id,))
            conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    def get_active_schedules(self):
        """Alias for the background scheduler loop."""
        return self.get_schedules()

    def toggle_schedule(self, schedule_id, enabled):
        """Toggles the enabled state of a schedule."""
        with self._get_connection() as conn:
            conn.execute("UPDATE schedules SET enabled = ? WHERE id = ?", (enabled, schedule_id))

    # --- SCAN EXECUTION LOGIC ---

    def start_scan(self, path, trigger_source="Manual"):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM live_results")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO scans (target_path, trigger_source) VALUES (?, ?)", (path, trigger_source))
            return cursor.lastrowid

    def complete_scan(self, scan_id, dirs, files, size_mb):
        with self._get_connection() as conn:
            conn.execute('''
                UPDATE scans 
                SET status = 'Completed', end_time = CURRENT_TIMESTAMP,
                    dirs_scanned = ?, files_scanned = ?, data_size_mb = ?
                WHERE id = ?
            ''', (dirs, files, size_mb, scan_id))

    def log_infection(self, scan_id, full_path, infection_type):
        file_name = os.path.basename(full_path)
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO threats (scan_id, file_path, file_name, infection_type)
                VALUES (?, ?, ?, ?)
            ''', (scan_id, full_path, file_name, infection_type))
            
            conn.execute('''
                INSERT OR REPLACE INTO live_results (file_path, infection_type)
                VALUES (?, ?)
            ''', (full_path, infection_type))
            
            conn.execute("UPDATE scans SET infections_found = infections_found + 1 WHERE id = ?", (scan_id,))

    def delete_scan(self, scan_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Only delete from the table we know exists
            cursor.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
            conn.commit()

    def clear_all_scans(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scans")
            conn.commit()

    # --- UI DATA RETRIEVAL ---

    def get_scan_history(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scans ORDER BY start_time DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_infections_for_scan(self, scan_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_path, infection_type as threat_name 
                FROM threats 
                WHERE scan_id = ?
            """, (scan_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_live_threats(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM live_results ORDER BY found_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def execute_query(self, query, params=()):
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()