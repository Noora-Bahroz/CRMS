"""Car category service module.

Validation and business rules for managing car categories from the admin
panel: create, update, and safe deactivation.
"""

from decimal import Decimal

from app.extensions import db
from app.models import CarCategory
from app.repositories import category_repository
from app.utils import validators


class CategoryError(Exception):
    """Raised when a category cannot be modified or deactivated."""


def validate_category_form(data):
    """Validate form input.

    Returns ``(values, errors)`` where *values* is a dict of cleaned values
    and *errors* is a list of human-readable messages.  Never raises.
    """
    errors = []
    values = {}

    name, error = validators.required_text(data.get("name"), "Name")
    if error:
        errors.append(error)
    else:
        values["name"] = name

    description, _ = validators.optional_text(data.get("description"))
    values["description"] = description

    daily_rate, error = validators.parse_decimal(
        data.get("daily_rate"), "Daily rate", min_value=Decimal("0.01")
    )
    if error:
        errors.append(error)
    else:
        values["daily_rate"] = daily_rate

    weekly_rate, error = validators.parse_decimal(
        data.get("weekly_rate"), "Weekly rate", min_value=Decimal("0.01")
    )
    if error:
        errors.append(error)
    else:
        values["weekly_rate"] = weekly_rate

    monthly_rate, error = validators.parse_decimal(
        data.get("monthly_rate"), "Monthly rate", min_value=Decimal("0.01")
    )
    if error:
        errors.append(error)
    else:
        values["monthly_rate"] = monthly_rate

    deposit_amount, error = validators.parse_decimal(
        data.get("deposit_amount"), "Deposit amount", min_value=Decimal("0.00")
    )
    if error:
        errors.append(error)
    else:
        values["deposit_amount"] = deposit_amount

    values["is_active"] = validators.parse_bool(data.get("is_active", True))
    return values, errors


def _ensure_name_free(name, exclude_id=None):
    """Return an error message if *name* (excluding *exclude_id*) is taken."""
    existing = category_repository.find_by_name(name)
    if existing is not None and (exclude_id is None or existing.id != exclude_id):
        return "A category with this name already exists."
    return None


def create_category(data) -> tuple[CarCategory | None, list[str]]:
    """Create a new category from validated form data.

    Returns ``(category, errors)``; when errors is non-empty the category
    is not persisted and is ``None``.
    """
    values, errors = validate_category_form(data)
    if errors:
        return None, errors

    name_error = _ensure_name_free(values["name"])
    if name_error:
        errors.append(name_error)
        return None, errors

    category = CarCategory(**values)
    db.session.add(category)
    db.session.commit()
    return category, []


def update_category(category, data) -> tuple[CarCategory | None, list[str]]:
    """Update an existing category from validated form data."""
    values, errors = validate_category_form(data)
    if errors:
        return category, errors

    name_error = _ensure_name_free(values["name"], exclude_id=category.id)
    if name_error:
        errors.append(name_error)
        return category, errors

    for field, value in values.items():
        setattr(category, field, value)
    db.session.commit()
    return category, []


def deactivate_category(category) -> None:
    """Safely deactivate a category.

    Raises :class:`CategoryError` when cars are still assigned to it, since
    those cars reference the category's pricing.
    """
    count = len(category.cars)
    if count:
        raise CategoryError(
            f"Cannot delete '{category.name}' because {count} car(s) "
            "are assigned to it."
        )
    category.is_active = False
    db.session.commit()