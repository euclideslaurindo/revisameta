#!/usr/bin/env bash
# Run testthat and lintr for the R statistics service inside its container.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose build stats-r
docker compose run --rm --no-deps stats-r Rscript -e '
  testthat::test_dir("tests/testthat", reporter = "summary", stop_on_failure = TRUE)
  lints <- lintr::lint_dir(".")
  print(lints)
  if (length(lints) > 0) quit(status = 1)
'
