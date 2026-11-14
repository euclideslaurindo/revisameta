#!/usr/bin/env bash
# Encrypted backup of the database and stored files into ./backups (and off-site if configured).
# Schedule it daily: Task Scheduler on Windows or cron on Linux (docs/deploy.md).
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash: keep container paths as-is
cd "$(dirname "$0")/.."
mkdir -p backups ops/rclone
docker compose --profile ops build backup >/dev/null
docker compose --profile ops run --rm backup
