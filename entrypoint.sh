#!/bin/bash
set -e

# Default to 1000 if not set
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Setting permissions on /app/data to $PUID:$PGID..."
mkdir -p /app/data
chown -R $PUID:$PGID /app/data

# Drop privileges and execute the passed command
echo "Starting application..."
exec gosu $PUID:$PGID "$@"
