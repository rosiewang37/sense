#!/usr/bin/env bash
# TypeScript type checking for frontend
set -e
cd "$(dirname "$0")/../frontend"
echo "[hook] Running TypeScript type check..."
npx tsc -b
