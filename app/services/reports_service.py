"""Reporting service.

Read-only aggregations for the admin reports page.  All figures come from
the existing database and the business rules already used elsewhere in the
project:

* revenue is the sum of COMPLETED payments (the same definition as the
  admin dashboard);
* booking counts use the pickup date, matching the booking report table;
* expenses use ``expense_date``, maintenance costs use the completed
  records' ``completed_date``.

No accounting rules are invented — the page simply presents existing
records and their sums.  Aggregation is done in Python (not with
database-specific date functions) so the queries behave identically on
SQLite and PostgreSQL.
"""

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Booking, Branch, Car, Expense, Maintenance, Payment
from app.utils import validators
from app.utils.constants import BookingStatus, MaintenanceStatus, PaymentStatus

_ZERO = Decimal("0")


def parse_date_range(from_raw: str, to_raw: str):
    """Validate an optional date-range pair.

    Returns ``(from_date, to_date, error)``.  Either bound may be blank;
    when a bound is blank it is ``None``.  When anything is invalid —
    wrong format, or from after to — both dates are ``None`` so no filters
    are applied and the page shows the error instead.
    """
    from_date, from_error = validators.optional_date(from_raw, "From date")
    to_date, to_error = validators.optional_date(to_raw, "To date")
    if from_error or to_error:
        return None, None, (from_error or to_error)
    if from_date and to_date and from_date > to_date:
        return None, None, "From date must not be after To date."
    return from_date, to_date, None


def _start(of) -> datetime:
    return datetime.combine(of, time.min)


def _end(of) -> datetime:
    return datetime.combine(of, time.max)


def _bookings_query(from_date, to_date, status=None, branch_id=None):
    """Booking base query filtered by pickup dates and optional extras."""
    query = Booking.query
    if from_date:
        query = query.filter(Booking.pickup_datetime >= _start(from_date))
    if to_date:
        query = query.filter(Booking.pickup_datetime <= _end(to_date))
    if status:
        query = query.filter(Booking.status == status)
    if branch_id:
        query = query.filter(Booking.pickup_branch_id == branch_id)
    return query


def summary_stats(from_date, to_date) -> dict:
    """High-level cards for the reports page."""
    bookings = _bookings_query(from_date, to_date)
    total_bookings = bookings.count()
    completed_bookings = bookings.filter(
        Booking.status == BookingStatus.COMPLETED
    ).count()
    cancelled_bookings = bookings.filter(
        Booking.status == BookingStatus.CANCELLED
    ).count()

    maintenance_query = db.session.query(
        func.count(Maintenance.id),
        func.coalesce(func.sum(Maintenance.cost), 0),
    ).filter(Maintenance.status == MaintenanceStatus.COMPLETED)
    if from_date:
        maintenance_query = maintenance_query.filter(
            Maintenance.completed_date >= from_date
        )
    if to_date:
        maintenance_query = maintenance_query.filter(
            Maintenance.completed_date <= to_date
        )
    maintenance_count, maintenance_cost_raw = maintenance_query.one()
    maintenance_count = int(maintenance_count)
    maintenance_cost = Decimal(maintenance_cost_raw)

    revenue = completed_payment_sum(from_date, to_date)
    expenses = expense_sum(from_date, to_date)

    return {
        "total_bookings": total_bookings,
        "completed_bookings": completed_bookings,
        "cancelled_bookings": cancelled_bookings,
        "revenue": revenue,
        "expenses": expenses,
        "net": revenue - expenses,
        "active_cars": Car.query.filter_by(is_active=True).count(),
        "total_cars": Car.query.count(),
        "maintenance_count": maintenance_count,
        "maintenance_cost": maintenance_cost,
    }


def completed_payment_sum(from_date, to_date, branch_id=None) -> Decimal:
    """Sum of COMPLETED payment amounts (the project's revenue rule)."""
    query = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(Payment.status == PaymentStatus.COMPLETED)
    if from_date:
        query = query.filter(Payment.created_at >= _start(from_date))
    if to_date:
        query = query.filter(Payment.created_at <= _end(to_date))
    if branch_id:
        query = query.join(Booking, Payment.booking_id == Booking.id).filter(
            Booking.pickup_branch_id == branch_id
        )
    return Decimal(query.scalar())


