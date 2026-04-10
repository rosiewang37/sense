#!/usr/bin/env bash
# Run backend pytest suite
set -e
cd "$(dirname "$0")/../backend"
echo "[hook] Running Python tests..."
pytest tests/ -v --tb=short
