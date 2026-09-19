"""Security utilities.

Password hashing/verification using Werkzeug's password-based hashing,
and file-upload safety helpers.
"""

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    """Return a secure hash of *password*. The hash includes a salt and is
    suitable for storage in the database — never store the plaintext.
    """
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return ``True`` if *password* matches the stored *password_hash*."""
    return check_password_hash(password_hash, password)
