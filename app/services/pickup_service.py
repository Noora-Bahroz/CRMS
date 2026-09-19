"""Pickup and return service module.

Validation and business rules for recording the physical pickup and return
of a booked vehicle from the admin panel.

The persistence for a record is the existing ``RentalAgreement`` (one per
booking): its ``pickup_mileage`` / ``fuel_level_pickup`` / ``return_mileage`` /
``fuel_level_return`` / ``notes`` fields already represent the vehicle
condition at handover, so no duplicate pickup/return storage is created.
Pickup and return actions reuse the booking status flow (``confirmed`` ->
``ongoing`` -> ``completed``), update the car status according to the
existing status model, and never touch invoice/payment data.

State machine enforced here:

* pickup: only a ``confirmed`` booking with a non-terminated rental
  agreement and an available/rented car may be picked up.  Recorded pickup
  marks the agreement ``active``, the booking ``ongoing``, the car
  ``rented`` and stamps ``actual_pickup_datetime``.
* return: only an ``ongoing`` booking may be returned.  Recorded return
  marks the agreement ``completed``, the booking ``completed``, the car
  ``available`` and stamps ``actual_return_datetime``.
"""

from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.utils import validators
from app.utils.constants import AgreementStatus, BookingStatus, CarStatus


def record_state(booking) -> str:
    """Return the pickup/return state label for a booking.

    ``ready_for_pickup`` (confirmed), ``picked_up`` (ongoing), ``returned``
    (completed), or ``not_applicable`` for any other booking status.
    """
    if booking.status == BookingStatus.ONGOING:
        return "picked_up"
    if booking.status == BookingStatus.COMPLETED:
        return "returned"
    if booking.status == BookingStatus.CONFIRMED:
        return "ready_for_pickup"
    return "not_applicable"


def pickup_eligibility_error(booking) -> str | None:
    """Return a human-readable reason why *booking* cannot be picked up,
    or None when it is eligible for pickup."""
    if booking.status == BookingStatus.ONGOING:
        return "This booking has already been picked up. " \
            "A booking cannot be picked up twice."
    if booking.status == BookingStatus.COMPLETED:
        return "This booking is already returned and completed."
    if booking.status == BookingStatus.PENDING:
        return "This booking is still pending confirmation. " \
            "Only confirmed bookings can be picked up."
    if booking.status == BookingStatus.CANCELLED:
        return "This booking is cancelled and cannot be picked up."

    agreement = booking.rental_agreement
    if agreement is None:
        return "Create a rental agreement for this booking before " \
            "recording pickup."
    if agreement.status == AgreementStatus.TERMINATED:
        return "The linked rental agreement is terminated, so pickup " \
            "cannot be recorded."
    if booking.car.status not in (CarStatus.AVAILABLE, CarStatus.RENTED):
        return f"Car {booking.car.license_plate} is not available for " \
            f"pickup (status: {booking.car.status})."
    return None


def return_eligibility_error(booking) -> str | None:
    """Return a human-readable reason why *booking* cannot be returned, or
    None when it is eligible for return."""
    if booking.status != BookingStatus.ONGOING:
        if booking.status == BookingStatus.COMPLETED:
            return "This booking has already been returned. " \
                "A booking cannot be returned twice."
        return "This booking has not been picked up yet, so it cannot " \
            "be returned."
    agreement = booking.rental_agreement
    if agreement is None:
        return "Create a rental agreement for this booking to record " \
            "its return."
    if agreement.status == AgreementStatus.TERMINATED:
        return "The linked rental agreement is terminated, so return " \
            "cannot be recorded."
    return None


def decorate(booking) -> dict:
    """Build a view model for one booking in the pickup/return records."""
    return {
        "booking": booking,
        "state": record_state(booking),
        "can_pickup": pickup_eligibility_error(booking) is None,
        "can_return": return_eligibility_error(booking) is None,
        "pickup_issue": pickup_eligibility_error(booking),
        "return_issue": return_eligibility_error(booking),
    }


