"""Branch data-access repository module.

Queries over the Branch model used by the branch service and the admin
branch routes.
"""

from sqlalchemy import func

from app.extensions import db
from app.models import Branch


def list_all() -> list[Branch]:
    """Return all branches ordered by name."""
    return Branch.query.order_by(Branch.name.asc()).all()


def list_active() -> list[Branch]:
    """Return only active branches ordered by name."""
    return Branch.query.filter_by(is_active=True).order_by(Branch.name.asc()).all()


def find_by_id(branch_id: int) -> Branch | None:
    """Return a branch by primary key, or None."""
    return db.session.get(Branch, branch_id)


def find_by_name(name: str) -> Branch | None:
    """Return a branch by exact (case-insensitive) name, or None."""
    return Branch.query.filter(func.lower(Branch.name) == name.lower()).first()