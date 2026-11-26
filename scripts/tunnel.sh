#!/usr/bin/env bash
# Exposes the local system through a Cloudflare quick tunnel (docs/deploy.md, F0).
#
#   scripts/tunnel.sh start   -> starts the tunnel, prints the https address and points
#                                the backend at it (links in e-mails, CORS, signed upload
#                                URLs, secure cookie). Your .env is not changed.
#   scripts/tunnel.sh stop    -> stops the tunnel and goes back to localhost only.
#   scripts/tunnel.sh url     -> prints the current address.
#
# The quick tunnel is free and needs no account, but the address changes on every
# start, and it only works while this computer is on. It does not carry SSE, so job
# progress falls back to polling (already built in).
set -euo pipefail
cd "$(dirname "$0")/.."

current_url() {
  docker compose --profile tunnel logs tunnel 2>/dev/null \
    | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1
}

restart_backend() {
  docker compose up -d --force-recreate backend worker >/dev/null
}

case "${1:-start}" in
  start)
    docker compose --profile tunnel up -d --force-recreate tunnel >/dev/null
    url=""
    for _ in $(seq 1 30); do
      url="$(current_url || true)"
      [ -n "$url" ] && break
      sleep 2
    done
    if [ -z "$url" ]; then
      echo "The tunnel did not give an address. See: docker compose --profile tunnel logs tunnel" >&2
      exit 1
    fi
    host="${url#https://}"
    cat > .env.tunnel <<EOF
# Written by scripts/tunnel.sh start; removed by scripts/tunnel.sh stop. Do not commit.
APP_BASE_URL=$url
ALLOWED_HOSTS=localhost,127.0.0.1,$host
CORS_ORIGINS=http://localhost:8080,$url
S3_PUBLIC_ENDPOINT=$url
COOKIE_SECURE=true
EOF
    restart_backend
    echo "Tunnel up: $url"
    echo "Open it on any device. It works while this computer is on; the address changes"
    echo "the next time the tunnel starts."
    ;;
  stop)
    docker compose --profile tunnel stop tunnel >/dev/null 2>&1 || true
    docker compose --profile tunnel rm -f tunnel >/dev/null 2>&1 || true
    rm -f .env.tunnel
    restart_backend
    echo "Tunnel stopped; the system answers on http://localhost:8080 only."
    ;;
  url)
    url="$(current_url || true)"
    if [ -n "$url" ] && [ -f .env.tunnel ]; then echo "$url"; else echo "No tunnel running."; fi
    ;;
  *)
    echo "usage: scripts/tunnel.sh [start|stop|url]" >&2
    exit 2
    ;;
esac
