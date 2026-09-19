"""Admin pickup & return records blueprint.

Dedicated admin area for recording the physical pickup and return of a
booked vehicle against an existing booking.  It reuses the booking and
rental-agreement records: pickup/return conditions are stored in the
existing agreement fields, and the actions drive the existing booking
status flow (``confirmed`` -> ``ongoing`` -> ``completed``).

Recorded on pickup:  agreement fields (pickup action) + booking
``actual_pickup_datetime`` + booking ``ongoing`` + car ``rented``.
Recorded on return:   agreement return fields + booking
``actual_return_datetime`` + booking ``completed`` + car ``available``.
No invoice/payment changes are made here.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import booking_repository
from app.services import pickup_service
from app.utils.decorators import admin_required

blueprint = Blueprint(
    "admin_pickup_return", __name__, url_prefix="/admin/pickup-return"
)


def _list_context():
    """Bookings decorated with pickup/return state for the records list."""
    term = request.args.get("q", "").strip()
    state = request.args.get("state", "").strip() or None
    if term:
        bookings = booking_repository.search(term)
    else:
        bookings = booking_repository.list_all()
    records = [pickup_service.decorate(booking) for booking in bookings]
    if state:
        records = [record for record in records if record["state"] == state]
    return records, term, state


@blueprint.get("")
@admin_required
def index():
    """List bookings as pickup/return records, with search and state filters."""
    records, term, state = _list_context()
    return render_template(
        "admin/pickup_return/index.html",
        records=records,
        search_term=term,
        state_filter=state or "",
        states=(
            ("ready_for_pickup", "Ready for pickup"),
            ("picked_up", "Picked up"),
            ("returned", "Returned"),
        ),
    )


@blueprint.get("/<int:booking_id>")
@admin_required
def detail(booking_id):
    """Show the pickup/return record for a booking."""
    booking = booking_repository.find_by_id(booking_id)
    if booking is None:
        abort(404)
    record = pickup_service.decorate(booking)
    return render_template("admin/pickup_return/detail.html", record=record)


def _form_context(booking, form, errors):
    return {
        "booking": booking,
        "agreement": booking.rental_agreement,
        "form": form or {},
        "errors": errors or [],
    }


@blueprint.route("/<int:booking_id>/pickup", methods=["GET", "POST"])
@admin_required
def pickup(booking_id):
    """Show the pickup form, or record pickup for an eligible booking."""
    booking = booking_repository.find_by_id(booking_id)
    if booking is None:
        abort(404)
    guard = pickup_service.pickup_eligibility_error(booking)
    if guard:
        flash(guard, "danger")
        return redirect(
            url_for("admin_pickup_return.detail", booking_id=booking.id)
        )

    if request.method == "POST":
        booking, errors = pickup_service.record_pickup(booking, request.form)
        if not errors:
            flash(
                f"Pickup recorded for booking {booking.booking_number}.",
                "success",
            )
            return redirect(
                url_for("admin_pickup_return.detail", booking_id=booking.id)
            )
        return render_template(
            "admin/pickup_return/pickup.html",
            **_form_context(booking, request.form, errors),
        )

    agreement = booking.rental_agreement
    initial = {
        "pickup_mileage": agreement.pickup_mileage,
        "fuel_level_pickup": agreement.fuel_level_pickup,
        "notes": agreement.notes or "",
    }
    return render_template(
        "admin/pickup_return/pickup.html",
        **_form_context(booking, initial, []),
    )


@blueprint.route("/<int:booking_id>/return", methods=["GET", "POST"])
@admin_required
def return_record(booking_id):
    """Show the return form, or record return for a picked-up booking."""
    booking = booking_repository.find_by_id(booking_id)
    if booking is None:
        abort(404)
    guard = pickup_service.return_eligibility_error(booking)
    if guard:
        flash(guard, "danger")
        return redirect(
            url_for("admin_pickup_return.detail", booking_id=booking.id)
        )

    if request.method == "POST":
        booking, errors = pickup_service.record_return(booking, request.form)
        if not errors:
            flash(
                f"Return recorded for booking {booking.booking_number}.",
                "success",
            )
            return redirect(
                url_for("admin_pickup_return.detail", booking_id=booking.id)
            )
        return render_template(
            "admin/pickup_return/return.html",
            **_form_context(booking, request.form, errors),
        )

    agreement = booking.rental_agreement
    initial = {
        "return_mileage": agreement.return_mileage or "",
        "fuel_level_return": agreement.fuel_level_return or "",
        "notes": agreement.notes or "",
    }
    return render_template(
        "admin/pickup_return/return.html",
        **_form_context(booking, initial, []),
    )