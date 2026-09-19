"""Branch service module.

Validation and business rules for managing branches from the admin panel:
create, update, and safe deactivation.
"""

from app.extensions import db
from app.models import Branch
from app.repositories import branch_repository
from app.utils import validators


class BranchError(Exception):
    """Raised when a branch cannot be modified or deactivated."""


def validate_branch_form(data):
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

    address, error = validators.required_text(data.get("address"), "Address")
    if error:
        errors.append(error)
    else:
        values["address"] = address

    city, error = validators.required_text(data.get("city"), "City")
    if error:
        errors.append(error)
    else:
        values["city"] = city

    state, _ = validators.optional_text(data.get("state"))
    values["state"] = state
    zip_code, _ = validators.optional_text(data.get("zip_code"))
    values["zip_code"] = zip_code
    phone, _ = validators.optional_text(data.get("phone"))
    values["phone"] = phone

    email, error = validators.optional_email(data.get("email"), "Email")
    if error:
        errors.append(error)
    else:
        values["email"] = email

    values["is_active"] = validators.parse_bool(data.get("is_active", True))
    return values, errors


def _ensure_name_free(name, exclude_id=None):
    """Return an error message if *name* (excluding *exclude_id*) is taken."""
    existing = branch_repository.find_by_name(name)
    if existing is not None and (exclude_id is None or existing.id != exclude_id):
        return "A branch with this name already exists."
    return None


def create_branch(data) -> tuple[Branch | None, list[str]]:
    """Create a new branch from validated form data.

    Returns ``(branch, errors)``; when errors is non-empty the branch is
    not persisted and is ``None``.
    """
    values, errors = validate_branch_form(data)
    if errors:
        return None, errors

    name_error = _ensure_name_free(values["name"])
    if name_error:
        errors.append(name_error)
        return None, errors

    branch = Branch(**values)
    db.session.add(branch)
    db.session.commit()
    return branch, []


def update_branch(branch, data) -> tuple[Branch | None, list[str]]:
    """Update an existing branch from validated form data."""
    values, errors = validate_branch_form(data)
    if errors:
        return branch, errors

    name_error = _ensure_name_free(values["name"], exclude_id=branch.id)
    if name_error:
        errors.append(name_error)
        return branch, errors

    for field, value in values.items():
        setattr(branch, field, value)
    db.session.commit()
    return branch, []


def deactivate_branch(branch) -> None:
    """Safely deactivate a branch.

    Raises :class:`BranchError` when the branch still has cars, bookings
    (pickup or return), or expenses, since those records depend on it.
    """
    blockers = []
    if branch.cars:
        blockers.append(f"{len(branch.cars)} car(s)")
    if branch.pickup_bookings:
        blockers.append(f"{len(branch.pickup_bookings)} pickup booking(s)")
    if branch.return_bookings:
        blockers.append(f"{len(branch.return_bookings)} return booking(s)")
    if branch.expenses:
        blockers.append(f"{len(branch.expenses)} expense(s)")
    if blockers:
        raise BranchError(
            f"Cannot delete '{branch.name}' because it has "
            + ", ".join(blockers) + "."
        )
    branch.is_active = False
    db.session.commit()