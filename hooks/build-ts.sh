#!/usr/bin/env bash
# Build frontend (TypeScript compile + Vite bundle)
set -e
cd "$(dirname "$0")/../frontend"
echo "[hook] Building frontend..."
npm run build
