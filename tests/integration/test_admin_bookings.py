"""Integration tests: admin booking management."""

from datetime import datetime

import pytest

from app.extensions import db
from app.models import Booking, Branch, Car, Customer
from app.utils.constants import BookingStatus

from scripts.seed_data import seed


@pytest.fixture()
def bookings_db(app):
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


def _create_booking(client, **overrides):
    """Create a two-day Sedan booking (Dec 1-3 2026) via the admin API."""
    with client.application.app_context():
        customer_id = Customer.query.first().id
        car_id = Car.query.filter_by(license_plate="KHI-1001").one().id
        branches = Branch.query.order_by(Branch.id.asc()).all()
        pickup_branch_id = branches[0].id
        return_branch_id = branches[1].id if len(branches) > 1 else branches[0].id
    data = {
        "customer_id": customer_id,
        "car_id": car_id,
        "pickup_branch_id": pickup_branch_id,
        "return_branch_id": return_branch_id,
        "pickup_datetime": "2026-12-01T10:00",
        "return_datetime": "2026-12-03T10:00",
        "status": "pending",
        "additional_charges": "0.00",
        "discount": "0.00",
        "notes": "Integration test booking.",
    }
    data.update(overrides)
    return client.post("/admin/bookings/new", data=data, follow_redirects=True)


