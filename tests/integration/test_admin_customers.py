"""Integration tests: admin customer management."""

from datetime import datetime

import pytest

from app.extensions import db
from app.models import Branch, Booking, Car, Customer
from app.services.authorization_service import is_admin_or_staff
from app.utils.constants import BookingStatus, UserRole
from app.utils.security import verify_password

from scripts.seed_data import seed


@pytest.fixture()
def customers_db(app):
    """Fresh schema with the seeded accounts."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed(app=app)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _login_admin(client):
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200


def _customer_form(**overrides):
    data = {
        "first_name": "Ahmed",
        "last_name": "Malik",
        "email": "ahmed.malik@example.com",
        "username": "ahmedmalik",
        "password": "Secret@123",
        "phone": "+92 300 123 4567",
        "driver_license_number": "DL-2024-5566",
        "driver_license_expiry": "2032-08-08",
        "date_of_birth": "1988-04-12",
        "emergency_contact_name": "Sana Malik",
        "emergency_contact_phone": "+92 300 765 4321",
        "address": "45-B, Model Town",
        "city": "Lahore",
        "state": "Punjab",
        "zip_code": "54700",
        "notes": "Prefers SUVs.",
    }
    data.update(overrides)
    return data


def test_unauthenticated_customers_redirects_to_login(customers_db, client):
    resp = client.get("/admin/customers")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_customer_admin(customers_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/customers")
    assert resp.status_code == 403


def test_admin_can_access_customer_list(customers_db, client):
    _login_admin(client)
    resp = client.get("/admin/customers")
    assert resp.status_code == 200
    assert b"Fatima" in resp.data
    assert b"Khan" in resp.data
    assert b"customer@example.com" in resp.data


def test_admin_can_view_customer_details(customers_db, client):
    _login_admin(client)
    with customers_db.app_context():
        customer_id = Customer.query.first().id
    resp = client.get(f"/admin/customers/{customer_id}")
    assert resp.status_code == 200
    assert b"Customer Details" in resp.data
    assert b"DL-2023-0099" in resp.data
    assert b"Login Account" in resp.data


def test_admin_can_create_customer(customers_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/customers/new", data=_customer_form(), follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"Ahmed Malik" in resp.data

    with customers_db.app_context():
        customer = Customer.query.filter_by(
            driver_license_number="DL-2024-5566"
        ).one()
        user = customer.user
        assert user.email == "ahmed.malik@example.com"
        assert user.username == "ahmedmalik"
        assert user.role == UserRole.STAFF
        assert verify_password("Secret@123", user.password_hash) is True
        assert is_admin_or_staff(user) is False


def test_admin_can_edit_customer(customers_db, client):
    _login_admin(client)
    with customers_db.app_context():
        customer_id = Customer.query.first().id
    resp = client.post(
        f"/admin/customers/{customer_id}/edit",
        data=_customer_form(
            first_name="Fatima",
            last_name="Khan",
            email="customer@example.com",
            username="customer",
            driver_license_number="DL-2023-0099",
            driver_license_expiry="2031-05-14",
            date_of_birth="1990-05-14",
            city="Gulberg, Lahore",
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data

    with customers_db.app_context():
        customer = db.session.get(Customer, customer_id)
        assert customer.city == "Gulberg, Lahore"
        assert customer.user.is_active is True


def test_customer_required_fields_validated(customers_db, client):
    _login_admin(client)
    resp = client.post("/admin/customers/new", data={})
    assert resp.status_code == 200
    for message in (
        b"First name is required",
        b"Last name is required",
        b"Email is required",
        b"Username is required",
        b"Password is required",
        b"Driver license number is required",
        b"License expiry is required",
    ):
        assert message in resp.data


def test_invalid_customer_data_rejected(customers_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/customers/new",
        data=_customer_form(
            email="not-an-email",
            password="abc",
            driver_license_expiry="31-14-2099",
        ),
    )
    assert resp.status_code == 200
    assert b"must be at least 6 characters" in resp.data
    assert b"must be a valid date" in resp.data

    resp = client.post(
        "/admin/customers/new",
        data=_customer_form(email="not-an-email"),
    )
    assert b"must be a valid email address" in resp.data


def test_duplicate_customer_data_rejected(customers_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/customers/new",
        data=_customer_form(email="customer@example.com"),
    )
    assert b"email already exists" in resp.data

    resp = client.post(
        "/admin/customers/new",
        data=_customer_form(username="customer", email="other.malik@example.com"),
    )
    assert b"username already exists" in resp.data

    resp = client.post(
        "/admin/customers/new",
        data=_customer_form(
            email="other.malik@example.com",
            username="othermalik",
            driver_license_number="dl-2023-0099",
        ),
    )
    assert b"license number already exists" in resp.data


def test_customer_search_filters_results(customers_db, client):
    _login_admin(client)
    resp = client.get("/admin/customers?q=Fatima")
    assert resp.status_code == 200
    assert b"customer@example.com" in resp.data

    resp = client.get("/admin/customers?q=zzz-nonexistent")
    assert resp.status_code == 200
    assert b"No customers match" in resp.data


def test_customer_passwords_never_exposed(customers_db, client):
    _login_admin(client)
    with customers_db.app_context():
        customer_id = Customer.query.first().id
        stored_hash = Customer.query.first().user.password_hash

    for url in (
        "/admin/customers",
        f"/admin/customers/{customer_id}",
        f"/admin/customers/{customer_id}/edit",
        "/admin/customers/new",
    ):
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"password_hash" not in resp.data
        assert stored_hash.encode() not in resp.data


def test_customer_with_bookings_cannot_be_deleted(customers_db, client):
    _login_admin(client)
    with customers_db.app_context():
        customer = Customer.query.first()
        car = Car.query.first()
        branch = Branch.query.first()
        booking = Booking(
            booking_number="BK-CUST-DELETE",
            customer_id=customer.id,
            car_id=car.id,
            pickup_branch_id=branch.id,
            return_branch_id=branch.id,
            pickup_datetime=datetime(2026, 10, 1, 10, 0),
            return_datetime=datetime(2026, 10, 4, 10, 0),
            status=BookingStatus.PENDING,
            estimated_days=3,
            daily_rate=car.category.daily_rate,
            base_cost=12000,
            total_amount=12000,
        )
        db.session.add(booking)
        db.session.commit()
        customer_id = customer.id
    resp = client.post(f"/admin/customers/{customer_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Cannot delete" in resp.data
    with customers_db.app_context():
        assert db.session.get(Customer, customer_id).user.is_active is True


def test_customer_without_bookings_can_be_deleted(customers_db, client):
    _login_admin(client)
    with customers_db.app_context():
        customer_id = Customer.query.first().id
    resp = client.post(f"/admin/customers/{customer_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"deleted" in resp.data
    with customers_db.app_context():
        assert db.session.get(Customer, customer_id).user.is_active is False