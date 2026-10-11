#!/usr/bin/env bash
set -euo pipefail
uv run tools/benchmark.py --setups all --workers 6 --output docs/benchmark-results.json --report docs/benchmark.md
