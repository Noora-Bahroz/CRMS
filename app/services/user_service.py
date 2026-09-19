"""User / staff account service module.

Validation and business rules for managing internal accounts from the
admin panel: create, update, and safe activation/deactivation.  Builds on
the existing single ``User`` model/role system — no duplicate account or
permission machinery is introduced.

Rules preserved here:

* role values come only from ``UserRole`` (admin/staff);
* customer-linked accounts keep their stored role (their Customer profile
  is the admin-panel discriminator, so their ``role`` value is never
  changed to avoid confusing transitions);
* passwords are stored only as hashes and are never returned;
* a blank password on update keeps the existing password unchanged;
* deactivation uses the existing ``is_active`` field.
"""

from app.extensions import db
from app.models import User
from app.repositories import user_repository
from app.utils import validators
from app.utils.constants import UserRole
from app.utils.security import hash_password


class UserError(Exception):
    """Raised when a user account cannot be modified or deactivated."""


def validate_user_form(data, user=None):
    """Validate user form input.

    Returns ``(values, errors)`` where *values* holds the cleaned User
    attributes and *errors* a list of human-readable messages.  Never
    raises.  The password is never part of the returned values; it is
    handled directly by the create/update functions.
    """
    errors = []
    values = {}

    first_name, error = validators.required_text(
        data.get("first_name"), "First name"
    )
    if error:
        errors.append(error)
    else:
        values["first_name"] = first_name

    last_name, error = validators.required_text(data.get("last_name"), "Last name")
    if error:
        errors.append(error)
    else:
        values["last_name"] = last_name

    email, error = validators.parse_email(data.get("email"), "Email")
    if error:
        errors.append(error)
    else:
        values["email"] = email

    username, error = validators.required_text(data.get("username"), "Username")
    if error:
        errors.append(error)
    else:
        values["username"] = username

    phone, _ = validators.optional_text(data.get("phone"))
    values["phone"] = phone

    if user is not None and user.customer is not None:
        # Customer accounts keep their stored role: a customer's panel
        # access is governed by their Customer profile, and their role
        # value must not be changed accidentally.
        values["role"] = user.role
    else:
        role = (data.get("role") or "").strip()
        if role not in UserRole.ALL:
            errors.append("Select a valid role.")
        else:
            values["role"] = role

    values["is_active"] = validators.parse_bool(
        data.get("is_active", True)
    )

    # Uniqueness checks (excluding the record being edited).
    exclude_id = user.id if user is not None else None
    if "email" in values:
        existing_email = user_repository.find_by_email_ci(values["email"])
        if (
            existing_email is not None
            and (exclude_id is None or existing_email.id != exclude_id)
        ):
            errors.append("A user with this email already exists.")
    if "username" in values:
        existing_username = user_repository.find_by_username(values["username"])
        if (
            existing_username is not None
            and (exclude_id is None or existing_username.id != exclude_id)
        ):
            errors.append("A user with this username already exists.")

    return values, errors


def create_user(data) -> tuple[User | None, list[str]]:
    """Create an internal admin/staff account.

    A password is required.  No Customer record is created — a Customer
    profile belongs to the customer module and links to its own account.
    Returns ``(user, errors)``; when errors is non-empty nothing is
    persisted and *user* is ``None``.
    """
    values, errors = validate_user_form(data)
    password, error = validators.parse_password(data.get("password"), "Password")
    if error:
        errors.append(error)
    if errors:
        return None, errors

    user = User(**values)
    user.password_hash = hash_password(password)
    db.session.add(user)
    db.session.commit()
    return user, []


def update_user(user, data) -> tuple[User | None, list[str]]:
    """Update an existing account.

    A blank password keeps the existing hash; a supplied password
    (6+ characters) is re-hashed.  Returns ``(user, errors)``.
    """
    values, errors = validate_user_form(data, user=user)
    password, error = validators.parse_password(
        data.get("password"), "Password", required=False
    )
    if error:
        errors.append(error)
    if errors:
        return user, errors

    for field, value in values.items():
        setattr(user, field, value)
    if password:
        user.password_hash = hash_password(password)
    db.session.commit()
    return user, []


def set_active(user, active: bool) -> None:
    """Set an account's ``is_active`` state (activation/deactivation).

    The row is always preserved — accounts are never deleted so historical
    and foreign-key relationships stay intact.  Login already rejects
    inactive accounts via the authentication service.  Guards around
    deactivating the currently logged-in account live in the route layer,
    which knows the acting user.
    """
    user.is_active = bool(active)
    db.session.commit()