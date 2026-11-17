#!/usr/bin/env bash
# Creates a demonstration project with the public dataset dat.normand1999 for an
# existing user (docs/modulos.md 7.11). Usage: scripts/seed-demo.sh someone@example.org
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
email="${1:?usage: scripts/seed-demo.sh <e-mail of an existing user>}"
fixtures="$(pwd -W 2>/dev/null || pwd)/stats-r/fixtures"
docker compose run --rm --no-deps -v "$fixtures:/stats-fixtures:ro" backend \
  python -m app.scripts.seed_demo --email "$email"
