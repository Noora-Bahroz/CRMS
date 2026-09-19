"""Admin authentication blueprint.

Serves the dedicated admin login page at ``/admin/login``. Reuses the
existing single authentication service: credentials are verified exactly
like the public login, then the admin authorization rules decide whether
the account may enter the panel. Admin/staff accounts without a Customer
profile are allowed; customer accounts are refused.
"""

from flask import Blueprint, redirect, render_template, request, url_for

from app.services.auth_service import (
    authenticate_user,
    get_current_user,
    login_user,
)
from app.services.authorization_service import is_admin_or_staff

blueprint = Blueprint("admin_auth", __name__, url_prefix="/admin")


@blueprint.route("/login", methods=["GET", "POST"])
def login():
    user = get_current_user()
    if user is not None:
        if is_admin_or_staff(user):
            return redirect(url_for("admin_dashboard.dashboard"))
        return redirect("/")

    error = None
    email = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        if not email or not password:
            error = "Email and password are required."
        else:
            user, message, _status = authenticate_user(email, password)
            if user is None:
                error = message
            elif not is_admin_or_staff(user):
                error = "This account does not have access to the admin panel."
            else:
                login_user(user)
                return redirect(url_for("admin_dashboard.dashboard"))

    return render_template("admin/login.html", error=error, email=email)