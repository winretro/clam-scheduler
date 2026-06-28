import os
import json
from .logger import logger

# --- VENDOR PATHING ---
current_dir = os.path.dirname(os.path.abspath(__file__))
AUTH_FILE = os.path.join(current_dir, "..", "data", "users.json")

def is_setup_complete():
    if not os.path.exists(AUTH_FILE):
        return False
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
            return bool(data.get("username") and data.get("password"))
    except Exception:
        return False

def verify_token(token: str) -> bool:
    """
    Checks if the provided token is valid. 
    Modify this to query your database/file store where sessions are saved.
    """
    # FOR NOW: Check if the token matches a known valid state
    try:
        return token is not None and len(token) > 5 
    except Exception:
        return False

def save_credentials(username, password):
    os.makedirs(os.path.dirname(AUTH_FILE), exist_ok=True)
    with open(AUTH_FILE, "w") as f:
        json.dump({"username": username, "password": password}, f)

def verify_admin(username, password):
    if not is_setup_complete():
        return {"auth": False, "isAdmin": False, "error": "Setup not complete"}
    
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
            if data.get("username") == username and data.get("password") == password:
                logger.debug(f"Auth Success: User={username}")
                return {"auth": True, "isAdmin": True, "SID": "local-docker-session"}
    except Exception as e:
        logger.error(f"Auth read error: {e}")
        
    return {"auth": False, "isAdmin": False, "error": "Invalid username or password"}
