#!/usr/bin/env bash
# Regenerates stats-r/renv.lock inside the R base image (no local R needed).
set -euo pipefail
cd "$(dirname "$0")/../stats-r"

# Git Bash on Windows: keep paths as-is and use a Windows-style mount source.
export MSYS_NO_PATHCONV=1
src="$(pwd -W 2>/dev/null || pwd)"

docker build --target base -t revisameta-stats-r-base .
docker run --rm -v "$src:/app" -w /app revisameta-stats-r-base Rscript scripts/lock.R
echo "renv.lock updated."
