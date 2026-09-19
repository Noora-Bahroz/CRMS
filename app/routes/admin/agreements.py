"""Admin rental agreement management blueprint.

CRUD routes for rental agreements, all guarded by the admin_required page
guard.  Agreements link to real DB-backed bookings (one per booking) and
carry the vehicle-condition and signature fields from the model.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import agreement_repository
from app.repositories.booking_repository import list_all as list_bookings
from app.services.agreement_service import (
    AgreementError,
    create_agreement,
    next_agreement_number,
    terminate_agreement,
    update_agreement,
)
from app.utils.constants import AgreementStatus
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_agreements", __name__, url_prefix="/admin/agreements")


def _form_from_agreement(agreement):
    """Render an agreement's current values as a form dict."""
    return {
        "booking_id": agreement.booking_id,
        "agreement_number": agreement.agreement_number,
        "status": agreement.status,
        "signed_by_customer": "1" if agreement.signed_by_customer else "",
        "signed_by_staff": "1" if agreement.signed_by_staff else "",
        "signed_at": agreement.signed_at.strftime("%Y-%m-%d") if agreement.signed_at else "",
        "terms_and_conditions": agreement.terms_and_conditions,
        "pickup_mileage": agreement.pickup_mileage,
        "return_mileage": agreement.return_mileage or "",
        "fuel_level_pickup": agreement.fuel_level_pickup,
        "fuel_level_return": agreement.fuel_level_return or "",
        "notes": agreement.notes or "",
    }


def _form_context(agreement=None, form=None, errors=None):
    """Common template variables for the agreement forms."""
    return {
        "bookings": list_bookings(),
        "statuses": AgreementStatus.ALL,
        "agreement": agreement,
        "form": form or {},
        "errors": errors or [],
    }


@blueprint.get("")
@admin_required
def index():
    """List agreements, optionally filtered by the ``q`` term and ``status``."""
    term = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip() or None
    if term or status:
        agreements = agreement_repository.search(term, status)
    else:
        agreements = agreement_repository.list_all()
    return render_template(
        "admin/agreements/index.html",
        agreements=agreements,
        search_term=term,
        status_filter=status or "",
        statuses=AgreementStatus.ALL,
    )


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new agreement."""
    if request.method == "POST":
        agreement, errors = create_agreement(request.form)
        if not errors:
            flash(
                f"Agreement {agreement.agreement_number} created successfully.",
                "success",
            )
            return redirect(
                url_for("admin_agreements.detail", agreement_id=agreement.id)
            )
        return render_template(
            "admin/agreements/form.html",
            **_form_context(form=request.form, errors=errors),
        )

    initial = {"agreement_number": next_agreement_number()}
    return render_template(
        "admin/agreements/form.html",
        **_form_context(form=initial),
    )


@blueprint.get("/<int:agreement_id>")
@admin_required
def detail(agreement_id):
    """Show an agreement's details and its linked booking."""
    agreement = agreement_repository.find_by_id(agreement_id)
    if agreement is None:
        abort(404)
    return render_template("admin/agreements/detail.html", agreement=agreement)


@blueprint.route("/<int:agreement_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(agreement_id):
    """Show the edit form, or persist changes to an agreement."""
    agreement = agreement_repository.find_by_id(agreement_id)
    if agreement is None:
        abort(404)

    if request.method == "POST":
        agreement, errors = update_agreement(agreement, request.form)
        if not errors:
            flash(
                f"Agreement {agreement.agreement_number} updated successfully.",
                "success",
            )
            return redirect(
                url_for("admin_agreements.detail", agreement_id=agreement.id)
            )
        return render_template(
            "admin/agreements/form.html",
            **_form_context(
                agreement=agreement, form=request.form, errors=errors
            ),
        )

    return render_template(
        "admin/agreements/form.html",
        **_form_context(agreement=agreement, form=_form_from_agreement(agreement)),
    )


@blueprint.post("/<int:agreement_id>/delete")
@admin_required
def delete(agreement_id):
    """Safely terminate (soft-delete) a rental agreement."""
    agreement = agreement_repository.find_by_id(agreement_id)
    if agreement is None:
        abort(404)

    try:
        terminate_agreement(agreement)
    except AgreementError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Agreement {agreement.agreement_number} terminated.", "success")
    return redirect(url_for("admin_agreements.index"))