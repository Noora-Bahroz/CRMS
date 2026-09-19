"""Integration tests: admin reports page.

Report figures are checked against records created in the test database
(plus the fixed seed data) so the assertions validate the page reads real
rows rather than hard-coded numbers.
"""

import pytest

from app.extensions import db
from app.models import Branch, Booking, Payment, User
from app.utils.constants import BookingStatus, PaymentStatus
from app.utils.security import hash_password

from scripts.seed_data import seed

# Seeded (fixed) aggregate values, computed directly from seed_data.py.
_SEEDED_EXPENSES = 35000 + 8000 + 180000 + 12000  # fuel+cleaning+insurance+maint
_SEEDED_MAINTENANCE_COST = 12000 + 5000  # two completed records


@pytest.fixture()
def reports_db(app):
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


def _create_booking(client, pickup="2026-12-01T10:00", ret="2026-12-03T10:00",
                    status="pending", car_plate="KHI-1001"):
    """Create a booking via the admin API and return its id."""
    with client.application.app_context():
        from app.models import Car, Customer

        customer_id = Customer.query.first().id
        car_id = Car.query.filter_by(license_plate=car_plate).one().id
        branches = Branch.query.order_by(Branch.id.asc()).all()
        payload = {
            "customer_id": customer_id,
            "car_id": car_id,
            "pickup_branch_id": branches[0].id,
            "return_branch_id": branches[1].id,
            "pickup_datetime": pickup,
            "return_datetime": ret,
            "status": status,
            "additional_charges": "0.00",
            "discount": "0.00",
        }
    resp = client.post("/admin/bookings/new", data=payload, follow_redirects=True)
    assert resp.status_code == 200
    with client.application.app_context():
        return Booking.query.order_by(Booking.id.desc()).first().id


def _add_payment(client, booking_id, amount="8000.00", status=PaymentStatus.COMPLETED):
    payload = {
        "booking_id": booking_id,
        "amount": amount,
        "method": "bank_transfer",
        "status": status,
        "reference_number": f"TXN-{booking_id}",
        "received_by": "System Administrator",
        "notes": "Test payment.",
    }
    resp = client.post("/admin/payments/new", data=payload, follow_redirects=True)
    assert resp.status_code == 200
    return resp


def _create_report_scenario(client):
    """Two bookings on distinct cars: one completed (with a payment),
    one cancelled.  Returns the completed booking's number."""
    completed_id = _create_booking(
        client, pickup="2026-12-01T10:00", ret="2026-12-03T10:00",
        status=BookingStatus.COMPLETED, car_plate="KHI-1001",
    )
    _add_payment(client, completed_id, amount="8000.00", status=PaymentStatus.COMPLETED)
    _add_payment(client, completed_id, amount="500.00", status=PaymentStatus.PENDING)
    cancelled_id = _create_booking(
        client, pickup="2026-11-10T10:00", ret="2026-11-12T10:00",
        status=BookingStatus.CANCELLED, car_plate="KHI-1003",
    )
    with client.application.app_context():
        return (
            db.session.get(Booking, completed_id).booking_number,
            db.session.get(Booking, cancelled_id).booking_number,
        )


