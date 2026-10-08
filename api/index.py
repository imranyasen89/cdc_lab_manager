"""
Vercel WSGI entry point for CDC Lab Manager Flask application.
Vercel runs serverless Python functions — this file exposes the Flask app
as a WSGI handler that Vercel's @vercel/python runtime can invoke.
"""
import sys
import os

# Ensure the project root is on the Python path so imports work correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

# Create the Flask application instance
app = create_app()

# Vercel looks for a callable named 'app' or 'handler'
# Flask's app object is itself a WSGI callable — no wrapper needed
