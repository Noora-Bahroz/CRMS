"""Shared pytest fixtures.

Provides a Flask application and client configured for testing. Extended
with model/database fixtures in the feature phase.
"""

import pytest


@pytest.fixture(scope="session")
def app():
    """Create the application with the testing configuration."""
    from app import create_app

    flask_app = create_app("testing")
    yield flask_app


@pytest.fixture()
def client(app):
    """Provide a test client for the application."""
    return app.test_client()


@pytest.fixture()
def app_context(app):
    """Provide an application context for unit-level tests."""
    with app.app_context():
        yield