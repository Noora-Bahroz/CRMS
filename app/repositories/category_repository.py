"""Car category data-access repository module.

Queries over the CarCategory model used by the category service and the
admin category routes.
"""

from sqlalchemy import func

from app.extensions import db
from app.models import CarCategory


def list_all() -> list[CarCategory]:
    """Return all categories ordered by name."""
    return (
        CarCategory.query.order_by(CarCategory.name.asc()).all()
    )


def list_active() -> list[CarCategory]:
    """Return only active categories ordered by name."""
    return (
        CarCategory.query.filter_by(is_active=True)
        .order_by(CarCategory.name.asc())
        .all()
    )


def find_by_id(category_id: int) -> CarCategory | None:
    """Return a category by primary key, or None."""
    return db.session.get(CarCategory, category_id)


def find_by_name(name: str) -> CarCategory | None:
    """Return a category by exact (case-insensitive) name, or None."""
    return (
        CarCategory.query.filter(func.lower(CarCategory.name) == name.lower()).first()
    )