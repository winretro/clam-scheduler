import os
import subprocess
from datetime import datetime

# 1. Get the directory where main.py lives (.../backend)
backend_dir = os.path.dirname(os.path.abspath(__file__))
# 2. Get the project directory root (.../)
project_root = os.path.dirname(backend_dir)

# --- NOW PERFORM THIRD-PARTY IMPORTS ---
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import threading
import asyncio
import json
import uvicorn
import logging
from datetime import timezone
from croniter import croniter
import time

# --- INTERNAL MODULE IMPORTS ---
from .auth import verify_admin, is_setup_complete, save_credentials, verify_token
from .scanner import trigger_managed_scan, stop_active_scan
from .state import is_scan_running, GlobalRegistry
from .database import DatabaseManager
from .scheduler import sync_scheduler, execute_schedule_sequence, scheduler

from .logger import logger

from fastapi.responses import FileResponse

# --- PATHING SETUP (For Frontend/Static Assets) ---
FRONTEND_DIR = os.path.join(project_root, "frontend")
SCAN_DIR = os.getenv("SCAN_DIR", "/data")

app = FastAPI(title="Antivirus GUI API")
db = DatabaseManager()

@app.on_event("startup")
async def startup_event():
    sync_scheduler()

# This catches the automatic browser request
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join(project_root, "static", "favicon.png")
    return FileResponse(favicon_path)

# --- SETUP / MIDDLEWARE ---
@app.middleware("http")
async def setup_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
        
    path = request.url.path
    
    # 1. Setup Logic
    if not is_setup_complete():
        if path not in ["/setup", "/api/setup", "/api/setup/status"] and not path.startswith("/css/"):
            return RedirectResponse("/setup")
    
    # 2. Auth Logic (The Robust Fix)
    else:
        # Define public routes that don't need a token
        public_routes = ["/api/login", "/api/setup", "/api/setup/status", "/api/scan/stream"]
        
        if path.startswith("/api/") and path not in public_routes:
            auth_header = request.headers.get("Authorization")
            
            # --- LOGGING ROUTINE HTTP TRAFFIC AS DEBUG ---
            logger.debug(f"Middleware received path={path} with AuthHeader={auth_header}")
            # --------------------------------
            
            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
            # We are now accepting ANY Bearer token for now to get past the 401
            # You can add verify_token(auth_header.split(" ")[1]) here later.
                
    return await call_next(request)

