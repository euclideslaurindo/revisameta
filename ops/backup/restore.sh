#!/usr/bin/env bash
# Restores an archive made by backup.sh: replaces the database and the stored files.
# Usage (inside the container): restore.sh revisameta_<stamp>.tar.gpg
source /usr/local/bin/common.sh

archive="/backups/$(basename "${1:?usage: restore.sh <archive name in ./backups>}")"
[ -f "$archive" ] || { echo "Archive not found: $archive" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

log "decrypting $(basename "$archive")"
decrypt "$archive" "$work/backup.tar"
tar -C "$work" -xf "$work/backup.tar"
cat "$work/manifest.txt"

log "restoring database"
pg_restore --clean --if-exists --no-owner --single-transaction --dbname="$PGDATABASE" "$work/database.dump"

log "restoring stored files"
rclone sync "$work/files" "$S3_REMOTE" --s3-no-check-bucket --quiet
log "restore finished"
