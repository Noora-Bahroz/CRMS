"""Driver service module.

Validation and business rules for managing hired/additional drivers from
the admin panel: create, update, and safe deactivation.

Drivers have no ``is_active`` flag; deactivation uses the model's own
``status`` field and moves the driver to ``DriverStatus.INACTIVE``, the
same safe soft-delete approach used elsewhere in the admin panel.
"""

from decimal import Decimal

from app.extensions import db
from app.models import Driver
from app.repositories import driver_repository
from app.utils import validators
from app.utils.constants import DriverStatus


class DriverError(Exception):
    """Raised when a driver cannot be modified or deactivated."""


def validate_driver_form(data, driver=None):
    """Validate form input.

    Returns ``(values, errors)`` where *values* is a dict of cleaned values
    and *errors* is a list of human-readable messages.  *driver* is the
    record being edited, used to allow a record to keep its own license
    number.  Never raises.
    """
    errors = []
    values = {}

    first_name, error = validators.required_text(data.get("first_name"), "First name")
    if error:
        errors.append(error)
    else:
        values["first_name"] = first_name

    last_name, error = validators.required_text(data.get("last_name"), "Last name")
    if error:
        errors.append(error)
    else:
        values["last_name"] = last_name

    phone, error = validators.required_text(data.get("phone"), "Phone")
    if error:
        errors.append(error)
    else:
        values["phone"] = phone

    email, error = validators.optional_email(data.get("email"), "Email")
    if error:
        errors.append(error)
    else:
        values["email"] = email

    license_number, error = validators.required_text(
        data.get("license_number"), "License number"
    )
    if error:
        errors.append(error)
    else:
        license_number = license_number.upper()
        existing = driver_repository.find_by_license_number(license_number)
        if existing is not None and (driver is None or existing.id != driver.id):
            errors.append("A driver with this license number already exists.")
        else:
            values["license_number"] = license_number

    license_expiry, error = validators.parse_date(
        data.get("license_expiry"), "License expiry"
    )
    if error:
        errors.append(error)
    else:
        values["license_expiry"] = license_expiry

    status = (data.get("status") or DriverStatus.AVAILABLE).strip()
    if status not in DriverStatus.ALL:
        errors.append("Select a valid status.")
    else:
        values["status"] = status

    daily_rate, error = validators.parse_decimal(
        data.get("daily_rate"), "Daily rate", min_value=Decimal("0.00")
    )
    if error:
        errors.append(error)
    else:
        values["daily_rate"] = daily_rate

    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    return values, errors


def create_driver(data) -> tuple[Driver | None, list[str]]:
    """Create a new driver from validated form data.

    Returns ``(driver, errors)``; when errors is non-empty the driver is
    not persisted and is ``None``.
    """
    values, errors = validate_driver_form(data)
    if errors:
        return None, errors

    driver = Driver(**values)
    db.session.add(driver)
    db.session.commit()
    return driver, []


def update_driver(driver, data) -> tuple[Driver | None, list[str]]:
    """Update an existing driver from validated form data."""
    values, errors = validate_driver_form(data, driver=driver)
    if errors:
        return driver, errors

    for field, value in values.items():
        setattr(driver, field, value)
    db.session.commit()
    return driver, []


def deactivate_driver(driver) -> None:
    """Safely deactivate a driver.

    Raises :class:`DriverError` when the driver is referenced by bookings,
    since historical data must stay intact.
    """
    if driver.bookings:
        raise DriverError(
            f"Cannot delete {driver.first_name} {driver.last_name} because they "
            f"are linked to {len(driver.bookings)} booking(s)."
        )
    driver.status = DriverStatus.INACTIVE
    db.session.commit()