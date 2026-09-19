"""Flask extension instances.

Extensions are declared here, decoupled from the application, so they can
be initialized inside the application factory (app/__init__.py) and reused
across blueprints, services and repositories.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()