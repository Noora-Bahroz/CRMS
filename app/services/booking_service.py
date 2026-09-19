"""Booking service module.

Validation and business rules for managing bookings from the admin panel:
create, update, status changes, safe cancellation, and the pricing
snapshot the model stores for invoicing.

Overlapping active bookings for a car are rejected (cancelled bookings do
not block future reservations).
"""

import secrets
from decimal import Decimal

from app.extensions import db
from app.models import Booking
from app.repositories import (
    booking_repository,
    branch_repository,
    car_repository,
    customer_repository,
    driver_repository,
)
from app.services import availability_service
from app.utils import validators
from app.utils.constants import BookingStatus


class BookingError(Exception):
    """Raised when a booking cannot be modified or cancelled."""


def _money(value) -> Decimal:
    """Best-effort conversion for Numeric columns."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


def calculate_pricing(car, pickup_datetime, return_datetime, driver=None,
                      additional_charges=0, discount=0) -> dict:
    """Compute the pricing snapshot the Booking model stores.

    The estimated rental days feed the base cost (category daily rate)
    and the optional driver cost; additional charges and discounts adjust
    the grand total.  No automatic weekly/monthly discount is applied so
    the numbers stay predictable for the admin UI.
    """
    days = max((return_datetime.date() - pickup_datetime.date()).days, 1)
    daily_rate = _money(car.category.daily_rate)
    weekly_rate = _money(car.category.weekly_rate)
    deposit_amount = _money(car.category.deposit_amount)

    base_cost = Decimal(days) * daily_rate
    driver_cost = Decimal("0.00")
    if driver is not None:
        driver_cost = Decimal(days) * _money(driver.daily_rate)

    additional = _money(additional_charges)
    discount = _money(discount)
    total = base_cost + driver_cost + additional - discount
    if total < 0:
        total = Decimal("0.00")

    return {
        "estimated_days": days,
        "daily_rate": daily_rate,
        "weekly_rate": weekly_rate,
        "base_cost": base_cost,
        "driver_cost": driver_cost,
        "additional_charges": additional,
        "discount": discount,
        "deposit_amount": deposit_amount,
        "total_amount": total,
    }


def _next_booking_number() -> str:
    """Return a fresh, practically-unique booking number."""
    while True:
        number = f"BK-{secrets.token_hex(3).upper()}"
        if booking_repository.find_by_number(number) is None:
            return number


def validate_booking_form(data, booking=None):
    """Validate booking form input.

    Returns ``(values, errors)`` where *values* holds the cleaned
    Booking attributes and *errors* is a list of human-readable messages.
    Never raises.
    """
    errors = []
    values = {}

    # --- Referenced records -------------------------------------------------
    customer_id, error = validators.parse_int(data.get("customer_id"), "Customer")
    if error:
        errors.append(error)
    elif customer_repository.find_by_id(customer_id) is None:
        errors.append("Select a valid customer.")
    else:
        values["customer_id"] = customer_id

    car_id, error = validators.parse_int(data.get("car_id"), "Car")
    if error:
        errors.append(error)
    elif car_repository.find_by_id(car_id) is None:
        errors.append("Select a valid car.")
    else:
        values["car_id"] = car_id

    pickup_branch_id, error = validators.parse_int(
        data.get("pickup_branch_id"), "Pickup branch"
    )
    if error:
        errors.append(error)
    elif branch_repository.find_by_id(pickup_branch_id) is None:
        errors.append("Select a valid pickup branch.")
    else:
        values["pickup_branch_id"] = pickup_branch_id

    return_branch_id, error = validators.parse_int(
        data.get("return_branch_id"), "Return branch"
    )
    if error:
        errors.append(error)
    elif branch_repository.find_by_id(return_branch_id) is None:
        errors.append("Select a valid return branch.")
    else:
        values["return_branch_id"] = return_branch_id

    driver_id = None
    raw_driver_id = (data.get("driver_id") or "").strip()
    if raw_driver_id:
        driver_id, error = validators.parse_int(data.get("driver_id"), "Driver")
        if error:
            errors.append(error)
        elif driver_repository.find_by_id(driver_id) is None:
            errors.append("Select a valid driver.")
        else:
            values["driver_id"] = driver_id

    # --- Date / time range ----------------------------------------------------
    pickup, error = validators.parse_datetime(
        data.get("pickup_datetime"), "Pickup date/time"
    )
    if error:
        errors.append(error)
    else:
        values["pickup_datetime"] = pickup

    ret, error = validators.parse_datetime(
        data.get("return_datetime"), "Return date/time"
    )
    if error:
        errors.append(error)
    else:
        values["return_datetime"] = ret

    if "pickup_datetime" in values and "return_datetime" in values:
        if values["return_datetime"] <= values["pickup_datetime"]:
            errors.append("Return date/time must be after the pickup date/time.")

    # --- Status ----------------------------------------------------------------
    status = (data.get("status") or BookingStatus.PENDING).strip()
    if status not in BookingStatus.ALL:
        errors.append("Select a valid status.")
    else:
        values["status"] = status

    # --- Driver requirement + pricing overrides --------------------------------
    requires_driver = validators.parse_bool(data.get("requires_driver", False))
    if driver_id is not None:
        requires_driver = True
    values["requires_driver"] = requires_driver

    additional_charges, error = validators.parse_decimal(
        data.get("additional_charges"), "Additional charges", min_value=Decimal("0.00"),
    )
    if error:
        errors.append(error)
    else:
        values["additional_charges"] = additional_charges

    discount, error = validators.parse_decimal(
        data.get("discount"), "Discount", min_value=Decimal("0.00"),
    )
    if error:
        errors.append(error)
    else:
        values["discount"] = discount

    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    return values, errors


def create_booking(data) -> tuple[Booking | None, list[str]]:
    """Create a booking with a fresh pricing snapshot.

    Returns ``(booking, errors)``; when errors is non-empty nothing is
    persisted and *booking* is ``None``.
    """
    values, errors = validate_booking_form(data)
    if errors:
        return None, errors

    # Final availability gate: car state (active/status/maintenance) plus
    # the existing overlap rule, resolved through the shared service so the
    # admin panel and the customer site enforce exactly the same rules.
    car = car_repository.find_by_id(values["car_id"])
    available, reason = availability_service.check_availability(
        car, values["pickup_datetime"], values["return_datetime"]
    )
    if not available:
        errors.append(reason)
        return None, errors

    driver = driver_repository.find_by_id(values["driver_id"]) if values.get("driver_id") else None
    pricing = calculate_pricing(
        car,
        values["pickup_datetime"],
        values["return_datetime"],
        driver=driver,
        additional_charges=values["additional_charges"],
        discount=values["discount"],
    )

    booking = Booking(
        booking_number=_next_booking_number(),
        **{
            k: v
            for k, v in values.items()
            if k not in ("driver_id", "additional_charges", "discount")
        },
        driver_id=values.get("driver_id"),
        **pricing,
    )
    db.session.add(booking)
    db.session.commit()
    return booking, []


def update_booking(booking, data) -> tuple[Booking | None, list[str]]:
    """Update a booking, recomputing its pricing snapshot.

    A blank or unchanged password is never involved here; this service
    only touches the booking record itself.
    """
    values, errors = validate_booking_form(data, booking=booking)
    if errors:
        return booking, errors

    # Same final availability gate as creation, excluding the booking being
    # edited from the overlap check.
    car = car_repository.find_by_id(values["car_id"])
    available, reason = availability_service.check_availability(
        car,
        values["pickup_datetime"],
        values["return_datetime"],
        exclude_booking_id=booking.id,
    )
    if not available:
        errors.append(reason)
        return booking, errors

    driver = driver_repository.find_by_id(values["driver_id"]) if values.get("driver_id") else None
    pricing = calculate_pricing(
        car,
        values["pickup_datetime"],
        values["return_datetime"],
        driver=driver,
        additional_charges=values["additional_charges"],
        discount=values["discount"],
    )

    for field, value in values.items():
        setattr(booking, field, value)
    if values.get("driver_id"):
        booking.driver_id = values["driver_id"]
    else:
        booking.driver_id = None
    for field, value in pricing.items():
        setattr(booking, field, value)
    db.session.commit()
    return booking, []


def cancel_booking(booking) -> None:
    """Safely cancel (soft-delete) a booking.

    Raises :class:`BookingError` when the booking is already cancelled.
    The row is kept and its status set to ``cancelled`` so historical
    payments and connected records remain intact.
    """
    if booking.status == BookingStatus.CANCELLED:
        raise BookingError(
            f"Booking {booking.booking_number} is already cancelled."
        )
    booking.status = BookingStatus.CANCELLED
    db.session.commit()