#!/usr/bin/env bash
# Binds to 127.0.0.1 only: schema dumps never leave this machine.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
exec .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port "${PORT:-8765}" --no-access-log
