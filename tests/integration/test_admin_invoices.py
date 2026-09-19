"""Integration tests: admin invoice management."""

from datetime import date

import pytest

from app.extensions import db
from app.models import Booking, Branch, Car, Customer, Invoice
from app.utils.constants import InvoiceStatus

from scripts.seed_data import seed


@pytest.fixture()
def invoices_db(app):
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


def _create_invoice(client, **overrides):
    """Create an invoice for the first booking via the admin API."""
    with client.application.app_context():
        booking_id = Booking.query.order_by(Booking.id.asc()).first().id
    data = {
        "booking_id": booking_id,
        "invoice_number": "INV-00001",
        "subtotal": "8000.00",
        "tax_amount": "0.00",
        "discount_amount": "0.00",
        "due_date": "2026-12-05",
        "paid_date": "",
        "status": "pending",
        "notes": "Integration test invoice.",
    }
    data.update(overrides)
    return client.post("/admin/invoices/new", data=data, follow_redirects=True)


def test_unauthenticated_invoices_redirects_to_login(invoices_db, client):
    resp = client.get("/admin/invoices")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_invoices(invoices_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/invoices")
    assert resp.status_code == 403


def test_admin_can_access_invoice_list(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = _create_invoice(client)
    assert resp.status_code == 200
    assert b"created successfully" in resp.data
    resp = client.get("/admin/invoices")
    assert resp.status_code == 200
    assert b"INV-00001" in resp.data
    assert b"Fatima" in resp.data
    assert b"8000.00" in resp.data


def test_admin_can_view_invoice_details(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(client).status_code == 200
    with invoices_db.app_context():
        invoice_id = Invoice.query.one().id
    resp = client.get(f"/admin/invoices/{invoice_id}")
    assert resp.status_code == 200
    assert b"Invoice Details" in resp.data
    assert b"INV-00001" in resp.data
    assert b"Rs 8000.00" in resp.data
    assert b"Fatima" in resp.data


def test_admin_can_create_invoice(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(client).status_code == 200
    with invoices_db.app_context():
        invoice = Invoice.query.one()
        assert invoice.invoice_number == "INV-00001"
        assert invoice.status == InvoiceStatus.PENDING
        assert str(invoice.subtotal) == "8000.00"
        assert str(invoice.total_amount) == "8000.00"
        assert invoice.due_date == date(2026, 12, 5)
        assert invoice.paid_date is None
        assert invoice.booking is not None


def test_invoice_total_is_computed(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(
        client, subtotal="8000.00", tax_amount="640.00", discount_amount="500.00"
    ).status_code == 200
    with invoices_db.app_context():
        invoice = Invoice.query.one()
        assert str(invoice.total_amount) == "8140.00"


def test_invoice_total_clamped_at_zero(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(
        client, subtotal="0.00", tax_amount="0.00", discount_amount="1000.00"
    ).status_code == 200
    with invoices_db.app_context():
        assert str(Invoice.query.one().total_amount) == "0.00"


def test_invoice_required_fields_validated(invoices_db, client):
    _login_admin(client)
    resp = client.post("/admin/invoices/new", data={})
    assert resp.status_code == 200
    for message in (
        b"Booking is required",
        b"Invoice number is required",
        b"Subtotal is required",
        b"Due date is required",
    ):
        assert message in resp.data


def test_invoice_invalid_booking_rejected(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = _create_invoice(client, booking_id="99999")
    assert resp.status_code == 200
    assert b"Select a valid booking." in resp.data
    assert Invoice.query.count() == 0


def test_invoice_duplicate_number_rejected(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(client).status_code == 200
    assert _create_booking(
        client,
        pickup_datetime="2026-12-10T10:00",
        return_datetime="2026-12-12T10:00",
    ).status_code == 200
    with invoices_db.app_context():
        second_booking_id = Booking.query.order_by(Booking.id.desc()).first().id
    resp = _create_invoice(client, booking_id=str(second_booking_id))
    assert resp.status_code == 200
    assert b"A booking with this invoice number already exists." in resp.data
    assert Invoice.query.count() == 1


def test_booking_cannot_have_two_invoices(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(client).status_code == 200
    resp = _create_invoice(client, invoice_number="INV-00002")
    assert resp.status_code == 200
    assert b"This booking already has an invoice." in resp.data
    assert Invoice.query.count() == 1


def test_invalid_invoice_status_rejected(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = _create_invoice(client, status="bogus")
    assert resp.status_code == 200
    assert b"Select a valid status." in resp.data
    assert Invoice.query.count() == 0


def test_admin_can_edit_invoice(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(client).status_code == 200
    with invoices_db.app_context():
        invoice = Invoice.query.one()
        invoice_id = invoice.id
        booking_id = invoice.booking_id
    resp = client.post(
        f"/admin/invoices/{invoice_id}/edit",
        data={
            "booking_id": booking_id,
            "invoice_number": "INV-00001",
            "subtotal": "8000.00",
            "tax_amount": "640.00",
            "discount_amount": "0.00",
            "due_date": "2026-12-10",
            "paid_date": "2026-12-04",
            "status": "paid",
            "notes": "Paid in full.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with invoices_db.app_context():
        invoice = db.session.get(Invoice, invoice_id)
        assert invoice.status == InvoiceStatus.PAID
        assert str(invoice.total_amount) == "8640.00"
        assert invoice.paid_date == date(2026, 12, 4)


def test_admin_can_cancel_invoice(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(client).status_code == 200
    with invoices_db.app_context():
        invoice_id = Invoice.query.one().id
    resp = client.post(f"/admin/invoices/{invoice_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"cancelled" in resp.data
    with invoices_db.app_context():
        invoice = db.session.get(Invoice, invoice_id)
        assert invoice.status == InvoiceStatus.CANCELLED
        assert invoice.invoice_number == "INV-00001"
    assert Invoice.query.count() == 1


def test_invoice_search_filters_results(invoices_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_invoice(client).status_code == 200
    with invoices_db.app_context():
        booking_number = Booking.query.one().booking_number
    resp = client.get("/admin/invoices?q=Corolla")
    assert b"INV-00001" in resp.data
    resp = client.get(f"/admin/invoices?q={booking_number}")
    assert b"INV-00001" in resp.data
    resp = client.get("/admin/invoices?q=zzz-nonexistent")
    assert b"No invoices match" in resp.data
    resp = client.get("/admin/invoices?status=paid")
    assert b"No invoices match" in resp.data