"""User data-access repository.

Encapsulates queries over the User model so authentication services never
touch the ORM session directly.  Also exposes admin-panel listing/search
helpers over the same table (internal staff + customer-linked accounts).
"""

from sqlalchemy import func, or_

from app.extensions import db
from app.models import User


def find_by_email(email: str) -> User | None:
    """Return the user with *email* or ``None``."""
    return User.query.filter_by(email=email).first()


def find_by_email_ci(email: str) -> User | None:
    """Return the user with *email* (case-insensitive) or ``None``."""
    return User.query.filter(func.lower(User.email) == email.lower()).first()


def find_by_username(username: str) -> User | None:
    """Return the user with *username* (case-insensitive) or ``None``."""
    return User.query.filter(func.lower(User.username) == username.lower()).first()


def find_by_id(user_id: int) -> User | None:
    """Return the user with *user_id* or ``None``."""
    return db.session.get(User, user_id)


def list_all() -> list[User]:
    """Return all users, newest first."""
    return User.query.order_by(User.created_at.desc(), User.id.desc()).all()


def search(
    term: str, role: str | None = None, active: bool | None = None
) -> list[User]:
    """Return users matching *term* (name, username, email) optionally
    filtered to one *role* and/or *active* state."""
    query = User.query
    pattern = f"%{term.strip()}%"
    if term:
        query = query.filter(
            or_(
                User.username.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    if role:
        query = query.filter(User.role == role)
    if active is not None:
        query = query.filter(User.is_active == active)
    return query.order_by(User.created_at.desc(), User.id.desc()).all()