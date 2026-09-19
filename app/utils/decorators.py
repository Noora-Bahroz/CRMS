"""Decorators for route protection.

Authentication and authorization are kept separate.

Authentication (``login_required``) guards any route behind an
authenticated session and returns 401 when unauthenticated. Authorization
(``role_required``, ``admin_required``) additionally restricts who may
call a route.

Admin **page** routes use ``admin_required``: unauthenticated visitors are
sent to the admin login page and non-admin users receive a 403. Admin
**JSON API** routes use ``json_admin_required`` so programmatic consumers
receive proper 401/403 responses.
"""

from functools import wraps

from flask import abort, jsonify, redirect, request, url_for

from app.services.auth_service import get_current_user
from app.services.authorization_service import is_admin_or_staff, is_customer_account

_AUTH_REQUIRED = {"error": "Authentication required."}
_FORBIDDEN = {"error": "You do not have permission to access this resource."}


def _authorize(view, check):
    """Wrap *view*, requiring authentication then satisfying *check*."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify(_AUTH_REQUIRED), 401
        if not check(user):
            return jsonify(_FORBIDDEN), 403
        return view(*args, **kwargs)

    return wrapped_view


def login_required(view):
    """Require an authenticated session to call *view*.

    Returns a 401 JSON response when the request is not authenticated; the
    view is called unchanged otherwise.
    """
    return _authorize(view, lambda user: True)


def json_admin_required(view):
    """Require an internal admin/staff account for a JSON API route.

    Returns a 401 JSON response when unauthenticated and a 403 JSON
    response when the authenticated user is not allowed.
    """
    return _authorize(view, is_admin_or_staff)


def role_required(*roles):
    """Require an authenticated user holding one of *roles*.

    The returned decorator returns 401 when unauthenticated and 403 when
    the authenticated user holds none of *roles*.

    Example::

        @blueprint.get("/staff-tasks")
        @role_required(UserRole.ADMIN, UserRole.STAFF)
        def staff_tasks():
            ...
    """

    def decorator(view):
        return _authorize(view, lambda user: user.role in roles)

    return decorator


def admin_required(view):
    """Require an internal admin/staff account to call a page route.

    Unauthenticated visitors are redirected to the admin login page and
    authenticated users who are not admin/staff receive a 403.
    """

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return redirect(url_for("admin_auth.login"))
        if not is_admin_or_staff(user):
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def customer_required(view):
    """Require an authenticated customer account for a page route.

    Unauthenticated visitors are sent to the public login page with a
    ``next`` target so they return to where they were headed.  Internal
    admin/staff accounts are never treated as customers: they are sent to
    the     admin dashboard instead of being handed the customer area.
    """

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return redirect(
                url_for("public.login", next=request.full_path.rstrip("?"))
            )
        if not is_customer_account(user):
            if is_admin_or_staff(user):
                return redirect(url_for("admin_dashboard.dashboard"))
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view