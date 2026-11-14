#!/usr/bin/env bash
# Fails if any commit message in the range mentions an AI assistant (CLAUDE.md 14.1, ADR-009).
# Usage: scripts/check-commit-messages.sh [revision range]   (default: whole history of HEAD)
set -euo pipefail
range="${1:-HEAD}"
pattern='anthropic|claude code|claude-session|claude\.(ai|com)/(code|session)|chatgpt|openai|copilot|generated with|🤖'

bad=0
while IFS= read -r -d $'\x1e' entry; do
  sha="${entry%%$'\x1f'*}"
  message="${entry#*$'\x1f'}"
  if grep -qiE "$pattern" <<<"$message"; then
    echo "Commit ${sha:0:10} mentions an AI assistant:" >&2
    grep -iE "$pattern" <<<"$message" | sed 's/^/    /' >&2
    bad=1
  fi
done < <(git log --format='%H%x1f%B%x1e' "$range")

if [ "$bad" -ne 0 ]; then
  exit 1
fi
echo "OK: no AI mentions in $(git rev-list --count "$range") commit messages."
