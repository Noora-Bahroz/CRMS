"""Admin payment management blueprint.

CRUD routes for payments, all guarded by the admin_required page guard.
Payments link to real bookings chosen from the database, and record cash
or card payments inside the existing CRMS database (no gateway
integration).
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import payment_repository
from app.repositories.booking_repository import list_all as list_bookings
from app.services.payment_service import (
    PaymentError,
    create_payment,
    delete_payment,
    update_payment,
)
from app.utils.constants import PaymentMethod, PaymentStatus
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_payments", __name__, url_prefix="/admin/payments")


def _form_from_payment(payment):
    """Render a payment's current values as a form dict."""
    return {
        "booking_id": payment.booking_id,
        "amount": payment.amount,
        "method": payment.method,
        "status": payment.status,
        "reference_number": payment.reference_number or "",
        "received_by": payment.received_by or "",
        "notes": payment.notes or "",
    }


def _form_context(payment=None, form=None, errors=None):
    """Common template variables for the payment forms."""
    return {
        "bookings": list_bookings(),
        "methods": PaymentMethod.ALL,
        "statuses": PaymentStatus.ALL,
        "payment": payment,
        "form": form,
        "errors": errors or [],
    }


@blueprint.get("")
@admin_required
def index():
    """List payments, optionally filtered by the ``q`` term and ``status``."""
    term = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip() or None
    if term or status:
        payments = payment_repository.search(term, status)
    else:
        payments = payment_repository.list_all()
    return render_template(
        "admin/payments/index.html",
        payments=payments,
        search_term=term,
        status_filter=status or "",
        statuses=PaymentStatus.ALL,
    )


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or record a new payment."""
    if request.method == "POST":
        payment, errors = create_payment(request.form)
        if not errors:
            flash("Payment recorded successfully.", "success")
            return redirect(url_for("admin_payments.detail", payment_id=payment.id))
        return render_template(
            "admin/payments/form.html",
            **_form_context(form=request.form, errors=errors),
        )

    return render_template(
        "admin/payments/form.html", **_form_context(form={}),
    )


@blueprint.get("/<int:payment_id>")
@admin_required
def detail(payment_id):
    """Show a payment's details and its linked booking."""
    payment = payment_repository.find_by_id(payment_id)
    if payment is None:
        abort(404)
    return render_template("admin/payments/detail.html", payment=payment)


@blueprint.route("/<int:payment_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(payment_id):
    """Show the edit form, or persist changes to a payment."""
    payment = payment_repository.find_by_id(payment_id)
    if payment is None:
        abort(404)

    if request.method == "POST":
        payment, errors = update_payment(payment, request.form)
        if not errors:
            flash("Payment updated successfully.", "success")
            return redirect(url_for("admin_payments.detail", payment_id=payment.id))
        return render_template(
            "admin/payments/form.html",
            **_form_context(payment=payment, form=request.form, errors=errors),
        )

    return render_template(
        "admin/payments/form.html",
        **_form_context(payment=payment, form=_form_from_payment(payment)),
    )


@blueprint.post("/<int:payment_id>/delete")
@admin_required
def delete(payment_id):
    """Delete a payment record."""
    payment = payment_repository.find_by_id(payment_id)
    if payment is None:
        abort(404)

    try:
        delete_payment(payment)
    except PaymentError as exc:
        flash(str(exc), "danger")
    else:
        flash("Payment deleted.", "success")
    return redirect(url_for("admin_payments.index"))