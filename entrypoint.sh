#!/bin/bash
set -e

# 1. Update Debian system timezone if TZ variable is provided
if [ -n "$TZ" ] && [ -f "/usr/share/zoneinfo/$TZ" ]; then
    echo "Setting OS timezone to $TZ..."
    ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime
    echo "$TZ" > /etc/timezone
    # This line is strictly required by Debian to apply the timezone system-wide
    export DEBIAN_FRONTEND=noninteractive
    dpkg-reconfigure -f noninteractive tzdata
fi

# 2. Default to 1000 if not set
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Setting permissions on /app/data to $PUID:$PGID..."
mkdir -p /app/data
chown -R $PUID:$PGID /app/data

# 3. Drop privileges and execute the passed command
echo "Starting application..."
exec gosu $PUID:$PGID "$@"