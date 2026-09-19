"""Integration tests: QA / production-hardening regressions.

Covers two production-readiness fixes:

* error pages are now context-aware, so a public visitor never sees the
  admin-branded error page (with Dashboard / Admin Login links);
* production startup refuses to boot without a SECRET_KEY.
"""

import pytest

from app import create_app
from app.config import validate_production_config
from app.extensions import db

from scripts.seed_data import seed


@pytest.fixture()
def qa_db(app):
    """Fresh schema seeded with the reference records."""
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


def test_public_404_uses_public_error_page(qa_db, client):
    resp = client.get("/cars/999999")
    assert resp.status_code == 404
    body = resp.get_data(as_text=True)
    assert "Back to home" in body
    assert "Admin Login" not in body
    assert "Dashboard" not in body


def test_public_403_uses_public_error_page(qa_db, client):
    # An admin account is refused the customer-only confirmation endpoint;
    # that 403 is on a public path, so it must not be admin-branded.
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200
    resp = client.post("/bookings/confirm")
    assert resp.status_code == 403
    body = resp.get_data(as_text=True)
    assert "Back to home" in body
    assert "Admin Login" not in body


def test_admin_404_uses_admin_error_page(qa_db, client):
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200
    resp = client.get("/admin/bookings/999999")
    assert resp.status_code == 404
    body = resp.get_data(as_text=True)
    assert "Admin Login" in body


def test_production_requires_secret_key():
    app = create_app("testing")
    app.config["SECRET_KEY"] = ""
    with pytest.raises(RuntimeError):
        validate_production_config(app, "production")


def test_production_guard_allows_a_secret_key():
    app = create_app("testing")
    app.config["SECRET_KEY"] = "configured-secret"
    validate_production_config(app, "production")
