import os
import time
import threading
import pyclamd
from .database import DatabaseManager
from .state import GlobalRegistry, is_scan_running
from .logger import logger

SCAN_DIR = os.getenv("SCAN_DIR", "/data")

# Initialize DB connection for scanner
db = DatabaseManager()

def trigger_managed_scan(path, trigger_source="Manual"):
    if is_scan_running():
        return {"status": "error", "message": "System busy"}
    
    if path and not path.startswith(SCAN_DIR):
        clean_path = path.lstrip('/')
        path = os.path.join(SCAN_DIR, clean_path)
    
    # Crucial: Resolve the path BEFORE threading to catch "Invalid path" early
    real_path = os.path.realpath(path)
    if not os.path.exists(real_path):
        return {"status": "error", "message": "Invalid path"}

    with GlobalRegistry.lock:
        GlobalRegistry.current_target = os.path.basename(real_path)

    # Start the background worker
    threading.Thread(
        target=run_docker_scan, 
        args=(real_path, trigger_source), 
        daemon=True
    ).start()
    
    return {"status": "success", "message": f"{trigger_source} scan started."}

def trigger_update_defs(trigger_source="Manual"):
    logger.info("Triggering Definitions Update / Reload")
    
    db = DatabaseManager()
    scan_id = db.start_scan("Definitions Update", trigger_source)
    
    try:
        cd = pyclamd.ClamdNetworkSocket(host='clamav', port=3310)
        if cd.ping():
            result = cd.reload()
            logger.info(f"Definitions reloaded successfully: {result}")
            db.complete_scan(scan_id, 0, 0, 0.0)
        else:
            logger.error("Ping failed before reload.")
            db.complete_scan(scan_id, 0, 0, 0.0)
    except Exception as e:
        logger.error(f"Failed to reload definitions: {e}")
        db.complete_scan(scan_id, 0, 0, 0.0)

def run_docker_scan(target_path, trigger_source="Manual"):
    scan_id = None
    total_files = 0
    try:
        # Connect to pyclamd
        try:
            cd = pyclamd.ClamdNetworkSocket(host='clamav', port=3310)
            if not cd.ping():
                raise Exception("Ping to clamav container failed.")
        except Exception as net_err:
            logger.error(f"Network error connecting to ClamAV daemon: {net_err}")
            return

        # Reset Registry for New Scan
        with GlobalRegistry.lock:
            GlobalRegistry.active_scan_pid = 1 
            GlobalRegistry.found_count = 0
            GlobalRegistry.completed_files = 0
            GlobalRegistry.progress = 0
            GlobalRegistry.current_file = "Scanning directory..."

        # 1. Precise File Count (Pre-scan)
        total_files = 0
        if os.path.isfile(target_path):
            total_files = 1
        elif os.path.isdir(target_path):
            for root, _, files in os.walk(target_path):
                total_files += len(files)
                
        with GlobalRegistry.lock:
            GlobalRegistry.total_files = total_files

        logger.info(f"Starting Scan via pyclamd: {target_path} ({total_files} files) - Trigger: {trigger_source}")
        
        scan_id = None
        scan_id = db.start_scan(target_path, trigger_source)

        # 2. Run Scan using pyclamd
        results = cd.multiscan_file(target_path)
        
        # 3. Parse results
        found_count = 0
        if results:
            for file_path, (status, threat_name) in results.items():
                if status == 'FOUND':
                    found_count += 1
                    logger.info(f"[DIAGNOSIS] !!! INFECTION: {file_path} -> {threat_name}")
                    if scan_id:
                        db.log_infection(scan_id, file_path, threat_name)
        
        with GlobalRegistry.lock:
            GlobalRegistry.found_count = found_count
            GlobalRegistry.completed_files = total_files  # Now correctly 1 for a single file
            GlobalRegistry.progress = 100

    except Exception as e:
        logger.error(f"Execution error: {str(e)}")
    finally:
        if scan_id:
            db.complete_scan(scan_id, 0, total_files, 0.0)
            
        with GlobalRegistry.lock:
            GlobalRegistry.completed_files = GlobalRegistry.total_files # Snap to 100%
            GlobalRegistry.progress = 100
            
        # 3. ADD A BUFFER DELAY (The magic fix)
        # Give the frontend's 1-second SSE stream time to catch the 100% state 
        # before we kill the thread and set active_scan_pid back to 0.
        time.sleep(1.5)
        
        with GlobalRegistry.lock:
            GlobalRegistry.active_scan_pid = 0
            
        logger.debug("Scan Finished logic executed.")

def stop_active_scan():
    with GlobalRegistry.lock:
        if GlobalRegistry.active_scan_pid:
            GlobalRegistry.active_scan_pid = 0
            logger.debug("Manually cleared scan state.")
            return {"success": True, "message": "State reset"}
        return {"success": False, "message": "No active scan found"}
