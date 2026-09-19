"""Customer-facing authentication blueprint.

Session-based login and logout plus a protected ``/me`` endpoint used to
resolve the authenticated user. Customer and admin accounts share the
``users`` table, so the same endpoint authenticates any active user;
``role`` is available on the returned user object as authorization
groundwork.
"""

from flask import Blueprint, jsonify, request

from app.services.auth_service import (
    authenticate_user,
    get_current_user,
    login_user,
    logout_user,
    user_to_dict,
)
from app.utils.decorators import login_required

blueprint = Blueprint("auth", __name__)


@blueprint.post("/login")
def login():
    """Authenticate a user and start a session."""
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user, error, status = authenticate_user(email, password)
    if user is None:
        return jsonify({"error": error}), status

    login_user(user)
    return jsonify({"message": "Login successful.", "user": user_to_dict(user)}), 200


@blueprint.post("/logout")
def logout():
    """End the current session."""
    logout_user()
    return jsonify({"message": "You have been logged out."}), 200


@blueprint.get("/me")
@login_required
def me():
    """Return the authenticated user's details."""
    return jsonify({"user": user_to_dict(get_current_user())}), 200