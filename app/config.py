"""Application configuration.

Configuration is driven by environment variables so no secrets are
hard-coded. The default class is selected unless an explicit config name
is provided to the application factory.
"""

import os

from dotenv import load_dotenv

# Load the project .env file before configuration classes are evaluated.
# No-op (or CLI-only) for Flask itself; this guarantees .env is loaded for
# any entry point: python run.py, flask run, gunicorn, pytest.
load_dotenv()


def _env_flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


class BaseConfig:
    """Shared configuration across all environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Uploads are stored outside public static directory and served
    # through protected routes (implemented in a later phase).
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "instance/uploads")

    # Security defaults.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL", "sqlite:///:memory:"
    )
    WTF_CSRF_ENABLED = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = _env_flag("SESSION_COOKIE_SECURE", default=True)


_CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name: str | None = None):
    """Return a configuration class by name or the default (dev) class."""
    name = (config_name or os.getenv("FLASK_CONFIG") or "development").lower()
    return _CONFIG_BY_NAME.get(name, DevelopmentConfig)


def validate_production_config(app, config_name: str | None = None) -> None:
    """Refuse to start production without usable SECRET_KEY and DATABASE_URL.

    An empty secret key silently breaks session signing and secure
    cookies, and an empty database URI only crashes on the first query
    with a cryptic error, so production must fail fast instead of booting
    in a broken and insecure state.
    """
    name = (config_name or os.getenv("FLASK_CONFIG") or "development").lower()
    if name != "production":
        return
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY must be set when running with the production "
            "configuration."
        )
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError(
            "DATABASE_URL must be set when running with the production "
            "configuration."
        )