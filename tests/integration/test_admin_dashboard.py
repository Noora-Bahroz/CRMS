"""Integration tests: admin dashboard page."""

import pytest

from app.extensions import db
from app.utils.security import hash_password

from scripts.seed_data import seed


@pytest.fixture()
def dashboard_db(app):
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


def test_admin_can_access_dashboard(dashboard_db, client):
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert b"CRMS Admin" in resp.data
    assert b"Dashboard" in resp.data
    assert b"Quick Actions" in resp.data
    assert b"Revenue" in resp.data
    assert b"PKR 0" in resp.data


def test_customer_cannot_access_dashboard(dashboard_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 403


def test_unauthenticated_dashboard_redirects_to_login(dashboard_db, client):
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"