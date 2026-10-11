#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d frontend/node_modules ]; then
  npm --prefix frontend install
fi

set -m
scripts/serve.sh &
api=$!
trap 'kill -- -"$api" 2>/dev/null || true' EXIT

echo "API    http://localhost:8000/docs"
echo "App    http://localhost:5173"
npm --prefix frontend run dev
