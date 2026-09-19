"""Customer area blueprint.

Authenticated customer pages under /customer: dashboard, booking history,
booking details, self-service profile editing, and read-only invoice and
payment history.

Every query is scoped to the signed-in customer's own ``customer_id`` so
one customer can never read or modify another's reservations, invoices,
or payments, and safe cancellation reuses the existing
``cancel_booking`` service (soft status change, so the row and its
payments stay intact).
"""

from datetime import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.repositories import (
    booking_repository,
    invoice_repository,
    payment_repository,
)
from app.services.auth_service import get_current_user
from app.services.booking_service import BookingError, cancel_booking
from app.services.customer_service import update_profile
from app.utils.constants import BookingStatus
from app.utils.decorators import customer_required

blueprint = Blueprint("customer", __name__)

# Only reservations that have not started yet may be cancelled by the
# customer; ongoing/completed/cancelled bookings are left to staff.
_CANCELLABLE = (BookingStatus.PENDING, BookingStatus.CONFIRMED)


def _current_customer():
    """Return the Customer profile of the signed-in customer account."""
    return get_current_user().customer


@blueprint.get("/dashboard")
@customer_required
def dashboard():
    """Customer overview: upcoming and recent reservations."""
    customer = _current_customer()
    bookings = booking_repository.list_for_customer(customer.id)

    now = datetime.utcnow()
    upcoming = [
        booking
        for booking in bookings
        if booking.pickup_datetime >= now
        and booking.status
        in (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ONGOING)
    ]
    upcoming.sort(key=lambda booking: booking.pickup_datetime)

    return render_template(
        "customer/dashboard.html",
        customer=customer,
        upcoming=upcoming[:5],
        recent=bookings[:5],
        total_bookings=len(bookings),
        total_invoices=len(invoice_repository.list_for_customer(customer.id)),
        total_payments=len(payment_repository.list_for_customer(customer.id)),
    )


@blueprint.route("/profile", methods=["GET", "POST"])
@customer_required
def profile():
    """View and update the signed-in customer's own profile.

    Reuses the shared customer validation/hashing so uniqueness rules and
    password handling stay identical to the admin panel.  Admin-only
    fields (role, is_active) are never accepted from this form.
    """
    customer = _current_customer()

    if request.method == "POST":
        _, errors = update_profile(customer, request.form)
        if errors:
            for message in errors:
                flash(message, "danger")
            return (
                render_template(
                    "customer/profile.html", customer=customer, form=request.form
                ),
                200,
            )
        flash("Your profile has been updated.", "success")
        return redirect(url_for("customer.profile"))

    return render_template("customer/profile.html", customer=customer, form=None)


@blueprint.get("/invoices")
@customer_required
def invoices():
    """Invoice list for the signed-in customer only."""
    customer = _current_customer()
    return render_template(
        "customer/invoices.html",
        customer=customer,
        invoices=invoice_repository.list_for_customer(customer.id),
    )


@blueprint.get("/invoices/<int:invoice_id>")
@customer_required
def invoice_detail(invoice_id):
    """Invoice details, only when the invoice's booking belongs to the
    customer."""
    customer = _current_customer()
    invoice = invoice_repository.find_for_customer(customer.id, invoice_id)
    if invoice is None:
        abort(404)
    return render_template(
        "customer/invoice_detail.html", customer=customer, invoice=invoice
    )


@blueprint.get("/payments")
@customer_required
def payments():
    """Payment history for the signed-in customer only.

    Read-only: payments are recorded through the existing admin module
    and customers can neither create nor edit them.
    """
    customer = _current_customer()
    return render_template(
        "customer/payments.html",
        customer=customer,
        payments=payment_repository.list_for_customer(customer.id),
    )


@blueprint.get("/bookings")
@customer_required
def bookings():
    """Full booking history for the signed-in customer only."""
    customer = _current_customer()
    return render_template(
        "customer/bookings.html",
        customer=customer,
        bookings=booking_repository.list_for_customer(customer.id),
    )


@blueprint.get("/bookings/<int:booking_id>")
@customer_required
def booking_detail(booking_id):
    """Booking details, only when the booking belongs to the customer."""
    customer = _current_customer()
    booking = booking_repository.find_for_customer(customer.id, booking_id)
    if booking is None:
        abort(404)
    return render_template(
        "customer/booking_detail.html",
        customer=customer,
        booking=booking,
        cancellable=booking.status in _CANCELLABLE,
    )


@blueprint.post("/bookings/<int:booking_id>/cancel")
@customer_required
def cancel(booking_id):
    """Cancel the customer's own booking using the shared service."""
    customer = _current_customer()
    booking = booking_repository.find_for_customer(customer.id, booking_id)
    if booking is None:
        abort(404)

    if booking.status not in _CANCELLABLE:
        flash(
            f"Booking {booking.booking_number} can no longer be cancelled. "
            "Please contact support.",
            "danger",
        )
        return redirect(
            url_for("customer.booking_detail", booking_id=booking.id)
        )

    try:
        cancel_booking(booking)
    except BookingError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Booking {booking.booking_number} has been cancelled.", "success")
    return redirect(url_for("customer.bookings"))
