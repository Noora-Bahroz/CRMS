"""Car/fleet data-access repository module.

Queries over the Car model used by the car service and the admin fleet
routes.
"""

from sqlalchemy import func

from app.extensions import db
from app.models import Car


def list_all() -> list[Car]:
    """Return all cars ordered by make then model (oldest first)."""
    return Car.query.order_by(Car.make.asc(), Car.model.asc()).all()


def list_active() -> list[Car]:
    """Return only active cars."""
    return Car.query.filter_by(is_active=True).all()


def find_by_id(car_id: int) -> Car | None:
    """Return a car by primary key, or None."""
    return db.session.get(Car, car_id)


def find_by_plate(license_plate: str) -> Car | None:
    """Return a car by license plate (case-insensitive), or None."""
    return (
        Car.query.filter(func.lower(Car.license_plate) == license_plate.lower()).first()
    )


def find_by_vin(vin: str) -> Car | None:
    """Return a car by VIN (case-insensitive, normalized), or None."""
    if not vin:
        return None
    return Car.query.filter(func.lower(Car.vin) == vin.lower()).first()