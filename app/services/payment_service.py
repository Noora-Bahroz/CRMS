"""Payment service module.

Validation and business rules for recording and managing payments
against bookings from the admin panel: create, update, and safe
deletion of payment records.
"""

from decimal import Decimal

from app.extensions import db
from app.models import Payment
from app.repositories import booking_repository, payment_repository
from app.utils import validators
from app.utils.constants import PaymentMethod, PaymentStatus


class PaymentError(Exception):
    """Raised when a payment cannot be modified or deleted."""


def validate_payment_form(data, payment=None):
    """Validate payment form input.

    Returns ``(values, errors)`` where *values* holds the cleaned Payment
    attributes and *errors* a list of human-readable messages.  Never
    raises.
    """
    errors = []
    values = {}

    booking_id, error = validators.parse_int(data.get("booking_id"), "Booking")
    if error:
        errors.append(error)
    elif booking_repository.find_by_id(booking_id) is None:
        errors.append("Select a valid booking.")
    else:
        values["booking_id"] = booking_id

    amount, error = validators.parse_decimal(
        data.get("amount"), "Amount", min_value=Decimal("0.01")
    )
    if error:
        errors.append(error)
    else:
        values["amount"] = amount

    method = (data.get("method") or "").strip()
    if method not in PaymentMethod.ALL:
        errors.append("Select a valid payment method.")
    else:
        values["method"] = method

    status = (data.get("status") or "").strip()
    if status not in PaymentStatus.ALL:
        errors.append("Select a valid payment status.")
    else:
        values["status"] = status

    reference_number, _ = validators.optional_text(data.get("reference_number"))
    values["reference_number"] = reference_number
    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    received_by, _ = validators.optional_text(data.get("received_by"))
    values["received_by"] = received_by
    return values, errors


def create_payment(data) -> tuple[Payment | None, list[str]]:
    """Record a new payment against a booking.

    Returns ``(payment, errors)``; when errors is non-empty nothing is
    persisted and *payment* is ``None``.
    """
    values, errors = validate_payment_form(data)
    if errors:
        return None, errors
    payment = Payment(**values)
    db.session.add(payment)
    db.session.commit()
    return payment, []


def update_payment(payment, data) -> tuple[Payment | None, list[str]]:
    """Update an existing payment record."""
    values, errors = validate_payment_form(data, payment=payment)
    if errors:
        return payment, errors
    for field, value in values.items():
        setattr(payment, field, value)
    db.session.commit()
    return payment, []


def delete_payment(payment) -> None:
    """Safely delete a payment record.

    Payments are leaf records with no dependent rows, but payment history
    is important: the admin UI confirms the action and the row is removed
    from the database.  Raises :class:`PaymentError` on failure.
    """
    try:
        db.session.delete(payment)
        db.session.commit()
    except Exception as exc:  # pragma: no cover - depends on DB state
        db.session.rollback()
        raise PaymentError("Could not delete the payment.") from exc