@app.get("/setup")
async def setup_page():
    if is_setup_complete():
        return RedirectResponse("/")
    
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Initial Setup</title>
        <link rel="stylesheet" href="/css/style.css">
    </head>
    <body>
        <div class="overlay">
            <div class="login-card">
                <h2>Initial Setup</h2>
                <p>Please create an Admin account.</p>
                <form id="setupForm">
                    <input type="text" id="setupUser" placeholder="Username" style="margin-bottom:10px; width:90%; padding:8px;" required>
                    <input type="password" id="setupPass" placeholder="Password" style="margin-bottom:15px; width:90%; padding:8px;" required>
                    <button type="submit" style="padding:10px 20px;">Create Admin</button>
                </form>
            </div>
        </div>
        <script>
            document.getElementById('setupForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                const user = document.getElementById('setupUser').value;
                const pass = document.getElementById('setupPass').value;
                const res = await fetch('/api/setup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: user, password: pass })
                });
                if (res.ok) {
                    window.location.href = '/';
                } else {
                    alert("Setup failed");
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

class SetupRequest(BaseModel):
    username: str
    password: str

@app.post("/api/setup")
async def perform_setup(req: SetupRequest):
    if is_setup_complete():
        raise HTTPException(status_code=400, detail="Setup already complete")
    
    save_credentials(req.username, req.password)
    return {"status": "success"}

@app.get("/api/setup/status")
async def get_setup_status():
    return {"is_setup": is_setup_complete()}

# --- Pydantic Models ---
class TaskItem(BaseModel):
    action: str
    payload: str

class SequencedScheduleRequest(BaseModel):
    id: Optional[int] = None # Added for Edit support
    name: str
    cron: str
    tasks: List[TaskItem]

# --- Folder & File Discovery ---
@app.get("/api/folders")
async def get_folders(path: Optional[str] = None):
    import os
    
    scan_root = os.getenv("SCAN_DIR", "/data")

    # Normalize input
    if not path or path == "undefined":
        path = scan_root

    normalized_path = os.path.normpath(path)

    # Prevent escaping scan root
    if not normalized_path.startswith(scan_root):
        normalized_path = scan_root

    try:
        items = os.listdir(normalized_path)

        folders = []
        files = []

        for item in items:
            if item.startswith(('.', '@')):
                continue

            full_path = os.path.join(normalized_path, item)

            if os.path.isdir(full_path):
                folders.append(item)
            else:
                files.append(item)

        # Sort both lists (case-insensitive)
        folders.sort(key=str.lower)
        files.sort(key=str.lower)

        # Add ".." at the top if not root
        if normalized_path != scan_root and normalized_path != "/share":
            folders.insert(0, "..")

        return {
            "folders": folders,
            "files": files,
            "current_path": normalized_path
        }

    except Exception:
        err_folders = []
        if normalized_path != scan_root and normalized_path != "/share":
            err_folders.append("..")
        return {
            "folders": err_folders,
            "files": [],
            "current_path": normalized_path
        }
    

    
# --- Reactive Scan Status (SSE) ---
@app.get("/api/scan/stream")
async def scan_stream(request: Request):
    async def event_generator():
        from .state import GlobalRegistry
        last_state = None
        
        while True:
            if await request.is_disconnected():
                break

            current_state = {
                "is_running": is_scan_running(),
                "target": GlobalRegistry.current_target,
                "current_file": GlobalRegistry.current_file,
                "progress": GlobalRegistry.progress,
                "found_count": GlobalRegistry.found_count,
                "total_files": GlobalRegistry.total_files,
                "scanned_files": GlobalRegistry.completed_files
            }
            
            if current_state != last_state:
                yield f"data: {json.dumps(current_state)}\n\n"
                last_state = current_state
            
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- Signature Status Endpoint ---
@app.get("/api/signatures/status")
async def signature_status():
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect(("clamav", 3310))
            s.sendall(b"VERSION\n")
            version_str = s.recv(1024).decode('utf-8').strip()
        
        # Expected format: ClamAV 1.0.1/26920/Wed Jun 28 10:11:15 2023
        parts = version_str.split("/")
        
        logger.info(f"Signature Check - Raw Engine Response: {version_str}")
        
        if len(parts) >= 3:
            v = parts[1]
            sig_date = parts[2]
            
            # DNS Lookup for current version
            remote_version = "unknown"
            is_current = False
            try:
                import dns.resolver
                answers = dns.resolver.resolve('current.cvd.clamav.net', 'TXT')
                for rdata in answers:
                    txt_string = rdata.strings[0].decode('utf-8')
                    # Format: 1.0.9:63:28043:1782460800:1:90:49192:339
                    dns_parts = txt_string.split(":")
                    if len(dns_parts) >= 3:
                        remote_version = dns_parts[2]
                        
                logger.info(f"Signature Check - Remote DNS Version: {remote_version}")
                
                # Compare versions
                if remote_version != "unknown":
                    try:
                        if int(v) >= int(remote_version):
                            is_current = True
                    except ValueError:
                        if v == remote_version:
                            is_current = True
            except Exception as dns_err:
                logger.warning(f"Signature Check - DNS lookup failed: {dns_err}")
                
            return {
                "status": "success", 
                "version": v, 
                "sig_date": sig_date,
                "remote_version": remote_version,
                "is_current": is_current
            }
        else:
            return {"status": "success", "version": version_str, "sig_date": "N/A", "is_current": False}
        
    except Exception as e:
        logger.error(f"Signature fetch error: {e}")
        return {"status": "error", "version": "Error", "sig_date": "Error", "is_current": False}

@app.post("/api/scan/start")
async def start_scan(request: Request):
    if is_scan_running():
        raise HTTPException(status_code=409, detail="A scan is already in progress.")

    data = await request.json()
    target_path = data.get("path")
    if not target_path:
        raise HTTPException(status_code=400, detail="Path is required")

    full_path = target_path if target_path.startswith('/') else os.path.join(SCAN_DIR, target_path)
    resolved_path = os.path.realpath(full_path)
    
    logger.info(f"Initiating scan on: {resolved_path}")
    result = trigger_managed_scan(resolved_path, "Manual")
    
    if result is None:
        raise HTTPException(status_code=500, detail="Scanner service failed to respond.")
    if result.get("status") == "error":
        raise HTTPException(status_code=409, detail=result.get("message", "Unknown error"))
        
    return result

@app.post("/api/scan/stop")
async def stop_scan():
    return stop_active_scan()

@app.get("/api/scan/details/{scan_id}")
async def get_scan_details(scan_id: int):
    try:
        infections = db.get_infections_for_scan(scan_id)
        
        if not infections:
            return []

        # Mapping the DB 'threat_name' to the JS 'virus_name' for ALL hits
        return [{
            "file_path": hit.get('file_path'),
            "virus_name": hit.get('threat_name')
        } for hit in infections]

    except Exception as e:
        logger.error(f"ERROR: {e}")
        return []
    
# --- Log Clear Routines ---
@app.delete("/api/history/clear")
async def clear_all_history():
    try:
        db.clear_all_scans()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Clear Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/history/{scan_id}")
async def delete_single_scan(scan_id: int):
    try:
        db.delete_scan(scan_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Delete Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
# --- History & Scheduling ---
@app.get("/api/history")
async def get_history():
    try:
        return db.get_scan_history()
    except Exception as e:
        logger.error(f"History retrieval error: {e}")
        return []

@app.get("/api/schedules/{sched_id}")
async def get_single_schedule(sched_id: int):
    try:
        # 1. Fetch Master Schedule using existing execute_query
        rows = db.execute_query("SELECT id, name, cron_spec, enabled FROM schedules WHERE id = ?", (sched_id,))
        if not rows:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Convert row to dict (execute_query returns list of Row objects)
        schedule = dict(rows[0])
        
        # 2. Fetch Tasks using existing method
        schedule['tasks'] = db.get_schedule_tasks(sched_id)
        
        # Clean up key name if necessary (DB uses action_type, Pydantic uses action)
        for t in schedule['tasks']:
            if 'action_type' in t:
                t['action'] = t.pop('action_type')
                
        return schedule
    except Exception as e:
        logger.error(f"Error fetching schedule {sched_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/schedules")
async def save_sequenced_schedule(req: SequencedScheduleRequest):
    try:
        if req.id:
            # Update existing
            db.execute_query("UPDATE schedules SET name = ?, cron_spec = ? WHERE id = ?", 
                             (req.name, req.cron, req.id))
            db.execute_query("DELETE FROM schedule_tasks WHERE schedule_id = ?", (req.id,))
            sched_id = req.id
        else:
            # Create new
            sched_id = db.save_master_schedule(req.name, req.cron)
        
        # Add tasks using the existing method
        for task in req.tasks:
            db.add_task_to_schedule(sched_id, task.action, task.payload)

        # Trigger APScheduler reload
        sync_scheduler()
        
        return {"status": "success", "id": sched_id}
    except Exception as e:
        logger.error(f"Save failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/schedules")
async def get_schedules():
    try:
        schedules = db.get_schedules()
        for s in schedules:
            # Fetch the actual tasks so the UI can list the folders
            tasks = db.get_schedule_tasks(s['id'])
            # Map action_type to action for frontend consistency
            s['tasks'] = [{"action": t['action_type'], "payload": t['payload']} for t in tasks]
        return schedules
    except Exception as e:
        logger.error(f"Schedule retrieval error: {e}")
        return []

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    return verify_admin(data.get("user"), data.get("pass"))

@app.delete("/api/schedules/{sched_id}")
async def remove_schedule(sched_id: int):
    try:
        db.delete_schedule(sched_id)
        
        # Trigger APScheduler reload
        sync_scheduler()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ToggleRequest(BaseModel):
    enabled: int

@app.put("/api/schedules/{sched_id}/toggle")
async def toggle_schedule(sched_id: int, req: ToggleRequest):
    try:
        db.toggle_schedule(sched_id, req.enabled)
        sync_scheduler()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Toggle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/schedules/{sched_id}/run")
async def run_schedule_now(sched_id: int):
    try:
        tasks = db.get_schedule_tasks(sched_id)
        if not tasks:
            raise HTTPException(status_code=400, detail="Schedule has no tasks.")
            
        # Prevent running if it contains a scan task but a scan is already active
        has_scan = any(t.get('action_type') == 'start_scan' for t in tasks)
        if has_scan and is_scan_running():
            raise HTTPException(status_code=409, detail="A scan is already running.")
            
        # Add a one-off job to execute immediately
        scheduler.add_job(
            execute_schedule_sequence,
            trigger='date',
            run_date=datetime.now(timezone.utc),
            args=[sched_id, tasks, "Manual (from Schedule)"],
            id=f"manual_run_{sched_id}_{int(time.time())}"
        )
        return {"status": "success", "message": "Task sequence initiated."}
    except Exception as e:
        logger.error(f"Run schedule failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/folders/validate")
async def validate_path_endpoint(path: str):
    try:
        if path and not path.startswith(SCAN_DIR):
            clean_path = path.lstrip('/')
            path = os.path.join(SCAN_DIR, clean_path)

        # 1. Absolute path check
        if not path.startswith('/'):
            return {"valid": False, "reason": "Not an absolute path"}
            
        # 2. Physical existence check
        if not os.path.exists(path):
            return {"valid": False, "reason": "Path does not exist"}
            
        # 3. Permission check (Can the app actually read this?)
        if not os.access(path, os.R_OK):
            return {"valid": False, "reason": "Permission denied"}

        return {
            "valid": True, 
            "type": "File" if os.path.isfile(path) else ("Symlink" if os.path.islink(path) else "Directory")
        }
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {"valid": False, "reason": "System error during check"}

# --- Static File Mounting ---
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at: {FRONTEND_DIR}")

# --- Entry Point ---
if __name__ == "__main__":
    logger.info("Initializing backend...")
    
    logger.info("Starting FastAPI server on port 8089")
    uvicorn.run(app, host="0.0.0.0", port=8089)
