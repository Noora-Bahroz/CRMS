"""Authorization service.

Kept separate from authentication: authentication resolves *who* the
current user is, while authorization decides what that user is allowed to
do.

Admin-panel access in CRMS is reserved for internal accounts. Customer
accounts share the ``users`` table but are always linked to a Customer
profile, which is the discriminator used here.
"""

from app.utils.constants import UserRole


def has_role(user, *roles) -> bool:
    """Return ``True`` if *user* holds any of *roles*."""
    return user is not None and user.role in roles


def is_customer_account(user) -> bool:
    """Return ``True`` if *user* is linked to a Customer profile."""
    return user is not None and user.customer is not None


def is_admin_or_staff(user) -> bool:
    """Return ``True`` for internal admin/staff accounts that may access
    the admin panel.

    Users holding the ADMIN or STAFF role pass, unless they are linked to
    a Customer profile (customer-facing accounts never get panel access,
    even when their stored ``role`` value is STAFF).
    """
    if not has_role(user, UserRole.ADMIN, UserRole.STAFF):
        return False
    return not is_customer_account(user)