"""Vercel production WSGI entry point.

Exposes the top-level ``app`` object that Vercel's Flask framework preset
loads at the project root (Vercel requires a direct top-level ``app``
assignment to detect the Flask application). The production configuration
is the default so deployment fails fast without a SECRET_KEY or DATABASE_URL.
"""

import os

from app import create_app

app = create_app(os.environ.get("FLASK_CONFIG", "production"))