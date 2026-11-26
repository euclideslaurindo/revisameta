#!/usr/bin/env bash
# Makes an existing account a system administrator (users, quotas and status page).
# Usage: scripts/make-admin.sh someone@example.org [--remove]
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
email="${1:?usage: scripts/make-admin.sh <e-mail of an existing account> [--remove]}"
shift
docker compose run --rm --no-deps backend python -m app.scripts.make_admin --email "$email" "$@"
