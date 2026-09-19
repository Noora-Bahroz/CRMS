"""Expense service module.

Validation and business rules for recording and managing operational and
fleet expenses from the admin panel: create, update, and safe deletion.
An expense is optionally linked to a branch, car, or maintenance record to
provide cost context; at least one reference is required so every expense
can be traced.
"""

from decimal import Decimal

from app.extensions import db
from app.models import Expense
from app.repositories import (
    branch_repository,
    car_repository,
    maintenance_repository,
)
from app.utils import validators
from app.utils.constants import ExpenseCategory


class ExpenseError(Exception):
    """Raised when an expense cannot be modified or deleted."""


def _optional_relation(raw, label, finder):
    """Validate an optional foreign-key form field.

    Blank input yields ``(None, None)``; otherwise the value must parse as
    an integer and exist in the referenced relation.
    """
    text = (raw or "").strip()
    if not text:
        return None, None
    value, error = validators.parse_int(raw, label)
    if error:
        return None, error
    if finder(value) is None:
        return None, f"Select a valid {label.lower()}."
    return value, None


def validate_expense_form(data, expense=None):
    """Validate expense form input.

    Returns ``(values, errors)`` where *values* holds the cleaned Expense
    attributes and *errors* a list of human-readable messages.  Never
    raises.
    """
    errors = []
    values = {}

    category = (data.get("category") or "").strip()
    if category not in ExpenseCategory.ALL:
        errors.append("Select a valid expense category.")
    else:
        values["category"] = category

    branch_id, error = _optional_relation(
        data.get("branch_id"), "Branch", branch_repository.find_by_id
    )
    if error:
        errors.append(error)
    elif branch_id is not None:
        values["branch_id"] = branch_id

    car_id, error = _optional_relation(
        data.get("car_id"), "Car", car_repository.find_by_id
    )
    if error:
        errors.append(error)
    elif car_id is not None:
        values["car_id"] = car_id

    maintenance_id, error = _optional_relation(
        data.get("maintenance_id"), "Maintenance",
        maintenance_repository.find_by_id,
    )
    if error:
        errors.append(error)
    elif maintenance_id is not None:
        values["maintenance_id"] = maintenance_id

    if not any(
        key in values for key in ("branch_id", "car_id", "maintenance_id")
    ):
        errors.append(
            "Select a branch, car, or maintenance to link this expense to."
        )

    amount, error = validators.parse_decimal(
        data.get("amount"), "Amount", min_value=Decimal("0.01")
    )
    if error:
        errors.append(error)
    else:
        values["amount"] = amount

    description, error = validators.required_text(
        data.get("description"), "Description"
    )
    if error:
        errors.append(error)
    else:
        values["description"] = description

    receipt_url, _ = validators.optional_text(data.get("receipt_url"))
    values["receipt_url"] = receipt_url
    recorded_by, _ = validators.optional_text(data.get("recorded_by"))
    values["recorded_by"] = recorded_by

    expense_date, error = validators.parse_date(
        data.get("expense_date"), "Expense date"
    )
    if error:
        errors.append(error)
    else:
        values["expense_date"] = expense_date

    return values, errors


def create_expense(data) -> tuple[Expense | None, list[str]]:
    """Record a new expense.

    Returns ``(expense, errors)``; when errors is non-empty nothing is
    persisted and *expense* is ``None``.
    """
    values, errors = validate_expense_form(data)
    if errors:
        return None, errors
    expense = Expense(**values)
    db.session.add(expense)
    db.session.commit()
    return expense, []


def update_expense(expense, data) -> tuple[Expense | None, list[str]]:
    """Update an existing expense record."""
    values, errors = validate_expense_form(data, expense=expense)
    if errors:
        return expense, errors
    for field, value in values.items():
        setattr(expense, field, value)
    db.session.commit()
    return expense, []


def delete_expense(expense) -> None:
    """Safely delete an expense record.

    Expenses are leaf records with no dependent rows, but cost history is
    important: the admin UI confirms the action and the row is removed
    from the database.  Raises :class:`ExpenseError` on failure.
    """
    try:
        db.session.delete(expense)
        db.session.commit()
    except Exception as exc:  # pragma: no cover - depends on DB state
        db.session.rollback()
        raise ExpenseError("Could not delete the expense.") from exc