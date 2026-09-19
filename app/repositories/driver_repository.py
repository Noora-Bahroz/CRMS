"""Driver data-access repository module.

Queries over the Driver model used by the driver service and the admin
driver routes.
"""

from sqlalchemy import func

from app.extensions import db
from app.models import Driver


def list_all() -> list[Driver]:
    """Return all drivers ordered by last name then first name."""
    return Driver.query.order_by(Driver.last_name.asc(), Driver.first_name.asc()).all()


def find_by_id(driver_id: int) -> Driver | None:
    """Return a driver by primary key, or None."""
    return db.session.get(Driver, driver_id)


def find_by_license_number(license_number: str) -> Driver | None:
    """Return a driver by license number (case-insensitive), or None."""
    return (
        Driver.query.filter(
            func.lower(Driver.license_number) == license_number.lower()
        ).first()
    )


def find_by_email(email: str) -> Driver | None:
    """Return a driver by email (case-insensitive), or None."""
    if not email:
        return None
    return Driver.query.filter(func.lower(Driver.email) == email.lower()).first()