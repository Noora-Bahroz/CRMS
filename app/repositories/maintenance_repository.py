"""Maintenance data-access repository module.

Queries over the Maintenance model for the admin maintenance routes and
service.  Maintenance records belong to a car and carry a status of
scheduled / in_progress / completed.
"""

from sqlalchemy import or_

from app.extensions import db
from app.models import Car, Maintenance
from app.utils.constants import MaintenanceStatus

# Scheduled or in-progress work is "active" and keeps a car off the road.
# Completed work no longer blocks a rental.
ACTIVE_STATUSES = (MaintenanceStatus.SCHEDULED, MaintenanceStatus.IN_PROGRESS)


def list_all() -> list[Maintenance]:
    """Return all maintenance records, newest first."""
    return Maintenance.query.order_by(
        Maintenance.created_at.desc(), Maintenance.id.desc()
    ).all()


def find_by_id(maintenance_id: int) -> Maintenance | None:
    """Return a maintenance record by primary key, or None."""
    return db.session.get(Maintenance, maintenance_id)


def has_active_for_car(car_id: int) -> bool:
    """Return True when *car_id* has scheduled or in-progress maintenance."""
    return db.session.query(
        Maintenance.query.filter(
            Maintenance.car_id == car_id,
            Maintenance.status.in_(ACTIVE_STATUSES),
        ).exists()
    ).scalar()


def blocked_car_ids() -> set[int]:
    """Return the ids of cars with active (non-completed) maintenance.

    Bulk form of :func:`has_active_for_car` so availability listings can
    exclude every blocked car in a single query.
    """
    rows = (
        db.session.query(Maintenance.car_id)
        .filter(Maintenance.status.in_(ACTIVE_STATUSES))
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def search(term: str, status: str | None = None) -> list[Maintenance]:
    """Return maintenance records matching *term* (car, type, description,
    service provider) optionally filtered to one *status*."""
    pattern = f"%{term.strip()}%"
    query = (
        Maintenance.query.join(Car, Maintenance.car_id == Car.id)
        .filter(
            or_(
                Maintenance.maintenance_type.ilike(pattern),
                Maintenance.description.ilike(pattern),
                Maintenance.service_provider.ilike(pattern),
                Car.make.ilike(pattern),
                Car.model.ilike(pattern),
                Car.license_plate.ilike(pattern),
            )
        )
    )
    if status:
        query = query.filter(Maintenance.status == status)
    return query.order_by(Maintenance.created_at.desc(), Maintenance.id.desc()).all()