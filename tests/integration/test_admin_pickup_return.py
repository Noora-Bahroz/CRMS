"""Integration tests: admin pickup & return records.

Covers the dedicated pickup/return feature built on top of the existing
booking and rental-agreement records:
  * pickup eligibility and state effects (confirmed -> ongoing, car rented)
  * return eligibility and state effects (ongoing -> completed, car
    available)
  * duplicate/early/invalid actions are rejected with clear messages
  * the existing customer booking flow and invoice/payment flow remain
    untouched
"""

import pytest

from app.extensions import db
from app.models import Booking, Branch, Car, Customer, Invoice, Payment, RentalAgreement
from app.utils.constants import AgreementStatus, BookingStatus, CarStatus

from scripts.seed_data import seed

_PICKUP = "2026-12-01T10:00"
_RETURN = "2026-12-03T10:00"


@pytest.fixture()
def pickup_return_db(app):
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


def _create_booking(client, status=BookingStatus.CONFIRMED, **overrides):
    """Create a two-day Sedan booking (Dec 1-3 2026) via the admin API."""
    with client.application.app_context():
        customer_id = Customer.query.first().id
        car_plate = overrides.pop("car_plate", "KHI-1001")
        car_id = Car.query.filter_by(license_plate=car_plate).one().id
        branches = Branch.query.order_by(Branch.id.asc()).all()
        pickup_branch_id = branches[0].id
        return_branch_id = branches[1].id if len(branches) > 1 else branches[0].id
    data = {
        "customer_id": customer_id,
        "car_id": car_id,
        "pickup_branch_id": pickup_branch_id,
        "return_branch_id": return_branch_id,
        "pickup_datetime": _PICKUP,
        "return_datetime": _RETURN,
        "status": status,
        "additional_charges": "0.00",
        "discount": "0.00",
        "notes": "Pickup/return integration booking.",
    }
    data.update(overrides)
    return client.post("/admin/bookings/new", data=data, follow_redirects=True)


def _create_agreement(client, **overrides):
    """Create an agreement for the first booking via the admin API."""
    with client.application.app_context():
        booking_id = Booking.query.order_by(Booking.id.asc()).first().id
    data = {
        "booking_id": booking_id,
        "agreement_number": "AGR-00001",
        "status": "draft",
        "signed_by_customer": "1",
        "signed_by_staff": "1",
        "signed_at": "2026-12-01",
        "terms_and_conditions": "Car driven carefully, no smoking.",
        "pickup_mileage": "1500",
        "return_mileage": "",
        "fuel_level_pickup": "100.00",
        "fuel_level_return": "",
        "notes": "",
    }
    data.update(overrides)
    return client.post("/admin/agreements/new", data=data, follow_redirects=True)


def _booking_id(app):
    with app.app_context():
        return Booking.query.one().id


def _pickup_form(**overrides):
    data = {
        "pickup_mileage": "1700",
        "fuel_level_pickup": "90.00",
        "notes": "Handed keys.",
    }
    data.update(overrides)
    return data


def _return_form(**overrides):
    data = {
        "return_mileage": "1800",
        "fuel_level_return": "75.00",
        "notes": "Returned clean.",
    }
    data.update(overrides)
    return data


def _set_booking_status(app, status):
    with app.app_context():
        booking = Booking.query.one()
        booking.status = status
        db.session.commit()


# --------------------------------------------------------------------------
# Access control + page rendering
# --------------------------------------------------------------------------

