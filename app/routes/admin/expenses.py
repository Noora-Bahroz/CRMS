"""Admin expense management blueprint.

CRUD routes for operational and fleet expenses, all guarded by the
admin_required page guard.  Expenses link to real branches, cars, or
maintenance records chosen from the database; at least one such reference
is required.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import expense_repository, maintenance_repository
from app.repositories.branch_repository import list_active as list_branches
from app.repositories.car_repository import list_active as list_cars
from app.services.expense_service import (
    ExpenseError,
    create_expense,
    delete_expense,
    update_expense,
)
from app.utils.constants import ExpenseCategory
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_expenses", __name__, url_prefix="/admin/expenses")


def _form_from_expense(expense):
    """Render an expense's current values as a form dict."""
    return {
        "category": expense.category,
        "branch_id": expense.branch_id or "",
        "car_id": expense.car_id or "",
        "maintenance_id": expense.maintenance_id or "",
        "amount": expense.amount,
        "description": expense.description,
        "receipt_url": expense.receipt_url or "",
        "recorded_by": expense.recorded_by or "",
        "expense_date": expense.expense_date.strftime("%Y-%m-%d"),
    }


def _form_context(expense=None, form=None, errors=None):
    """Common template variables for the expense forms."""
    return {
        "categories": ExpenseCategory.ALL,
        "branches": list_branches(),
        "cars": list_cars(),
        "maintenance_records": maintenance_repository.list_all(),
        "expense": expense,
        "form": form or {},
        "errors": errors or [],
    }


@blueprint.get("")
@admin_required
def index():
    """List expenses, optionally filtered by ``q`` + ``category``."""
    term = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip() or None
    if term or category:
        expenses = expense_repository.search(term, category)
    else:
        expenses = expense_repository.list_all()
    return render_template(
        "admin/expenses/index.html",
        expenses=expenses,
        search_term=term,
        category_filter=category or "",
        categories=ExpenseCategory.ALL,
    )


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new expense."""
    if request.method == "POST":
        expense, errors = create_expense(request.form)
        if not errors:
            flash("Expense recorded successfully.", "success")
            return redirect(url_for("admin_expenses.detail", expense_id=expense.id))
        return render_template(
            "admin/expenses/form.html",
            **_form_context(form=request.form, errors=errors),
        )

    return render_template("admin/expenses/form.html", **_form_context())


@blueprint.get("/<int:expense_id>")
@admin_required
def detail(expense_id):
    """Show an expense's details and its linked references."""
    expense = expense_repository.find_by_id(expense_id)
    if expense is None:
        abort(404)
    return render_template("admin/expenses/detail.html", expense=expense)


@blueprint.route("/<int:expense_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(expense_id):
    """Show the edit form, or persist changes to an expense."""
    expense = expense_repository.find_by_id(expense_id)
    if expense is None:
        abort(404)

    if request.method == "POST":
        expense, errors = update_expense(expense, request.form)
        if not errors:
            flash(f"Expense #{expense.id} updated successfully.", "success")
            return redirect(url_for("admin_expenses.detail", expense_id=expense.id))
        return render_template(
            "admin/expenses/form.html",
            **_form_context(expense=expense, form=request.form, errors=errors),
        )

    return render_template(
        "admin/expenses/form.html",
        **_form_context(expense=expense, form=_form_from_expense(expense)),
    )


@blueprint.post("/<int:expense_id>/delete")
@admin_required
def delete(expense_id):
    """Delete an expense record."""
    expense = expense_repository.find_by_id(expense_id)
    if expense is None:
        abort(404)

    try:
        delete_expense(expense)
    except ExpenseError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Expense #{expense_id} deleted.", "success")
    return redirect(url_for("admin_expenses.index"))