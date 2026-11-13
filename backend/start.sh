#!/usr/bin/env bash
# Start the Hollandse Luchten backend API server.
# No environment variables needed — data path is auto-detected from the repo layout.
set -e
cd "$(dirname "$0")"
exec ../hollandseluchten/backend/.venv/bin/uvicorn app.main:app --reload --port 8000