def test_unauthenticated_records_redirect_to_login(pickup_return_db, client):
    resp = client.get("/admin/pickup-return")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_records(pickup_return_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/pickup-return")
    assert resp.status_code == 403


def test_admin_can_list_records(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = client.get("/admin/pickup-return")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Pickup &amp; Return Records" in body
    assert b"Ready for pickup" in resp.data


def test_record_detail_page_loads(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = client.get(f"/admin/pickup-return/{_booking_id(pickup_return_db)}")
    assert resp.status_code == 200
    assert b"Pickup &amp; Return Record" in resp.data


def test_pickup_form_page_loads_for_eligible_booking(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert b"created successfully" in _create_agreement(client).data
    resp = client.get(f"/admin/pickup-return/{_booking_id(pickup_return_db)}/pickup")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Record Pickup" in body
    assert "value=\"1500\"" in body
    assert "value=\"100.00\"" in body


def test_return_form_page_loads_after_pickup(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/pickup",
        data=_pickup_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Pickup recorded" in resp.data
    resp = client.get(f"/admin/pickup-return/{booking_id}/return")
    assert resp.status_code == 200
    assert b"Record Return" in resp.data
    assert b"1700 km" in resp.data


def test_invalid_booking_reference_is_404(pickup_return_db, client):
    _login_admin(client)
    for url in (
        "/admin/pickup-return/999999",
        "/admin/pickup-return/999999/pickup",
        "/admin/pickup-return/999999/return",
    ):
        assert client.get(url).status_code == 404


# --------------------------------------------------------------------------
# Pickup workflow
# --------------------------------------------------------------------------

def test_pickup_can_be_recorded_for_eligible_booking(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert b"created successfully" in _create_agreement(client).data
    booking_id = _booking_id(pickup_return_db)
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/pickup",
        data=_pickup_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Pickup recorded" in resp.data
    with pickup_return_db.app_context():
        booking = db.session.get(Booking, booking_id)
        agreement = Booking.query.one().rental_agreement
        assert booking.status == BookingStatus.ONGOING
        assert booking.actual_pickup_datetime is not None
        assert booking.car.status == CarStatus.RENTED
        assert agreement.status == AgreementStatus.ACTIVE
        assert agreement.pickup_mileage == 1700
        assert str(agreement.fuel_level_pickup) == "90.00"
        assert agreement.notes == "Handed keys."


def test_duplicate_pickup_rejected(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    client.post(f"/admin/pickup-return/{booking_id}/pickup", data=_pickup_form())
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/pickup",
        data=_pickup_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"already been picked up" in resp.data
    with pickup_return_db.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking.status == BookingStatus.ONGOING


def test_pickup_requires_confirmed_booking(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client, status=BookingStatus.PENDING).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/pickup",
        data=_pickup_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"still pending confirmation" in resp.data
    with pickup_return_db.app_context():
        assert Booking.query.one().status == BookingStatus.PENDING


def test_pickup_requires_rental_agreement(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    # The form page itself must refuse to open without an agreement.
    resp = client.get(f"/admin/pickup-return/{booking_id}/pickup", follow_redirects=True)
    assert b"Create a rental agreement" in resp.data
    # And the POST is rejected the same way.
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/pickup",
        data=_pickup_form(),
        follow_redirects=True,
    )
    assert b"Create a rental agreement" in resp.data
    with pickup_return_db.app_context():
        assert Booking.query.one().status == BookingStatus.CONFIRMED


def test_pickup_rejected_when_car_unavailable(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    with pickup_return_db.app_context():
        car = Booking.query.one().car
        car.status = CarStatus.MAINTENANCE
        db.session.commit()
    booking_id = _booking_id(pickup_return_db)
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/pickup",
        data=_pickup_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"not available for pickup" in resp.data
    assert b"maintenance" in resp.data
    with pickup_return_db.app_context():
        booking = Booking.query.one()
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.car.status == CarStatus.MAINTENANCE


def test_pickup_validation_errors(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/pickup",
        data={"pickup_mileage": "", "fuel_level_pickup": "101.00"},
    )
    assert resp.status_code == 200
    assert b"Pickup mileage is required" in resp.data
    assert b"Fuel level at pickup must be at most 100.00" in resp.data
    with pickup_return_db.app_context():
        assert Booking.query.one().status == BookingStatus.CONFIRMED


# --------------------------------------------------------------------------
# Return workflow
# --------------------------------------------------------------------------

def _record_pickup(client, booking_id, **overrides):
    return client.post(
        f"/admin/pickup-return/{booking_id}/pickup",
        data=_pickup_form(**overrides),
        follow_redirects=True,
    )


def test_return_cannot_happen_before_pickup(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/return",
        data=_return_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"has not been picked up yet" in resp.data
    with pickup_return_db.app_context():
        assert Booking.query.one().status == BookingStatus.CONFIRMED


def test_return_can_be_recorded_after_pickup(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    assert _record_pickup(client, booking_id).status_code == 200
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/return",
        data=_return_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Return recorded" in resp.data
    with pickup_return_db.app_context():
        booking = db.session.get(Booking, booking_id)
        agreement = Booking.query.one().rental_agreement
        assert booking.status == BookingStatus.COMPLETED
        assert booking.actual_return_datetime is not None
        assert booking.car.status == CarStatus.AVAILABLE
        assert agreement.status == AgreementStatus.COMPLETED
        assert agreement.return_mileage == 1800
        assert str(agreement.fuel_level_return) == "75.00"
        assert agreement.notes == "Returned clean."


def test_duplicate_return_rejected(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    assert _record_pickup(client, booking_id).status_code == 200
    client.post(f"/admin/pickup-return/{booking_id}/return", data=_return_form())
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/return",
        data=_return_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"already been returned" in resp.data
    with pickup_return_db.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking.status == BookingStatus.COMPLETED
        assert booking.actual_return_datetime is not None


def test_return_mileage_below_pickup_rejected(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    assert _record_pickup(client, booking_id).status_code == 200
    resp = client.post(
        f"/admin/pickup-return/{booking_id}/return",
        data=_return_form(return_mileage="1600"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Return mileage must not be less than pickup mileage" in resp.data
    with pickup_return_db.app_context():
        assert Booking.query.one().status == BookingStatus.ONGOING
        assert Booking.query.one().rental_agreement.return_mileage is None


# --------------------------------------------------------------------------
# Search / state filtering
# --------------------------------------------------------------------------

def test_state_filter_and_search(pickup_return_db, client):
    _login_admin(client)
    # Booking A: picked up.  Booking B: confirmed (ready for pickup).
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    assert _record_pickup(client, booking_id).status_code == 200
    with pickup_return_db.app_context():
        booking_a = Booking.query.one().booking_number
    assert _create_booking(
        client,
        car_plate="KHI-1006",
        pickup_datetime="2026-12-10T10:00",
        return_datetime="2026-12-12T10:00",
    ).status_code == 200
    with pickup_return_db.app_context():
        booking_b = Booking.query.order_by(Booking.id.desc()).first()
    assert client.post(
        "/admin/agreements/new",
        data={
            "booking_id": booking_b.id,
            "agreement_number": "AGR-00002",
            "status": "draft",
            "signed_by_customer": "1",
            "signed_by_staff": "1",
            "signed_at": "2026-12-01",
            "terms_and_conditions": "Terms.",
            "pickup_mileage": "1000",
            "return_mileage": "",
            "fuel_level_pickup": "95.00",
            "fuel_level_return": "",
            "notes": "",
        },
        follow_redirects=True,
    ).status_code == 200
    booking_b_number = booking_b.booking_number

    resp = client.get("/admin/pickup-return?state=picked_up")
    assert resp.status_code == 200
    assert booking_a.encode() in resp.data
    assert booking_b_number.encode() not in resp.data

    resp = client.get("/admin/pickup-return?state=ready_for_pickup")
    assert resp.status_code == 200
    assert booking_b_number.encode() in resp.data
    assert booking_a.encode() not in resp.data

    resp = client.get(f"/admin/pickup-return?q={booking_b_number}")
    assert resp.status_code == 200
    assert booking_b_number.encode() in resp.data

    resp = client.get("/admin/pickup-return?q=zzz-nonexistent")
    assert b"No pickup/return records match" in resp.data


# --------------------------------------------------------------------------
# Integration parity: customer flow + invoice/payment flow still work
# --------------------------------------------------------------------------

def test_customer_booking_flow_still_works(pickup_return_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    with pickup_return_db.app_context():
        car_id = Car.query.filter_by(license_plate="KHI-1001").one().id
        branches = Branch.query.order_by(Branch.id.asc()).all()
    data = {
        "car_id": car_id,
        "pickup_branch_id": branches[0].id,
        "return_branch_id": branches[1].id,
        "pickup_datetime": "2026-12-10T10:00",
        "return_datetime": "2026-12-12T10:00",
        "driver_id": "",
        "notes": "",
    }
    assert client.post("/bookings/new", data=data).status_code == 302
    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert resp.status_code == 200
    assert b"confirmed" in resp.data.lower()

    _login_admin(client)
    with pickup_return_db.app_context():
        booking = Booking.query.one()
        assert booking.status == BookingStatus.PENDING
        booking_number = booking.booking_number
    resp = client.get("/admin/pickup-return")
    assert booking_number.encode() in resp.data
    body = resp.get_data(as_text=True)
    assert "Not applicable" in body


def test_invoice_and_payment_flow_still_works_after_return(pickup_return_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    booking_id = _booking_id(pickup_return_db)
    assert _record_pickup(client, booking_id).status_code == 200
    assert client.post(
        f"/admin/pickup-return/{booking_id}/return",
        data=_return_form(),
        follow_redirects=True,
    ).status_code == 200

    resp = client.post(
        "/admin/invoices/new",
        data={
            "booking_id": booking_id,
            "invoice_number": "INV-00001",
            "subtotal": "8000.00",
            "tax_amount": "0.00",
            "discount_amount": "0.00",
            "due_date": "2026-12-05",
            "paid_date": "",
            "status": "pending",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    resp = client.post(
        "/admin/payments/new",
        data={
            "booking_id": booking_id,
            "amount": "8000.00",
            "method": "bank_transfer",
            "status": "completed",
            "reference_number": "TXN-ABC-123",
            "received_by": "System Administrator",
            "notes": "Post-return payment.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Payment recorded successfully" in resp.data

    with pickup_return_db.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking.status == BookingStatus.COMPLETED
        assert Invoice.query.filter_by(booking_id=booking_id).count() == 1
        assert Payment.query.filter_by(booking_id=booking_id).count() == 1
        assert RentalAgreement.query.filter_by(booking_id=booking_id).count() == 1