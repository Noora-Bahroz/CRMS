"""Authentication service.

Responsible for the full login/logout lifecycle:
  * credential verification against the stored werkzeug password hash,
  * session establishment and teardown,
  * resolving the currently authenticated user.

The ``UserRole`` values available on ``User.role`` are the authorization
groundwork: ``login_required`` guards any endpoint, and role-based checks
can be layered on top in a later phase. Password hashes are never
returned here or via the view layer.
"""

from flask import g, session

from app.repositories.user_repository import find_by_email, find_by_id
from app.utils.security import verify_password


def authenticate_user(email: str, password: str) -> tuple:
    """Verify *email*/*password* against the database.

    Returns ``(user, error_message, status_code)``:
      * valid, active user          -> ``(user, None, None)``
      * unknown email / bad password-> ``(None, msg, 401)`` (generic error)
      * deactivated account         -> ``(None, msg, 403)``

    Unknown emails and wrong passwords return the same generic message so
    the endpoint never reveals which part failed.
    """
    user = find_by_email(email)
    if user is None:
        return None, "Invalid email or password.", 401
    if not user.is_active:
        return None, "This account has been deactivated.", 403
    if not verify_password(password, user.password_hash):
        return None, "Invalid email or password.", 401
    return user, None, None


def login_user(user) -> None:
    """Establish an authenticated session for *user*."""
    session["user_id"] = user.id
    g.user = user


def logout_user() -> None:
    """Clear the authenticated session."""
    session.pop("user_id", None)
    g.pop("user", None)


def get_current_user():
    """Return the authenticated user for the current request, or ``None``.

    The user is re-loaded from the database so role/active changes are
    respected on every request.
    """
    user_id = session.get("user_id")
    if user_id is None:
        return None

    user = getattr(g, "user", None)
    if user is None or user.id != user_id:
        user = find_by_id(user_id)

    if user is None or not user.is_active:
        session.pop("user_id", None)
        return None

    g.user = user
    return user


def user_to_dict(user) -> dict:
    """Serialize a user for API responses.

    Deliberately excludes ``password_hash`` (and anything derived from it).
    ``role`` is included as groundwork for future authorization rules.
    """
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
    }