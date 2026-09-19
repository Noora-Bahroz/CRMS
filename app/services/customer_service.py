"""Customer service module.

Validation and business rules for managing customers from the admin
panel.

A Customer profile is always linked to a User account (``Customer.user_id``
is unique and required), so creating a customer also creates its login
account.  Passwords are stored only as hashes via ``app.utils.security``
and are never returned by this module.
"""

from app.extensions import db
from app.models import Customer, User
from app.repositories import customer_repository, user_repository
from app.utils import validators
from app.utils.constants import UserRole
from app.utils.security import hash_password


class CustomerError(Exception):
    """Raised when a customer cannot be modified or deactivated."""


def validate_customer_form(data, customer=None):
    """Validate form input for a customer (and its linked account).

    Returns ``(user_values, customer_values, errors)`` where *user_values*
    holds the attributes that belong on the User record, *customer_values*
    the ones on the Customer profile, and *errors* is a list of
    human-readable messages.  The password is never part of the returned
    values; it is handled directly by the create/update functions.
    Never raises.
    """
    errors = []
    user_values = {}
    customer_values = {}

    # --- User account fields ---
    first_name, error = validators.required_text(data.get("first_name"), "First name")
    if error:
        errors.append(error)
    else:
        user_values["first_name"] = first_name

    last_name, error = validators.required_text(data.get("last_name"), "Last name")
    if error:
        errors.append(error)
    else:
        user_values["last_name"] = last_name

    email, error = validators.parse_email(data.get("email"), "Email")
    if error:
        errors.append(error)
    else:
        user_values["email"] = email

    username, error = validators.required_text(data.get("username"), "Username")
    if error:
        errors.append(error)
    else:
        user_values["username"] = username

    phone, _ = validators.optional_text(data.get("phone"))
    user_values["phone"] = phone

    # --- Customer profile fields ---
    license_number, error = validators.required_text(
        data.get("driver_license_number"), "Driver license number"
    )
    if error:
        errors.append(error)
    else:
        customer_values["driver_license_number"] = license_number.upper()

    license_expiry, error = validators.parse_date(
        data.get("driver_license_expiry"), "License expiry"
    )
    if error:
        errors.append(error)
    else:
        customer_values["driver_license_expiry"] = license_expiry

    date_of_birth, error = validators.optional_date(
        data.get("date_of_birth"), "Date of birth"
    )
    if error:
        errors.append(error)
    else:
        customer_values["date_of_birth"] = date_of_birth

    address, _ = validators.optional_text(data.get("address"))
    customer_values["address"] = address
    city, _ = validators.optional_text(data.get("city"))
    customer_values["city"] = city
    state, _ = validators.optional_text(data.get("state"))
    customer_values["state"] = state
    zip_code, _ = validators.optional_text(data.get("zip_code"))
    customer_values["zip_code"] = zip_code
    emergency_contact_name, _ = validators.optional_text(
        data.get("emergency_contact_name")
    )
    customer_values["emergency_contact_name"] = emergency_contact_name
    emergency_contact_phone, _ = validators.optional_text(
        data.get("emergency_contact_phone")
    )
    customer_values["emergency_contact_phone"] = emergency_contact_phone
    notes, _ = validators.optional_text(data.get("notes"))
    customer_values["notes"] = notes

    # --- Uniqueness checks (excluding the record being edited) ---
    exclude_user_id = customer.user_id if customer is not None else None
    if "email" in user_values:
        existing_email = user_repository.find_by_email_ci(user_values["email"])
        if (
            existing_email is not None
            and (exclude_user_id is None or existing_email.id != exclude_user_id)
        ):
            errors.append("A user with this email already exists.")

    if "username" in user_values:
        existing_username = user_repository.find_by_username(user_values["username"])
        if (
            existing_username is not None
            and (exclude_user_id is None or existing_username.id != exclude_user_id)
        ):
            errors.append("A user with this username already exists.")

    if "driver_license_number" in customer_values:
        existing_license = customer_repository.find_by_license_number(
            customer_values["driver_license_number"]
        )
        if existing_license is not None and (
            customer is None or existing_license.id != customer.id
        ):
            errors.append("A customer with this driver license number already exists.")

    return user_values, customer_values, errors


def create_customer(data) -> tuple[Customer | None, list[str]]:
    """Create a customer and its linked login account.

    Returns ``(customer, errors)``; when errors is non-empty nothing is
    persisted and *customer* is ``None``.  A password is required.
    """
    user_values, customer_values, errors = validate_customer_form(data)
    password, error = validators.parse_password(data.get("password"), "Password")
    if error:
        errors.append(error)
    if errors:
        return None, errors

    user = User(role=UserRole.STAFF, is_active=True, **user_values)
    user.password_hash = hash_password(password)
    db.session.add(user)
    db.session.flush()

    customer = Customer(user_id=user.id, **customer_values)
    db.session.add(customer)
    db.session.commit()
    return customer, []


def update_customer(customer, data) -> tuple[Customer | None, list[str]]:
    """Update an existing customer and its linked account.

    A blank password keeps the current one.
    """
    user_values, customer_values, errors = validate_customer_form(
        data, customer=customer
    )
    password, password_error = validators.parse_password(
        data.get("password"), "Password", required=False
    )
    if password_error:
        errors.append(password_error)
    if errors:
        return customer, errors

    user = customer.user
    for field, value in user_values.items():
        setattr(user, field, value)
    for field, value in customer_values.items():
        setattr(customer, field, value)

    if password:
        user.password_hash = hash_password(password)

    customer.user.is_active = validators.parse_bool(data.get("is_active", True))
    db.session.commit()
    return customer, []


def update_profile(customer, data) -> tuple[Customer | None, list[str]]:
    """Update a customer's own profile from the customer area.

    Reuses the same field validation and uniqueness rules as the admin
    form (``validate_customer_form``) so behaviour never diverges, but
    ignores admin-only fields: the linked account's ``role`` and
    ``is_active`` are never touched, so a customer cannot elevate or
    deactivate themselves.  A blank password keeps the current one and
    passwords are only ever stored as hashes.
    """
    user_values, customer_values, errors = validate_customer_form(
        data, customer=customer
    )

    password, password_error = validators.parse_password(
        data.get("password"), "Password", required=False
    )
    if password_error:
        errors.append(password_error)

    if password:
        confirm_password = data.get("confirm_password") or ""
        if password != confirm_password:
            errors.append("Passwords do not match.")

    if errors:
        return customer, errors

    user = customer.user
    for field, value in user_values.items():
        setattr(user, field, value)
    for field, value in customer_values.items():
        setattr(customer, field, value)

    if password:
        user.password_hash = hash_password(password)

    db.session.commit()
    return customer, []


def deactivate_customer(customer) -> None:
    """Safely deactivate a customer account.

    Raises :class:`CustomerError` when the customer still has bookings,
    since historical data must stay intact.  Deactivation is applied to the
    linked User account (customers have no own ``is_active`` column).
    """
    if customer.bookings:
        raise CustomerError(
            f"Cannot delete customer because they have "
            f"{len(customer.bookings)} booking(s)."
        )
    customer.user.is_active = False
    db.session.commit()