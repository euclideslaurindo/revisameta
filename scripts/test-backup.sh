#!/usr/bin/env bash
# Backup/restore drill on the running stack (exit criterion of Etapa 0, docs/deploy.md 10.8).
# 1. records the current state, 2. backs up, 3. changes data, 4. restores, 5. compares.
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash: keep container paths as-is
cd "$(dirname "$0")/.."

psql() { docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$0"' "$1"; }
s3() { # rclone <command> on <path in the bucket> [extra args]
  docker compose --profile ops run --rm -T --entrypoint bash backup -c     "source /usr/local/bin/common.sh; rclone $1 \"\$S3_REMOTE/$2\" --s3-no-check-bucket ${3:-}" 2>/dev/null
}
state() { echo "users=$(psql 'select count(*) from users') projects=$(psql 'select count(*) from projects') audit=$(psql 'select count(*) from audit_log') files=$(s3 lsf '' '-R --files-only' | wc -l)"; }

docker compose --profile ops build backup >/dev/null
docker compose --profile ops run --rm -T --entrypoint bash backup -c   "source /usr/local/bin/common.sh; printf 'drill marker' | rclone rcat \"\$S3_REMOTE/drill/marker.txt\" --s3-no-check-bucket" 2>/dev/null

before="$(state)"
echo "before backup:  $before"
scripts/backup.sh
archive="$(ls -1t backups/revisameta_*.tar.gpg | head -1)"

echo "changing data after the backup..."
psql "update projects set title = title || ' (changed)'" >/dev/null
psql "insert into users (id, name, email, password_hash, is_active, is_system_admin, ui_language, created_at, updated_at, version) values (gen_random_uuid(), 'Drill', 'drill@example.org', 'x', true, false, 'pt-BR', now(), now(), 1)" >/dev/null
s3 deletefile drill/marker.txt
echo "after changes:  $(state)"

scripts/restore.sh "$(basename "$archive")" --yes
after="$(state)"
echo "after restore:  $after"

changed=$(psql "select count(*) from projects where title like '% (changed)'")
marker=$(s3 cat drill/marker.txt)
s3 deletefile drill/marker.txt
if [ "$before" = "$after" ] && [ "$changed" = "0" ] && [ "$marker" = "drill marker" ]; then
  echo "BACKUP DRILL OK: data after restore matches the backup"
else
  echo "BACKUP DRILL FAILED" >&2
  exit 1
fi
