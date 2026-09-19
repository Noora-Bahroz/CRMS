"""Integration tests: customer booking flow and customer area.

Covers the full reservation path (form -> review -> login -> confirm ->
confirmation), reuse of the shared booking service, availability re-checks,
authentication/ownership guards, and the customer dashboard/bookings
pages.  A signed-in customer must never be able to see or touch another
customer's data, and internal admin accounts are never treated as
customers.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Booking, Branch, Car, Customer, Driver, User
from app.utils.constants import BookingStatus, UserRole
from app.utils.security import hash_password

from scripts.seed_data import seed

_PICKUP = "2026-12-01T10:00"
_RETURN = "2026-12-03T10:00"

_BOOKING_FORM = {
    "pickup_datetime": _PICKUP,
    "return_datetime": _RETURN,
    "notes": "",
}


@pytest.fixture()
def booking_db(app):
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


def _driver_id(license_number):
    return Driver.query.filter_by(license_number=license_number).one().id


def _customer():
    return Customer.query.first()


def _add_booking(plate="KHI-1001", pickup=_PICKUP, ret=_RETURN,
                 status=BookingStatus.CONFIRMED, number="BK-OTHER-01",
                 customer_id=None):
    """Insert a booking directly so availability can be exercised."""
    booking = Booking(
        booking_number=number,
        customer_id=customer_id or _customer().id,
        car_id=_car_id(plate),
        pickup_branch_id=_branch_id("Head Office"),
        return_branch_id=_branch_id("Airport Branch"),
        pickup_datetime=datetime.strptime(pickup, "%Y-%m-%dT%H:%M"),
        return_datetime=datetime.strptime(ret, "%Y-%m-%dT%H:%M"),
        status=status,
        estimated_days=2,
        daily_rate="4000.00",
        base_cost="8000.00",
        total_amount="8000.00",
    )
    db.session.add(booking)
    db.session.commit()
    return booking.id


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


def _login(client, email, password, next_url=None):
    data = {"email": email, "password": password}
    if next_url:
        data["next"] = next_url
    return client.post("/login", data=data, follow_redirects=False)


def _login_customer(client):
    return _login(client, "customer@example.com", "Customer@123")


def _login_admin(client):
    return _login(client, "admin@example.com", "Admin@123")


def _submit_details(client, car_id, pickup_branch_id, return_branch_id,
                    **overrides):
    data = {
        **_BOOKING_FORM,
        "car_id": car_id,
        "pickup_branch_id": pickup_branch_id,
        "return_branch_id": return_branch_id,
        "driver_id": "",
    }
    data.update(overrides)
    return client.post("/bookings/new", data=data, follow_redirects=False)


def _seeded_selection(booking_db):
    """Return ids for a valid Corolla rental (Dec 1-3 2026)."""
    with booking_db.app_context():
        return {
            "car_id": _car_id("KHI-1001"),
            "pickup_branch_id": _branch_id("Head Office"),
            "return_branch_id": _branch_id("Airport Branch"),
        }


def _session_user_id(client):
    with client.session_transaction() as session:
        return session.get("user_id")


# --------------------------------------------------------------------------
# Booking form / validation
# --------------------------------------------------------------------------

def test_anonymous_can_view_booking_form(booking_db):
    client = booking_db.test_client()
    resp = client.get("/bookings/new")
    assert resp.status_code == 200
    assert "Book your car" in resp.get_data(as_text=True)


def test_authenticated_customer_can_open_booking_form(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    resp = client.get("/bookings/new")
    assert resp.status_code == 200
    assert "Review booking" in resp.get_data(as_text=True)


def test_booking_form_required_fields_validated(booking_db):
    client = booking_db.test_client()
    resp = client.post("/bookings/new", data={})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for message in (
        "Car is required.",
        "Pickup branch is required.",
        "Return branch is required.",
        "Pickup date/time is required.",
        "Return date/time is required.",
    ):
        assert message in body


def test_booking_invalid_car_rejected(booking_db):
    client = booking_db.test_client()
    selection = _seeded_selection(booking_db)
    resp = _submit_details(client, 99999, selection["pickup_branch_id"],
                           selection["return_branch_id"])
    assert resp.status_code == 200
    assert "Select a valid car." in resp.get_data(as_text=True)


def test_booking_invalid_branch_rejected(booking_db):
    client = booking_db.test_client()
    selection = _seeded_selection(booking_db)
    resp = _submit_details(client, selection["car_id"], 99999,
                           selection["return_branch_id"])
    assert "Select a valid pickup branch." in resp.get_data(as_text=True)

    resp = _submit_details(client, selection["car_id"],
                           selection["pickup_branch_id"], 99999)
    assert "Select a valid return branch." in resp.get_data(as_text=True)


def test_booking_invalid_date_range_rejected(booking_db):
    client = booking_db.test_client()
    selection = _seeded_selection(booking_db)
    resp = _submit_details(
        client, selection["car_id"], selection["pickup_branch_id"],
        selection["return_branch_id"],
        pickup_datetime="2026-12-05T10:00", return_datetime="2026-12-03T10:00",
    )
    assert "must be after the pickup date/time" in resp.get_data(as_text=True)

    resp = _submit_details(
        client, selection["car_id"], selection["pickup_branch_id"],
        selection["return_branch_id"], pickup_datetime="not-a-date",
    )
    assert "must be a valid date/time" in resp.get_data(as_text=True)


# --------------------------------------------------------------------------
# Review step
# --------------------------------------------------------------------------

def test_valid_selection_moves_to_review(booking_db):
    client = booking_db.test_client()
    selection = _seeded_selection(booking_db)
    resp = _submit_details(client, selection["car_id"],
                           selection["pickup_branch_id"],
                           selection["return_branch_id"])
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/bookings/review")

    review = client.get("/bookings/review")
    assert review.status_code == 200
    body = review.get_data(as_text=True)
    assert "Review your booking" in body
    assert "Corolla" in body
    assert "PKR 8,000.00" in body
    assert "Confirm booking" in body


def test_review_shows_driver_and_price_when_selected(booking_db):
    client = booking_db.test_client()
    selection = _seeded_selection(booking_db)
    with booking_db.app_context():
        driver_id = _driver_id("DRV-1001")
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"], driver_id=driver_id)
    body = client.get("/bookings/review").get_data(as_text=True)
    assert "Ahmed Raza" in body
    # 2 days x 3000 driver rate on top of 8000 base.
    assert "PKR 14,000.00" in body


# --------------------------------------------------------------------------
# Authentication gate before final booking
# --------------------------------------------------------------------------

def test_anonymous_cannot_finalize_booking(booking_db):
    client = booking_db.test_client()
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])
    resp = client.post("/bookings/confirm")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert "next=/bookings/review" in resp.headers["Location"]
    with booking_db.app_context():
        assert Booking.query.count() == 0


def test_login_returns_customer_to_booking_flow(booking_db):
    client = booking_db.test_client()
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])

    # Confirm while anonymous sends the visitor to login with a return target.
    redirect = client.post("/bookings/confirm")
    assert redirect.status_code == 302
    assert "next=/bookings/review" in redirect.headers["Location"]

    resp = _login(client, "customer@example.com", "Customer@123",
                  next_url="/bookings/review")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/bookings/review")

    # The draft survived the login and can still be confirmed.
    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert resp.status_code == 200
    assert "Booking confirmed" in resp.get_data(as_text=True)
    with booking_db.app_context():
        assert Booking.query.count() == 1


def test_registration_returns_customer_to_booking_flow(booking_db):
    client = booking_db.test_client()
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])

    registration = {
        "first_name": "New",
        "last_name": "Renter",
        "email": "new.booking@example.com",
        "username": "newbooking",
        "phone": "+92 300 1234567",
        "driver_license_number": "DL-2026-5555",
        "driver_license_expiry": "2030-01-01",
        "password": "Secret@123",
        "confirm_password": "Secret@123",
        "next": "/bookings/review",
    }
    resp = client.post("/register", data=registration, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/bookings/review")

    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "Booking confirmed" in resp.get_data(as_text=True)
    with booking_db.app_context():
        new_user = User.query.filter_by(
            email="new.booking@example.com"
        ).one()
        booking = Booking.query.one()
        assert booking.customer_id == new_user.customer.id


def test_admin_is_not_treated_as_customer(booking_db):
    client = booking_db.test_client()
    resp = _login_admin(client)
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["Location"]

    # Admin hitting the customer dashboard is redirected, not shown it.
    resp = client.get("/customer/dashboard")
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["Location"]

    # Admin cannot confirm a customer booking.
    assert client.post("/bookings/confirm").status_code == 403


# --------------------------------------------------------------------------
# Booking creation + confirmation
# --------------------------------------------------------------------------

def test_available_car_can_be_booked_and_stored(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])

    resp = client.post("/bookings/confirm", follow_redirects=False)
    assert resp.status_code == 302
    assert "/confirmation" in resp.headers["Location"]

    with booking_db.app_context():
        booking = Booking.query.one()
        assert booking.booking_number.startswith("BK-")
        assert booking.status == BookingStatus.PENDING
        assert booking.customer_id == _customer().id
        assert booking.car_id == selection["car_id"]
        assert booking.pickup_branch_id == selection["pickup_branch_id"]
        assert booking.return_branch_id == selection["return_branch_id"]
        assert booking.estimated_days == 2
        assert booking.daily_rate == Decimal("4000.00")
        assert booking.base_cost == Decimal("8000.00")
        assert booking.total_amount == Decimal("8000.00")
        assert booking.driver_id is None


def test_booking_with_driver_stores_driver_cost(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    with booking_db.app_context():
        driver_id = _driver_id("DRV-1002")
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"], driver_id=driver_id)
    client.post("/bookings/confirm", follow_redirects=True)

    with booking_db.app_context():
        booking = Booking.query.one()
        assert booking.driver_id == driver_id
        assert booking.requires_driver is True
        assert booking.driver_cost == Decimal("7000.00")
        assert booking.total_amount == Decimal("15000.00")


def test_confirmation_page_shows_booking(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])
    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Booking confirmed" in body
    assert "Corolla" in body
    assert "Head Office" in body
    assert "Airport Branch" in body
    assert "PKR 8,000.00" in body
    with booking_db.app_context():
        booking_number = Booking.query.one().booking_number
    assert booking_number in body


# --------------------------------------------------------------------------
# Availability integration
# --------------------------------------------------------------------------

def test_overlapping_active_booking_rejected(booking_db):
    client = booking_db.test_client()
    with booking_db.app_context():
        _add_booking("KHI-1001", _PICKUP, _RETURN)
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])

    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert resp.status_code == 200
    assert "already booked" in resp.get_data(as_text=True)
    with booking_db.app_context():
        assert Booking.query.count() == 1


def test_cancelled_booking_does_not_block(booking_db):
    client = booking_db.test_client()
    with booking_db.app_context():
        _add_booking("KHI-1001", _PICKUP, _RETURN,
                     status=BookingStatus.CANCELLED)
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])

    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "Booking confirmed" in resp.get_data(as_text=True)
    with booking_db.app_context():
        assert Booking.query.count() == 2


def test_cancelled_booking_disappears_from_availability(booking_db):
    client = booking_db.test_client()
    with booking_db.app_context():
        booking_id = _add_booking("KHI-1001", _PICKUP, _RETURN,
                                  status=BookingStatus.CONFIRMED)
    _login_customer(client)

    blocked = client.get(
        f"/cars?pickup_datetime={_PICKUP}&return_datetime={_RETURN}"
    ).get_data(as_text=True)
    assert "Corolla" not in blocked

    client.post(f"/customer/bookings/{booking_id}/cancel", follow_redirects=True)

    available = client.get(
        f"/cars?pickup_datetime={_PICKUP}&return_datetime={_RETURN}"
    ).get_data(as_text=True)
    assert "Corolla" in available


# --------------------------------------------------------------------------
# Customer area
# --------------------------------------------------------------------------

def test_customer_dashboard_requires_authentication(booking_db):
    client = booking_db.test_client()
    resp = client.get("/customer/dashboard")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_customer_can_view_own_bookings(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])
    client.post("/bookings/confirm", follow_redirects=True)

    body = client.get("/customer/bookings").get_data(as_text=True)
    with booking_db.app_context():
        booking_number = Booking.query.one().booking_number
    assert booking_number in body
    assert "Corolla" in body

    dashboard = client.get("/customer/dashboard").get_data(as_text=True)
    assert "Welcome back, Fatima" in dashboard
    assert booking_number in dashboard


def test_customer_cannot_view_another_customers_booking(booking_db):
    client = booking_db.test_client()
    with booking_db.app_context():
        other = _add_other_customer()
        other_booking_id = _add_booking(customer_id=other.id, number="BK-OTHER-99")

    _login_customer(client)

    assert client.get(
        f"/customer/bookings/{other_booking_id}"
    ).status_code == 404
    assert client.get(
        f"/bookings/{other_booking_id}/confirmation"
    ).status_code == 404

    body = client.get("/customer/bookings").get_data(as_text=True)
    assert "BK-OTHER-99" not in body


def test_customer_booking_detail_works(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])
    client.post("/bookings/confirm", follow_redirects=True)

    with booking_db.app_context():
        booking = Booking.query.one()
        booking_id, number = booking.id, booking.booking_number

    body = client.get(f"/customer/bookings/{booking_id}").get_data(as_text=True)
    assert number in body
    assert "Corolla" in body
    assert "Head Office" in body
    assert "Airport Branch" in body
    assert "Price summary" in body
    assert "Cancel booking" in body


def test_customer_can_cancel_own_pending_booking(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])
    client.post("/bookings/confirm", follow_redirects=True)

    with booking_db.app_context():
        booking_id = Booking.query.one().id

    resp = client.post(
        f"/customer/bookings/{booking_id}/cancel", follow_redirects=True
    )
    assert resp.status_code == 200
    assert "has been cancelled" in resp.get_data(as_text=True)
    with booking_db.app_context():
        assert db.session.get(Booking, booking_id).status == BookingStatus.CANCELLED


def test_customer_cannot_cancel_completed_booking(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    with booking_db.app_context():
        booking_id = _add_booking(
            "KHI-1003", status=BookingStatus.COMPLETED, number="BK-DONE-01"
        )
    resp = client.post(
        f"/customer/bookings/{booking_id}/cancel", follow_redirects=True
    )
    assert "can no longer be cancelled" in resp.get_data(as_text=True)
    with booking_db.app_context():
        assert db.session.get(Booking, booking_id).status == BookingStatus.COMPLETED


# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------

def test_customer_cannot_modify_another_customers_booking(booking_db):
    client = booking_db.test_client()
    with booking_db.app_context():
        other = _add_other_customer()
        other_booking_id = _add_booking(
            customer_id=other.id, number="BK-OTHER-77"
        )
    _login_customer(client)

    resp = client.post(f"/customer/bookings/{other_booking_id}/cancel")
    assert resp.status_code == 404
    with booking_db.app_context():
        assert db.session.get(Booking, other_booking_id).status == (
            BookingStatus.CONFIRMED
        )


def test_customer_cannot_set_status_or_customer(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])

    with booking_db.app_context():
        other = _add_other_customer()
        other_id = other.id
        own_id = _customer().id

    # Tampered fields are ignored: the session account + PENDING status win.
    resp = client.post(
        "/bookings/confirm",
        data={"status": BookingStatus.CONFIRMED, "customer_id": other_id},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with booking_db.app_context():
        booking = Booking.query.one()
        assert booking.status == BookingStatus.PENDING
        assert booking.customer_id == own_id


def test_customer_cannot_access_admin_panel(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    assert client.get("/admin/dashboard").status_code == 403
    assert client.get("/admin/bookings").status_code == 403


def test_no_password_hashes_in_customer_pages(booking_db):
    client = booking_db.test_client()
    _login_customer(client)
    with booking_db.app_context():
        admin_hash = User.query.filter_by(
            email="admin@example.com"
        ).one().password_hash

    selection = _seeded_selection(booking_db)
    _submit_details(client, selection["car_id"],
                    selection["pickup_branch_id"],
                    selection["return_branch_id"])

    for url in ["/bookings/new", "/bookings/review", "/customer/dashboard",
                "/customer/bookings"]:
        body = client.get(url).get_data()
        assert b"password_hash" not in body, url
        assert b"scrypt:" not in body, url
        assert admin_hash.encode() not in body, url
