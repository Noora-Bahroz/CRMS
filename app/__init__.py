"""CRMS application package.

Exposes the create_app application factory used for both local development
(run.py) and production WSGI deployment (e.g. gunicorn: app:create_app()).
"""

from datetime import datetime

from flask import Flask

from app.config import get_config, validate_production_config
from app.errors.handlers import register_error_handlers
from app.extensions import db, migrate
from app.services.auth_service import get_current_user


def create_app(config_name: str | None = None) -> Flask:
    """Application factory.

    Initializes configuration, database extensions, blueprint registration,
    and error handlers.
    """
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object(get_config(config_name))
    validate_production_config(app, config_name)

    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so Flask-Migrate / Alembic autogenerate can discover
    # all db.Model subclasses.  Must happen AFTER db.init_app().
    from app import models  # noqa: F401

    from app.routes import register_blueprints

    register_blueprints(app)
    register_error_handlers(app)

    @app.context_processor
    def inject_template_globals():
        """Expose common values to all templates."""
        return {
            "now": datetime.now(),
            "current_user": get_current_user(),
        }

    # Car photo lookup is needed inside Jinja macros (fleet cards, car
    # detail), which do not receive render context, so register it globally.
    from app.car_images import car_image_url

    app.jinja_env.globals["car_image_url"] = car_image_url

    return app