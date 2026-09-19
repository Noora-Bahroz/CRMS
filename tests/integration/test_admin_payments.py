"""Integration tests: admin payment management."""

import pytest

from app.extensions import db
from app.models import Branch, Booking, Car, Customer, Payment
from app.utils.constants import BookingStatus, PaymentMethod, PaymentStatus

from scripts.seed_data import seed


@pytest.fixture()
def payments_db(app):
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


def _create_booking(client, pickup="2026-12-01T10:00", ret="2026-12-03T10:00"):
    """Create a two-day Sedan booking via the admin API and return its id."""
    with client.application.app_context():
        customer_id = Customer.query.first().id
        car_id = Car.query.filter_by(license_plate="KHI-1001").one().id
        branches = Branch.query.order_by(Branch.id.asc()).all()
        payload = {
            "customer_id": customer_id,
            "car_id": car_id,
            "pickup_branch_id": branches[0].id,
            "return_branch_id": branches[1].id if len(branches) > 1 else branches[0].id,
            "pickup_datetime": pickup,
            "return_datetime": ret,
            "status": "pending",
            "additional_charges": "0.00",
            "discount": "0.00",
        }
    resp = client.post("/admin/bookings/new", data=payload, follow_redirects=True)
    assert resp.status_code == 200
    with client.application.app_context():
        return Booking.query.one().id


def _payment_form(client, **overrides):
    booking_id = _create_booking(client)
    data = {
        "booking_id": booking_id,
        "amount": "8000.00",
        "method": PaymentMethod.BANK_TRANSFER,
        "status": PaymentStatus.COMPLETED,
        "reference_number": "TXN-ABC-123",
        "received_by": "System Administrator",
        "notes": "Advance payment.",
    }
    data.update(overrides)
    return data


def test_unauthenticated_payments_redirects_to_login(payments_db, client):
    resp = client.get("/admin/payments")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_payments(payments_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/payments")
    assert resp.status_code == 403


def test_admin_can_access_payment_list(payments_db, client):
    _login_admin(client)
    form = _payment_form(client)
    resp = client.post("/admin/payments/new", data=form, follow_redirects=True)
    assert resp.status_code == 200
    resp = client.get("/admin/payments")
    assert resp.status_code == 200
    assert b"BK-" in resp.data
    assert b"8,000.00" in resp.data or b"8000.00" in resp.data
    assert b"Fatima" in resp.data


def test_admin_can_create_and_view_payment(payments_db, client):
    _login_admin(client)
    form = _payment_form(client)
    resp = client.post("/admin/payments/new", data=form, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Payment recorded" in resp.data
    with payments_db.app_context():
        payment = Payment.query.one()
        assert payment.amount == 8000
        assert payment.method == PaymentMethod.BANK_TRANSFER
        assert payment.status == PaymentStatus.COMPLETED
        payment_id = payment.id
    resp = client.get(f"/admin/payments/{payment_id}")
    assert resp.status_code == 200
    assert b"Payment Information" in resp.data
    assert b"TXN-ABC-123" in resp.data
    assert b"Fatima" in resp.data


def test_payment_linked_to_booking(payments_db, client):
    _login_admin(client)
    form = _payment_form(client)
    resp = client.post("/admin/payments/new", data=form, follow_redirects=True)
    assert resp.status_code == 200
    with payments_db.app_context():
        payment = Payment.query.one()
        assert payment.booking.booking_number.startswith("BK-")
        assert payment in payment.booking.payments
        booking_id = payment.booking_id
    resp = client.get(f"/admin/bookings/{booking_id}")
    assert resp.status_code == 200
    assert payment.booking.booking_number.encode() in resp.data


def test_payment_invalid_data_rejected(payments_db, client):
    _login_admin(client)
    form = _payment_form(client)

    bad_booking = dict(form, booking_id="99999")
    resp = client.post("/admin/payments/new", data=bad_booking)
    assert b"Select a valid booking." in resp.data

    zero_amount = dict(form, amount="0")
    resp = client.post("/admin/payments/new", data=zero_amount)
    assert b"Amount must be at least 0.01" in resp.data

    bad_amount = dict(form, amount="abc")
    resp = client.post("/admin/payments/new", data=bad_amount)
    assert b"Amount must be a valid number" in resp.data

    bad_method = dict(form, method="paypal")
    resp = client.post("/admin/payments/new", data=bad_method)
    assert b"Select a valid payment method." in resp.data

    bad_status = dict(form, status="pending2")
    resp = client.post("/admin/payments/new", data=bad_status)
    assert b"Select a valid payment status." in resp.data

    assert Payment.query.count() == 0


def test_payment_required_fields_validated(payments_db, client):
    _login_admin(client)
    resp = client.post("/admin/payments/new", data={})
    assert resp.status_code == 200
    assert b"Booking is required" in resp.data
    assert b"Amount is required" in resp.data
    assert b"Select a valid payment method." in resp.data
    assert b"Select a valid payment status." in resp.data


def test_admin_can_edit_payment(payments_db, client):
    _login_admin(client)
    form = _payment_form(client)
    resp = client.post("/admin/payments/new", data=form, follow_redirects=True)
    with payments_db.app_context():
        payment_id = Payment.query.one().id
    edit = dict(form, amount="5000.00", status=PaymentStatus.PENDING,
                reference_number="TXN-UPDATED")
    resp = client.post(
        f"/admin/payments/{payment_id}/edit", data=edit, follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"Payment updated" in resp.data
    with payments_db.app_context():
        payment = db.session.get(Payment, payment_id)
        assert payment.amount == 5000
        assert payment.status == PaymentStatus.PENDING
        assert payment.reference_number == "TXN-UPDATED"


def test_admin_can_delete_payment(payments_db, client):
    _login_admin(client)
    form = _payment_form(client)
    resp = client.post("/admin/payments/new", data=form, follow_redirects=True)
    with payments_db.app_context():
        payment_id = Payment.query.one().id
    resp = client.post(f"/admin/payments/{payment_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Payment deleted" in resp.data
    with payments_db.app_context():
        assert Payment.query.filter_by(id=payment_id).first() is None