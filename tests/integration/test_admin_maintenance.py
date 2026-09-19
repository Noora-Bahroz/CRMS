"""Integration tests: admin maintenance management."""

import pytest

from app.extensions import db
from app.models import Car, Maintenance
from app.utils.constants import MaintenanceStatus, MaintenanceType

from scripts.seed_data import seed


@pytest.fixture()
def maintenance_db(app):
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


def _maintenance_form(client, **overrides):
    """A valid maintenance payload for the first seeded car."""
    with client.application.app_context():
        car_id = Car.query.filter_by(license_plate="KHI-1001").one().id
    data = {
        "car_id": car_id,
        "maintenance_type": MaintenanceType.ROUTINE_SERVICE,
        "status": MaintenanceStatus.SCHEDULED,
        "description": "Routine oil and filter change.",
        "cost": "7500.00",
        "scheduled_date": "2026-12-10",
        "completed_date": "",
        "service_provider": "Auto Zone Services",
        "notes": "Integration test record.",
    }
    data.update(overrides)
    return data


def test_unauthenticated_maintenance_redirects_to_login(maintenance_db, client):
    resp = client.get("/admin/maintenance")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_maintenance(maintenance_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/maintenance")
    assert resp.status_code == 403


def test_admin_can_open_maintenance_list(maintenance_db, client):
    _login_admin(client)
    resp = client.get("/admin/maintenance")
    assert resp.status_code == 200
    assert b"Maintenance" in resp.data
    assert b"KHI-1001" in resp.data
    assert b"ROUTINE SERVICE" in resp.data
    assert b"Master Motors Workshop" in resp.data


def test_admin_can_open_maintenance_detail(maintenance_db, client):
    _login_admin(client)
    with maintenance_db.app_context():
        record = Maintenance.query.order_by(Maintenance.id.asc()).first()
    resp = client.get(f"/admin/maintenance/{record.id}")
    assert resp.status_code == 200
    assert b"Maintenance Details" in resp.data
    assert b"Routine service: oil, filters, brakes" in resp.data
    assert b"KHI-1001" in resp.data


def test_admin_can_create_maintenance(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new", data=_maintenance_form(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data
    with maintenance_db.app_context():
        record = Maintenance.query.order_by(Maintenance.id.desc()).first()
        assert record.description == "Routine oil and filter change."
        assert record.maintenance_type == MaintenanceType.ROUTINE_SERVICE
        assert record.status == MaintenanceStatus.SCHEDULED
        assert str(record.cost) == "7500.00"
        assert record.completed_date is None
        assert record.car.license_plate == "KHI-1001"


def test_admin_can_edit_maintenance(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new", data=_maintenance_form(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with maintenance_db.app_context():
        record = Maintenance.query.order_by(Maintenance.id.desc()).first()
        record_id = record.id
        base = {
            "car_id": record.car_id,
            "maintenance_type": MaintenanceType.REPAIR,
            "description": "Brake pad replacement.",
            "cost": "15000.00",
            "scheduled_date": "2026-12-15",
            "completed_date": "2026-12-16",
            "service_provider": "Master Motors Workshop",
            "notes": "Updated.",
        }
    resp = client.post(
        f"/admin/maintenance/{record_id}/edit",
        data={**base, "status": MaintenanceStatus.COMPLETED},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with maintenance_db.app_context():
        record = db.session.get(Maintenance, record_id)
        assert record.status == MaintenanceStatus.COMPLETED
        assert record.maintenance_type == MaintenanceType.REPAIR
        assert str(record.cost) == "15000.00"


def test_maintenance_required_fields_validated(maintenance_db, client):
    _login_admin(client)
    resp = client.post("/admin/maintenance/new", data={})
    assert resp.status_code == 200
    for message in (
        b"Car is required",
        b"Select a valid maintenance type",
        b"Description is required",
        b"Scheduled date is required",
    ):
        assert message in resp.data


def test_maintenance_invalid_car_rejected(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new", data=_maintenance_form(client, car_id="99999")
    )
    assert resp.status_code == 200
    assert b"Select a valid car." in resp.data
    assert Maintenance.query.count() == 3


def test_maintenance_invalid_status_rejected(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new", data=_maintenance_form(client, status="bogus")
    )
    assert resp.status_code == 200
    assert b"Select a valid status." in resp.data


def test_maintenance_invalid_date_range_rejected(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new",
        data=_maintenance_form(
            client,
            scheduled_date="2026-12-10",
            completed_date="2026-12-01",
            status=MaintenanceStatus.COMPLETED,
        ),
    )
    assert resp.status_code == 200
    assert b"Completed date must not be before the scheduled date." in resp.data
    assert Maintenance.query.count() == 3


def test_maintenance_completed_requires_completed_date(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new",
        data=_maintenance_form(client, status=MaintenanceStatus.COMPLETED),
    )
    assert resp.status_code == 200
    assert b"Set a completed date for a completed maintenance record." in resp.data
    assert Maintenance.query.count() == 3


def test_maintenance_invalid_cost_rejected(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new", data=_maintenance_form(client, cost="-5.00")
    )
    assert resp.status_code == 200
    assert b"Cost must be at least 0.00" in resp.data
    assert Maintenance.query.count() == 3


def test_admin_can_complete_maintenance(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new", data=_maintenance_form(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with maintenance_db.app_context():
        record = Maintenance.query.order_by(Maintenance.id.desc()).first()
        record_id = record.id
    resp = client.post(
        f"/admin/maintenance/{record_id}/complete", follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"completed" in resp.data
    with maintenance_db.app_context():
        record = db.session.get(Maintenance, record_id)
        assert record.status == MaintenanceStatus.COMPLETED
        assert record.completed_date is not None
    resp = client.post(
        f"/admin/maintenance/{record_id}/complete", follow_redirects=True
    )
    assert b"already completed" in resp.data


def test_maintenance_with_linked_expense_cannot_be_deleted(maintenance_db, client):
    _login_admin(client)
    with maintenance_db.app_context():
        record = Maintenance.query.filter(Maintenance.expenses.any()).first()
        record_id = record.id
    resp = client.post(
        f"/admin/maintenance/{record_id}/delete", follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"linked expenses" in resp.data
    with maintenance_db.app_context():
        assert db.session.get(Maintenance, record_id) is not None


def test_admin_can_delete_maintenance_without_expenses(maintenance_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/maintenance/new", data=_maintenance_form(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with maintenance_db.app_context():
        count_before = Maintenance.query.count()
        record_id = Maintenance.query.order_by(Maintenance.id.desc()).first().id
    resp = client.post(
        f"/admin/maintenance/{record_id}/delete", follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"deleted" in resp.data
    with maintenance_db.app_context():
        assert Maintenance.query.count() == count_before - 1


def test_maintenance_search_filters_results(maintenance_db, client):
    _login_admin(client)
    resp = client.get("/admin/maintenance?q=KHI-1001")
    assert b"ROUTINE SERVICE" in resp.data
    resp = client.get("/admin/maintenance?q=zzz-nonexistent")
    assert b"No maintenance records match" in resp.data
    resp = client.get("/admin/maintenance?status=in_progress")
    assert b"In Progress" in resp.data
    resp = client.get("/admin/maintenance?status=completed")
    assert b"No maintenance records match" not in resp.data
    resp = client.get("/admin/maintenance?q=Master+Motors")
    assert b"ROUTINE SERVICE" in resp.data