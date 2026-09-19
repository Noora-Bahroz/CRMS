"""Integration tests: admin branch management."""

import pytest

from app.extensions import db
from app.models import Branch

from scripts.seed_data import seed


@pytest.fixture()
def branches_db(app):
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


def _branch_form(**overrides):
    data = {
        "name": "Clifton Branch",
        "address": "Block 3, Clifton",
        "city": "Karachi",
        "state": "Sindh",
        "zip_code": "75600",
        "phone": "+92 21 555 666 777",
        "email": "clifton@crms.pk",
    }
    data.update(overrides)
    return data


def test_unauthenticated_branches_redirects_to_login(branches_db, client):
    resp = client.get("/admin/branches")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_branches(branches_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/branches")
    assert resp.status_code == 403


def test_admin_can_list_branches(branches_db, client):
    _login_admin(client)
    resp = client.get("/admin/branches")
    assert resp.status_code == 200
    assert b"Head Office" in resp.data
    assert b"Airport Branch" in resp.data


def test_admin_can_create_branch(branches_db, client):
    _login_admin(client)
    resp = client.post("/admin/branches/new", data=_branch_form(), follow_redirects=True)
    assert resp.status_code == 200
    assert b"Clifton Branch" in resp.data
    with branches_db.app_context():
        assert Branch.query.filter_by(name="Clifton Branch").one() is not None


def test_duplicate_branch_name_rejected(branches_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/branches/new", data=_branch_form(name="Head Office")
    )
    assert resp.status_code == 200
    assert b"already exists" in resp.data


def test_branch_required_fields_validated(branches_db, client):
    _login_admin(client)
    resp = client.post("/admin/branches/new", data={})
    assert resp.status_code == 200
    assert b"Name is required" in resp.data
    assert b"Address is required" in resp.data
    assert b"City is required" in resp.data


def test_admin_can_edit_branch(branches_db, client):
    _login_admin(client)
    with branches_db.app_context():
        branch_id = Branch.query.filter_by(name="Airport Branch").one().id
    resp = client.post(
        f"/admin/branches/{branch_id}/edit",
        data=_branch_form(name="Airport Branch", phone="+92 42 999 888 777"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with branches_db.app_context():
        assert db.session.get(Branch, branch_id).phone == "+92 42 999 888 777"


def test_branch_with_dependencies_cannot_be_deleted(branches_db, client):
    _login_admin(client)
    with branches_db.app_context():
        branch_id = Branch.query.filter_by(name="Head Office").one().id
    resp = client.post(f"/admin/branches/{branch_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Cannot delete" in resp.data
    with branches_db.app_context():
        assert db.session.get(Branch, branch_id).is_active is True


def test_empty_branch_can_be_deleted(branches_db, client):
    _login_admin(client)
    with branches_db.app_context():
        branch = Branch(
            name="Temp Branch",
            address="Temporary premises",
            city="Karachi",
        )
        db.session.add(branch)
        db.session.commit()
        branch_id = branch.id
    resp = client.post(f"/admin/branches/{branch_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"deleted" in resp.data
    with branches_db.app_context():
        assert db.session.get(Branch, branch_id).is_active is False