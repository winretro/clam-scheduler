# ClamAV Scheduler

> A complete web-based GUI client, persistent scheduling engine, and management layer for the ClamAV Docker ecosystem.

## System Overview

ClamAV Scheduler provides a fully featured graphical user interface (GUI) accessible via your web browser to manage and monitor a containerized ClamAV daemon. It replaces command-line operations with a visual dashboard, persistent SQLite-backed task scheduling, and real-time scan reporting. Designed for strict environment segregation, it relies on direct host-to-container timezone mapping and dynamic log routing to maintain operational integrity without polluting the host environment.

## 1. Architectural Stack

* **Backend System:** Python FastAPI (Asynchronous routing)
* **Frontend Interface:** Native HTML/CSS/JS Web GUI (Zero-dependency, responsive dashboard)
* **Task Engine:** APScheduler (Persistent job queues)
* **Scanner Daemon:** ClamAV (Cisco Talos)
* **Database:** SQLite (State, scan history, and configuration persistence)

### Topology

```text
[ Host OS ] <===( Mount )===> [ Scanner Container ] <===( API )===> [ Backend Container ]
    |                               |                                      |
  Target                         clamd / freshclam                 FastAPI / Web GUI
```

## 2. Prerequisites

* Docker Engine (v20.10+)
* Docker Compose (v2.0+)
* Valid `PUID` and `PGID` mapped to the host filesystem to ensure correct read/write permissions for scanning.

## 3. Environment Configuration

The application is strictly governed by the runtime environment. A template is provided in the repository.

**Do not commit your `.env` file to version control.**

### `.env` Reference

| Variable | Type | Description | Example | 
 | ----- | ----- | ----- | ----- | 
| `PUID` | Integer | Host User ID for permission mapping. | `1000` | 
| `PGID` | Integer | Host Group ID for permission mapping. | `1000` | 
| `HOST_UI_PORT` | Integer | The external port exposed for the web interface. | `8089` | 
| `TZ` | String (ISO) | Host timezone. **Critical** for accurate scheduler execution. | `Pacific/Auckland` | 
| `LOG_LEVEL` | String | Sets backend verbosity (`INFO` or `DEBUG`). | `INFO` | 
| `HOST_SCAN_TARGET` | Path | Absolute path to the host directory targeted for scanning. | `/mnt/nas/data` | 

## 4. Deployment Initialization

The containerized environment operates on a strictly decoupled configuration. Initializing the application requires setting the environment before boot.

### Step 1: Environment Setup

```bash
# Clone the repository
git clone https://github.com/winretro/clam-scheduler.git
cd clam-scheduler

# Generate the local configuration file
cp .env.example .env

# Edit the environment variables to match your host topology
nano .env 
```

*Note for Windows Hosts: When defining `HOST_SCAN_TARGET`, ensure you use forward slashes (`/`) instead of backslashes.*

### Step 2: Build and Deploy

```bash
# Build and bring the stack online in a detached state
docker compose up -d --build

# Note: If the TZ variable is changed post-build, a container re-evaluation is required to update the internal clock
docker compose up -d --force-recreate
```

### Step 3: Application Initialization

Navigate to `http://localhost:8089` in your web browser to access the GUI. Or the port you set in the .env file (HOST_UI_PORT).

Upon first launch, the system will intercept the connection and trigger the **Auth-Initialization Routine**. Administrator credentials are cryptographically hashed and committed to the persistent database volume on this first boot.

## 5. Diagnostic Logging

The backend utilizes standardized Python logging mapped to standard output. Log verbosity is controlled entirely via the `LOG_LEVEL` environment variable.

* `INFO`: Standard production mode. Outputs job execution states, critical system failures, and `[DIAGNOSIS] !!! INFECTION:` alerts.
* `DEBUG`: Troubleshooting mode. Outputs raw pyclamd payload strings, APScheduler evaluations, and routine HTTP traffic.

**To trigger a diagnostic trace:**

1. Change `LOG_LEVEL=DEBUG` in your `.env` file.
2. Restart the backend container: `docker compose restart antivirus-gui`
3. Follow the trace: `docker logs -f antivirus-gui`

## 6. License

Distributed under the MIT License. Copyright (C) 2026 Robert Wingrove