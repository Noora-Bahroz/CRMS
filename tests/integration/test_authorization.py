"""Integration tests: RBAC authorization for the admin panel."""

import pytest

from app.extensions import db
from app.models import User
from app.utils.constants import UserRole
from app.utils.security import hash_password

from scripts.seed_data import seed


@pytest.fixture()
def admin_db(app):
    """Fresh schema seeded with accounts plus a plain staff user."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed(app=app)
        db.session.add(
            User(
                username="staff",
                email="staff@example.com",
                password_hash=hash_password("Staff@123"),
                first_name="Staff",
                last_name="User",
                role=UserRole.STAFF,
                is_active=True,
            )
        )
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_unauthenticated_gets_401(admin_db, client):
    resp = client.get("/admin/me")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Authentication required."


def test_customer_gets_403(admin_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/me")
    assert resp.status_code == 403
    assert "permission" in resp.get_json()["error"]


def test_seeded_customer_staff_role_does_not_grant_admin(admin_db, client):
    with admin_db.app_context():
        account = User.query.filter_by(email="customer@example.com").one()
        assert account.role == UserRole.STAFF

    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/me")
    assert resp.status_code == 403


def test_admin_can_access(admin_db, client):
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200
    resp = client.get("/admin/me")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["email"] == "admin@example.com"
    assert body["user"]["role"] == UserRole.ADMIN
    assert "password_hash" not in body["user"]


def test_staff_can_access(admin_db, client):
    assert _login(client, "staff@example.com", "Staff@123").status_code == 200
    resp = client.get("/admin/me")
    assert resp.status_code == 200
    assert resp.get_json()["user"]["email"] == "staff@example.com"


def test_logout_revokes_admin_access(admin_db, client):
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200
    assert client.post("/auth/logout").status_code == 200
    resp = client.get("/admin/me")
    assert resp.status_code == 401