"""Integration tests: admin driver management."""

from datetime import datetime

import pytest

from app.extensions import db
from app.models import Branch, Booking, Car, Customer, Driver
from app.utils.constants import BookingStatus, DriverStatus

from scripts.seed_data import seed


@pytest.fixture()
def drivers_db(app):
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


def _driver_form(**overrides):
    data = {
        "first_name": "Ali",
        "last_name": "Siddiqui",
        "phone": "+92 300 777 8899",
        "email": "ali.siddiqui@example.com",
        "license_number": "DRV-1009",
        "license_expiry": "2030-05-05",
        "status": "available",
        "daily_rate": "4000.00",
        "notes": "Reliable, city routes.",
    }
    data.update(overrides)
    return data


def test_unauthenticated_drivers_redirects_to_login(drivers_db, client):
    resp = client.get("/admin/drivers")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_drivers(drivers_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/drivers")
    assert resp.status_code == 403


def test_admin_can_list_drivers(drivers_db, client):
    _login_admin(client)
    resp = client.get("/admin/drivers")
    assert resp.status_code == 200
    for name in ("Ahmed", "Raza", "Bilal", "Khan", "Farhan", "Sheikh"):
        assert name.encode() in resp.data
    assert b"DRV-1001" in resp.data


def test_admin_can_create_driver(drivers_db, client):
    _login_admin(client)
    resp = client.post("/admin/drivers/new", data=_driver_form(), follow_redirects=True)
    assert resp.status_code == 200
    assert b"Ali Siddiqui" in resp.data
    with drivers_db.app_context():
        driver = Driver.query.filter_by(license_number="DRV-1009").one()
        assert driver.email == "ali.siddiqui@example.com"


def test_duplicate_license_number_rejected(drivers_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/drivers/new", data=_driver_form(license_number="drv-1001")
    )
    assert resp.status_code == 200
    assert b"already exists" in resp.data


def test_driver_required_fields_validated(drivers_db, client):
    _login_admin(client)
    resp = client.post("/admin/drivers/new", data={})
    assert resp.status_code == 200
    assert b"First name is required" in resp.data
    assert b"Last name is required" in resp.data
    assert b"Phone is required" in resp.data
    assert b"License number is required" in resp.data
    assert b"License expiry is required" in resp.data
    assert b"Daily rate is required" in resp.data


def test_invalid_email_and_expiry_rejected(drivers_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/drivers/new",
        data=_driver_form(email="not-an-email", license_expiry="32-14-2099"),
    )
    assert resp.status_code == 200
    assert b"must be a valid email address" in resp.data
    assert b"must be a valid date" in resp.data


def test_admin_can_edit_driver(drivers_db, client):
    _login_admin(client)
    with drivers_db.app_context():
        driver_id = Driver.query.filter_by(license_number="DRV-1002").one().id
    resp = client.post(
        f"/admin/drivers/{driver_id}/edit",
        data=_driver_form(
            first_name="Bilal", last_name="Khan", license_number="DRV-1002",
            license_expiry="2030-06-30", daily_rate="3800.00",
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with drivers_db.app_context():
        driver = db.session.get(Driver, driver_id)
        assert driver.daily_rate == 3800
        assert driver.status == DriverStatus.AVAILABLE


def test_driver_with_bookings_cannot_be_deleted(drivers_db, client):
    _login_admin(client)
    with drivers_db.app_context():
        driver = Driver.query.filter_by(license_number="DRV-1003").one()
        customer = Customer.query.first()
        car = Car.query.first()
        branch = Branch.query.first()
        booking = Booking(
            booking_number="BK-TEST-DELETE",
            customer_id=customer.id,
            car_id=car.id,
            driver_id=driver.id,
            pickup_branch_id=branch.id,
            return_branch_id=branch.id,
            pickup_datetime=datetime(2026, 10, 1, 10, 0),
            return_datetime=datetime(2026, 10, 3, 10, 0),
            status=BookingStatus.PENDING,
            estimated_days=2,
            daily_rate=car.category.daily_rate,
            base_cost=8000,
            total_amount=8000,
        )
        db.session.add(booking)
        db.session.commit()
        driver_id = driver.id
        original_status = driver.status
    resp = client.post(f"/admin/drivers/{driver_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Cannot delete" in resp.data
    with drivers_db.app_context():
        assert db.session.get(Driver, driver_id).status == original_status


def test_driver_without_bookings_can_be_deleted(drivers_db, client):
    _login_admin(client)
    with drivers_db.app_context():
        driver = Driver.query.filter_by(license_number="DRV-1001").one()
        driver_id = driver.id
    resp = client.post(f"/admin/drivers/{driver_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"deleted" in resp.data
    with drivers_db.app_context():
        assert db.session.get(Driver, driver_id).status == DriverStatus.INACTIVE