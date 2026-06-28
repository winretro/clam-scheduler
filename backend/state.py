import threading

class GlobalRegistry:
    """Tracks active scan state for the UI heartbeat."""
    active_scan_pid = 0 
    current_target = "None"
    current_file = "Idle"
    progress = 0
    total_files = 0
    completed_files = 0
    found_count = 0
    lock = threading.Lock()

def is_scan_running():
    with GlobalRegistry.lock:
        return GlobalRegistry.active_scan_pid != 0
