"""Admin category management blueprint.

CRUD routes for car categories, all guarded by the admin_required page
guard. Uses flash messages for feedback and follows the service layer for
validation and safe deactivation.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import category_repository
from app.services.category_service import (
    CategoryError,
    create_category,
    deactivate_category,
    update_category,
)
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_categories", __name__, url_prefix="/admin/categories")


def _form_from_category(category):
    """Render a category's current values as a form dict."""
    return {
        "name": category.name,
        "description": category.description or "",
        "daily_rate": category.daily_rate,
        "weekly_rate": category.weekly_rate,
        "monthly_rate": category.monthly_rate,
        "deposit_amount": category.deposit_amount,
        "is_active": "1" if category.is_active else "",
    }


@blueprint.get("")
@admin_required
def index():
    """List all categories."""
    categories = category_repository.list_all()
    return render_template("admin/categories/index.html", categories=categories)


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new category."""
    if request.method == "POST":
        category, errors = create_category(request.form)
        if not errors:
            flash(f"Category '{category.name}' created successfully.", "success")
            return redirect(url_for("admin_categories.index"))
        return render_template(
            "admin/categories/form.html",
            category=None, form=request.form, errors=errors,
        )

    return render_template(
        "admin/categories/form.html", category=None, form={}, errors=[]
    )


@blueprint.route("/<int:category_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(category_id):
    """Show the edit form, or persist changes to a category."""
    category = category_repository.find_by_id(category_id)
    if category is None:
        abort(404)

    if request.method == "POST":
        category, errors = update_category(category, request.form)
        if not errors:
            flash(f"Category '{category.name}' updated successfully.", "success")
            return redirect(url_for("admin_categories.index"))
        return render_template(
            "admin/categories/form.html",
            category=category, form=request.form, errors=errors,
        )

    return render_template(
        "admin/categories/form.html",
        category=category, form=_form_from_category(category), errors=[],
    )


@blueprint.post("/<int:category_id>/delete")
@admin_required
def delete(category_id):
    """Safely deactivate a category."""
    category = category_repository.find_by_id(category_id)
    if category is None:
        abort(404)

    try:
        deactivate_category(category)
    except CategoryError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Category '{category.name}' deleted.", "success")
    return redirect(url_for("admin_categories.index"))