def test_unauthenticated_bookings_redirects_to_login(bookings_db, client):
    resp = client.get("/admin/bookings")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_bookings(bookings_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/bookings")
    assert resp.status_code == 403


def test_admin_can_access_booking_list(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(client)
    assert resp.status_code == 200
    assert b"BK-" in resp.data
    resp = client.get("/admin/bookings")
    assert resp.status_code == 200
    assert b"BK-" in resp.data
    assert b"Fatima" in resp.data
    assert b"Corolla" in resp.data


def test_admin_can_view_booking_details(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(client)
    assert resp.status_code == 200
    with bookings_db.app_context():
        booking_id = Booking.query.one().id
    resp = client.get(f"/admin/bookings/{booking_id}")
    assert resp.status_code == 200
    assert b"Rental Details" in resp.data
    assert b"Pricing" in resp.data
    assert b"Payments" in resp.data
    assert b"DL-2023-0099" not in resp.data


def test_admin_can_create_booking(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(client)
    assert resp.status_code == 200
    assert b"created successfully" in resp.data
    with bookings_db.app_context():
        booking = Booking.query.one()
        assert booking.status == BookingStatus.PENDING
        assert booking.estimated_days == 2
        assert booking.base_cost == 8000
        assert booking.total_amount == 8000
        assert booking.driver_id is None


def test_booking_required_fields_validated(bookings_db, client):
    _login_admin(client)
    resp = client.post("/admin/bookings/new", data={})
    assert resp.status_code == 200
    for message in (
        b"Customer is required",
        b"Car is required",
        b"Pickup branch is required",
        b"Return branch is required",
        b"Pickup date/time is required",
        b"Return date/time is required",
    ):
        assert message in resp.data


def test_booking_invalid_references_rejected(bookings_db, client):
    _login_admin(client)
    with bookings_db.app_context():
        datetimes = {
            "pickup_datetime": "2026-12-01T10:00",
            "return_datetime": "2026-12-03T10:00",
        }
    resp = _create_booking(
        client, customer_id="99999", status="pending", **datetimes,
    )
    assert b"Select a valid customer." in resp.data
    resp = _create_booking(client, car_id="99999", **datetimes)
    assert b"Select a valid car." in resp.data
    resp = _create_booking(client, pickup_branch_id="99999", **datetimes)
    assert b"Select a valid pickup branch." in resp.data
    resp = _create_booking(client, driver_id="99999", **datetimes)
    assert b"Select a valid driver." in resp.data


def test_booking_invalid_date_range_rejected(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(
        client,
        pickup_datetime="2026-12-05T10:00",
        return_datetime="2026-12-03T10:00",
    )
    assert resp.status_code == 200
    assert b"must be after the pickup date/time" in resp.data
    assert Booking.query.count() == 0


def test_booking_invalid_datetime_rejected(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(
        client,
        pickup_datetime="not-a-date",
        return_datetime="2026-12-03T10:00",
    )
    assert resp.status_code == 200
    assert b"must be a valid date/time" in resp.data


def test_admin_can_edit_booking(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(client)
    assert resp.status_code == 200
    with bookings_db.app_context():
        booking = Booking.query.one()
        booking_id = booking.id
        base = {
            "customer_id": booking.customer_id,
            "car_id": booking.car_id,
            "pickup_branch_id": booking.pickup_branch_id,
            "return_branch_id": booking.return_branch_id,
            "status": "confirmed",
            "additional_charges": "500.00",
            "discount": "0.00",
            "notes": "Extended rental.",
        }
    resp = client.post(
        f"/admin/bookings/{booking_id}/edit",
        data={
            **base,
            "pickup_datetime": "2026-12-10T10:00",
            "return_datetime": "2026-12-13T10:00",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with bookings_db.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking.estimated_days == 3
        assert booking.total_amount == 3 * 4000 + 500
        assert booking.notes == "Extended rental."


def test_booking_status_change_works(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(client)
    assert resp.status_code == 200
    with bookings_db.app_context():
        booking_id = Booking.query.one().id
    resp = _create_booking_status(client, booking_id, BookingStatus.CONFIRMED)
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with bookings_db.app_context():
        assert db.session.get(Booking, booking_id).status == BookingStatus.CONFIRMED


def _create_booking_status(client, booking_id, status):
    with client.application.app_context():
        booking = db.session.get(Booking, booking_id)
        data = {
            "customer_id": booking.customer_id,
            "car_id": booking.car_id,
            "pickup_branch_id": booking.pickup_branch_id,
            "return_branch_id": booking.return_branch_id,
            "pickup_datetime": booking.pickup_datetime.strftime("%Y-%m-%dT%H:%M"),
            "return_datetime": booking.return_datetime.strftime("%Y-%m-%dT%H:%M"),
            "status": status,
            "additional_charges": booking.additional_charges,
            "discount": booking.discount,
            "notes": booking.notes or "",
        }
    return client.post(
        f"/admin/bookings/{booking_id}/edit", data=data, follow_redirects=True
    )


def test_overlapping_active_booking_rejected(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(client)
    assert resp.status_code == 200
    with bookings_db.app_context():
        booking = Booking.query.one()
        car_id = booking.car_id
        customer_id = booking.customer_id
        branches = [booking.pickup_branch_id, booking.return_branch_id]

    base = {
        "customer_id": customer_id,
        "car_id": car_id,
        "pickup_branch_id": branches[0],
        "return_branch_id": branches[1],
        "status": "pending",
        "additional_charges": "0.00",
        "discount": "0.00",
    }

    resp = client.post(
        "/admin/bookings/new",
        data={**base, "pickup_datetime": "2026-12-02T10:00",
              "return_datetime": "2026-12-04T10:00"},
    )
    assert resp.status_code == 200
    assert b"already booked" in resp.data

    resp = client.post(
        "/admin/bookings/new",
        data={**base, "pickup_datetime": "2026-12-03T10:00",
              "return_datetime": "2026-12-05T10:00"},
        follow_redirects=True,
    )
    assert b"already booked" not in resp.data
    assert Booking.query.count() == 2


def test_cancelled_booking_does_not_block_car(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(client)
    with bookings_db.app_context():
        booking_id = Booking.query.one().id
    client.post(f"/admin/bookings/{booking_id}/delete", follow_redirects=True)
    with bookings_db.app_context():
        assert db.session.get(Booking, booking_id).status == BookingStatus.CANCELLED
        booking = db.session.get(Booking, booking_id)
        car_id, customer_id = booking.car_id, booking.customer_id
        branches = [booking.pickup_branch_id, booking.return_branch_id]
    resp = client.post(
        "/admin/bookings/new",
        data={
            "customer_id": customer_id,
            "car_id": car_id,
            "pickup_branch_id": branches[0],
            "return_branch_id": branches[1],
            "pickup_datetime": "2026-12-01T10:00",
            "return_datetime": "2026-12-03T10:00",
            "status": "pending",
            "additional_charges": "0.00",
            "discount": "0.00",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"already booked" not in resp.data
    assert Booking.query.count() == 2


def test_booking_search_filters_results(bookings_db, client):
    _login_admin(client)
    resp = _create_booking(client)
    with bookings_db.app_context():
        booking_number = Booking.query.one().booking_number
    resp = client.get("/admin/bookings?q=Corolla")
    assert b"Corolla" in resp.data
    resp = client.get(f"/admin/bookings?q={booking_number}")
    assert b"Corolla" in resp.data
    resp = client.get("/admin/bookings?q=zzz-nonexistent")
    assert b"No bookings match" in resp.data