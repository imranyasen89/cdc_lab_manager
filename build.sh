#!/usr/bin/env bash
# build.sh — Production build script (Render / Railway)
# For Vercel, use api/index.py as the entry point instead.

set -o errexit  # Exit on error

pip install -r requirements.txt

# Run database migrations if migrations directory exists
if [ -d "migrations" ]; then
    echo "Running database migrations against Supabase..."
    python -m flask db upgrade
else
    echo "No migrations directory found. Creating tables directly..."
    python -c "from app import create_app, db; app = create_app(); app.app_context().__enter__(); db.create_all(); print('Database tables created.')"
fi
