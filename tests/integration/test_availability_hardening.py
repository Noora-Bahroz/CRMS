"""Integration tests: booking & availability hardening.

Verifies the single availability decision (car active flag, car status,
active maintenance, and the existing booking-overlap rule) and that the
exact same rules apply to the public site, the customer booking flow, and
the admin booking panel.

Seeded reference facts used here:

* KHI-1001 Toyota Corolla - available, only *completed* maintenance;
* KHI-1002 Honda Civic   - status ``maintenance`` + active (in-progress) work;
* KHI-1006 Suzuki Wagon R - available with no maintenance (used for
  maintenance/status experiments).
"""

from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import Booking, Branch, Car, Customer, Maintenance
from app.services import availability_service
from app.utils.constants import (
    BookingStatus,
    CarStatus,
    MaintenanceStatus,
    MaintenanceType,
)

from scripts.seed_data import seed

_PICKUP = "2026-12-01T10:00"
_RETURN = "2026-12-03T10:00"


@pytest.fixture()
def availability_db(app):
    """Fresh schema seeded with the reference records."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed(app=app)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _car(plate):
    return Car.query.filter_by(license_plate=plate).one()


def _car_id(plate):
    return _car(plate).id


def _branch_id(name):
    return Branch.query.filter_by(name=name).one().id


def _customer_id():
    return Customer.query.first().id


def _set_status(plate, status):
    """Force a car's status and return its id."""
    car = _car(plate)
    car.status = status
    db.session.commit()
    return car.id


def _add_maintenance(plate, status=MaintenanceStatus.IN_PROGRESS,
                     scheduled=date(2026, 9, 1), completed=None,
                     description="Workshop job."):
    """Insert a maintenance record so availability can be exercised."""
    maintenance = Maintenance(
        car_id=_car_id(plate),
        maintenance_type=MaintenanceType.REPAIR,
        status=status,
        description=description,
        cost="5000.00",
        scheduled_date=scheduled,
        completed_date=completed,
    )
    db.session.add(maintenance)
    db.session.commit()
    return maintenance.id


def _add_booking(plate="KHI-1001", pickup=_PICKUP, ret=_RETURN,
                 status=BookingStatus.CONFIRMED, number="BK-AVAIL-01"):
    booking = Booking(
        booking_number=number,
        customer_id=_customer_id(),
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


def _login(client, email, password):
    return client.post(
        "/login", data={"email": email, "password": password},
        follow_redirects=False,
    )


def _login_customer(client):
    return _login(client, "customer@example.com", "Customer@123")


def _login_admin(client):
    return client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"},
    )


def _submit(client, car_id, **overrides):
    """POST the customer rental-details form (bookings/new)."""
    data = {
        "car_id": car_id,
        "pickup_branch_id": _branch_id("Head Office"),
        "return_branch_id": _branch_id("Airport Branch"),
        "pickup_datetime": _PICKUP,
        "return_datetime": _RETURN,
        "driver_id": "",
        "notes": "",
    }
    data.update(overrides)
    return client.post("/bookings/new", data=data, follow_redirects=False)


def _admin_create(client, car_id, **overrides):
    data = {
        "customer_id": _customer_id(),
        "car_id": car_id,
        "pickup_branch_id": _branch_id("Head Office"),
        "return_branch_id": _branch_id("Airport Branch"),
        "pickup_datetime": _PICKUP,
        "return_datetime": _RETURN,
        "status": BookingStatus.PENDING,
        "additional_charges": "0.00",
        "discount": "0.00",
        "notes": "",
    }
    data.update(overrides)
    return client.post("/admin/bookings/new", data=data, follow_redirects=True)


# --------------------------------------------------------------------------
# 1. Available car can be booked
# --------------------------------------------------------------------------

def test_available_car_can_be_booked(availability_db):
    client = availability_db.test_client()
    _login_customer(client)
    _submit(client, _car_id("KHI-1001"))
    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "Booking confirmed" in resp.get_data(as_text=True)
    with availability_db.app_context():
        booking = Booking.query.one()
        assert booking.car_id == _car_id("KHI-1001")
        assert booking.status == BookingStatus.PENDING


# --------------------------------------------------------------------------
# 2. Non-rentable car status cannot be booked
# --------------------------------------------------------------------------

