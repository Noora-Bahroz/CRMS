"""Integration tests: admin fleet (car) management."""

import pytest

from app.extensions import db
from app.models import Car, CarCategory, Branch

from scripts.seed_data import seed


@pytest.fixture()
def cars_db(app):
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


def _car_form(app, **overrides):
    with app.app_context():
        category = CarCategory.query.first()
        branch = Branch.query.first()
        data = {
            "make": "Toyota",
            "model": "Camry",
            "year": "2024",
            "color": "Black",
            "license_plate": "ISB-2001",
            "vin": "4T1B11HK1JU123456",
            "mileage": "500",
            "fuel_level": "90.00",
            "category_id": str(category.id),
            "branch_id": str(branch.id),
            "status": "available",
        }
    data.update(overrides)
    return data


def test_unauthenticated_cars_redirects_to_login(cars_db, client):
    resp = client.get("/admin/cars")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_cars(cars_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/cars")
    assert resp.status_code == 403


def test_admin_can_list_cars(cars_db, client):
    _login_admin(client)
    resp = client.get("/admin/cars")
    assert resp.status_code == 200
    for plate in ("KHI-1001", "KHI-1006", "LHR-1004"):
        assert plate.encode() in resp.data
    assert b"Corolla" in resp.data
    assert b"Sedan" in resp.data


def test_admin_can_create_car(cars_db, client):
    _login_admin(client)
    resp = client.post("/admin/cars/new", data=_car_form(cars_db), follow_redirects=True)
    assert resp.status_code == 200
    assert b"ISB-2001" in resp.data
    with cars_db.app_context():
        assert Car.query.filter_by(license_plate="ISB-2001").one() is not None


def test_duplicate_plate_rejected(cars_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/cars/new", data=_car_form(cars_db, license_plate="khi-1001")
    )
    assert resp.status_code == 200
    assert b"already exists" in resp.data


def test_car_required_fields_validated(cars_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/cars/new",
        data=_car_form(cars_db, license_plate="", year="abc", mileage="-5"),
    )
    assert resp.status_code == 200
    assert b"License plate is required" in resp.data
    assert b"must be a whole number" in resp.data
    assert b"at least 0" in resp.data


def test_admin_can_edit_car(cars_db, client):
    _login_admin(client)
    with cars_db.app_context():
        car = Car.query.filter_by(license_plate="LHR-1005").one()
        car_id = car.id
    resp = client.post(
        f"/admin/cars/{car_id}/edit",
        data=_car_form(cars_db, license_plate="LHR-1005", color="Charcoal"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with cars_db.app_context():
        assert db.session.get(Car, car_id).color == "Charcoal"


def test_car_with_history_cannot_be_deleted(cars_db, client):
    _login_admin(client)
    with cars_db.app_context():
        car_id = Car.query.filter_by(license_plate="KHI-1001").one().id
    resp = client.post(f"/admin/cars/{car_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Cannot delete" in resp.data
    with cars_db.app_context():
        assert db.session.get(Car, car_id).is_active is True


def test_new_car_can_be_deleted(cars_db, client):
    _login_admin(client)
    with cars_db.app_context():
        car = Car(
            category_id=CarCategory.query.first().id,
            branch_id=Branch.query.first().id,
            make="Honda",
            model="Accord",
            year=2023,
            license_plate="ISB-2002",
            vin="1HGCV1F34LA012345",
        )
        db.session.add(car)
        db.session.commit()
        car_id = car.id
    resp = client.post(f"/admin/cars/{car_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"deleted" in resp.data
    with cars_db.app_context():
        assert db.session.get(Car, car_id).is_active is False