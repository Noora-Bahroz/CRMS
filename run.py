"""Local development entry point for the CRMS Flask application.

The production WSGI entry point is `app:create_app`; this module is used
only for local development convenience.
"""

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)