def test_out_of_service_car_cannot_be_booked(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        car_id = _set_status("KHI-1006", CarStatus.OUT_OF_SERVICE)
    _login_customer(client)

    resp = _submit(client, car_id)
    assert "out of service" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


def test_maintenance_status_car_cannot_be_booked(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        car_id = _car_id("KHI-1002")  # seeded with status maintenance
    _login_customer(client)

    resp = _submit(client, car_id)
    assert "undergoing maintenance" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


def test_rented_status_car_cannot_be_booked(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        car_id = _set_status("KHI-1006", CarStatus.RENTED)
    _login_customer(client)

    resp = _submit(client, car_id)
    assert "currently unavailable" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


def test_inactive_car_cannot_be_booked(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        car = _car("KHI-1006")
        car.is_active = False
        db.session.commit()
        car_id = car.id
    _login_customer(client)

    resp = _submit(client, car_id)
    assert "currently unavailable" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


# --------------------------------------------------------------------------
# 3. Active maintenance blocks a car
# --------------------------------------------------------------------------

def test_active_maintenance_blocks_booking(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        _add_maintenance("KHI-1006", status=MaintenanceStatus.IN_PROGRESS)
        car_id = _car_id("KHI-1006")
    _login_customer(client)

    resp = _submit(client, car_id)
    assert "undergoing maintenance" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


def test_scheduled_maintenance_blocks_booking(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        _add_maintenance("KHI-1006", status=MaintenanceStatus.SCHEDULED)
        car_id = _car_id("KHI-1006")
    _login_customer(client)

    resp = _submit(client, car_id)
    assert "undergoing maintenance" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


# --------------------------------------------------------------------------
# 4. Completed maintenance does not block
# --------------------------------------------------------------------------

def test_completed_maintenance_does_not_block(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        # KHI-1006 gets a *completed* record and must stay bookable.
        _add_maintenance(
            "KHI-1006",
            status=MaintenanceStatus.COMPLETED,
            completed=date(2026, 9, 3),
        )
        car_id = _car_id("KHI-1006")
    _login_customer(client)

    _submit(client, car_id)
    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "Booking confirmed" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 1


def test_seeded_completed_maintenance_keeps_car_bookable(availability_db):
    # KHI-1001's only seeded maintenance record is completed.
    with availability_db.app_context():
        assert availability_service.unavailable_reason(_car("KHI-1001")) is None


# --------------------------------------------------------------------------
# 5 & 6. Existing overlap behaviour is preserved
# --------------------------------------------------------------------------

def test_active_overlap_blocks_booking(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        _add_booking("KHI-1001", _PICKUP, _RETURN)
    _login_customer(client)

    _submit(client, _car_id("KHI-1001"))
    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "already booked" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 1


def test_cancelled_booking_does_not_block(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        _add_booking(
            "KHI-1001", _PICKUP, _RETURN, status=BookingStatus.CANCELLED
        )
    _login_customer(client)

    _submit(client, _car_id("KHI-1001"))
    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "Booking confirmed" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 2


# --------------------------------------------------------------------------
# 7. Admin booking creation follows the same rules
# --------------------------------------------------------------------------

def test_admin_create_respects_status_rules(availability_db):
    client = availability_db.test_client()
    _login_admin(client)
    with availability_db.app_context():
        car_id = _set_status("KHI-1006", CarStatus.OUT_OF_SERVICE)

    resp = _admin_create(client, car_id)
    assert "out of service" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


def test_admin_create_respects_maintenance_rules(availability_db):
    client = availability_db.test_client()
    _login_admin(client)
    with availability_db.app_context():
        _add_maintenance("KHI-1006", status=MaintenanceStatus.SCHEDULED)
        car_id = _car_id("KHI-1006")

    resp = _admin_create(client, car_id)
    assert "undergoing maintenance" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


def test_admin_create_respects_overlap(availability_db):
    client = availability_db.test_client()
    _login_admin(client)
    with availability_db.app_context():
        _add_booking("KHI-1001", _PICKUP, _RETURN)

    resp = _admin_create(client, _car_id("KHI-1001"))
    assert "already booked" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 1


def test_admin_edit_respects_maintenance_rules(availability_db):
    client = availability_db.test_client()
    _login_admin(client)
    _admin_create(client, _car_id("KHI-1001"))
    with availability_db.app_context():
        booking = Booking.query.one()
        booking_id = booking.id
        _add_maintenance("KHI-1006", status=MaintenanceStatus.IN_PROGRESS)
        payload = {
            "customer_id": booking.customer_id,
            "car_id": _car_id("KHI-1006"),
            "pickup_branch_id": booking.pickup_branch_id,
            "return_branch_id": booking.return_branch_id,
            "pickup_datetime": booking.pickup_datetime.strftime("%Y-%m-%dT%H:%M"),
            "return_datetime": booking.return_datetime.strftime("%Y-%m-%dT%H:%M"),
            "status": booking.status,
            "additional_charges": "0.00",
            "discount": "0.00",
            "notes": "",
        }

    resp = client.post(
        f"/admin/bookings/{booking_id}/edit", data=payload,
        follow_redirects=True,
    )
    assert "undergoing maintenance" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert db.session.get(Booking, booking_id).car_id == _car_id("KHI-1001")


def test_admin_edit_excludes_itself_from_overlap(availability_db):
    client = availability_db.test_client()
    _login_admin(client)
    _admin_create(client, _car_id("KHI-1001"))
    with availability_db.app_context():
        booking = Booking.query.one()
        booking_id = booking.id
        payload = {
            "customer_id": booking.customer_id,
            "car_id": booking.car_id,
            "pickup_branch_id": booking.pickup_branch_id,
            "return_branch_id": booking.return_branch_id,
            "pickup_datetime": booking.pickup_datetime.strftime("%Y-%m-%dT%H:%M"),
            "return_datetime": booking.return_datetime.strftime("%Y-%m-%dT%H:%M"),
            "status": BookingStatus.CONFIRMED,
            "additional_charges": "0.00",
            "discount": "0.00",
            "notes": "Unchanged dates.",
        }

    resp = client.post(
        f"/admin/bookings/{booking_id}/edit", data=payload,
        follow_redirects=True,
    )
    assert "updated successfully" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert db.session.get(Booking, booking_id).status == BookingStatus.CONFIRMED


# --------------------------------------------------------------------------
# 8. Customer booking creation follows the same rules
# --------------------------------------------------------------------------

def test_customer_confirm_rechecks_car_state(availability_db):
    client = availability_db.test_client()
    _login_customer(client)
    car_id = _car_id("KHI-1006")
    # Draft a valid selection while the car is free...
    _submit(client, car_id)
    # ...then the car goes into maintenance before confirmation.
    with availability_db.app_context():
        _set_status("KHI-1006", CarStatus.MAINTENANCE)

    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "undergoing maintenance" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 0


# --------------------------------------------------------------------------
# 9. Availability/search never presents unavailable cars as bookable
# --------------------------------------------------------------------------

def test_fleet_excludes_status_blocked_cars(availability_db):
    client = availability_db.test_client()
    body = client.get("/cars").get_data(as_text=True)
    assert "Corolla" in body
    assert "Civic" not in body  # seeded status=maintenance

    with availability_db.app_context():
        _set_status("KHI-1006", CarStatus.OUT_OF_SERVICE)
    body = client.get("/cars").get_data(as_text=True)
    assert "Wagon" not in body


def test_fleet_excludes_active_maintenance_car(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        _add_maintenance("KHI-1006", status=MaintenanceStatus.IN_PROGRESS)

    body = client.get("/cars").get_data(as_text=True)
    assert "Wagon" not in body
    assert "Corolla" in body


def test_home_does_not_feature_unavailable_cars(availability_db):
    client = availability_db.test_client()
    body = client.get("/").get_data(as_text=True)
    # Honda Civic is in maintenance and must not appear as a featured car.
    assert "Civic" not in body


def test_car_detail_hides_cta_when_unavailable(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        car_id = _set_status("KHI-1006", CarStatus.MAINTENANCE)

    body = client.get(f"/cars/{car_id}").get_data(as_text=True)
    assert "undergoing maintenance" in body
    assert "Rent Now" not in body


def test_search_excludes_maintenance_car(availability_db):
    client = availability_db.test_client()
    body = client.get(
        f"/cars?pickup_datetime={_PICKUP}&return_datetime={_RETURN}"
    ).get_data(as_text=True)
    assert "Corolla" in body
    assert "Civic" not in body


def test_search_excludes_overlapping_car(availability_db):
    client = availability_db.test_client()
    with availability_db.app_context():
        _add_booking("KHI-1001", _PICKUP, _RETURN)

    body = client.get(
        f"/cars?pickup_datetime={_PICKUP}&return_datetime={_RETURN}"
    ).get_data(as_text=True)
    assert "Corolla" not in body
    assert "Fortuner" in body


def test_booking_form_lists_only_bookable_cars(availability_db):
    client = availability_db.test_client()
    body = client.get("/bookings/new").get_data(as_text=True)
    assert "Corolla" in body
    assert "Civic" not in body  # maintenance


# --------------------------------------------------------------------------
# 10. Booking review cannot bypass availability validation
# --------------------------------------------------------------------------

def test_review_flags_overlap_and_hides_confirm(availability_db):
    client = availability_db.test_client()
    _login_customer(client)
    _submit(client, _car_id("KHI-1001"))
    with availability_db.app_context():
        _add_booking("KHI-1001", _PICKUP, _RETURN)

    body = client.get("/bookings/review").get_data(as_text=True)
    assert "already booked" in body
    assert "Confirm booking" not in body


def test_review_revalidates_car_state(availability_db):
    client = availability_db.test_client()
    _login_customer(client)
    _submit(client, _car_id("KHI-1006"))
    with availability_db.app_context():
        _set_status("KHI-1006", CarStatus.MAINTENANCE)

    body = client.get("/bookings/review").get_data(as_text=True)
    assert "undergoing maintenance" in body
    assert "Confirm booking" not in body


# --------------------------------------------------------------------------
# 11. Final confirmation rechecks availability
# --------------------------------------------------------------------------

def test_confirm_rechecks_overlap(availability_db):
    client = availability_db.test_client()
    _login_customer(client)
    _submit(client, _car_id("KHI-1001"))
    # A competing booking lands after review but before confirm.
    with availability_db.app_context():
        _add_booking("KHI-1001", _PICKUP, _RETURN, number="BK-RACE-01")

    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "already booked" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 1


# --------------------------------------------------------------------------
# 12. Existing valid flow still works
# --------------------------------------------------------------------------

def test_valid_booking_flow_still_works(availability_db):
    client = availability_db.test_client()
    _login_customer(client)

    resp = _submit(client, _car_id("KHI-1001"))
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/bookings/review")

    review = client.get("/bookings/review").get_data(as_text=True)
    assert "Review your booking" in review
    assert "Confirm booking" in review

    resp = client.post("/bookings/confirm", follow_redirects=True)
    assert "Booking confirmed" in resp.get_data(as_text=True)
    with availability_db.app_context():
        assert Booking.query.count() == 1


# --------------------------------------------------------------------------
# The shared decision itself
# --------------------------------------------------------------------------

def test_unavailable_reason_maps_statuses(availability_db):
    with availability_db.app_context():
        assert availability_service.unavailable_reason(_car("KHI-1001")) is None
        assert (
            availability_service.unavailable_reason(_car("KHI-1002"))
            == availability_service.CAR_MAINTENANCE
        )
        _set_status("LHR-1004", CarStatus.OUT_OF_SERVICE)
        assert (
            availability_service.unavailable_reason(_car("LHR-1004"))
            == availability_service.CAR_OUT_OF_SERVICE
        )
        _set_status("LHR-1005", CarStatus.RENTED)
        assert (
            availability_service.unavailable_reason(_car("LHR-1005"))
            == availability_service.CAR_UNAVAILABLE
        )


def test_check_availability_combines_state_and_overlap(availability_db):
    with availability_db.app_context():
        car = _car("KHI-1001")
        bookable, reason = availability_service.check_availability(
            car, datetime.strptime(_PICKUP, "%Y-%m-%dT%H:%M"),
            datetime.strptime(_RETURN, "%Y-%m-%dT%H:%M"),
        )
        assert bookable is True and reason is None

        _add_booking("KHI-1001", _PICKUP, _RETURN)
        bookable, reason = availability_service.check_availability(
            car, datetime.strptime(_PICKUP, "%Y-%m-%dT%H:%M"),
            datetime.strptime(_RETURN, "%Y-%m-%dT%H:%M"),
        )
        assert bookable is False
        assert reason == availability_service.CAR_ALREADY_BOOKED
