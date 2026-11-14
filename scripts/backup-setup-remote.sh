#!/usr/bin/env bash
# One-time interactive setup of the off-site destination (e.g. Google Drive) for backups.
# Credentials are stored in ops/rclone/rclone.conf, which is git-ignored.
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash: keep container paths as-is
cd "$(dirname "$0")/.."
mkdir -p ops/rclone
docker compose --profile ops build backup >/dev/null
docker compose --profile ops run --rm --entrypoint rclone backup config
