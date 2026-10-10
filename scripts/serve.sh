#!/usr/bin/env bash
set -euo pipefail
uv run uvicorn model_x_ray.server:app_from_env --factory --port 8000
