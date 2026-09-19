"""Integration tests: admin rental agreement management."""

import pytest

from app.extensions import db
from app.models import Booking, Branch, Car, Customer, RentalAgreement
from app.utils.constants import AgreementStatus

from scripts.seed_data import seed


@pytest.fixture()
def agreements_db(app):
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
        "notes": "Integration test agreement.",
    }
    data.update(overrides)
    return client.post("/admin/agreements/new", data=data, follow_redirects=True)


def test_unauthenticated_agreements_redirects_to_login(agreements_db, client):
    resp = client.get("/admin/agreements")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_agreements(agreements_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/agreements")
    assert resp.status_code == 403


def test_admin_can_access_agreement_list(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = _create_agreement(client)
    assert resp.status_code == 200
    assert b"created successfully" in resp.data
    resp = client.get("/admin/agreements")
    assert resp.status_code == 200
    assert b"AGR-00001" in resp.data
    assert b"Fatima" in resp.data
    assert b"Corolla" in resp.data


def test_admin_can_view_agreement_details(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    with agreements_db.app_context():
        agreement_id = RentalAgreement.query.one().id
    resp = client.get(f"/admin/agreements/{agreement_id}")
    assert resp.status_code == 200
    assert b"Rental Agreement Details" in resp.data
    assert b"AGR-00001" in resp.data
    assert b"1500 km" in resp.data
    assert b"100.0%" in resp.data
    assert b"Car driven carefully, no smoking." in resp.data


def test_admin_can_create_agreement(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    with agreements_db.app_context():
        agreement = RentalAgreement.query.one()
        assert agreement.agreement_number == "AGR-00001"
        assert agreement.status == AgreementStatus.DRAFT
        assert agreement.signed_by_customer is True
        assert agreement.signed_by_staff is True
        assert agreement.pickup_mileage == 1500
        assert agreement.return_mileage is None
        assert str(agreement.fuel_level_pickup) == "100.00"
        assert agreement.fuel_level_return is None
        assert agreement.booking is not None


def test_agreement_required_fields_validated(agreements_db, client):
    _login_admin(client)
    resp = client.post("/admin/agreements/new", data={})
    assert resp.status_code == 200
    for message in (
        b"Booking is required",
        b"Agreement number is required",
        b"Terms and conditions is required",
        b"Pickup mileage is required",
        b"Fuel level at pickup is required",
    ):
        assert message in resp.data


def test_agreement_invalid_booking_rejected(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = _create_agreement(client, booking_id="99999")
    assert resp.status_code == 200
    assert b"Select a valid booking." in resp.data
    assert RentalAgreement.query.count() == 0


def test_agreement_duplicate_number_rejected(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    assert _create_booking(
        client,
        pickup_datetime="2026-12-10T10:00",
        return_datetime="2026-12-12T10:00",
    ).status_code == 200
    with agreements_db.app_context():
        second_booking_id = Booking.query.order_by(Booking.id.desc()).first().id
    resp = _create_agreement(client, booking_id=str(second_booking_id))
    assert resp.status_code == 200
    assert b"An agreement with this number already exists." in resp.data
    assert RentalAgreement.query.count() == 1


def test_booking_cannot_have_two_agreements(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    resp = _create_agreement(client, agreement_number="AGR-00002")
    assert resp.status_code == 200
    assert b"This booking already has a rental agreement." in resp.data
    assert RentalAgreement.query.count() == 1


def test_agreement_return_mileage_below_pickup_rejected(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = _create_agreement(client, return_mileage="1400")
    assert resp.status_code == 200
    assert b"Return mileage must not be less than pickup mileage." in resp.data
    assert RentalAgreement.query.count() == 0


def test_agreement_fuel_out_of_range_rejected(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = _create_agreement(client, fuel_level_pickup="101.00")
    assert resp.status_code == 200
    assert b"Fuel level at pickup must be at most 100.00" in resp.data
    assert RentalAgreement.query.count() == 0


def test_invalid_agreement_status_rejected(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    resp = _create_agreement(client, status="bogus")
    assert resp.status_code == 200
    assert b"Select a valid status." in resp.data
    assert RentalAgreement.query.count() == 0


def test_admin_can_edit_agreement(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    with agreements_db.app_context():
        agreement = RentalAgreement.query.one()
        agreement_id = agreement.id
        base = {
            "booking_id": agreement.booking_id,
            "agreement_number": "AGR-00001",
            "terms_and_conditions": "Updated terms.",
            "pickup_mileage": "1500",
            "fuel_level_pickup": "80.00",
        }
    resp = client.post(
        f"/admin/agreements/{agreement_id}/edit",
        data={
            **base,
            "status": "active",
            "signed_by_customer": "1",
            "signed_by_staff": "0",
            "signed_at": "2026-12-01",
            "return_mileage": "1600",
            "fuel_level_return": "60.00",
            "notes": "Returned with full history.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with agreements_db.app_context():
        agreement = db.session.get(RentalAgreement, agreement_id)
        assert agreement.status == AgreementStatus.ACTIVE
        assert agreement.return_mileage == 1600
        assert str(agreement.fuel_level_return) == "60.00"
        assert agreement.signed_by_staff is False
        assert agreement.terms_and_conditions == "Updated terms."


def test_admin_can_terminate_agreement(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    with agreements_db.app_context():
        agreement_id = RentalAgreement.query.one().id
    resp = client.post(f"/admin/agreements/{agreement_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"terminated" in resp.data
    with agreements_db.app_context():
        agreement = db.session.get(RentalAgreement, agreement_id)
        assert agreement.status == AgreementStatus.TERMINATED
        assert agreement.agreement_number == "AGR-00001"
    assert RentalAgreement.query.count() == 1


def test_agreement_search_filters_results(agreements_db, client):
    _login_admin(client)
    assert _create_booking(client).status_code == 200
    assert _create_agreement(client).status_code == 200
    with agreements_db.app_context():
        booking_number = Booking.query.one().booking_number
    resp = client.get("/admin/agreements?q=Corolla")
    assert b"AGR-00001" in resp.data
    resp = client.get(f"/admin/agreements?q={booking_number}")
    assert b"AGR-00001" in resp.data
    resp = client.get("/admin/agreements?q=zzz-nonexistent")
    assert b"No agreements match" in resp.data
    resp = client.get("/admin/agreements?status=active")
    assert b"No agreements match" in resp.data