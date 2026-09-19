"""Integration tests: database schema and seed reference data."""

import pytest

from app.extensions import db
from app.models import (
    Booking,
    Branch,
    Car,
    CarCategory,
    Customer,
    Driver,
    Expense,
    Maintenance,
    Payment,
    RentalAgreement,
    User,
)
from app.utils.constants import UserRole
from app.utils.security import verify_password

from scripts.seed_data import seed


@pytest.fixture()
def db_setup(app):
    """A fresh schema for each test, bound to the shared test app."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_seed_creates_reference_data(db_setup):
    created = seed(app=db_setup)

    assert created == {
        "users": 2,
        "customers": 1,
        "categories": 5,
        "branches": 2,
        "cars": 6,
        "drivers": 3,
        "maintenance": 3,
        "expenses": 4,
    }

    with db_setup.app_context():
        admin = User.query.filter_by(email="admin@example.com").one()
        assert admin.username == "admin"
        assert admin.role == UserRole.ADMIN
        assert verify_password("Admin@123", admin.password_hash)

        account = User.query.filter_by(email="customer@example.com").one()
        assert verify_password("Customer@123", account.password_hash)
        assert Customer.query.filter_by(user_id=account.id).one()

        assert CarCategory.query.filter_by(name="Economy").one().daily_rate == 2500
        assert Branch.query.count() == 2
        assert Car.query.filter_by(license_plate="KHI-1002").one().status == "maintenance"
        assert Driver.query.filter_by(license_number="DRV-1001").one().daily_rate == 3000
        assert Maintenance.query.count() == 3
        assert Expense.query.count() == 4


def test_seed_is_idempotent(db_setup):
    first = seed(app=db_setup)
    second = seed(app=db_setup)

    assert first["users"] == 2
    assert set(second.values()) == {0}

    with db_setup.app_context():
        assert User.query.count() == 2
        assert Customer.query.count() == 1
        assert CarCategory.query.count() == 5
        assert Branch.query.count() == 2
        assert Car.query.count() == 6
        assert Driver.query.count() == 3
        assert Maintenance.query.count() == 3
        assert Expense.query.count() == 4


def test_seed_leaves_operational_tables_empty(db_setup):
    seed(app=db_setup)

    with db_setup.app_context():
        assert Booking.query.count() == 0
        assert Payment.query.count() == 0
        assert RentalAgreement.query.count() == 0


def test_duplicate_emails_are_rejected(db_setup):
    from app.models import User

    with db_setup.app_context():
        db.session.add(
            User(
                username="newadmin",
                email="admin@example.com",
                password_hash="x",
                first_name="N",
                last_name="A",
                role=UserRole.ADMIN,
            )
        )
        db.session.commit()

        db.session.add(
            User(
                username="other",
                email="admin@example.com",
                password_hash="y",
                first_name="B",
                last_name="B",
                role=UserRole.ADMIN,
            )
        )

        with pytest.raises(Exception):
            db.session.commit()