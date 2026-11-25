#!/usr/bin/env bash
# build.sh — Production build script (Render / Railway)
# Vercel does not use this script; it runs run:app (see pyproject.toml [tool.vercel]).

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