def test_unauthenticated_reports_redirects_to_login(reports_db, client):
    resp = client.get("/admin/reports")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_reports(reports_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/reports")
    assert resp.status_code == 403


def test_admin_can_open_reports_page(reports_db, client):
    _login_admin(client)
    resp = client.get("/admin/reports")
    assert resp.status_code == 200
    assert b"Reports" in resp.data
    assert b"Summary" in resp.data
    assert b"Booking / Revenue Report" in resp.data
    assert b"Expense Report" in resp.data
    assert b"Fleet / Vehicle Report" in resp.data
    assert b"Branch Summary" in resp.data


def test_summary_cards_use_real_database_data(reports_db, client):
    _login_admin(client)
    completed_no, cancelled_no = _create_report_scenario(client)
    resp = client.get("/admin/reports")
    assert b"Total Bookings" in resp.data
    assert b">2<" in resp.data  # total bookings card
    assert b"Rs 8,000" in resp.data  # revenue card: one completed 8000 payment
    assert b"Rs 235,000" in resp.data  # expense card: 4 seeded expenses
    assert b"Rs -227,000" in resp.data  # net card (8000 - 235000)
    assert b">6<" in resp.data  # active cars card
    assert b"Rs 17,000" in resp.data  # completed maintenance cost
    assert b"2 completed" in resp.data  # maintenance record count


def test_booking_report_displays_real_booking_data(reports_db, client):
    _login_admin(client)
    completed_no, cancelled_no = _create_report_scenario(client)
    resp = client.get("/admin/reports")
    assert completed_no.encode() in resp.data
    assert cancelled_no.encode() in resp.data
    assert b"Fatima" in resp.data
    assert b"Corolla" in resp.data
    assert b"2026-12-01" in resp.data
    assert b"completed" in resp.data
    assert b"cancelled" in resp.data


def test_payment_revenue_totals_from_real_records(reports_db, client):
    _login_admin(client)
    _create_report_scenario(client)
    resp = client.get("/admin/reports")
    # Completed payment 8000 recorded; the pending 500 must not count.
    assert b"Rs 8000.00" in resp.data  # paid cell / recorded payments chip
    # Rental values: Sedan 2x4000=8000 and SUV 2x6000=12000 -> 20000 total.
    assert b"Rs 20000.00" in resp.data  # rental total footer
    # Cancelled SUV booking is unpaid -> 12000 outstanding.
    assert b"Rs 12000.00" in resp.data  # balance / outstanding chip
    assert b"2 booking(s)" in resp.data


def test_expense_report_displays_real_expenses(reports_db, client):
    _login_admin(client)
    resp = client.get("/admin/reports")
    assert b"FUEL" in resp.data
    assert b"INSURANCE" in resp.data
    assert b"Monthly fuel bulk purchase" in resp.data
    assert b"Annual fleet insurance premium" in resp.data


def test_expense_totals_are_correct(reports_db, client):
    _login_admin(client)
    resp = client.get("/admin/reports")
    assert b"4 expense(s)" in resp.data
    assert f"Rs {_SEEDED_EXPENSES:.2f}".encode() in resp.data


def test_fleet_report_displays_real_cars(reports_db, client):
    _login_admin(client)
    _create_report_scenario(client)
    resp = client.get("/admin/reports")
    assert b"KHI-1001" in resp.data
    assert b"KHI-1006" in resp.data
    assert b"Corolla" in resp.data
    assert b"Fortuner" in resp.data
    assert b"Sedan" in resp.data
    assert b"Economy" in resp.data


def test_branch_summary_displays_real_branch_data(reports_db, client):
    _login_admin(client)
    _create_report_scenario(client)
    resp = client.get("/admin/reports")
    assert b"Head Office" in resp.data
    assert b"Airport Branch" in resp.data
    assert b"Karachi" in resp.data
    assert b"Lahore" in resp.data


def test_booking_status_filter_works(reports_db, client):
    _login_admin(client)
    completed_no, cancelled_no = _create_report_scenario(client)
    resp = client.get("/admin/reports?status=cancelled")
    assert cancelled_no.encode() in resp.data
    assert completed_no.encode() not in resp.data
    assert b"1 booking(s)" in resp.data


def test_expense_category_filter_works(reports_db, client):
    _login_admin(client)
    resp = client.get("/admin/reports?category=fuel")
    assert b"1 expense(s)" in resp.data
    assert b"Rs 35000.00" in resp.data
    assert b"Insurance" not in resp.data


def test_date_range_filter_works(reports_db, client):
    _login_admin(client)
    _create_report_scenario(client)
    # Only the seeded maintenance expense falls inside August 2026.
    resp = client.get("/admin/reports?from=2026-08-01&to=2026-08-31")
    assert b"1 expense(s)" in resp.data
    assert b"Rs 12000.00" in resp.data
    # Neither test booking (Nov/Dec) is in range, so the booking report is empty.
    assert b"No bookings match the selected filters." in resp.data
    # Expenses in September (fuel/cleaning/insurance) excluded.
    assert b"Rs 35000.00" not in resp.data


def test_invalid_date_range_is_rejected_safely(reports_db, client):
    _login_admin(client)
    _create_report_scenario(client)
    resp = client.get("/admin/reports?from=2026-12-20&to=2026-12-01")
    assert resp.status_code == 200
    assert b"From date must not be after To date." in resp.data
    # No filter is applied when the range is invalid: both bookings shown.
    assert b"2 booking(s)" in resp.data


def test_invalid_date_format_is_rejected_safely(reports_db, client):
    _login_admin(client)
    resp = client.get("/admin/reports?from=not-a-date")
    assert resp.status_code == 200
    assert b"must be a valid date (YYYY-MM-DD)" in resp.data


def test_branch_filter_works(reports_db, client):
    _login_admin(client)
    with reports_db.app_context():
        head_office_id = Branch.query.filter_by(name="Head Office").one().id
    resp = client.get(f"/admin/reports?branch={head_office_id}")
    # Head Office holds fuel, insurance, and maintenance expenses.
    assert b"3 expense(s)" in resp.data
    assert b"Rs 227000.00" in resp.data
    assert b"Interior deep-cleaning" not in resp.data


def test_no_password_hashes_exposed(reports_db, client):
    _login_admin(client)
    _create_report_scenario(client)
    with reports_db.app_context():
        admin_hash = (
            User.query.filter_by(email="admin@example.com").one().password_hash
        )
    resp = client.get("/admin/reports")
    assert resp.status_code == 200
    assert b"password_hash" not in resp.data
    assert admin_hash.encode() not in resp.data
    customer_hash = (
        User.query.filter_by(email="customer@example.com").one().password_hash
    )
    assert customer_hash.encode() not in resp.data