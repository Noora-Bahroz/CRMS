"""Admin booking management blueprint.

CRUD routes for bookings, all guarded by the admin_required page guard.
Bookings use real database records for customer, car, branch, and driver
dropdowns, and the service layer rejects overlapping active bookings for
the same car.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import booking_repository
from app.repositories.branch_repository import list_all as list_branches
from app.repositories.car_repository import list_all as list_cars
from app.repositories.customer_repository import list_all as list_customers
from app.repositories.driver_repository import list_all as list_drivers
from app.services.booking_service import (
    BookingError,
    cancel_booking,
    create_booking,
    update_booking,
)
from app.utils.constants import BookingStatus
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_bookings", __name__, url_prefix="/admin/bookings")


def _form_from_booking(booking):
    """Render a booking's current values as a form dict."""
    return {
        "customer_id": booking.customer_id,
        "car_id": booking.car_id,
        "driver_id": booking.driver_id or "",
        "pickup_branch_id": booking.pickup_branch_id,
        "return_branch_id": booking.return_branch_id,
        "pickup_datetime": booking.pickup_datetime.strftime("%Y-%m-%dT%H:%M"),
        "return_datetime": booking.return_datetime.strftime("%Y-%m-%dT%H:%M"),
        "status": booking.status,
        "requires_driver": "1" if booking.requires_driver else "",
        "additional_charges": booking.additional_charges,
        "discount": booking.discount,
        "notes": booking.notes or "",
    }


def _form_context(booking=None, form=None, errors=None):
    """Common template variables for the booking forms."""
    return {
        "customers": list_customers(),
        "cars": list_cars(),
        "branches": list_branches(),
        "drivers": list_drivers(),
        "statuses": BookingStatus.ALL,
        "booking": booking,
        "form": form,
        "errors": errors or [],
    }


@blueprint.get("")
@admin_required
def index():
    """List bookings, optionally filtered by the ``q`` term and ``status``."""
    term = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip() or None
    if term or status:
        bookings = booking_repository.search(term, status)
    else:
        bookings = booking_repository.list_all()
    return render_template(
        "admin/bookings/index.html",
        bookings=bookings,
        search_term=term,
        status_filter=status or "",
        statuses=BookingStatus.ALL,
    )


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new booking."""
    if request.method == "POST":
        booking, errors = create_booking(request.form)
        if not errors:
            flash(
                f"Booking {booking.booking_number} created successfully.",
                "success",
            )
            return redirect(url_for("admin_bookings.detail", booking_id=booking.id))
        return render_template(
            "admin/bookings/form.html",
            **_form_context(form=request.form, errors=errors),
        )

    return render_template(
        "admin/bookings/form.html", **_form_context(form={}),
    )


@blueprint.get("/<int:booking_id>")
@admin_required
def detail(booking_id):
    """Show a booking's details and its linked payments."""
    booking = booking_repository.find_by_id(booking_id)
    if booking is None:
        abort(404)
    return render_template("admin/bookings/detail.html", booking=booking)


@blueprint.route("/<int:booking_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(booking_id):
    """Show the edit form, or persist changes to a booking."""
    booking = booking_repository.find_by_id(booking_id)
    if booking is None:
        abort(404)

    if request.method == "POST":
        booking, errors = update_booking(booking, request.form)
        if not errors:
            flash(f"Booking {booking.booking_number} updated successfully.", "success")
            return redirect(url_for("admin_bookings.detail", booking_id=booking.id))
        return render_template(
            "admin/bookings/form.html",
            **_form_context(booking=booking, form=request.form, errors=errors),
        )

    return render_template(
        "admin/bookings/form.html",
        **_form_context(booking=booking, form=_form_from_booking(booking)),
    )


@blueprint.post("/<int:booking_id>/delete")
@admin_required
def delete(booking_id):
    """Safely cancel (soft-delete) a booking."""
    booking = booking_repository.find_by_id(booking_id)
    if booking is None:
        abort(404)

    try:
        cancel_booking(booking)
    except BookingError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Booking {booking.booking_number} cancelled.", "success")
    return redirect(url_for("admin_bookings.index"))