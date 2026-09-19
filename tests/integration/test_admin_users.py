"""Integration tests: admin user / staff management."""

import pytest

from app.extensions import db
from app.models import User
from app.utils.constants import UserRole
from app.utils.security import verify_password

from scripts.seed_data import seed


@pytest.fixture()
def users_db(app):
    """Fresh schema with the seeded reference records."""
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


def _user_form(**overrides):
    """A valid staff-user payload."""
    data = {
        "first_name": "Zara",
        "last_name": "Malik",
        "username": "zmalik",
        "email": "zara@example.com",
        "phone": "+92 300 111 2222",
        "role": UserRole.STAFF,
        "password": "Secret123",
        "is_active": "1",
    }
    data.update(overrides)
    return data


def _find_user(email="zara@example.com"):
    return User.query.filter_by(email=email).first()


def test_unauthenticated_users_redirects_to_login(users_db, client):
    resp = client.get("/admin/users")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_users(users_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/users")
    assert resp.status_code == 403


def test_admin_can_open_users_list(users_db, client):
    _login_admin(client)
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert b"Users" in resp.data
    assert b"admin@example.com" in resp.data
    assert b"customer@example.com" in resp.data


def test_user_list_displays_real_db_users(users_db, client):
    _login_admin(client)
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert b"@admin" in resp.data
    assert b"@customer" in resp.data
    assert b"ADMIN" in resp.data
    assert b"STAFF" in resp.data
    assert b"Customer" in resp.data
    assert b"Active" in resp.data
    assert b"password_hash" not in resp.data


def test_user_search_works(users_db, client):
    _login_admin(client)
    resp = client.get("/admin/users?q=admin@example.com")
    assert b"@admin" in resp.data
    resp = client.get("/admin/users?q=zzz-nonexistent")
    assert b"No users match" in resp.data


def test_role_filter_works(users_db, client):
    _login_admin(client)
    resp = client.get("/admin/users?role=admin")
    assert b"@admin" in resp.data
    assert b"customer@example.com" not in resp.data
    resp = client.get("/admin/users?role=staff")
    assert b"@customer" in resp.data
    assert b"@admin" not in resp.data


def test_active_inactive_filter_works(users_db, client):
    _login_admin(client)
    resp = client.post("/admin/users/new", data=_user_form(), follow_redirects=True)
    assert b"created successfully" in resp.data
    with users_db.app_context():
        user_id = _find_user().id
    client.post(f"/admin/users/{user_id}/deactivate", follow_redirects=True)
    resp = client.get("/admin/users?active=inactive")
    assert b"zmalik" in resp.data
    resp = client.get("/admin/users?active=active")
    assert b"zmalik" not in resp.data


def test_admin_can_open_create_user_form(users_db, client):
    _login_admin(client)
    resp = client.get("/admin/users/new")
    assert resp.status_code == 200
    assert b'name="role"' in resp.data
    assert b"ADMIN" in resp.data
    assert b"STAFF" in resp.data


def test_admin_can_create_staff_user(users_db, client):
    _login_admin(client)
    resp = client.post("/admin/users/new", data=_user_form(), follow_redirects=True)
    assert resp.status_code == 200
    assert b"created successfully" in resp.data
    with users_db.app_context():
        user = _find_user()
        assert user is not None
        assert user.role == UserRole.STAFF
        assert user.is_active is True
        assert user.customer is None
        assert verify_password("Secret123", user.password_hash)
        assert user.password_hash.startswith("scrypt:")


def test_admin_can_create_admin_user(users_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/users/new",
        data=_user_form(username="newadmin", email="newadmin@example.com",
                        role=UserRole.ADMIN),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data
    with users_db.app_context():
        user = _find_user("newadmin@example.com")
        assert user.role == UserRole.ADMIN
        assert user.customer is None


def test_user_required_fields_validated(users_db, client):
    _login_admin(client)
    resp = client.post("/admin/users/new", data={})
    assert resp.status_code == 200
    for message in (
        b"First name is required",
        b"Last name is required",
        b"Username is required",
        b"Email is required",
        b"Password is required",
        b"Select a valid role",
    ):
        assert message in resp.data


def test_user_invalid_email_rejected(users_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/users/new", data=_user_form(email="not-an-email")
    )
    assert resp.status_code == 200
    assert b"Email must be a valid email address." in resp.data
    with users_db.app_context():
        assert User.query.count() == 2


def test_user_duplicate_email_rejected(users_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/users/new", data=_user_form(email="admin@example.com")
    )
    assert resp.status_code == 200
    assert b"A user with this email already exists." in resp.data


def test_user_duplicate_username_rejected(users_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/users/new", data=_user_form(username="admin")
    )
    assert resp.status_code == 200
    assert b"A user with this username already exists." in resp.data


def test_user_invalid_role_rejected(users_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/users/new", data=_user_form(role="superuser")
    )
    assert resp.status_code == 200
    assert b"Select a valid role." in resp.data


def test_user_password_below_minimum_rejected(users_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/users/new", data=_user_form(password="123")
    )
    assert resp.status_code == 200
    assert b"Password must be at least 6 characters." in resp.data


def test_admin_can_open_edit_user_form(users_db, client):
    _login_admin(client)
    resp = client.post("/admin/users/new", data=_user_form(), follow_redirects=True)
    assert b"created successfully" in resp.data
    with users_db.app_context():
        user_id = _find_user().id
    resp = client.get(f"/admin/users/{user_id}/edit")
    assert resp.status_code == 200
    assert b"zmalik" in resp.data
    assert b"zara@example.com" in resp.data
    assert b"password_hash" not in resp.data


def test_admin_can_edit_user_details(users_db, client):
    _login_admin(client)
    resp = client.post("/admin/users/new", data=_user_form(), follow_redirects=True)
    assert b"created successfully" in resp.data
    with users_db.app_context():
        user_id = _find_user().id
    resp = client.post(
        f"/admin/users/{user_id}/edit",
        data=_user_form(
            first_name="Zainab",
            username="zmalik2",
            email="zainab@example.com",
            password="",
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with users_db.app_context():
        user = db.session.get(User, user_id)
        assert user.first_name == "Zainab"
        assert user.username == "zmalik2"
        assert user.email == "zainab@example.com"


def test_user_password_kept_when_blank_on_edit(users_db, client):
    _login_admin(client)
    assert client.post(
        "/admin/users/new", data=_user_form(), follow_redirects=True
    ).status_code == 200
    with users_db.app_context():
        user_id = _find_user().id
    resp = client.post(
        f"/admin/users/{user_id}/edit",
        data=_user_form(first_name="Zainab", username="zmalik2",
                        email="zainab@example.com", password=""),
        follow_redirects=True,
    )
    assert b"updated successfully" in resp.data
    with users_db.app_context():
        user = db.session.get(User, user_id)
        assert verify_password("Secret123", user.password_hash)
        assert not verify_password("WrongPass123", user.password_hash)


def test_user_password_changes_when_supplied(users_db, client):
    _login_admin(client)
    assert client.post(
        "/admin/users/new", data=_user_form(), follow_redirects=True
    ).status_code == 200
    with users_db.app_context():
        user_id = _find_user().id
    resp = client.post(
        f"/admin/users/{user_id}/edit",
        data=_user_form(first_name="Zainab", username="zmalik2",
                        email="zainab@example.com", password="NewPass123"),
        follow_redirects=True,
    )
    assert b"updated successfully" in resp.data
    with users_db.app_context():
        user = db.session.get(User, user_id)
        assert verify_password("NewPass123", user.password_hash)
        assert not verify_password("Secret123", user.password_hash)


def test_user_cannot_be_edited_by_customer_linked_to_customer_account(users_db, client):
    """The customer-linked account's role stays fixed (STAFF) even if a
    role value is tampered with; access remains governed by the profile."""
    _login_admin(client)
    with users_db.app_context():
        customer_user = User.query.filter_by(email="customer@example.com").one()
        user_id = customer_user.id
    resp = client.post(
        f"/admin/users/{user_id}/edit",
        data=_user_form(
            first_name="Fatima",
            username=customer_user.username,
            email=customer_user.email,
            role=UserRole.ADMIN,
            password="",
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with users_db.app_context():
        user = db.session.get(User, user_id)
        assert user.role == UserRole.STAFF
        assert user.customer is not None


def test_admin_can_activate_and_deactivate_user(users_db, client):
    _login_admin(client)
    assert client.post(
        "/admin/users/new", data=_user_form(), follow_redirects=True
    ).status_code == 200
    with users_db.app_context():
        user_id = _find_user().id
        assert _find_user().is_active is True
    resp = client.post(f"/admin/users/{user_id}/deactivate", follow_redirects=True)
    assert b"deactivated" in resp.data
    with users_db.app_context():
        assert _find_user().is_active is False
    resp = client.post(f"/admin/users/{user_id}/activate", follow_redirects=True)
    assert b"reactivated" in resp.data
    with users_db.app_context():
        assert _find_user().is_active is True


def test_deactivated_user_cannot_login(users_db, client):
    _login_admin(client)
    assert client.post(
        "/admin/users/new", data=_user_form(), follow_redirects=True
    ).status_code == 200
    with users_db.app_context():
        user_id = _find_user().id
    client.post(f"/admin/users/{user_id}/deactivate", follow_redirects=True)
    resp = client.post(
        "/auth/login", json={"email": "zara@example.com", "password": "Secret123"}
    )
    assert resp.status_code == 403


def test_admin_cannot_deactivate_own_account(users_db, client):
    _login_admin(client)
    with users_db.app_context():
        admin_id = User.query.filter_by(email="admin@example.com").one().id
    resp = client.post(f"/admin/users/{admin_id}/deactivate", follow_redirects=True)
    assert resp.status_code == 200
    assert b"You cannot deactivate your own account." in resp.data
    with users_db.app_context():
        assert db.session.get(User, admin_id).is_active is True


def test_admin_cannot_deactivate_self_via_edit_form(users_db, client):
    _login_admin(client)
    with users_db.app_context():
        admin = User.query.filter_by(email="admin@example.com").one()
        admin_id = admin.id
    resp = client.post(
        f"/admin/users/{admin_id}/edit",
        data={
            "first_name": admin.first_name,
            "last_name": admin.last_name,
            "username": admin.username,
            "email": admin.email,
            "phone": admin.phone or "",
            "role": admin.role,
            "password": "",
            "is_active": "",
        },
    )
    assert b"You cannot deactivate your own account." in resp.data
    with users_db.app_context():
        assert db.session.get(User, admin_id).is_active is True


def test_role_filter_does_not_expose_password_hashes(users_db, client):
    _login_admin(client)
    for url in ("/admin/users", "/admin/users/new"):
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"password_hash" not in resp.data
        assert b"Secret123" not in resp.data


def test_edit_form_never_exposes_password_hash(users_db, client):
    _login_admin(client)
    assert client.post(
        "/admin/users/new", data=_user_form(), follow_redirects=True
    ).status_code == 200
    with users_db.app_context():
        user_id = _find_user().id
        actual_hash = _find_user().password_hash.encode()
    resp = client.get(f"/admin/users/{user_id}/edit")
    assert resp.status_code == 200
    assert b"password_hash" not in resp.data
    assert actual_hash not in resp.data