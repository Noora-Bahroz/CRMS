"""Expense data-access repository module.

Queries over the Expense model for the admin expense routes and service.
Expenses are optionally linked to a branch, car, or maintenance record to
provide cost context.
"""

from sqlalchemy import or_

from app.extensions import db
from app.models import Branch, Car, Expense


def list_all() -> list[Expense]:
    """Return all expenses, newest first."""
    return Expense.query.order_by(
        Expense.created_at.desc(), Expense.id.desc()
    ).all()


def find_by_id(expense_id: int) -> Expense | None:
    """Return an expense by primary key, or None."""
    return db.session.get(Expense, expense_id)


def search(term: str, category: str | None = None) -> list[Expense]:
    """Return expenses matching *term* (category, description, recorded by,
    branch, car) optionally filtered to one *category*."""
    pattern = f"%{term.strip()}%"
    query = (
        Expense.query.outerjoin(Branch, Expense.branch_id == Branch.id)
        .outerjoin(Car, Expense.car_id == Car.id)
        .filter(
            or_(
                Expense.category.ilike(pattern),
                Expense.description.ilike(pattern),
                Expense.recorded_by.ilike(pattern),
                Branch.name.ilike(pattern),
                Car.make.ilike(pattern),
                Car.model.ilike(pattern),
                Car.license_plate.ilike(pattern),
            )
        )
    )
    if category:
        query = query.filter(Expense.category == category)
    return query.order_by(Expense.created_at.desc(), Expense.id.desc()).all()