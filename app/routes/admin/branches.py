"""Admin branch management blueprint.

CRUD routes for branches, all guarded by the admin_required page guard.
Uses flash messages for feedback and follows the service layer for
validation and safe deactivation.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import branch_repository
from app.services.branch_service import (
    BranchError,
    create_branch,
    deactivate_branch,
    update_branch,
)
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_branches", __name__, url_prefix="/admin/branches")


def _form_from_branch(branch):
    """Render a branch's current values as a form dict."""
    return {
        "name": branch.name,
        "address": branch.address,
        "city": branch.city,
        "state": branch.state or "",
        "zip_code": branch.zip_code or "",
        "phone": branch.phone or "",
        "email": branch.email or "",
        "is_active": "1" if branch.is_active else "",
    }


@blueprint.get("")
@admin_required
def index():
    """List all branches."""
    branches = branch_repository.list_all()
    return render_template("admin/branches/index.html", branches=branches)


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new branch."""
    if request.method == "POST":
        branch, errors = create_branch(request.form)
        if not errors:
            flash(f"Branch '{branch.name}' created successfully.", "success")
            return redirect(url_for("admin_branches.index"))
        return render_template(
            "admin/branches/form.html",
            branch=None, form=request.form, errors=errors,
        )

    return render_template("admin/branches/form.html", branch=None, form={}, errors=[])


@blueprint.route("/<int:branch_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(branch_id):
    """Show the edit form, or persist changes to a branch."""
    branch = branch_repository.find_by_id(branch_id)
    if branch is None:
        abort(404)

    if request.method == "POST":
        branch, errors = update_branch(branch, request.form)
        if not errors:
            flash(f"Branch '{branch.name}' updated successfully.", "success")
            return redirect(url_for("admin_branches.index"))
        return render_template(
            "admin/branches/form.html",
            branch=branch, form=request.form, errors=errors,
        )

    return render_template(
        "admin/branches/form.html",
        branch=branch, form=_form_from_branch(branch), errors=[],
    )


@blueprint.post("/<int:branch_id>/delete")
@admin_required
def delete(branch_id):
    """Safely deactivate a branch."""
    branch = branch_repository.find_by_id(branch_id)
    if branch is None:
        abort(404)

    try:
        deactivate_branch(branch)
    except BranchError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Branch '{branch.name}' deleted.", "success")
    return redirect(url_for("admin_branches.index"))