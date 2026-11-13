#!/usr/bin/env bash
# Lint, type-check and test the backend inside containers (no local Python needed).
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --profile test build backend-test
status=0
docker compose --profile test run --rm backend-test \
  sh -c "ruff check . && ruff format --check . && mypy app && pytest" || status=$?
docker compose --profile test rm -sf postgres-test redis-test storage-test >/dev/null
exit $status
