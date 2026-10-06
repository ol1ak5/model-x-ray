#!/usr/bin/env bash
set -euo pipefail
uv run tools/measure_tool_calling.py --runs 10 --output docs/research/nemotron-tool-calling-results.md
