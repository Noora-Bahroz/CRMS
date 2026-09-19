"""Booking model.

Rental reservations linking a customer, car, driver (optional), and
pickup/return branches.  Stores the calculated pricing fields required
for invoicing.  Schema is prepared for overlapping-booking prevention
but enforcement lives in the service layer.
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import BookingStatus


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    booking_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    customer_id = db.Column(
        db.Integer, db.ForeignKey("customers.id"), nullable=False
    )
    car_id = db.Column(db.Integer, db.ForeignKey("cars.id"), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"))
    pickup_branch_id = db.Column(
        db.Integer, db.ForeignKey("branches.id"), nullable=False
    )
    return_branch_id = db.Column(
        db.Integer, db.ForeignKey("branches.id"), nullable=False
    )

    # Dates / times
    pickup_datetime = db.Column(db.DateTime, nullable=False, index=True)
    return_datetime = db.Column(db.DateTime, nullable=False, index=True)
    actual_pickup_datetime = db.Column(db.DateTime)
    actual_return_datetime = db.Column(db.DateTime)

    # Driver requirement
    requires_driver = db.Column(db.Boolean, nullable=False, default=False)

    # Status
    status = db.Column(
        db.String(20), nullable=False, default=BookingStatus.PENDING, index=True
    )

    # Pricing snapshot (calculated at booking creation, stored for invoicing)
    estimated_days = db.Column(db.Integer, nullable=False, default=1)
    daily_rate = db.Column(db.Numeric(10, 2), nullable=False)
    weekly_rate = db.Column(db.Numeric(10, 2))
    base_cost = db.Column(db.Numeric(10, 2), nullable=False)
    driver_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    additional_charges = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)

    notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    customer = db.relationship("Customer", back_populates="bookings")
    car = db.relationship("Car", back_populates="bookings")
    driver = db.relationship("Driver", back_populates="bookings")
    pickup_branch = db.relationship(
        "Branch", foreign_keys=[pickup_branch_id], back_populates="pickup_bookings"
    )
    return_branch = db.relationship(
        "Branch", foreign_keys=[return_branch_id], back_populates="return_bookings"
    )
    payments = db.relationship("Payment", back_populates="booking")
    invoice = db.relationship("Invoice", back_populates="booking", uselist=False)
    rental_agreement = db.relationship(
        "RentalAgreement", back_populates="booking", uselist=False
    )

    # Indexes for overlapping-booking checks (used by the service layer)
    __table_args__ = (
        db.Index(
            "ix_bookings_car_dates",
            "car_id",
            "pickup_datetime",
            "return_datetime",
        ),
        db.Index(
            "ix_bookings_customer_status",
            "customer_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Booking {self.booking_number!r} status={self.status!r}>"
