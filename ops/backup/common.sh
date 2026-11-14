#!/usr/bin/env bash
# Shared settings for backup.sh and restore.sh (run inside the backup container).
set -euo pipefail

: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is not set}"
: "${S3_BUCKET:?S3_BUCKET is not set}"
export PGHOST="${PGHOST:-postgres}" PGUSER="${POSTGRES_USER}" PGPASSWORD="${POSTGRES_PASSWORD}" PGDATABASE="${POSTGRES_DB}"

if [ "${BACKUP_PASSPHRASE}" = "change-me" ]; then
  echo "Refusing to run: set a real BACKUP_PASSPHRASE in .env" >&2
  exit 1
fi

# Storage (RustFS/S3) as an rclone connection string; no config file needed.
S3_REMOTE=":s3,provider=Other,env_auth=false,endpoint='${S3_ENDPOINT:-http://storage:9000}',access_key_id='${S3_ACCESS_KEY}',secret_access_key='${S3_SECRET_KEY}':${S3_BUCKET}"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

encrypt() { # in out
  printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --quiet --pinentry-mode loopback \
    --passphrase-fd 0 --symmetric --cipher-algo AES256 --compress-algo none -o "$2" "$1"
}

decrypt() { # in out
  printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --quiet --pinentry-mode loopback \
    --passphrase-fd 0 --decrypt -o "$2" "$1"
}
