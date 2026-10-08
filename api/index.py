"""
Vercel WSGI entry point for CDC Lab Manager Flask application.
Vercel serverless Python runtime looks for the top-level 'app' callable.
"""
import sys
import os
import traceback

# Ensure the project root is on the Python path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from app import create_app
    app = create_app()
except Exception as e:
    print("FATAL ERROR during Flask app initialization:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    raise
