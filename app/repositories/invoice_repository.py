"""Invoice data-access repository module.

Queries over the Invoice model used by the invoice service and the admin
invoice routes.  A booking can have at most one invoice (``booking_id`` is
unique), enforced here and in the service layer.
"""

from sqlalchemy import func, or_

from app.extensions import db
from app.models import Booking, Car, Customer, Invoice, User


def list_all() -> list[Invoice]:
    """Return all invoices, newest first."""
    return Invoice.query.order_by(Invoice.created_at.desc(), Invoice.id.desc()).all()


def find_by_id(invoice_id: int) -> Invoice | None:
    """Return an invoice by primary key, or None."""
    return db.session.get(Invoice, invoice_id)


def find_by_number(invoice_number: str) -> Invoice | None:
    """Return an invoice by its number (case-insensitive), or None."""
    return Invoice.query.filter(
        func.lower(Invoice.invoice_number) == invoice_number.lower()
    ).first()


def find_by_booking_id(booking_id: int) -> Invoice | None:
    """Return the invoice for a booking, or None."""
    return Invoice.query.filter_by(booking_id=booking_id).first()


def list_for_customer(customer_id: int) -> list[Invoice]:
    """Return one customer's invoices, newest first.

    Scoping through the invoice's booking keeps a customer account from
    ever seeing another customer's financial records.
    """
    return (
        Invoice.query.join(Booking, Invoice.booking_id == Booking.id)
        .filter(Booking.customer_id == customer_id)
        .order_by(Invoice.created_at.desc(), Invoice.id.desc())
        .all()
    )


def find_for_customer(customer_id: int, invoice_id: int) -> Invoice | None:
    """Return *invoice_id* only when its booking belongs to *customer_id*.

    Returns ``None`` for a missing invoice *and* for one owned by a
    different customer, so callers can render a plain 404 without leaking
    whether the record exists.
    """
    return (
        Invoice.query.join(Booking, Invoice.booking_id == Booking.id)
        .filter(Invoice.id == invoice_id, Booking.customer_id == customer_id)
        .first()
    )


def search(term: str, status: str | None = None) -> list[Invoice]:
    """Return invoices matching *term* (number, booking number, customer,
    car) optionally filtered to one *status*."""
    pattern = f"%{term.strip()}%"
    query = (
        Invoice.query.join(Booking, Invoice.booking_id == Booking.id)
        .join(Customer, Booking.customer_id == Customer.id)
        .join(User, Customer.user_id == User.id)
        .join(Car, Booking.car_id == Car.id)
        .filter(
            or_(
                Invoice.invoice_number.ilike(pattern),
                Booking.booking_number.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                Car.make.ilike(pattern),
                Car.model.ilike(pattern),
                Car.license_plate.ilike(pattern),
            )
        )
    )
    if status:
        query = query.filter(Invoice.status == status)
    return query.order_by(Invoice.created_at.desc(), Invoice.id.desc()).all()