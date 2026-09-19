"""Validation helpers.

Shared input parsing/validation used by the admin services. Functions
return ``(value, error)`` and never raise on bad input, so services can
collect several errors before re-rendering a form.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def required_text(value, label):
    """Require a non-blank string, returned stripped."""
    text = (value or "").strip()
    if not text:
        return None, f"{label} is required."
    return text, None


def optional_text(value):
    """Return a stripped string, or None when blank."""
    text = (value or "").strip()
    return text or None, None


def parse_int(value, label, min_value=None, max_value=None):
    """Parse a whole number with optional bounds."""
    text = (value or "").strip()
    if not text:
        return None, f"{label} is required."
    try:
        number = int(text)
    except (TypeError, ValueError):
        return None, f"{label} must be a whole number."
    if min_value is not None and number < min_value:
        return None, f"{label} must be at least {min_value}."
    if max_value is not None and number > max_value:
        return None, f"{label} must be at most {max_value}."
    return number, None


def parse_decimal(value, label, min_value=None, max_value=None, required=True):
    """Parse a decimal number with optional bounds.

    When *required* is False an empty input returns ``(None, None)``.
    """
    text = (value or "").strip()
    if not text:
        if not required:
            return None, None
        return None, f"{label} is required."
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None, f"{label} must be a valid number."
    if min_value is not None and number < min_value:
        return None, f"{label} must be at least {min_value}."
    if max_value is not None and number > max_value:
        return None, f"{label} must be at most {max_value}."
    return number, None


def parse_bool(value):
    """Interpret checkbox-style values as a boolean."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "on", "true", "yes")


def parse_date(value, label):
    """Parse a ``YYYY-MM-DD`` date, returning a ``datetime.date``."""
    text = (value or "").strip()
    if not text:
        return None, f"{label} is required."
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None, f"{label} must be a valid date (YYYY-MM-DD)."
    return parsed, None


def parse_datetime(value, label):
    """Parse a ``YYYY-MM-DDTHH:MM`` datetime, returning a ``datetime``."""
    text = (value or "").strip()
    if not text:
        return None, f"{label} is required."
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None, f"{label} must be a valid date/time (YYYY-MM-DDTHH:MM)."
    return parsed, None


def optional_email(value, label):
    """Return a stripped email when provided, validating its shape."""
    text = (value or "").strip()
    if not text:
        return None, None
    if not _EMAIL_RE.match(text):
        return None, f"{label} must be a valid email address."
    return text, None


def parse_email(value, label):
    """Require a non-blank string shaped like an email address."""
    text = (value or "").strip()
    if not text:
        return None, f"{label} is required."
    if not _EMAIL_RE.match(text):
        return None, f"{label} must be a valid email address."
    return text, None


def optional_date(value, label):
    """Parse a date that may be left blank."""
    text = (value or "").strip()
    if not text:
        return None, None
    return parse_date(text, label)


def parse_password(value, label, required=True):
    """Parse a password; enforces a minimum length when provided.

    When *required* is False an empty input returns ``(None, None)``,
    meaning the caller should keep the existing password.
    """
    password = value or ""
    if not password:
        if not required:
            return None, None
        return None, f"{label} is required."
    if len(password) < 6:
        return None, f"{label} must be at least 6 characters."
    return password, None