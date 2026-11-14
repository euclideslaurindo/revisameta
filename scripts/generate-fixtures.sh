#!/usr/bin/env bash
# Regenerates the statistical reference fixtures by running R inside the stats-r
# container (values are never written by hand; docs/validacao.md, 11.1).
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
docker compose build stats-r
fixtures="$(pwd -W 2>/dev/null || pwd)/stats-r/fixtures"
docker compose run --rm --no-deps --user "0" -v "$fixtures:/app/fixtures" stats-r sh -c '
  for script in fixtures/scripts/*.R; do Rscript "$script"; done
'
