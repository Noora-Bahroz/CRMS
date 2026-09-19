"""Integration tests: admin car category management."""

import pytest

from app.extensions import db
from app.models import CarCategory

from scripts.seed_data import seed


@pytest.fixture()
def categories_db(app):
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


def _category_form(**overrides):
    data = {
        "name": "Premium SUV",
        "description": "High-end SUVs for families.",
        "daily_rate": "8000.00",
        "weekly_rate": "50000.00",
        "monthly_rate": "190000.00",
        "deposit_amount": "30000.00",
    }
    data.update(overrides)
    return data


def test_unauthenticated_categories_redirects_to_login(categories_db, client):
    resp = client.get("/admin/categories")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_categories(categories_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/categories")
    assert resp.status_code == 403


def test_admin_can_list_categories(categories_db, client):
    _login_admin(client)
    resp = client.get("/admin/categories")
    assert resp.status_code == 200
    for name in ("Economy", "Sedan", "SUV", "Luxury", "Van"):
        assert name.encode() in resp.data


def test_admin_can_create_category(categories_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/categories/new", data=_category_form(), follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"Premium SUV" in resp.data
    with categories_db.app_context():
        assert CarCategory.query.filter_by(name="Premium SUV").one() is not None


def test_duplicate_category_name_rejected(categories_db, client):
    _login_admin(client)
    resp = client.post("/admin/categories/new", data=_category_form(name="Economy"))
    assert resp.status_code == 200
    assert b"already exists" in resp.data


def test_category_required_fields_validated(categories_db, client):
    _login_admin(client)
    resp = client.post("/admin/categories/new", data={})
    assert resp.status_code == 200
    assert b"Name is required" in resp.data
    assert b"Daily rate is required" in resp.data
    assert b"Deposit amount is required" in resp.data


def test_admin_can_edit_category(categories_db, client):
    _login_admin(client)
    with categories_db.app_context():
        category = CarCategory.query.filter_by(name="Luxury").one()
        category_id = category.id
    resp = client.post(
        f"/admin/categories/{category_id}/edit",
        data=_category_form(name="Luxury", daily_rate="13000.00"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with categories_db.app_context():
        assert db.session.get(CarCategory, category_id).daily_rate == 13000


def test_category_with_cars_cannot_be_deleted(categories_db, client):
    _login_admin(client)
    with categories_db.app_context():
        category_id = CarCategory.query.filter_by(name="Sedan").one().id
    resp = client.post(
        f"/admin/categories/{category_id}/delete", follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"car(s) are assigned" in resp.data
    with categories_db.app_context():
        assert db.session.get(CarCategory, category_id).is_active is True


def test_empty_category_can_be_deleted(categories_db, client):
    _login_admin(client)
    with categories_db.app_context():
        category_id = CarCategory.query.filter_by(name="Van").one().id
    resp = client.post(
        f"/admin/categories/{category_id}/delete", follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"deleted" in resp.data
    with categories_db.app_context():
        assert db.session.get(CarCategory, category_id).is_active is False