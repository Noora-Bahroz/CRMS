"""Maintenance service module.

Validation and business rules for managing fleet maintenance records from
the admin panel: create, update, safe completion, and deletion.  Records
follow the existing statuses (scheduled / in_progress / completed).

Deleting a record is only safe while nothing depends on it: a maintenance
record that has linked expenses is kept and must be closed (completed)
instead.
"""

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Maintenance
from app.repositories import car_repository, maintenance_repository
from app.utils import validators
from app.utils.constants import MaintenanceStatus, MaintenanceType


class MaintenanceError(Exception):
    """Raised when a maintenance record cannot be modified or deleted."""


def validate_maintenance_form(data, maintenance=None):
    """Validate maintenance form input.

    Returns ``(values, errors)`` where *values* holds the cleaned
    Maintenance attributes and *errors* a list of human-readable messages.
    Never raises.
    """
    errors = []
    values = {}

    car_id, error = validators.parse_int(data.get("car_id"), "Car")
    if error:
        errors.append(error)
    elif car_repository.find_by_id(car_id) is None:
        errors.append("Select a valid car.")
    else:
        values["car_id"] = car_id

    maintenance_type = (data.get("maintenance_type") or "").strip()
    if maintenance_type not in MaintenanceType.ALL:
        errors.append("Select a valid maintenance type.")
    else:
        values["maintenance_type"] = maintenance_type

    status = (data.get("status") or MaintenanceStatus.SCHEDULED).strip()
    if status not in MaintenanceStatus.ALL:
        errors.append("Select a valid status.")
    else:
        values["status"] = status

    description, error = validators.required_text(
        data.get("description"), "Description"
    )
    if error:
        errors.append(error)
    else:
        values["description"] = description

    cost, error = validators.parse_decimal(
        data.get("cost"), "Cost", min_value=Decimal("0.00"), required=False
    )
    if error:
        errors.append(error)
    else:
        values["cost"] = cost if cost is not None else Decimal("0.00")

    scheduled_date, error = validators.parse_date(
        data.get("scheduled_date"), "Scheduled date"
    )
    if error:
        errors.append(error)
    else:
        values["scheduled_date"] = scheduled_date

    completed_date, error = validators.optional_date(
        data.get("completed_date"), "Completed date"
    )
    if error:
        errors.append(error)
    else:
        values["completed_date"] = completed_date

    if (
        "scheduled_date" in values
        and values["completed_date"] is not None
        and values["completed_date"] < values["scheduled_date"]
    ):
        errors.append("Completed date must not be before the scheduled date.")

    if (
        values.get("status") == MaintenanceStatus.COMPLETED
        and values.get("completed_date") is None
    ):
        errors.append("Set a completed date for a completed maintenance record.")

    service_provider, _ = validators.optional_text(data.get("service_provider"))
    values["service_provider"] = service_provider
    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    return values, errors


def create_maintenance(data) -> tuple[Maintenance | None, list[str]]:
    """Create a maintenance record for a car.

    Returns ``(maintenance, errors)``; when errors is non-empty nothing is
    persisted and *maintenance* is ``None``.
    """
    values, errors = validate_maintenance_form(data)
    if errors:
        return None, errors
    maintenance = Maintenance(**values)
    db.session.add(maintenance)
    db.session.commit()
    return maintenance, []


def update_maintenance(
    maintenance, data
) -> tuple[Maintenance | None, list[str]]:
    """Update an existing maintenance record."""
    values, errors = validate_maintenance_form(data, maintenance=maintenance)
    if errors:
        return maintenance, errors
    for field, value in values.items():
        setattr(maintenance, field, value)
    db.session.commit()
    return maintenance, []


def complete_maintenance(maintenance) -> None:
    """Close a maintenance record by marking it completed.

    Keeps any recorded completed date and defaults to today when the
    record was not yet given one.  Raises :class:`MaintenanceError` when
    the record is already completed.
    """
    if maintenance.status == MaintenanceStatus.COMPLETED:
        raise MaintenanceError(
            f"Maintenance #{maintenance.id} is already completed."
        )
    maintenance.status = MaintenanceStatus.COMPLETED
    if maintenance.completed_date is None:
        maintenance.completed_date = date.today()
    db.session.commit()


def delete_maintenance(maintenance) -> None:
    """Safely delete a maintenance record.

    Raises :class:`MaintenanceError` when the record still has linked
    expenses (their cost context depends on it); close the record with
    :func:`complete_maintenance` instead.  Otherwise the row is removed.
    """
    if maintenance.expenses:
        raise MaintenanceError(
            "This maintenance record has linked expenses and cannot be "
            "deleted. Mark it completed instead."
        )
    db.session.delete(maintenance)
    db.session.commit()