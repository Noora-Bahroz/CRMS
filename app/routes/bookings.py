"""Customer booking flow blueprint.

Customers move through: choose a car -> rental details -> review ->
(authenticate if required) -> confirm -> confirmation.

The flow reuses the single booking service for validation, the overlap
guard, the pricing snapshot, and booking-number generation.  The
in-progress selection is carried in the session between review and
confirm, so an unauthenticated visitor can review a booking, be sent to
log in, and return without re-entering everything.
"""

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.repositories import (
    booking_repository,
    branch_repository,
    car_repository,
    driver_repository,
)
from app.services import availability_service
from app.services.auth_service import get_current_user
from app.services.authorization_service import is_customer_account
from app.services.booking_service import calculate_pricing, create_booking
from app.utils import validators
from app.utils.constants import BookingStatus, DriverStatus
from app.utils.decorators import customer_required

blueprint = Blueprint("bookings", __name__, url_prefix="/bookings")

DRAFT_KEY = "pending_booking"
_DRAFT_FIELDS = (
    "car_id",
    "pickup_branch_id",
    "return_branch_id",
    "pickup_datetime",
    "return_datetime",
    "driver_id",
    "notes",
)


def _draft_from_form(form):
    """Extract the customer-editable booking fields as plain strings."""
    return {field: (form.get(field) or "").strip() for field in _DRAFT_FIELDS}


def _load_selection(draft):
    """Validate a car/branch/date/driver selection (no customer involved).

    Returns ``(selection, errors)``.  *selection* holds the resolved
    records and parsed datetimes.  Validation reuses the shared helpers so
    messages match the admin booking guard exactly.
    """
    errors = []
    selection = {}

    car_id, error = validators.parse_int(draft.get("car_id"), "Car")
    if error:
        errors.append(error)
    else:
        car = car_repository.find_by_id(car_id)
        if car is None:
            errors.append("Select a valid car.")
        else:
            reason = availability_service.unavailable_reason(car)
            if reason:
                errors.append(reason)
            else:
                selection["car"] = car

    pickup_branch_id, error = validators.parse_int(
        draft.get("pickup_branch_id"), "Pickup branch"
    )
    if error:
        errors.append(error)
    else:
        branch = branch_repository.find_by_id(pickup_branch_id)
        if branch is None:
            errors.append("Select a valid pickup branch.")
        else:
            selection["pickup_branch"] = branch

    return_branch_id, error = validators.parse_int(
        draft.get("return_branch_id"), "Return branch"
    )
    if error:
        errors.append(error)
    else:
        branch = branch_repository.find_by_id(return_branch_id)
        if branch is None:
            errors.append("Select a valid return branch.")
        else:
            selection["return_branch"] = branch

    if (draft.get("driver_id") or "").strip():
        driver_id, error = validators.parse_int(draft.get("driver_id"), "Driver")
        if error:
            errors.append(error)
        else:
            driver = driver_repository.find_by_id(driver_id)
            if driver is None:
                errors.append("Select a valid driver.")
            else:
                selection["driver"] = driver

    pickup, error = validators.parse_datetime(
        draft.get("pickup_datetime"), "Pickup date/time"
    )
    if error:
        errors.append(error)
    else:
        selection["pickup"] = pickup

    ret, error = validators.parse_datetime(
        draft.get("return_datetime"), "Return date/time"
    )
    if error:
        errors.append(error)
    else:
        selection["return"] = ret

    if "pickup" in selection and "return" in selection:
        if selection["return"] <= selection["pickup"]:
            errors.append("Return date/time must be after the pickup date/time.")

    return selection, errors


def _pricing_for(selection):
    """Price a selection using the shared booking service calculation."""
    return calculate_pricing(
        selection["car"],
        selection["pickup"],
        selection["return"],
        driver=selection.get("driver"),
        additional_charges=0,
        discount=0,
    )


def _form_context(form, errors):
    """Common template variables for the booking form."""
    return {
        "form": form,
        "errors": errors,
        "cars": availability_service.find_available_cars(),
        "branches": branch_repository.list_active(),
        "drivers": [
            driver
            for driver in driver_repository.list_all()
            if driver.status == DriverStatus.AVAILABLE
        ],
    }


@blueprint.route("/new", methods=["GET", "POST"])
def new():
    """Show the rental-details form, or move a valid selection to review."""
    if request.method == "POST":
        draft = _draft_from_form(request.form)
        selection, errors = _load_selection(draft)
        if errors:
            return render_template(
                "bookings/form.html", **_form_context(draft, errors)
            )
        session[DRAFT_KEY] = draft
        return redirect(url_for("bookings.review"))

    form = {field: (request.args.get(field) or "") for field in _DRAFT_FIELDS}
    return render_template("bookings/form.html", **_form_context(form, []))


@blueprint.get("/review")
def review():
    """Review the selection and its price before confirming."""
    draft = session.get(DRAFT_KEY)
    if not draft:
        flash("Choose a car and rental dates to start a booking.", "info")
        return redirect(url_for("cars.index"))

    selection, errors = _load_selection(draft)
    if errors:
        return render_template(
            "bookings/form.html", **_form_context(draft, errors)
        )

    _, availability_reason = availability_service.check_availability(
        selection["car"], selection["pickup"], selection["return"]
    )

    return render_template(
        "bookings/review.html",
        selection=selection,
        car=selection["car"],
        driver=selection.get("driver"),
        pricing=_pricing_for(selection),
        availability_reason=availability_reason,
        authenticated=is_customer_account(get_current_user()),
    )


@blueprint.post("/confirm")
def confirm():
    """Authenticated customer confirmation: create the real booking."""
    user = get_current_user()
    if user is None:
        flash(
            "Please sign in or create an account to confirm your booking.",
            "info",
        )
        return redirect(url_for("public.login", next=url_for("bookings.review")))
    if not is_customer_account(user):
        abort(403)

    draft = session.get(DRAFT_KEY)
    if not draft:
        flash("Your booking session expired. Please choose a car again.", "warning")
        return redirect(url_for("cars.index"))

    data = dict(draft)
    # The customer never chooses these: the account is taken from the
    # session, the initial status is the existing PENDING state, and
    # adjustments are reserved for admin.
    data["customer_id"] = str(user.customer.id)
    data["status"] = BookingStatus.PENDING
    data["additional_charges"] = "0.00"
    data["discount"] = "0.00"

    booking, errors = create_booking(data)
    if errors:
        for error in errors:
            flash(error, "danger")
        return redirect(url_for("bookings.review"))

    session.pop(DRAFT_KEY, None)
    flash(f"Booking {booking.booking_number} confirmed.", "success")
    return redirect(
        url_for("bookings.confirmation", booking_id=booking.id)
    )


@blueprint.get("/<int:booking_id>/confirmation")
@customer_required
def confirmation(booking_id):
    """Show a customer-safe confirmation for one of the customer's bookings."""
    user = get_current_user()
    booking = booking_repository.find_for_customer(user.customer.id, booking_id)
    if booking is None:
        abort(404)
    return render_template("bookings/confirmation.html", booking=booking)
