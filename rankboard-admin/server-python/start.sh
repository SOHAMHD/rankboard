#!/usr/bin/env bash
# Production start for the RankBoard Python API.
#
#   - Binds the platform's $PORT (Render injects it), falling back to 4000
#     locally — never a hardcoded port.
#   - No --reload (that's a dev-only convenience and reloads on file changes).
#   - DEBUG is explicitly unset so /docs, /redoc and /openapi.json stay OFF in
#     production regardless of the inherited environment.
#   - JWT_SECRET is NOT defaulted here on purpose: app/config.py fails fast if
#     it's missing, which is what we want.
#
# Render start command:  bash start.sh   (or ./start.sh after `chmod +x`)
set -euo pipefail

# Run from this script's folder so `app.main` resolves no matter where it's
# invoked from.
cd "$(dirname "$0")"

unset DEBUG

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-4000}"
