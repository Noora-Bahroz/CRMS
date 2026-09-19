"""Availability service module.

The single availability decision for the whole system.  Every entry point
- public browse/search, car detail, the customer booking flow, and admin
booking create/edit - resolves "is this car bookable?" through the
functions here, so a customer can never bypass a rule an admin must
follow.

A car is bookable only when all of the following hold:

* the car is active (not deactivated);
* ``Car.status`` is a rentable status (only the existing ``available``);
* it has no active maintenance (scheduled / in-progress, i.e. not yet
  completed);
* it has no non-cancelled booking overlapping the requested range.

The overlap rule itself lives in ``booking_repository`` and is reused
unchanged (cancelled bookings never block a car, and the booking being
edited excludes itself).
"""

from datetime import datetime

from app.models import Car
from app.repositories import booking_repository, maintenance_repository
from app.utils import validators
from app.utils.constants import CarStatus

# Only the existing "available" status is rentable.  rented / maintenance /
# out_of_service are operational states that must not accept new rentals.
RENTABLE_CAR_STATUSES = (CarStatus.AVAILABLE,)

# Customer-friendly, non-internal messages.  They never mention records,
# ids, or admin concepts.
CAR_UNAVAILABLE = "This car is currently unavailable."
CAR_MAINTENANCE = "This vehicle is undergoing maintenance."
CAR_OUT_OF_SERVICE = "This vehicle is currently out of service."
CAR_ALREADY_BOOKED = (
    "This car is already booked during the selected dates. "
    "Choose another car or different dates."
)

_STATUS_REASONS = {
    CarStatus.MAINTENANCE: CAR_MAINTENANCE,
    CarStatus.OUT_OF_SERVICE: CAR_OUT_OF_SERVICE,
}


def parse_datetime_range(pickup_raw, return_raw):
    """Validate an optional pickup/return pair from a search form.

    Returns ``(pickup, return, errors)``.  Either side may be blank (then
    availability is not date-filtered).  When anything is invalid — bad
    format, or return not after pickup — both are ``None`` and *errors*
    holds the messages so the page can show them safely.
    """
    errors = []
    pickup = None
    ret = None

    if (pickup_raw or "").strip():
        pickup, error = validators.parse_datetime(
            pickup_raw, "Pickup date/time"
        )
        if error:
            errors.append(error)
    if (return_raw or "").strip():
        ret, error = validators.parse_datetime(return_raw, "Return date/time")
        if error:
            errors.append(error)

    if pickup is not None and ret is not None and ret <= pickup:
        errors.append("Return date/time must be after the pickup date/time.")

    if errors:
        return None, None, errors
    return pickup, ret, []


def unavailable_reason(car) -> str | None:
    """Return why *car* cannot be booked, or None when it is rentable.

    Checks only the car's own state (active flag, status, active
    maintenance) - no dates are involved.  Uses the same rules for the
    public site and the admin panel.
    """
    if car is None or not car.is_active:
        return CAR_UNAVAILABLE
    if car.status not in RENTABLE_CAR_STATUSES:
        return _STATUS_REASONS.get(car.status, CAR_UNAVAILABLE)
    if maintenance_repository.has_active_for_car(car.id):
        return CAR_MAINTENANCE
    return None


def check_availability(
    car,
    pickup_datetime: datetime | None = None,
    return_datetime: datetime | None = None,
    exclude_booking_id: int | None = None,
) -> tuple[bool, str | None]:
    """Return ``(bookable, reason)`` for a car over an optional range.

    Combines :func:`unavailable_reason` with the existing overlap rule.
    *exclude_booking_id* skips the booking being edited.  This is the one
    decision reused by the booking service, the customer flow, and the
    public site.
    """
    reason = unavailable_reason(car)
    if reason:
        return False, reason
    if (
        pickup_datetime is not None
        and return_datetime is not None
        and booking_repository.has_overlap(
            car.id,
            pickup_datetime,
            return_datetime,
            exclude_id=exclude_booking_id,
        )
    ):
        return False, CAR_ALREADY_BOOKED
    return True, None


def find_available_cars(
    category_id: int | None = None,
    branch_id: int | None = None,
    pickup_datetime: datetime | None = None,
    return_datetime: datetime | None = None,
) -> list[Car]:
    """Return rentable cars, optionally filtered by category/branch and to
    those genuinely free for the given range.

    Always excludes inactive cars, non-rentable statuses, and cars with
    active maintenance.  Without a complete date range no booking-overlap
    check is applied (it is a browse, not a date search).
    """
    query = Car.query.filter(
        Car.is_active.is_(True),
        Car.status.in_(RENTABLE_CAR_STATUSES),
    )
    if category_id:
        query = query.filter(Car.category_id == category_id)
    if branch_id:
        query = query.filter(Car.branch_id == branch_id)

    blocked_maintenance = maintenance_repository.blocked_car_ids()
    if blocked_maintenance:
        query = query.filter(Car.id.notin_(blocked_maintenance))

    if pickup_datetime and return_datetime:
        blocked = booking_repository.overlapping_car_ids(
            pickup_datetime, return_datetime
        )
        if blocked:
            query = query.filter(Car.id.notin_(blocked))

    return query.order_by(Car.make.asc(), Car.model.asc()).all()