"""Payment data-access repository module.

Queries over the Payment model used by the payment service and the admin
payment routes.
"""

from sqlalchemy import or_

from app.extensions import db
from app.models import Booking, Customer, Payment, User


def list_all() -> list[Payment]:
    """Return all payments, newest first."""
    return Payment.query.order_by(Payment.created_at.desc(), Payment.id.desc()).all()


def find_by_id(payment_id: int) -> Payment | None:
    """Return a payment by primary key, or None."""
    return db.session.get(Payment, payment_id)


def list_for_customer(customer_id: int) -> list[Payment]:
    """Return one customer's payments, newest first.

    Scoping through the payment's booking keeps a customer account from
    ever seeing another customer's payment history.
    """
    return (
        Payment.query.join(Booking, Payment.booking_id == Booking.id)
        .filter(Booking.customer_id == customer_id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )


def search(term: str, status: str | None = None) -> list[Payment]:
    """Return payments matching *term* (reference or booking number)
    optionally filtered to one *status*."""
    pattern = f"%{term.strip()}%"
    query = (
        Payment.query.join(Booking, Payment.booking_id == Booking.id)
        .filter(
            or_(
                Payment.reference_number.ilike(pattern),
                Booking.booking_number.ilike(pattern),
            )
        )
    )
    if status:
        query = query.filter(Payment.status == status)
    return query.order_by(Payment.created_at.desc(), Payment.id.desc()).all()