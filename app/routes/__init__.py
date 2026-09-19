"""Blueprint registry.

All route modules expose a ``blueprint`` object. This module centralizes
registration so the application factory stays clean and blueprint URL
prefixes are defined in one place.
"""

from app.routes.admin.auth import blueprint as admin_auth_bp
from app.routes.admin.agreements import blueprint as admin_agreements_bp
from app.routes.admin.bookings import blueprint as admin_bookings_bp
from app.routes.admin.branches import blueprint as admin_branches_bp
from app.routes.admin.cars import blueprint as admin_cars_bp
from app.routes.admin.categories import blueprint as admin_categories_bp
from app.routes.admin.customers import blueprint as admin_customers_bp
from app.routes.admin.dashboard import blueprint as admin_dashboard_bp
from app.routes.admin.drivers import blueprint as admin_drivers_bp
from app.routes.admin.expenses import blueprint as admin_expenses_bp
from app.routes.admin.invoices import blueprint as admin_invoices_bp
from app.routes.admin.maintenance import blueprint as admin_maintenance_bp
from app.routes.admin.payments import blueprint as admin_payments_bp
from app.routes.admin.pickup_return import blueprint as admin_pickup_return_bp
from app.routes.admin.reports import blueprint as admin_reports_bp
from app.routes.admin.users import blueprint as admin_users_bp
from app.routes.auth import blueprint as auth_bp
from app.routes.bookings import blueprint as bookings_bp
from app.routes.cars import blueprint as cars_bp
from app.routes.customer import blueprint as customer_bp
from app.routes.public import blueprint as public_bp


def register_blueprints(app) -> None:
    """Register all application blueprints on the Flask app."""
    # Public / customer-facing areas.
    app.register_blueprint(public_bp)
    app.register_blueprint(cars_bp)
    app.register_blueprint(bookings_bp)

    # Customer authentication and customer area.
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(customer_bp, url_prefix="/customer")

    # Admin panel (own authentication + management areas). Each admin
    # blueprint declares its own url_prefix under /admin.
    for bp in (
        admin_auth_bp,
        admin_dashboard_bp,
        admin_cars_bp,
        admin_categories_bp,
        admin_customers_bp,
        admin_bookings_bp,
        admin_pickup_return_bp,
        admin_payments_bp,
        admin_invoices_bp,
        admin_agreements_bp,
        admin_drivers_bp,
        admin_maintenance_bp,
        admin_expenses_bp,
        admin_branches_bp,
        admin_users_bp,
        admin_reports_bp,
    ):
        app.register_blueprint(bp)