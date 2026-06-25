#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
PYTHON="${HSMT_PYTHON:-python}"
if [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python; fi
exec "$PYTHON" -m uvicorn app:app --host "${HSMT_WEB_HOST:-0.0.0.0}" --port "${HSMT_WEB_PORT:-8004}"
