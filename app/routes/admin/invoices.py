"""Admin invoice management blueprint.

CRUD routes for invoices, all guarded by the admin_required page guard.
Invoices link to real DB-backed bookings (one per booking) and store
their own amount snapshot so history survives later edits.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import invoice_repository
from app.repositories.booking_repository import list_all as list_bookings
from app.services.invoice_service import (
    InvoiceError,
    cancel_invoice,
    create_invoice,
    next_invoice_number,
    update_invoice,
)
from app.utils.constants import InvoiceStatus
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_invoices", __name__, url_prefix="/admin/invoices")


def _form_from_invoice(invoice):
    """Render an invoice's current values as a form dict."""
    return {
        "booking_id": invoice.booking_id,
        "invoice_number": invoice.invoice_number,
        "subtotal": invoice.subtotal,
        "tax_amount": invoice.tax_amount,
        "discount_amount": invoice.discount_amount,
        "due_date": invoice.due_date.strftime("%Y-%m-%d"),
        "paid_date": invoice.paid_date.strftime("%Y-%m-%d") if invoice.paid_date else "",
        "status": invoice.status,
        "notes": invoice.notes or "",
    }


def _form_context(invoice=None, form=None, errors=None):
    """Common template variables for the invoice forms."""
    return {
        "bookings": list_bookings(),
        "statuses": InvoiceStatus.ALL,
        "invoice": invoice,
        "form": form or {},
        "errors": errors or [],
    }


@blueprint.get("")
@admin_required
def index():
    """List invoices, optionally filtered by the ``q`` term and ``status``."""
    term = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip() or None
    if term or status:
        invoices = invoice_repository.search(term, status)
    else:
        invoices = invoice_repository.list_all()
    return render_template(
        "admin/invoices/index.html",
        invoices=invoices,
        search_term=term,
        status_filter=status or "",
        statuses=InvoiceStatus.ALL,
    )


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new invoice."""
    if request.method == "POST":
        invoice, errors = create_invoice(request.form)
        if not errors:
            flash(
                f"Invoice {invoice.invoice_number} created successfully.",
                "success",
            )
            return redirect(url_for("admin_invoices.detail", invoice_id=invoice.id))
        return render_template(
            "admin/invoices/form.html",
            **_form_context(form=request.form, errors=errors),
        )

    initial = {"invoice_number": next_invoice_number()}
    return render_template(
        "admin/invoices/form.html",
        **_form_context(form=initial),
    )


@blueprint.get("/<int:invoice_id>")
@admin_required
def detail(invoice_id):
    """Show an invoice's details and its linked booking."""
    invoice = invoice_repository.find_by_id(invoice_id)
    if invoice is None:
        abort(404)
    return render_template("admin/invoices/detail.html", invoice=invoice)


@blueprint.route("/<int:invoice_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(invoice_id):
    """Show the edit form, or persist changes to an invoice."""
    invoice = invoice_repository.find_by_id(invoice_id)
    if invoice is None:
        abort(404)

    if request.method == "POST":
        invoice, errors = update_invoice(invoice, request.form)
        if not errors:
            flash(f"Invoice {invoice.invoice_number} updated successfully.", "success")
            return redirect(url_for("admin_invoices.detail", invoice_id=invoice.id))
        return render_template(
            "admin/invoices/form.html",
            **_form_context(invoice=invoice, form=request.form, errors=errors),
        )

    return render_template(
        "admin/invoices/form.html",
        **_form_context(invoice=invoice, form=_form_from_invoice(invoice)),
    )


@blueprint.post("/<int:invoice_id>/delete")
@admin_required
def delete(invoice_id):
    """Safely cancel (soft-delete) an invoice."""
    invoice = invoice_repository.find_by_id(invoice_id)
    if invoice is None:
        abort(404)

    try:
        cancel_invoice(invoice)
    except InvoiceError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Invoice {invoice.invoice_number} cancelled.", "success")
    return redirect(url_for("admin_invoices.index"))