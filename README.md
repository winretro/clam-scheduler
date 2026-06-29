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

The containerized environment operates on a strictly decoupled configuration and utilizes a pre-built image from the GitHub Container Registry. Initializing the application requires setting the environment before boot. Choose the deployment method that fits your environment.

### Method 1: Docker Managers (Dockge / Portainer)

This method is recommended for users who prefer graphical stack management.

1. Create a new stack in your Docker manager (e.g., Dockge or Portainer).
2. Copy the contents of the `docker-compose.yml` file from this repository and paste it into the stack editor.
3. Configure your environment variables (`PUID`, `PGID`, etc.) using the provided GUI or by creating a `.env` file in the stack directory (referencing the template above).
   *Note for Windows Hosts: When defining `HOST_SCAN_TARGET`, ensure you use forward slashes (`/`) instead of backslashes.*
4. Click **Deploy** in your Docker manager. It will automatically pull the pre-built image and start the stack.
5. **Updates:** To update the application in the future, simply click the **Update** button in your manager to pull the latest image layer from GHCR and recreate the container.

### Method 2: Standard CLI Deployment

This method provides a clean, non-fragile command-line deployment without needing to clone the entire repository.

1. Create a new directory for your deployment and navigate into it:
   ```bash
   mkdir clam-scheduler && cd clam-scheduler
   ```
2. Download the required configuration files (replace URL with actual repository URL if different):
   ```bash
   curl -O https://raw.githubusercontent.com/winretro/clam-scheduler/main/docker-compose.yml
   curl -o .env https://raw.githubusercontent.com/winretro/clam-scheduler/main/.env.example
   ```
3. Edit the `.env` file to configure your environment variables (referencing the template above).
   *Note for Windows Hosts: When defining `HOST_SCAN_TARGET`, ensure you use forward slashes (`/`) instead of backslashes.*
4. Start the stack:
   ```bash
   docker compose up -d
   ```
5. **Updates:** To update the application, simply pull the latest image and restart:
   ```bash
   docker compose pull && docker compose up -d
   ```

### Application Initialization

Navigate to `http://localhost:8089` in your web browser to access the GUI. Or the port you set in the .env file (`HOST_UI_PORT`).

Upon first launch, the system will intercept the connection and trigger the **Auth-Initialization Routine**. Administrator credentials are cryptographically hashed and committed to the persistent database volume on this first boot.

## 5. Diagnostic Logging

The backend utilizes standardized Python logging mapped to standard output. Log verbosity is controlled entirely via the `LOG_LEVEL` environment variable.

* `INFO`: Standard production mode. Outputs job execution states, critical system failures, and `[DIAGNOSIS] !!! INFECTION:` alerts.
* `DEBUG`: Troubleshooting mode. Outputs raw pyclamd payload strings, APScheduler evaluations, and routine HTTP traffic.

**To trigger a diagnostic trace:**

1. Change `LOG_LEVEL=DEBUG` in your `.env` file.
2. Restart the backend container: `docker compose restart antivirus-gui`
3. Follow the trace: `docker logs -f antivirus-gui`

## 6. Developer Update Workflow

Because of the GitHub Actions CI/CD pipeline, deploying a new version of the application is fully automated. As a maintainer, you do not need to manually compile or upload Docker images. 

To release a new version:
1. Make your code changes locally.
2. Commit and push your changes to the `main` branch:
   ```bash
   git add .
   git commit -m "Your commit message"
   git push origin main
   ```
3. GitHub's servers will automatically intercept the push, compile the new Docker image, and publish it to the GitHub Container Registry (GHCR) in the background. Users can then pull the update using the methods described in Section 4.

## 7. License

Distributed under the MIT License. Copyright (C) 2026 Robert Wingrove