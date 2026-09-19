"""Integration tests: session-based authentication endpoints."""

import pytest

from app.extensions import db
from app.models import User
from app.utils.constants import UserRole
from app.utils.security import hash_password

from scripts.seed_data import seed


@pytest.fixture()
def auth_db(app):
    """Fresh schema with the seeded accounts plus an inactive user."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed(app=app)
        db.session.add(
            User(
                username="inactive",
                email="inactive@example.com",
                password_hash=hash_password("Inactive@123"),
                first_name="In",
                last_name="Active",
                role=UserRole.STAFF,
                is_active=False,
            )
        )
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_valid_admin_login(auth_db, client):
    resp = _login(client, "admin@example.com", "Admin@123")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["email"] == "admin@example.com"
    assert body["user"]["role"] == UserRole.ADMIN
    assert body["user"]["is_active"] is True
    assert "password_hash" not in body["user"]
    with client.session_transaction() as sess:
        assert "user_id" in sess


def test_valid_customer_login(auth_db, client):
    resp = _login(client, "customer@example.com", "Customer@123")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["email"] == "customer@example.com"
    assert body["user"]["role"] == UserRole.STAFF


def test_invalid_password_rejected(auth_db, client):
    resp = _login(client, "admin@example.com", "WrongPassword")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Invalid email or password."
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_nonexistent_email_rejected(auth_db, client):
    resp = _login(client, "ghost@example.com", "Whatever@123")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Invalid email or password."


def test_inactive_user_rejected(auth_db, client):
    resp = _login(client, "inactive@example.com", "Inactive@123")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "This account has been deactivated."
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_missing_credentials_rejected(auth_db, client):
    resp = client.post("/auth/login", json={"email": "admin@example.com"})
    assert resp.status_code == 400


def test_logout_clears_session(auth_db, client):
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200
    with client.session_transaction() as sess:
        assert "user_id" in sess

    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_me_requires_login(auth_db, client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Authentication required."


def test_me_returns_current_user(auth_db, client):
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["email"] == "admin@example.com"
    assert body["user"]["role"] == UserRole.ADMIN
    assert "password_hash" not in body["user"]