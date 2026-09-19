"""Integration tests: customer account area (profile, invoices, payments).

Covers the customer-facing account pages added on top of the existing
customer area: self-service profile editing, read-only invoice and payment
history, dashboard integration, and strict ownership authorization.  A
signed-in customer must never see another customer's financial records,
payments are read-only for customers, and internal admin accounts are
never treated as customers.
"""

import re
from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import Booking, Branch, Car, Customer, Invoice, Payment, User
from app.utils.constants import (
    BookingStatus,
    InvoiceStatus,
    PaymentMethod,
    PaymentStatus,
    UserRole,
)
from app.utils.security import hash_password

from scripts.seed_data import seed

_PICKUP = "2026-12-01T10:00"
_RETURN = "2026-12-03T10:00"


@pytest.fixture()
def account_db(app):
    """Fresh schema seeded with the reference records."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed(app=app)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _car_id(plate):
    return Car.query.filter_by(license_plate=plate).one().id


def _branch_id(name):
    return Branch.query.filter_by(name=name).one().id


def _customer():
    return Customer.query.first()


def _add_booking(customer_id=None, plate="KHI-1001", status=BookingStatus.CONFIRMED,
                 number="BK-ACC-01"):
    booking = Booking(
        booking_number=number,
        customer_id=customer_id or _customer().id,
        car_id=_car_id(plate),
        pickup_branch_id=_branch_id("Head Office"),
        return_branch_id=_branch_id("Airport Branch"),
        pickup_datetime=datetime.strptime(_PICKUP, "%Y-%m-%dT%H:%M"),
        return_datetime=datetime.strptime(_RETURN, "%Y-%m-%dT%H:%M"),
        status=status,
        estimated_days=2,
        daily_rate="4000.00",
        base_cost="8000.00",
        total_amount="8000.00",
    )
    db.session.add(booking)
    db.session.commit()
    return booking


def _add_invoice(booking, number="INV-00001", status=InvoiceStatus.PENDING,
                 subtotal="8000.00", tax="640.00", discount="0.00"):
    invoice = Invoice(
        booking_id=booking.id,
        invoice_number=number,
        subtotal=subtotal,
        tax_amount=tax,
        discount_amount=discount,
        total_amount="8640.00",
        due_date=date(2026, 12, 10),
        status=status,
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


def _add_payment(booking, amount="5000.00", method=PaymentMethod.CASH,
                 status=PaymentStatus.COMPLETED, reference="TXN-ACCT-001"):
    payment = Payment(
        booking_id=booking.id,
        amount=amount,
        method=method,
        status=status,
        reference_number=reference,
        received_by="admin",
    )
    db.session.add(payment)
    db.session.commit()
    return payment


def _add_other_customer():
    """Create a second customer account and return its Customer row."""
    user = User(
        username="otherrenter",
        email="other@example.com",
        password_hash=hash_password("Other@123"),
        first_name="Other",
        last_name="Renter",
        role=UserRole.STAFF,
        is_active=True,
    )
    db.session.add(user)
    db.session.flush()
    customer = Customer(
        user_id=user.id,
        driver_license_number="DL-OTHER-0001",
        driver_license_expiry=date(2030, 1, 1),
    )
    db.session.add(customer)
    db.session.commit()
    return customer


def _login(client, email, password):
    return client.post(
        "/login", data={"email": email, "password": password},
        follow_redirects=False,
    )


def _login_customer(client):
    return _login(client, "customer@example.com", "Customer@123")


def _login_admin(client):
    return _login(client, "admin@example.com", "Admin@123")


def _profile_form(**overrides):
    """A valid profile payload matching the seeded customer."""
    data = {
        "first_name": "Fatima",
        "last_name": "Khan",
        "username": "customer",
        "email": "customer@example.com",
        "phone": "+92 300 987 6543",
        "driver_license_number": "DL-2023-0099",
        "driver_license_expiry": "2031-05-14",
        "date_of_birth": "1990-05-14",
        "address": "12-B, Gulberg III",
        "city": "Lahore",
        "state": "Punjab",
        "zip_code": "54660",
        "emergency_contact_name": "Imran Khan",
        "emergency_contact_phone": "+92 300 555 1212",
        "password": "",
        "confirm_password": "",
    }
    data.update(overrides)
    return data


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------

def test_customer_can_open_profile(account_db):
    client = account_db.test_client()
    _login_customer(client)
    resp = client.get("/customer/profile")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Profile" in body
    assert "customer@example.com" in body
    assert "DL-2023-0099" in body
    assert "Account summary" in body


def test_customer_can_update_profile(account_db):
    client = account_db.test_client()
    _login_customer(client)
    resp = client.post(
        "/customer/profile",
        data=_profile_form(phone="+92 311 000 0000", city="Karachi",
                           address="99 Clifton Block 5"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Your profile has been updated." in resp.get_data(as_text=True)

    with account_db.app_context():
        customer = _customer()
        assert customer.city == "Karachi"
        assert customer.address == "99 Clifton Block 5"
        assert customer.user.phone == "+92 311 000 0000"


def test_invalid_profile_data_rejected(account_db):
    client = account_db.test_client()
    _login_customer(client)
    resp = client.post(
        "/customer/profile",
        data=_profile_form(email="not-an-email"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Email must be a valid email address." in resp.get_data(as_text=True)
    with account_db.app_context():
        assert _customer().user.email == "customer@example.com"


def test_profile_duplicate_email_and_username_rejected(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        _add_other_customer()
    _login_customer(client)

    resp = client.post(
        "/customer/profile",
        data=_profile_form(email="other@example.com"),
        follow_redirects=True,
    )
    assert "A user with this email already exists." in resp.get_data(as_text=True)

    resp = client.post(
        "/customer/profile",
        data=_profile_form(username="otherrenter"),
        follow_redirects=True,
    )
    assert "A user with this username already exists." in resp.get_data(as_text=True)

    with account_db.app_context():
        customer = _customer()
        assert customer.user.email == "customer@example.com"
        assert customer.user.username == "customer"


def test_password_change_hashes_and_blank_keeps(account_db):
    client = account_db.test_client()
    _login_customer(client)
    with account_db.app_context():
        original = _customer().user.password_hash

    # Blank password leaves the existing hash in place.
    client.post("/customer/profile", data=_profile_form(), follow_redirects=True)
    with account_db.app_context():
        assert _customer().user.password_hash == original

    # A supplied password is stored as a fresh hash (never plaintext).
    client.post(
        "/customer/profile",
        data=_profile_form(password="Newpass@123", confirm_password="Newpass@123"),
        follow_redirects=True,
    )
    with account_db.app_context():
        new_hash = _customer().user.password_hash
        assert new_hash != original
        assert new_hash.startswith("scrypt:")
        assert "Newpass@123" not in new_hash


def test_password_hash_never_in_html(account_db):
    client = account_db.test_client()
    _login_customer(client)
    with account_db.app_context():
        admin_hash = User.query.filter_by(email="admin@example.com").one().password_hash

    for url in ("/customer/profile", "/customer/invoices", "/customer/payments",
                "/customer/dashboard"):
        body = client.get(url).get_data()
        assert b"password_hash" not in body, url
        assert b"scrypt:" not in body, url
        assert admin_hash.encode() not in body, url


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------

def test_customer_can_open_invoice_list(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        booking = _add_booking()
        _add_invoice(booking, number="INV-10001")
    _login_customer(client)

    resp = client.get("/customer/invoices")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "INV-10001" in body
    assert "BK-ACC-01" in body


def test_customer_sees_only_own_invoices(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        own = _add_booking(number="BK-OWN-01")
        _add_invoice(own, number="INV-OWN-01")
        other = _add_other_customer()
        other_booking = _add_booking(
            customer_id=other.id, number="BK-OTHER-01"
        )
        _add_invoice(other_booking, number="INV-OTHER-01")
    _login_customer(client)

    body = client.get("/customer/invoices").get_data(as_text=True)
    assert "INV-OWN-01" in body
    assert "INV-OTHER-01" not in body
    assert "BK-OTHER-01" not in body


def test_customer_can_open_own_invoice_detail(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        booking = _add_booking()
        invoice = _add_invoice(booking, number="INV-20001")
        invoice_id = invoice.id
    _login_customer(client)

    resp = client.get(f"/customer/invoices/{invoice_id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "INV-20001" in body
    assert "BK-ACC-01" in body


def test_customer_cannot_open_another_customers_invoice(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        other = _add_other_customer()
        other_booking = _add_booking(customer_id=other.id, number="BK-OTHER-02")
        other_invoice = _add_invoice(other_booking, number="INV-OTHER-02")
        other_invoice_id = other_invoice.id
    _login_customer(client)

    assert client.get(
        f"/customer/invoices/{other_invoice_id}"
    ).status_code == 404


def test_invoice_information_displayed_correctly(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        booking = _add_booking()
        invoice = _add_invoice(
            booking, number="INV-30001", subtotal="8000.00", tax="640.00",
            discount="100.00",
        )
        invoice_id = invoice.id
    _login_customer(client)

    body = client.get(f"/customer/invoices/{invoice_id}").get_data(as_text=True)
    assert "INV-30001" in body
    assert "BK-ACC-01" in body
    assert "Fatima" in body
    assert "Corolla" in body
    assert "PKR 8,000.00" in body
    assert "PKR 640.00" in body
    assert "PKR 100.00" in body
    assert "PKR 8,640.00" in body
    assert "10 Dec 2026" in body
    assert "Pending" in body


# --------------------------------------------------------------------------
# Payments
# --------------------------------------------------------------------------

def test_customer_can_open_payment_history(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        booking = _add_booking()
        _add_payment(booking, reference="TXN-10001")
    _login_customer(client)

    resp = client.get("/customer/payments")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "BK-ACC-01" in body
    assert "TXN-10001" in body


def test_customer_sees_only_own_payments(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        own = _add_booking(number="BK-OWN-02")
        _add_payment(own, reference="TXN-OWN-01")
        other = _add_other_customer()
        other_booking = _add_booking(customer_id=other.id, number="BK-OTHER-03")
        _add_payment(other_booking, reference="TXN-OTHER-01")
    _login_customer(client)

    body = client.get("/customer/payments").get_data(as_text=True)
    assert "TXN-OWN-01" in body
    assert "TXN-OTHER-01" not in body
    assert "BK-OTHER-03" not in body


def test_customer_cannot_see_another_customers_payments(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        other = _add_other_customer()
        other_booking = _add_booking(customer_id=other.id, number="BK-OTHER-04")
        _add_payment(other_booking, reference="TXN-OTHER-SECRET")
    _login_customer(client)

    body = client.get("/customer/payments").get_data(as_text=True)
    assert "TXN-OTHER-SECRET" not in body


def test_payment_information_displayed_correctly(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        booking = _add_booking()
        _add_payment(
            booking, amount="5000.00", method=PaymentMethod.CREDIT_CARD,
            status=PaymentStatus.COMPLETED, reference="TXN-5000",
        )
    _login_customer(client)

    body = client.get("/customer/payments").get_data(as_text=True)
    assert "BK-ACC-01" in body
    assert "PKR 5,000.00" in body
    assert "Credit Card" in body
    assert "Completed" in body
    assert "TXN-5000" in body


def test_customer_cannot_create_arbitrary_payment_records(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        booking = _add_booking()
        booking_id = booking.id
    _login_customer(client)

    # No POST route exists for the customer payment history.
    resp = client.post(
        "/customer/payments",
        data={"booking_id": booking_id, "amount": "999999.00",
              "method": "cash", "status": "completed"},
    )
    assert resp.status_code == 405
    assert client.post("/customer/payments/new").status_code == 404

    with account_db.app_context():
        assert Payment.query.count() == 0


def test_customer_cannot_modify_invoice_records(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        booking = _add_booking()
        invoice = _add_invoice(booking, number="INV-LOCK-01")
        invoice_id = invoice.id
    _login_customer(client)

    resp = client.post(
        f"/customer/invoices/{invoice_id}",
        data={"status": InvoiceStatus.PAID, "total_amount": "1.00"},
    )
    assert resp.status_code == 405
    with account_db.app_context():
        assert db.session.get(Invoice, invoice_id).status == InvoiceStatus.PENDING


# --------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "/customer/profile",
    "/customer/invoices",
    "/customer/payments",
])
def test_unauthenticated_cannot_access_account_pages(account_db, url):
    client = account_db.test_client()
    resp = client.get(url)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_is_not_treated_as_customer(account_db):
    client = account_db.test_client()
    resp = _login_admin(client)
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["Location"]

    for url in ("/customer/profile", "/customer/invoices", "/customer/payments"):
        resp = client.get(url)
        assert resp.status_code == 302
        assert "/admin/dashboard" in resp.headers["Location"], url


def test_existing_admin_functionality_still_works(account_db):
    client = account_db.test_client()
    _login_admin(client)
    assert client.get("/admin/invoices").status_code == 200
    assert client.get("/admin/payments").status_code == 200
    assert client.get("/admin/bookings").status_code == 200


# --------------------------------------------------------------------------
# Dashboard integration
# --------------------------------------------------------------------------

def test_dashboard_links_to_account_sections(account_db):
    client = account_db.test_client()
    _login_customer(client)
    body = client.get("/customer/dashboard").get_data(as_text=True)
    assert '/customer/invoices"' in body
    assert '/customer/payments"' in body
    assert '/customer/profile"' in body


def test_dashboard_counts_come_from_database(account_db):
    client = account_db.test_client()
    with account_db.app_context():
        booking = _add_booking()
        _add_invoice(booking, number="INV-DASH-01")
        _add_payment(booking, reference="TXN-DASH-01")
        _add_payment(booking, reference="TXN-DASH-02")
        _add_payment(booking, reference="TXN-DASH-03")
    _login_customer(client)

    body = client.get("/customer/dashboard").get_data(as_text=True)
    assert "1 booking on your account." in body
    assert re.search(
        r'fw-bold">1</div>\s*<div class="small text-muted-2">Invoices</div>', body
    )
    assert re.search(
        r'fw-bold">3</div>\s*<div class="small text-muted-2">Payments</div>', body
    )
