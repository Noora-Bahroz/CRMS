"""Integration tests: public customer-facing website.

Covers the marketing pages, fleet browsing/filtering, availability search
(reusing the shared booking-overlap rule), registration, login/logout and
the safety guarantees (customer accounts cannot reach the admin panel,
password hashes never leak into public HTML).
"""

from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import Booking, Car, CarCategory, Customer, User
from app.utils.constants import BookingStatus, UserRole
from app.utils.security import hash_password

from scripts.seed_data import seed

_PICKUP = "2026-12-01T10:00"
_RETURN = "2026-12-03T10:00"


@pytest.fixture()
def public_db(app):
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


def _category_id(name):
    return CarCategory.query.filter_by(name=name).one().id


def _branch_id(name):
    from app.models import Branch

    return Branch.query.filter_by(name=name).one().id


def _customer_id():
    return Customer.query.first().id


def _add_booking(plate, pickup, ret, status=BookingStatus.CONFIRMED,
                 number="BK-TEST-01"):
    """Insert a booking directly so availability can be exercised."""
    branches = _branch_id("Head Office"), _branch_id("Airport Branch")
    booking = Booking(
        booking_number=number,
        customer_id=_customer_id(),
        car_id=_car_id(plate),
        pickup_branch_id=branches[0],
        return_branch_id=branches[1],
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


def _login(client, email, password):
    return client.post(
        "/login", data={"email": email, "password": password},
        follow_redirects=False,
    )


def _login_customer(client):
    return _login(client, "customer@example.com", "Customer@123")


def _session_user_id(client):
    with client.session_transaction() as session:
        return session.get("user_id")


# --------------------------------------------------------------------------
# Public pages
# --------------------------------------------------------------------------

def test_public_pages_return_200(public_db):
    client = public_db.test_client()
    for url in ["/", "/cars", "/about", "/contact", "/terms"]:
        assert client.get(url).status_code == 200, url


def test_home_shows_branches_and_featured_cars(public_db):
    client = public_db.test_client()
    body = client.get("/").get_data(as_text=True)
    assert "Head Office" in body
    assert "Airport Branch" in body
    assert "Toyota" in body
    assert "Browse the fleet" in body


def test_car_detail_page(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        car_id = _car_id("KHI-1001")
    resp = client.get(f"/cars/{car_id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Corolla" in body
    assert "Book this car" in body
    assert "KHI-1001" not in body  # public pages never expose the plate


def test_car_detail_unknown_returns_404(public_db):
    client = public_db.test_client()
    assert client.get("/cars/999999").status_code == 404


def test_inactive_car_returns_404(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        car = Car.query.filter_by(license_plate="KHI-1001").one()
        car.is_active = False
        db.session.commit()
        car_id = car.id
    assert client.get(f"/cars/{car_id}").status_code == 404
    assert "Corolla" not in client.get("/cars").get_data(as_text=True)


# --------------------------------------------------------------------------
# Fleet filtering
# --------------------------------------------------------------------------

def test_fleet_lists_real_cars(public_db):
    client = public_db.test_client()
    body = client.get("/cars").get_data(as_text=True)
    assert "Corolla" in body
    assert "Fortuner" in body
    assert "Wagon" in body


def test_fleet_category_filter(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        sedan = _category_id("Sedan")
        suv = _category_id("SUV")

    sedans = client.get(f"/cars?category={sedan}").get_data(as_text=True)
    assert "Corolla" in sedans
    assert "Fortuner" not in sedans

    suvs = client.get(f"/cars?category={suv}").get_data(as_text=True)
    assert "Fortuner" in suvs
    assert "Corolla" not in suvs


def test_fleet_branch_filter(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        airport = _branch_id("Airport Branch")

    body = client.get(f"/cars?branch={airport}").get_data(as_text=True)
    assert "Sportage" in body
    assert "Corolla" not in body


# --------------------------------------------------------------------------
# Availability search
# --------------------------------------------------------------------------

def test_availability_search_shows_free_cars(public_db):
    client = public_db.test_client()
    resp = client.get(
        f"/cars?pickup_datetime={_PICKUP}&return_datetime={_RETURN}"
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Corolla" in body
    assert "Date availability applied" in body


def test_active_booking_blocks_car(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        _add_booking("KHI-1001", _PICKUP, _RETURN)
    body = client.get(
        f"/cars?pickup_datetime={_PICKUP}&return_datetime={_RETURN}"
    ).get_data(as_text=True)
    assert "Corolla" not in body
    assert "Fortuner" in body


def test_cancelled_booking_does_not_block(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        _add_booking(
            "KHI-1001", _PICKUP, _RETURN, status=BookingStatus.CANCELLED
        )
    body = client.get(
        f"/cars?pickup_datetime={_PICKUP}&return_datetime={_RETURN}"
    ).get_data(as_text=True)
    assert "Corolla" in body


def test_invalid_date_range_is_handled(public_db):
    client = public_db.test_client()
    resp = client.get(
        "/cars?pickup_datetime=2026-12-03T10:00&return_datetime=2026-12-01T10:00"
    )
    assert resp.status_code == 200
    assert "Return date/time must be after the pickup date/time." in (
        resp.get_data(as_text=True)
    )

    resp = client.get(
        "/cars?pickup_datetime=garbage&return_datetime=2026-12-01T10:00"
    )
    assert resp.status_code == 200
    assert "must be a valid date/time" in resp.get_data(as_text=True)


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

_REGISTRATION = {
    "first_name": "New",
    "last_name": "Renter",
    "email": "new.renter@example.com",
    "username": "newrenter",
    "phone": "+92 300 1234567",
    "driver_license_number": "DL-2026-7777",
    "driver_license_expiry": "2030-01-01",
    "password": "Secret@123",
    "confirm_password": "Secret@123",
}


def test_registration_creates_user_and_customer(public_db):
    client = public_db.test_client()
    resp = client.post("/register", data=_REGISTRATION, follow_redirects=True)
    assert resp.status_code == 200
    assert "Your account has been created" in resp.get_data(as_text=True)

    with public_db.app_context():
        user = User.query.filter_by(email=_REGISTRATION["email"]).one()
        assert user.role == UserRole.STAFF
        assert user.is_active is True
        assert user.password_hash.startswith("scrypt:")
        assert user.customer is not None
        assert user.customer.driver_license_number == "DL-2026-7777"
        assert user.id == _session_user_id(client)


def test_registration_rejects_password_mismatch(public_db):
    client = public_db.test_client()
    data = dict(_REGISTRATION, confirm_password="Different@123")
    resp = client.post("/register", data=data, follow_redirects=True)
    assert "Passwords do not match." in resp.get_data(as_text=True)
    with public_db.app_context():
        assert User.query.filter_by(
            email=_REGISTRATION["email"]
        ).first() is None


def test_registration_rejects_duplicates(public_db):
    client = public_db.test_client()
    data = dict(_REGISTRATION, email="admin@example.com", username="admin")
    resp = client.post("/register", data=data, follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "A user with this email already exists." in body
    assert "A user with this username already exists." in body


# --------------------------------------------------------------------------
# Login / logout
# --------------------------------------------------------------------------

def test_customer_login_works(public_db):
    client = public_db.test_client()
    resp = _login_customer(client)
    assert resp.status_code == 302
    with public_db.app_context():
        customer_user = User.query.filter_by(
            email="customer@example.com"
        ).one()
    assert _session_user_id(client) == customer_user.id


def test_login_rejects_invalid_credentials(public_db):
    client = public_db.test_client()
    resp = client.post(
        "/login",
        data={"email": "customer@example.com", "password": "wrong"},
        follow_redirects=True,
    )
    assert "Invalid email or password." in resp.get_data(as_text=True)
    assert _session_user_id(client) is None


def test_login_rejects_inactive_customer(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        user = User(
            username="inactiveuser",
            email="inactive@example.com",
            password_hash=hash_password("Secret@123"),
            first_name="Inactive",
            last_name="Renter",
            role=UserRole.STAFF,
            is_active=False,
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(
            Customer(
                user_id=user.id,
                driver_license_number="DL-2026-8888",
                driver_license_expiry=date(2030, 1, 1),
            )
        )
        db.session.commit()

    resp = client.post(
        "/login",
        data={"email": "inactive@example.com", "password": "Secret@123"},
        follow_redirects=True,
    )
    assert "This account has been deactivated." in resp.get_data(as_text=True)
    assert _session_user_id(client) is None


def test_logout_clears_session(public_db):
    client = public_db.test_client()
    _login_customer(client)
    assert _session_user_id(client) is not None

    resp = client.post("/logout", follow_redirects=True)
    assert resp.status_code == 200
    assert "You have been signed out." in resp.get_data(as_text=True)
    assert _session_user_id(client) is None


def test_logged_in_navbar_shows_signout(public_db):
    client = public_db.test_client()
    anonymous = client.get("/").get_data(as_text=True)
    assert "Sign in" in anonymous
    assert "Register" in anonymous

    _login_customer(client)
    authenticated = client.get("/").get_data(as_text=True)
    assert "Sign out" in authenticated
    assert "Fatima" in authenticated


def test_admin_public_login_routes_to_dashboard(public_db):
    client = public_db.test_client()
    resp = _login(client, "admin@example.com", "Admin@123")
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["Location"]


# --------------------------------------------------------------------------
# Safety guarantees
# --------------------------------------------------------------------------

def test_admin_login_still_works(public_db):
    client = public_db.test_client()
    resp = client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "Admin@123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["Location"]


def test_json_auth_login_still_works(public_db):
    client = public_db.test_client()
    resp = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["user"]["email"] == "admin@example.com"
    assert "password_hash" not in payload["user"]


def test_customer_cannot_access_admin_panel(public_db):
    client = public_db.test_client()
    _login_customer(client)
    assert client.get("/admin/dashboard").status_code == 403


def test_password_hashes_not_in_public_html(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        car_id = _car_id("KHI-1001")
        admin_hash = User.query.filter_by(email="admin@example.com").one(
        ).password_hash

    urls = ["/", "/cars", f"/cars/{car_id}", "/about", "/contact",
            "/terms", "/login", "/register"]
    for url in urls:
        body = client.get(url).get_data()
        assert b"password_hash" not in body, url
        assert b"scrypt:" not in body, url
        assert admin_hash.encode() not in body, url


# --------------------------------------------------------------------------
# Contact form
# --------------------------------------------------------------------------

def test_contact_validation_errors(public_db):
    client = public_db.test_client()
    resp = client.post("/contact", data={}, follow_redirects=True)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Name is required." in body
    assert "Email is required." in body
    assert "Message is required." in body


def test_contact_success_shows_confirmation(public_db):
    client = public_db.test_client()
    resp = client.post(
        "/contact",
        data={
            "name": "Ali Raza",
            "email": "ali@example.com",
            "message": "Do you have an SUV available next weekend?",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Thank you for contacting CRMS" in resp.get_data(as_text=True)


# --------------------------------------------------------------------------
# Public website UI / design sections
# --------------------------------------------------------------------------

def test_home_has_hero_and_booking_search(public_db):
    client = public_db.test_client()
    body = client.get("/").get_data(as_text=True)
    assert "Luxury Car Rental" in body
    assert "Rent Now" in body
    assert "Pickup location" in body
    assert "Return location" in body
    # Branch options are populated from the database, never hard-coded.
    assert "Head Office" in body
    assert "Airport Branch" in body


def test_home_has_featured_fleet_and_categories(public_db):
    client = public_db.test_client()
    body = client.get("/").get_data(as_text=True)
    assert "Pick Your Dream Car" in body
    assert "Check Wide Range of Vehicles" in body
    assert "Premium Fleet Collection" in body
    assert "Why choose CRMS" in body


def test_home_brands_come_from_database(public_db):
    client = public_db.test_client()
    body = client.get("/").get_data(as_text=True)
    # Makes of rentable cars, rendered without hard-coding.  The Honda
    # Civic is in maintenance, so it must not be featured as available.
    assert "TOYOTA" in body
    assert "SUZUKI" in body
    assert "HONDA" not in body


def test_home_footer_has_required_links(public_db):
    client = public_db.test_client()
    body = client.get("/").get_data(as_text=True)
    assert "Terms &amp; Conditions" in body or "Terms & Conditions" in body
    assert "Privacy Policy" in body
    assert "site-footer" in body


def test_public_pages_use_public_shell_not_admin(public_db):
    client = public_db.test_client()
    for url in ["/", "/cars", "/about", "/contact", "/terms"]:
        body = client.get(url).get_data(as_text=True)
        assert "site-shell" in body, url
        assert "css/public.css" in body, url
        # The admin panel chrome must never leak into public pages.
        assert "admin/base.html" not in body, url
        assert "sidebar" not in body, url


def test_fleet_page_has_filters_and_cards(public_db):
    client = public_db.test_client()
    body = client.get("/cars").get_data(as_text=True)
    assert "Search availability" in body
    assert "filter-category" in body
    assert "filter-branch" in body
    assert "car-card" in body
    assert "Rent Now" in body


def test_car_detail_has_booking_cta_and_specs(public_db):
    client = public_db.test_client()
    with public_db.app_context():
        car_id = _car_id("KHI-1001")
    body = client.get(f"/cars/{car_id}").get_data(as_text=True)
    assert "Rent Now" in body
    assert "Book this car" in body
    assert "Vehicle details" in body
    assert "spec-table" in body
    assert "booking-aside" in body


def test_car_photos_by_name_present(public_db):
    client = public_db.test_client()
    body = client.get("/cars").get_data(as_text=True)
    # Each seeded car renders its own photo (matched by make + model), and
    # none falls back to the SVG placeholder.  KHI-1002 (Honda Civic) is in
    # maintenance so it is not listed on the public fleet page.
    assert "img/cars/toyota-corolla.jpg" in body
    assert "img/cars/toyota-fortuner.jpg" in body
    assert "img/cars/kia-sportage.jpg" in body
    assert "img/cars/hyundai-tucson.jpg" in body
    assert "img/cars/suzuki-wagon-r.jpg" in body
    assert "img/cars/honda-civic.jpg" not in body
    assert "img/car-placeholder.svg" not in body
