#!/usr/bin/env bash
# Daily sync for Marketing Data Hub - run by cron on macOS/Linux.
# Portable: finds the repo from this script's own location.
# Logs to logs/sync.log.
#
# Install as a cron job (6am daily), e.g.:
#   crontab -e
#   0 6 * * * /path/to/marketing-data-hub/scripts/sync_daily.sh
set -euo pipefail
HUB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
mkdir -p "$HUB_DIR/logs"
{
  echo "[$(date)] sync starting"
  "$PYTHON" -m hub.cli sync all --config "$HUB_DIR/config.yaml"
  echo "[$(date)] sync finished with exit code $?"
} >> "$HUB_DIR/logs/sync.log" 2>&1
