"""Admin customer management blueprint.

CRUD routes for customers, all guarded by the admin_required page guard.
Customer identity data lives on the linked User account; passwords are
hashed by the service layer and never exposed to the UI.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import customer_repository
from app.services.customer_service import (
    CustomerError,
    create_customer,
    deactivate_customer,
    update_customer,
)
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_customers", __name__, url_prefix="/admin/customers")


def _form_from_customer(customer):
    """Render a customer's current values as a form dict (no password)."""
    user = customer.user
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "username": user.username,
        "phone": user.phone or "",
        "driver_license_number": customer.driver_license_number,
        "driver_license_expiry": customer.driver_license_expiry.strftime("%Y-%m-%d"),
        "date_of_birth": customer.date_of_birth.strftime("%Y-%m-%d")
        if customer.date_of_birth
        else "",
        "address": customer.address or "",
        "city": customer.city or "",
        "state": customer.state or "",
        "zip_code": customer.zip_code or "",
        "emergency_contact_name": customer.emergency_contact_name or "",
        "emergency_contact_phone": customer.emergency_contact_phone or "",
        "notes": customer.notes or "",
        "is_active": "1" if user.is_active else "",
    }


@blueprint.get("")
@admin_required
def index():
    """List customers, optionally filtered by the ``q`` search term."""
    term = request.args.get("q", "").strip()
    if term:
        customers = customer_repository.search_customers(term)
    else:
        customers = customer_repository.list_all()
    return render_template(
        "admin/customers/index.html", customers=customers, search_term=term
    )


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new customer + account."""
    if request.method == "POST":
        customer, errors = create_customer(request.form)
        if not errors:
            flash(
                f"Customer {customer.user.first_name} {customer.user.last_name} "
                "created successfully.",
                "success",
            )
            return redirect(url_for("admin_customers.index"))
        return render_template(
            "admin/customers/form.html",
            customer=None, form=request.form, errors=errors,
        )

    return render_template(
        "admin/customers/form.html", customer=None, form={}, errors=[]
    )


@blueprint.get("/<int:customer_id>")
@admin_required
def detail(customer_id):
    """Show a customer's profile and linked account (no password data)."""
    customer = customer_repository.find_by_id(customer_id)
    if customer is None:
        abort(404)
    return render_template("admin/customers/detail.html", customer=customer)


@blueprint.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(customer_id):
    """Show the edit form, or persist changes to a customer."""
    customer = customer_repository.find_by_id(customer_id)
    if customer is None:
        abort(404)

    if request.method == "POST":
        customer, errors = update_customer(customer, request.form)
        if not errors:
            flash(
                f"Customer {customer.user.first_name} {customer.user.last_name} "
                "updated successfully.",
                "success",
            )
            return redirect(url_for("admin_customers.detail", customer_id=customer.id))
        return render_template(
            "admin/customers/form.html",
            customer=customer, form=request.form, errors=errors,
        )

    return render_template(
        "admin/customers/form.html",
        customer=customer, form=_form_from_customer(customer), errors=[],
    )


@blueprint.post("/<int:customer_id>/delete")
@admin_required
def delete(customer_id):
    """Safely deactivate a customer account."""
    customer = customer_repository.find_by_id(customer_id)
    if customer is None:
        abort(404)

    try:
        deactivate_customer(customer)
    except CustomerError as exc:
        flash(str(exc), "danger")
    else:
        flash(
            f"Customer {customer.user.first_name} {customer.user.last_name} "
            "deleted.",
            "success",
        )
    return redirect(url_for("admin_customers.index"))