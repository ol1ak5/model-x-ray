#!/usr/bin/env bash
set -euo pipefail
uv run tools/benchmark.py --setups all --output docs/benchmark-results.json
