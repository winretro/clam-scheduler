# ClamAV Scheduler

> A GUI client, persistent scheduling engine, and management layer for the ClamAV Docker ecosystem.

## 1. Architectural Stack

- **Backend:** Python FastAPI
- **Frontend:** Native HTML/CSS/JS
- **Task Engine:** APScheduler
- **Scanner:** ClamAV (Cisco Talos)
- **Database:** SQLite

## 2. Prerequisites

- Docker Engine (v20.10+)
- Docker Compose (v2.0+)

## 3. Configuration

All configuration is managed directly within the `docker-compose.yml` file. Update the `environment:` block under each service to match your host requirements.

| Variable | Description | Example |
| :--- | :--- | :--- |
| `PUID` | Host User ID for permission mapping. | `568` |
| `PGID` | Host Group ID for permission mapping. | `568` |
| `HOST_UI_PORT` | The external port exposed for the web interface. | `8089` |
| `TZ` | Host timezone (must be valid IANA string). | `Pacific/Auckland` |
| `LOG_LEVEL` | Backend verbosity (`INFO` or `DEBUG`). | `INFO` |
| `HOST_SCAN_TARGET` | Absolute path to the host directory for scanning. | `/mnt/data` |

## 4. Deployment Initialization

### Method 1: Docker Managers (Dockge / Portainer)

1. Create a new stack in your manager.
2. Copy the contents of `docker-compose.yml` into the editor.
3. Edit the values directly in the `environment:` section for both services.
4. Click **Deploy**.

### Method 2: Standard CLI Deployment

This method uses standard Linux tools to manage your configuration in-place.

1. Create and enter your deployment directory:

   ```bash
   mkdir clam-scheduler && cd clam-scheduler
   ```

2. Download the configuration:

   ```bash
   curl -O https://raw.githubusercontent.com/winretro/clam-scheduler/main/docker-compose.yml
   ```

3. Edit the configuration file using a terminal-based editor (e.g., nano):

   ```bash
   nano docker-compose.yml
   ```

4. Modify the `environment:` values as needed. Save and exit (in nano: `Ctrl+O`, `Enter`, `Ctrl+X`).

5. Start the stack:

   ```bash
   docker compose up -d
   ```

### Updates

To update, simply pull the latest image and restart:

```bash
docker compose pull && docker compose up -d
```

## 5. Diagnostic Logging

To change log verbosity, edit the `LOG_LEVEL` variable in `docker-compose.yml` and restart the services.

Edit the configuration:

```bash
nano docker-compose.yml
```

Change `LOG_LEVEL` to `DEBUG`.

Apply the changes:

```bash
docker compose up -d
```

Follow the logs:

```bash
docker compose logs -f antivirus-gui
```

## 6. Developer Update Workflow

GitHub Actions handles the image build process automatically.

Commit and push your changes to `main`:

```bash
git add .
git commit -m "Update"
git push origin main
```

The image will be compiled and pushed to GHCR automatically. Users can then update via:

```bash
docker compose pull && docker compose up -d
```

## 7. License

Distributed under the MIT License.

Copyright (C) 2026 Robert Wingrove