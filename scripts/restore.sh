#!/usr/bin/env bash
# Restores a backup from ./backups. REPLACES the current database and stored files.
# Usage: scripts/restore.sh revisameta_<stamp>.tar.gpg [--yes]
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash: keep container paths as-is
cd "$(dirname "$0")/.."
archive="${1:?usage: scripts/restore.sh <archive in ./backups> [--yes]}"
archive="$(basename "$archive")"
[ -f "backups/$archive" ] || { echo "Not found: backups/$archive" >&2; exit 1; }

if [ "${2:-}" != "--yes" ]; then
  read -r -p "This replaces ALL current data with $archive. Type 'restaurar' to continue: " answer
  [ "$answer" = "restaurar" ] || { echo "Cancelled."; exit 1; }
fi

docker compose --profile ops build backup >/dev/null
echo "Stopping backend and worker during the restore..."
docker compose stop backend worker
status=0
docker compose --profile ops run --rm --entrypoint /usr/local/bin/restore.sh backup "$archive" || status=$?
docker compose up -d backend worker
exit $status