def validate_pickup_form(data, agreement) -> tuple[dict, list[str]]:
    """Validate pickup form input.

    Returns ``(values, errors)`` where *values* holds the cleaned
    attributes applied to the existing agreement.  Never raises.
    """
    errors = []
    values = {}

    pickup_mileage, error = validators.parse_int(
        data.get("pickup_mileage"), "Pickup mileage", min_value=0,
    )
    if error:
        errors.append(error)
    else:
        values["pickup_mileage"] = pickup_mileage

    fuel_level_pickup, error = validators.parse_decimal(
        data.get("fuel_level_pickup"), "Fuel level at pickup",
        min_value=Decimal("0.00"), max_value=Decimal("100.00"),
    )
    if error:
        errors.append(error)
    else:
        values["fuel_level_pickup"] = fuel_level_pickup

    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    return values, errors


def validate_return_form(data, agreement) -> tuple[dict, list[str]]:
    """Validate return form input.

    Returns ``(values, errors)`` where *values* holds the cleaned
    attributes applied to the existing agreement.  Never raises.
    """
    errors = []
    values = {}

    return_mileage, error = validators.parse_int(
        data.get("return_mileage"), "Return mileage", min_value=0,
    )
    if error:
        errors.append(error)
    elif return_mileage < agreement.pickup_mileage:
        errors.append(
            "Return mileage must not be less than pickup mileage."
        )
    else:
        values["return_mileage"] = return_mileage

    fuel_level_return, error = validators.parse_decimal(
        data.get("fuel_level_return"), "Fuel level at return",
        min_value=Decimal("0.00"), max_value=Decimal("100.00"),
    )
    if error:
        errors.append(error)
    else:
        values["fuel_level_return"] = fuel_level_return

    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    return values, errors


def record_pickup(booking, data) -> tuple[object, list[str]]:
    """Record that *booking*'s car has been picked up.

    Rejects ineligible bookings (see :func:`pickup_eligibility_error`) and
    invalid input.  On success the existing rental agreement carries the
    pickup condition, becomes ``active``, the booking moves to ``ongoing``,
    the car to ``rented``, and ``actual_pickup_datetime`` is stamped.
    """
    guard = pickup_eligibility_error(booking)
    if guard:
        return booking, [guard]

    agreement = booking.rental_agreement
    values, errors = validate_pickup_form(data, agreement)
    if errors:
        return booking, errors

    agreement.pickup_mileage = values["pickup_mileage"]
    agreement.fuel_level_pickup = values["fuel_level_pickup"]
    agreement.notes = values["notes"]
    agreement.status = AgreementStatus.ACTIVE
    booking.actual_pickup_datetime = datetime.utcnow()
    booking.status = BookingStatus.ONGOING
    if booking.car.status == CarStatus.AVAILABLE:
        booking.car.status = CarStatus.RENTED
    db.session.commit()
    return booking, []


def record_return(booking, data) -> tuple[object, list[str]]:
    """Record that *booking*'s car has been returned.

    Rejects bookings that have not been picked up (see
    :func:`return_eligibility_error`) and invalid input.  On success the
    existing rental agreement carries the return condition, becomes
    ``completed``, the booking moves to ``completed``, the car to
    ``available``, and ``actual_return_datetime`` is stamped.  No financial
    charges are created: invoice/payment remain admin-driven as before.
    """
    guard = return_eligibility_error(booking)
    if guard:
        return booking, [guard]

    agreement = booking.rental_agreement
    values, errors = validate_return_form(data, agreement)
    if errors:
        return booking, errors

    agreement.return_mileage = values["return_mileage"]
    agreement.fuel_level_return = values["fuel_level_return"]
    agreement.notes = values["notes"]
    agreement.status = AgreementStatus.COMPLETED
    booking.actual_return_datetime = datetime.utcnow()
    booking.status = BookingStatus.COMPLETED
    if booking.car.status == CarStatus.RENTED:
        booking.car.status = CarStatus.AVAILABLE
    db.session.commit()
    return booking, []