#!/usr/bin/env bash
# Daily backup (docs/deploy.md, 10.8): database dump + stored files, encrypted before leaving
# the container. Keeps 7 daily, 4 weekly (Sundays) and 3 monthly (1st day) archives locally,
# and copies the new archive off-site when BACKUP_RCLONE_REMOTE is set.
source /usr/local/bin/common.sh

stamp="$(date -u +%Y-%m-%d_%H%M%S)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

log "dumping database"
pg_dump --format=custom --no-owner --file="$work/database.dump"

log "copying stored files"
mkdir -p "$work/files"
rclone copy "$S3_REMOTE" "$work/files" --s3-no-check-bucket --quiet

cat > "$work/manifest.txt" <<MANIFEST
created_utc=$stamp
database=$PGDATABASE
bucket=$S3_BUCKET
files=$(find "$work/files" -type f | wc -l)
MANIFEST

archive="/backups/revisameta_${stamp}.tar.gpg"
tar -C "$work" -cf "$work/backup.tar" database.dump files manifest.txt
encrypt "$work/backup.tar" "$archive"
log "created $(basename "$archive") ($(du -h "$archive" | cut -f1))"

# Retention: keep the newest per day; then 7 daily, 4 weekly (Sunday), 3 monthly (day 01).
keep=$(
  ls -1 /backups/revisameta_*.tar.gpg 2>/dev/null | sort -r | awk -F'[_.]' '
    { day=$2; if (seen[day]++) next; days[++n]=day; file[day]=$0 }
    END {
      for (i=1; i<=n; i++) {
        d=days[i]; cmd="date -u -d " d " +%u"; cmd | getline dow; close(cmd)
        if (i<=7) print file[d]
        else if (dow==7 && weekly++<4) print file[d]
        else if (substr(d,9,2)=="01" && monthly++<3) print file[d]
      }
    }'
)
for f in /backups/revisameta_*.tar.gpg; do
  [ -e "$f" ] || continue
  grep -qxF "$f" <<<"$keep" || { log "pruning $(basename "$f")"; rm -f "$f"; }
done

if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  log "uploading to $BACKUP_RCLONE_REMOTE"
  rclone copy "$archive" "$BACKUP_RCLONE_REMOTE" --quiet
fi

if [ -n "${BACKUP_HEALTHCHECK_URL:-}" ]; then
  curl -fsS -m 10 --retry 3 "$BACKUP_HEALTHCHECK_URL" >/dev/null || log "healthcheck ping failed"
fi
log "backup finished"
