"""Admin user / staff management blueprint.

CRUD routes for internal accounts, all guarded by the admin_required page
guard.  Uses the existing single User model and UserRole values.  Accounts
are never deleted — only activated/deactivated via ``is_active`` — and the
currently logged-in account cannot be deactivated from this panel.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import user_repository
from app.services.auth_service import get_current_user
from app.services.user_service import create_user, set_active, update_user
from app.utils import validators
from app.utils.constants import UserRole
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_users", __name__, url_prefix="/admin/users")


def _form_from_user(user):
    """Render a user's current values as a form dict (no password)."""
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "email": user.email,
        "phone": user.phone or "",
        "role": user.role,
        "is_active": "1" if user.is_active else "",
    }


def _form_context(user=None, form=None, errors=None):
    """Common template variables for the user forms."""
    return {
        "roles": UserRole.ALL,
        "user": user,
        "is_customer": user is not None and user.customer is not None,
        "form": form or {},
        "errors": errors or [],
    }


@blueprint.get("")
@admin_required
def index():
    """List users, optionally filtered by ``q``, ``role`` and ``active``."""
    term = request.args.get("q", "").strip()
    role = request.args.get("role", "").strip() or None
    active_raw = request.args.get("active", "").strip() or None
    active = active_raw == "active" if active_raw is not None else None
    users = user_repository.search(term, role, active)
    return render_template(
        "admin/users/index.html",
        users=users,
        search_term=term,
        role_filter=role or "",
        active_filter=active_raw or "",
        roles=UserRole.ALL,
        current_user=get_current_user(),
    )


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new staff/admin account."""
    if request.method == "POST":
        user, errors = create_user(request.form)
        if not errors:
            flash(
                f"User {user.first_name} {user.last_name} ({user.username}) "
                "created successfully.",
                "success",
            )
            return redirect(url_for("admin_users.index"))
        return render_template(
            "admin/users/form.html",
            **_form_context(form=request.form, errors=errors),
        )

    return render_template("admin/users/form.html", **_form_context())


@blueprint.route("/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(user_id):
    """Show the edit form, or persist changes to a user account."""
    user = user_repository.find_by_id(user_id)
    if user is None:
        abort(404)

    if request.method == "POST":
        form = request.form
        if (
            user.id == get_current_user().id
            and not validators.parse_bool(form.get("is_active", True))
        ):
            return render_template(
                "admin/users/form.html",
                **_form_context(
                    user=user,
                    form=form,
                    errors=["You cannot deactivate your own account."],
                ),
            )
        user, errors = update_user(user, form)
        if not errors:
            flash(
                f"User {user.first_name} {user.last_name} updated successfully.",
                "success",
            )
            return redirect(url_for("admin_users.index"))
        return render_template(
            "admin/users/form.html",
            **_form_context(user=user, form=form, errors=errors),
        )

    return render_template(
        "admin/users/form.html",
        **_form_context(user=user, form=_form_from_user(user)),
    )


@blueprint.post("/<int:user_id>/activate")
@admin_required
def activate(user_id):
    """Re-activate a deactivated account."""
    user = user_repository.find_by_id(user_id)
    if user is None:
        abort(404)
    set_active(user, True)
    flash(f"User {user.username} reactivated.", "success")
    return redirect(url_for("admin_users.index"))


@blueprint.post("/<int:user_id>/deactivate")
@admin_required
def deactivate(user_id):
    """Deactivate an account (never the currently logged-in one)."""
    user = user_repository.find_by_id(user_id)
    if user is None:
        abort(404)
    if user.id == get_current_user().id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("admin_users.index"))
    set_active(user, False)
    flash(f"User {user.username} deactivated.", "success")
    return redirect(url_for("admin_users.index"))