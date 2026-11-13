#!/usr/bin/env bash
# Writes frontend/openapi.json from the backend and regenerates the Angular API client.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --profile test build backend-test >/dev/null
docker compose --profile test run --rm --no-deps -e APP_ENV=test backend-test \
  python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2, ensure_ascii=False))" \
  > frontend/openapi.json
(cd frontend && npm run api)
