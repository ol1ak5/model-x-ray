#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

runner=npm
if command -v bun >/dev/null 2>&1; then
  runner=bun
fi

if [ ! -d frontend/node_modules ]; then
  if [ "$runner" = bun ]; then
    (cd frontend && bun install)
  else
    npm --prefix frontend install
  fi
fi

set -m
scripts/serve.sh &
api=$!
trap 'kill -- -"$api" 2>/dev/null || true' EXIT

echo "API    http://localhost:8000/docs"
echo "App    http://localhost:5173 (via $runner)"
if [ "$runner" = bun ]; then
  (cd frontend && bun run dev)
else
  npm --prefix frontend run dev
fi
