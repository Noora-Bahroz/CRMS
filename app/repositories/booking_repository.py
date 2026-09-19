"""Booking data-access repository module.

Queries over the Booking model used by the booking service and the admin
booking routes, including the overlapping-booking check that keeps a car
from being double-booked within the same active date range.
"""

from datetime import datetime

from sqlalchemy import and_, or_

from app.extensions import db
from app.models import Booking, Car, Customer, User
from app.utils.constants import BookingStatus


def list_all() -> list[Booking]:
    """Return all bookings, newest first."""
    return Booking.query.order_by(Booking.created_at.desc(), Booking.id.desc()).all()


def find_by_id(booking_id: int) -> Booking | None:
    """Return a booking by primary key, or None."""
    return db.session.get(Booking, booking_id)


def list_for_customer(customer_id: int) -> list[Booking]:
    """Return one customer's bookings, newest first.

    Scoping by ``customer_id`` is what keeps a customer account from ever
    seeing (or being handed) another customer's reservations.
    """
    return (
        Booking.query.filter(Booking.customer_id == customer_id)
        .order_by(Booking.created_at.desc(), Booking.id.desc())
        .all()
    )


def find_for_customer(customer_id: int, booking_id: int) -> Booking | None:
    """Return *booking_id* only when it belongs to *customer_id*.

    Returns ``None`` for a missing booking *and* for a booking owned by a
    different customer, so callers can render a plain 404 without leaking
    whether the record exists.
    """
    return Booking.query.filter(
        Booking.id == booking_id, Booking.customer_id == customer_id
    ).first()


def find_by_number(booking_number: str) -> Booking | None:
    """Return a booking by its unique booking number, or None."""
    return Booking.query.filter_by(booking_number=booking_number).first()


def search(term: str, status: str | None = None) -> list[Booking]:
    """Return bookings matching *term* (number, customer, car) optionally
    filtered to one *status*."""
    pattern = f"%{term.strip()}%"
    query = (
        Booking.query.join(Customer, Booking.customer_id == Customer.id)
        .join(User, Customer.user_id == User.id)
        .join(Car, Booking.car_id == Car.id)
        .filter(
            or_(
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
        query = query.filter(Booking.status == status)
    return query.order_by(Booking.created_at.desc(), Booking.id.desc()).all()


def has_overlap(
    car_id: int,
    pickup_datetime: datetime,
    return_datetime: datetime,
    exclude_id: int | None = None,
) -> bool:
    """Return True when *car_id* is already booked by a non-cancelled
    booking whose range overlaps (pickup <= new_return and
    return >= new_pickup).  *exclude_id* skips the booking being edited.
    """
    query = Booking.query.filter(
        Booking.car_id == car_id,
        Booking.status != BookingStatus.CANCELLED,
        Booking.pickup_datetime < return_datetime,
        Booking.return_datetime > pickup_datetime,
    )
    if exclude_id is not None:
        query = query.filter(Booking.id != exclude_id)
    return db.session.query(query.exists()).scalar()


def find_overlap(
    car_id: int,
    pickup_datetime: datetime,
    return_datetime: datetime,
    exclude_id: int | None = None,
) -> Booking | None:
    """Return the first conflicting booking for *car_id*, or None."""
    query = Booking.query.filter(
        Booking.car_id == car_id,
        Booking.status != BookingStatus.CANCELLED,
        Booking.pickup_datetime < return_datetime,
        Booking.return_datetime > pickup_datetime,
    )
    if exclude_id is not None:
        query = query.filter(Booking.id != exclude_id)
    return query.first()


def overlapping_car_ids(
    pickup_datetime: datetime, return_datetime: datetime
) -> set[int]:
    """Return the ids of cars that have a non-cancelled booking overlapping
    the given range.

    Uses the exact same overlap rule as :func:`has_overlap`/
    :func:`find_overlap` (cancelled bookings never block a car) so the
    public availability lookup and the admin booking guard stay in sync.
    """
    rows = (
        db.session.query(Booking.car_id)
        .filter(
            Booking.status != BookingStatus.CANCELLED,
            Booking.pickup_datetime < return_datetime,
            Booking.return_datetime > pickup_datetime,
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}