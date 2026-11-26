#!/usr/bin/env bash
# Creates an already-confirmed account with a temporary password (no e-mail needed).
# Usage: scripts/create-user.sh someone@example.org "Full name"
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
email="${1:?usage: scripts/create-user.sh <e-mail> \"<full name>\"}"
name="${2:?usage: scripts/create-user.sh <e-mail> \"<full name>\"}"
docker compose run --rm --no-deps backend python -m app.scripts.create_user --email "$email" --name "$name"
