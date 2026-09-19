"""Integration tests: admin login page and redirects."""

import pytest

from app.extensions import db

from scripts.seed_data import seed


@pytest.fixture()
def login_db(app):
    """Fresh schema with the seeded accounts."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed(app=app)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _post_login(client, email, password):
    return client.post(
        "/admin/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_login_page_is_accessible(login_db, client):
    resp = client.get("/admin/login")
    assert resp.status_code == 200
    assert b"CRMS Admin" in resp.data
    assert b"Sign in" in resp.data


def test_valid_admin_login_succeeds(login_db, client):
    resp = _post_login(client, "admin@example.com", "Admin@123")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/dashboard"
    with client.session_transaction() as sess:
        assert "user_id" in sess


def test_valid_admin_login_redirects_to_dashboard(login_db, client):
    resp = _post_login(client, "admin@example.com", "Admin@123")
    assert resp.headers["Location"] == "/admin/dashboard"
    assert client.get("/admin/dashboard").status_code == 200


def test_invalid_credentials_rejected(login_db, client):
    resp = _post_login(client, "admin@example.com", "WrongPassword")
    assert resp.status_code == 200
    assert b"Invalid email or password." in resp.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_customer_credentials_rejected_from_admin_panel(login_db, client):
    resp = _post_login(client, "customer@example.com", "Customer@123")
    assert resp.status_code == 200
    assert b"does not have access" in resp.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    assert client.get("/admin/dashboard").status_code == 302


def test_unauthenticated_dashboard_redirects_to_login(login_db, client):
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_authenticated_admin_visiting_login_redirects_to_dashboard(login_db, client):
    assert _post_login(client, "admin@example.com", "Admin@123").status_code == 302
    resp = client.get("/admin/login")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/dashboard"