def expense_sum(from_date, to_date, category=None, branch_id=None) -> Decimal:
    """Sum of expenses matching the supplied filters."""
    query = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    )
    if from_date:
        query = query.filter(Expense.expense_date >= from_date)
    if to_date:
        query = query.filter(Expense.expense_date <= to_date)
    if category:
        query = query.filter(Expense.category == category)
    if branch_id:
        query = query.filter(Expense.branch_id == branch_id)
    return Decimal(query.scalar())


def _paid_by_booking(bookings) -> dict:
    """Map booking id -> completed payment total for a set of bookings."""
    ids = [b.id for b in bookings]
    if not ids:
        return {}
    rows = (
        db.session.query(
            Payment.booking_id,
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .filter(
            Payment.booking_id.in_(ids),
            Payment.status == PaymentStatus.COMPLETED,
        )
        .group_by(Payment.booking_id)
        .all()
    )
    return {booking_id: Decimal(amount) for booking_id, amount in rows}


def booking_report(from_date, to_date, status=None, branch_id=None) -> dict:
    """Booking/rental report rows plus rental/payment/outstanding totals.

    Distinct figures are kept apart: the rental value is the bookings'
    stored ``total_amount``, while payments shown are the actual recorded
    COMPLETED payments for each booking.
    """
    bookings = (
        _bookings_query(from_date, to_date, status, branch_id)
        .order_by(Booking.pickup_datetime.desc(), Booking.id.desc())
        .all()
    )
    paid_map = _paid_by_booking(bookings)

    rows = []
    rental_total = _ZERO
    paid_total = _ZERO
    outstanding = _ZERO
    for booking in bookings:
        paid = paid_map.get(booking.id, _ZERO)
        balance = booking.total_amount - paid
        rental_total += booking.total_amount
        paid_total += paid
        outstanding += balance
        rows.append(
            {
                "booking": booking,
                "rental": booking.total_amount,
                "paid": paid,
                "balance": balance,
            }
        )

    return {
        "rows": rows,
        "count": len(rows),
        "rental_total": rental_total,
        "paid_total": paid_total,
        "outstanding": outstanding,
    }


def expense_report(from_date, to_date, category=None, branch_id=None) -> dict:
    """Expense report rows and the matching total."""
    query = Expense.query
    if from_date:
        query = query.filter(Expense.expense_date >= from_date)
    if to_date:
        query = query.filter(Expense.expense_date <= to_date)
    if category:
        query = query.filter(Expense.category == category)
    if branch_id:
        query = query.filter(Expense.branch_id == branch_id)
    expenses = query.order_by(
        Expense.expense_date.desc(), Expense.id.desc()
    ).all()
    return {
        "rows": expenses,
        "count": len(expenses),
        "total": expense_sum(from_date, to_date, category, branch_id),
    }


def fleet_report(from_date, to_date) -> dict:
    """Per-car fleet summary from real relationships.

    Booking count and revenue use the pickup range and completed-payment
    range respectively; maintenance count/cost covers completed records
    within the range (all completed when unfiltered).  No new vehicle
    status is introduced — the cars' own ``status`` is displayed as-is.
    """
    cars = Car.query.order_by(Car.make.asc(), Car.model.asc(), Car.id.asc()).all()
    if not cars:
        return {"rows": [], "count": 0}
    car_ids = [car.id for car in cars]

    count_query = db.session.query(
        Booking.car_id, func.count(Booking.id)
    ).filter(Booking.car_id.in_(car_ids))
    if from_date:
        count_query = count_query.filter(Booking.pickup_datetime >= _start(from_date))
    if to_date:
        count_query = count_query.filter(Booking.pickup_datetime <= _end(to_date))
    booking_counts = dict(count_query.group_by(Booking.car_id).all())

    revenue_map = {}
    revenue_query = db.session.query(
        Booking.car_id, func.coalesce(func.sum(Payment.amount), 0)
    ).join(Payment, Payment.booking_id == Booking.id).filter(
        Payment.status == PaymentStatus.COMPLETED,
        Booking.car_id.in_(car_ids),
    )
    if from_date:
        revenue_query = revenue_query.filter(Payment.created_at >= _start(from_date))
    if to_date:
        revenue_query = revenue_query.filter(Payment.created_at <= _end(to_date))
    revenue_map = {
        car_id: Decimal(amount)
        for car_id, amount in revenue_query.group_by(Booking.car_id).all()
    }

    maintenance_map = {}
    maintenance_query = db.session.query(
        Maintenance.car_id,
        func.count(Maintenance.id),
        func.coalesce(func.sum(Maintenance.cost), 0),
    ).filter(
        Maintenance.car_id.in_(car_ids),
        Maintenance.status == MaintenanceStatus.COMPLETED,
    )
    if from_date:
        maintenance_query = maintenance_query.filter(
            Maintenance.completed_date >= from_date
        )
    if to_date:
        maintenance_query = maintenance_query.filter(
            Maintenance.completed_date <= to_date
        )
    for car_id, count, cost in maintenance_query.group_by(
        Maintenance.car_id
    ).all():
        maintenance_map[car_id] = {
            "count": int(count),
            "cost": Decimal(cost),
        }

    rows = []
    for car in cars:
        maint = maintenance_map.get(car.id, {"count": 0, "cost": _ZERO})
        rows.append(
            {
                "car": car,
                "category_name": car.category.name if car.category else "—",
                "branch_name": car.branch.name if car.branch else "—",
                "booking_count": int(booking_counts.get(car.id, 0)),
                "revenue": revenue_map.get(car.id, _ZERO),
                "maintenance_count": maint["count"],
                "maintenance_cost": maint["cost"],
            }
        )
    return {"rows": rows, "count": len(rows)}


def branch_summary(from_date, to_date) -> dict:
    """Branch-level summary using pickup bookings, payments, and expenses."""
    branches = Branch.query.filter_by(is_active=True).order_by(Branch.name.asc()).all()
    rows = []
    for branch in branches:
        bookings = _bookings_query(from_date, to_date, branch_id=branch.id)
        row = {
            "branch": branch,
            "cars": len(branch.cars),
            "bookings": bookings.count(),
            "revenue": completed_payment_sum(from_date, to_date, branch.id),
            "expenses": expense_sum(from_date, to_date, branch_id=branch.id),
        }
        rows.append(row)
    return {
        "rows": rows,
        "total_revenue": sum((r["revenue"] for r in rows), _ZERO),
        "total_expenses": sum((r["expenses"] for r in rows), _ZERO),
    }


def chart_data(from_date, to_date, status=None, branch_id=None) -> dict:
    """Chart-ready series (format-safe floats, bounded by the filter range).

    Bucketing happens in Python so the page works on any backend.  The
    booking series reuse the same query/filters as the booking report.
    """
    bookings = (
        _bookings_query(from_date, to_date, status, branch_id)
        .order_by(Booking.pickup_datetime.asc())
        .all()
    )

    status_counts: dict[str, int] = {}
    for booking in bookings:
        status_counts[booking.status] = status_counts.get(booking.status, 0) + 1

    booking_months: dict[tuple, int] = {}
    for booking in bookings:
        month = (booking.pickup_datetime.year, booking.pickup_datetime.month)
        booking_months[month] = booking_months.get(month, 0) + 1

    payment_rows = db.session.query(
        Payment.created_at, Payment.amount
    ).filter(Payment.status == PaymentStatus.COMPLETED)
    if from_date:
        payment_rows = payment_rows.filter(Payment.created_at >= _start(from_date))
    if to_date:
        payment_rows = payment_rows.filter(Payment.created_at <= _end(to_date))

    expense_rows = Expense.query.with_entities(Expense.expense_date, Expense.amount)
    if from_date:
        expense_rows = expense_rows.filter(Expense.expense_date >= from_date)
    if to_date:
        expense_rows = expense_rows.filter(Expense.expense_date <= to_date)

    revenue_months: dict[tuple, int] = {}
    for created_at, amount in payment_rows.all():
        month = (created_at.year, created_at.month)
        revenue_months[month] = revenue_months.get(month, 0) + int(amount)
    expense_months: dict[tuple, int] = {}
    for expense_date, amount in expense_rows.all():
        month = (expense_date.year, expense_date.month)
        expense_months[month] = expense_months.get(month, 0) + int(amount)

    months = sorted(set(booking_months) | set(revenue_months) | set(expense_months))

    return {
        "booking_status": [
            {"label": status, "count": status_counts[status]}
            for status in BookingStatus.ALL
            if status_counts.get(status, 0) > 0
        ],
        "bookings_over_time": [
            {
                "label": f"{year}-{month:02d}",
                "count": booking_months.get((year, month), 0),
            }
            for (year, month) in months
        ],
        "revenue_vs_expenses": [
            {
                "label": f"{year}-{month:02d}",
                "revenue": revenue_months.get((year, month), 0),
                "expenses": expense_months.get((year, month), 0),
            }
            for (year, month) in months
        ],
    }