"""Vercel production WSGI entry point.

Exposes the top-level ``app`` object that Vercel's Flask framework preset
loads at the project root. The production configuration is the default so
deployment fails fast without a SECRET_KEY or DATABASE_URL. If application
creation fails, a minimal fallback app renders the failure reason instead
of Vercel's generic 500 page.
"""

import os

from app import create_app


def _startup_error_app(exc: Exception):
    """Return a minimal Flask app that reports a startup failure."""
    from flask import Flask

    fallback = Flask(__name__)

    @fallback.route("/", defaults={"path": ""})
    @fallback.route("/<path:path>")
    def _report(path):
        lines = [
            "CRMS failed to start.",
            "",
            f"{type(exc).__name__}: {exc}",
            "",
            "Check SECRET_KEY and DATABASE_URL in the Vercel production "
            "environment variables, then redeploy. See the Vercel function "
            "logs for the full traceback.",
        ]
        return "\n".join(lines), 503

    return fallback


try:
    app = create_app(os.environ.get("FLASK_CONFIG", "production"))
except Exception as exc:
    app = _startup_error_app(exc)