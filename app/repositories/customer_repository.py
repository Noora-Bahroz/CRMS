"""Customer data-access repository module.

Queries over the Customer model used by the customer service and the
admin customer routes.  Customer profile data lives on the Customer row
while login identity (email, username, passwords) lives on the linked
User record.
"""

from sqlalchemy import func, or_

from app.extensions import db
from app.models import Customer, User


def _base_query():
    return Customer.query.join(Customer.user)


def list_all() -> list[Customer]:
    """Return all customers ordered by last name then first name."""
    return (
        _base_query()
        .order_by(User.last_name.asc(), User.first_name.asc())
        .all()
    )


def find_by_id(customer_id: int) -> Customer | None:
    """Return a customer by primary key, or None."""
    return db.session.get(Customer, customer_id)


def find_by_license_number(license_number: str) -> Customer | None:
    """Return a customer by driver license number (case-insensitive), or None."""
    return (
        Customer.query.filter(
            func.lower(Customer.driver_license_number) == license_number.lower()
        ).first()
    )


def search_customers(term: str) -> list[Customer]:
    """Return customers matching *term* across name, email, or license."""
    pattern = f"%{term.strip()}%"
    return (
        _base_query()
        .filter(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.email.ilike(pattern),
                Customer.driver_license_number.ilike(pattern),
            )
        )
        .order_by(User.last_name.asc(), User.first_name.asc())
        .all()
    )