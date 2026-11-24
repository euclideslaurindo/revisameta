#!/usr/bin/env bash
# Interface tests (Playwright) against the running stack (docker compose up -d).
# Creates verified test accounts under example.org with a random password (never
# committed), a fresh demonstration project, then runs e2e/ in the official Playwright
# image sharing Caddy's network. Report: e2e/report/index.html.
# Usage: scripts/test-e2e.sh [playwright args, e.g. tests/grade.spec.ts]
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
root="$(pwd -W 2>/dev/null || pwd)"
image="mcr.microsoft.com/playwright:v1.65.0-noble"
password="e2e-$(openssl rand -hex 12)"
users="e2e.a@example.org,e2e.b@example.org,e2e.c@example.org,e2e.d@example.org"

demo_id="$(docker compose run --rm --no-deps -v "$root/stats-r/fixtures:/stats-fixtures:ro" backend \
  python -m app.scripts.e2e_users --password "$password" --demo ${users//,/ } | tail -1 | tr -d '\r')"
echo "demonstration project: $demo_id"

caddy="$(docker compose ps -q caddy)"
docker run --rm --network "container:$caddy" \
  -v "$root/e2e:/e2e" -v "$root/stats-r/fixtures:/fixtures:ro" \
  -v "$root/frontend/public/i18n:/i18n:ro" -w /e2e \
  -e E2E_USERS="$users" -e E2E_PASSWORD="$password" -e E2E_DEMO_ID="$demo_id" \
  "$image" sh -c "npm ci --no-audit --no-fund >/dev/null && npx playwright test $*"
