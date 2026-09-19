"""Rental agreement data-access repository module.

Queries over the RentalAgreement model used by the agreement service and
the admin agreement routes.  A booking can have at most one agreement
(``booking_id`` is unique), enforced here and in the service layer.
"""

from sqlalchemy import func, or_

from app.extensions import db
from app.models import Booking, Car, Customer, RentalAgreement, User


def list_all() -> list[RentalAgreement]:
    """Return all agreements, newest first."""
    return RentalAgreement.query.order_by(
        RentalAgreement.created_at.desc(), RentalAgreement.id.desc()
    ).all()


def find_by_id(agreement_id: int) -> RentalAgreement | None:
    """Return an agreement by primary key, or None."""
    return db.session.get(RentalAgreement, agreement_id)


def find_by_number(agreement_number: str) -> RentalAgreement | None:
    """Return an agreement by its number (case-insensitive), or None."""
    return RentalAgreement.query.filter(
        func.lower(RentalAgreement.agreement_number) == agreement_number.lower()
    ).first()


def find_by_booking_id(booking_id: int) -> RentalAgreement | None:
    """Return the agreement for a booking, or None."""
    return RentalAgreement.query.filter_by(booking_id=booking_id).first()


def search(term: str, status: str | None = None) -> list[RentalAgreement]:
    """Return agreements matching *term* (number, booking number, customer,
    car) optionally filtered to one *status*."""
    pattern = f"%{term.strip()}%"
    query = (
        RentalAgreement.query.join(
            Booking, RentalAgreement.booking_id == Booking.id
        )
        .join(Customer, Booking.customer_id == Customer.id)
        .join(User, Customer.user_id == User.id)
        .join(Car, Booking.car_id == Car.id)
        .filter(
            or_(
                RentalAgreement.agreement_number.ilike(pattern),
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
        query = query.filter(RentalAgreement.status == status)
    return query.order_by(
        RentalAgreement.created_at.desc(), RentalAgreement.id.desc()
    ).all()