"""Admin dashboard blueprint.

Serves the admin dashboard under /admin. ``/admin/me`` establishes the
authorization gate and ``/admin/dashboard`` is the dashboard landing page
with live statistics. Management-area routes are added in later phases;
every route here is protected by ``admin_required``.
"""

from flask import Blueprint, jsonify, render_template

from app.extensions import db
from app.models import Booking, Car, Customer, Payment
from app.services.auth_service import get_current_user, user_to_dict
from app.utils.constants import PaymentStatus
from app.utils.decorators import admin_required, json_admin_required

blueprint = Blueprint("admin_dashboard", __name__, url_prefix="/admin")


@blueprint.get("/dashboard")
@admin_required
def dashboard():
    """Render the admin dashboard with live statistics."""
    stats = {
        "cars": Car.query.count(),
        "customers": Customer.query.count(),
        "bookings": Booking.query.count(),
        "revenue": db.session.query(
            db.func.coalesce(db.func.sum(Payment.amount), 0)
        )
        .filter(Payment.status == PaymentStatus.COMPLETED)
        .scalar(),
    }
    recent_activity = (
        Booking.query.order_by(Booking.created_at.desc()).limit(5).all()
    )
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_activity=recent_activity,
        current_user=get_current_user(),
    )


@blueprint.get("/me")
@json_admin_required
def me():
    """Return the authenticated admin/staff user's details."""
    return jsonify({"user": user_to_dict(get_current_user())}), 200