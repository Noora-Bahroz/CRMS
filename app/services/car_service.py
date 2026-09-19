"""Car/fleet service module.

Validation and business rules for managing fleet cars from the admin
panel: create, update, and safe deactivation. Availability status is
tracked through the CarStatus constants.
"""

from app.extensions import db
from app.models import Car
from app.repositories import branch_repository, car_repository, category_repository
from app.utils import validators
from app.utils.constants import CarStatus


class CarError(Exception):
    """Raised when a car cannot be modified or deactivated."""


def validate_car_form(data, car=None):
    """Validate car form input.

    Returns ``(values, errors)`` where *values* holds cleaned attributes
    and *errors* is a list of human-readable messages.  *car* is the record
    being edited, used to allow a record to keep its own plate/VIN.
    """
    errors = []
    values = {}

    make, error = validators.required_text(data.get("make"), "Make")
    if error:
        errors.append(error)
    else:
        values["make"] = make

    model, error = validators.required_text(data.get("model"), "Model")
    if error:
        errors.append(error)
    else:
        values["model"] = model

    year, error = validators.parse_int(data.get("year"), "Year", min_value=1900, max_value=2100)
    if error:
        errors.append(error)
    else:
        values["year"] = year

    color, _ = validators.optional_text(data.get("color"))
    values["color"] = color

    license_plate, error = validators.required_text(
        data.get("license_plate"), "License plate"
    )
    if error:
        errors.append(error)
    else:
        values["license_plate"] = license_plate.upper()

    vin, _ = validators.optional_text(data.get("vin"))
    if vin:
        values["vin"] = vin.upper()

    mileage, error = validators.parse_int(data.get("mileage"), "Mileage", min_value=0)
    if error:
        errors.append(error)
    else:
        values["mileage"] = mileage

    fuel_level, error = validators.parse_decimal(
        data.get("fuel_level"), "Fuel level",
        min_value=0, max_value=100, required=False,  # fuel_level may be omitted
    )
    if error:
        errors.append(error)
    else:
        values["fuel_level"] = fuel_level if fuel_level is not None else 100

    category_id, error = validators.parse_int(
        data.get("category_id"), "Category", min_value=1
    )
    if error:
        errors.append(error)
    else:
        values["category_id"] = category_id

    branch_id, error = validators.parse_int(
        data.get("branch_id"), "Branch", min_value=1
    )
    if error:
        errors.append(error)
    else:
        values["branch_id"] = branch_id

    status = (data.get("status") or CarStatus.AVAILABLE).strip()
    if status not in CarStatus.ALL:
        errors.append("Select a valid status.")
    else:
        values["status"] = status

    image_url, _ = validators.optional_text(data.get("image_url"))
    values["image_url"] = image_url
    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    values["is_active"] = validators.parse_bool(data.get("is_active", True))

    if "license_plate" in values:
        existing = car_repository.find_by_plate(values["license_plate"])
        if existing is not None and (car is None or existing.id != car.id):
            errors.append("A car with this license plate already exists.")

    if vin:
        existing_vin = car_repository.find_by_vin(vin.upper())
        if existing_vin is not None and (car is None or existing_vin.id != car.id):
            errors.append("A car with this VIN already exists.")

    if "category_id" in values and category_repository.find_by_id(category_id) is None:
        errors.append("Select a valid category.")

    if "branch_id" in values and branch_repository.find_by_id(branch_id) is None:
        errors.append("Select a valid branch.")

    return values, errors


def create_car(data) -> tuple[Car | None, list[str]]:
    """Create a new car from validated form data.

    Returns ``(car, errors)``; when errors is non-empty the car is not
    persisted and is ``None``.
    """
    values, errors = validate_car_form(data)
    if errors:
        return None, errors

    car = Car(**values)
    db.session.add(car)
    db.session.commit()
    return car, []


def update_car(car, data) -> tuple[Car | None, list[str]]:
    """Update an existing car from validated form data."""
    values, errors = validate_car_form(data, car=car)
    if errors:
        return car, errors

    for field, value in values.items():
        setattr(car, field, value)
    db.session.commit()
    return car, []


def deactivate_car(car) -> None:
    """Safely deactivate a car.

    Raises :class:`CarError` when the car is referenced by bookings,
    maintenance records, or expenses, since historical data must stay intact.
    """
    blockers = []
    if car.bookings:
        blockers.append(f"{len(car.bookings)} booking(s)")
    if car.maintenance_records:
        blockers.append(f"{len(car.maintenance_records)} maintenance record(s)")
    if car.expenses:
        blockers.append(f"{len(car.expenses)} expense(s)")
    if blockers:
        raise CarError(
            f"Cannot delete {car.make} {car.model} ({car.license_plate}) because "
            "it has " + ", ".join(blockers) + "."
        )
    car.is_active = False
    db.session.commit()