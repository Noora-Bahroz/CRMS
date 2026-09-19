"""Driver model.

Hired / additional drivers that customers can request for their bookings.
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import DriverStatus


class Driver(db.Model):
    __tablename__ = "drivers"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(255), index=True)
    license_number = db.Column(db.String(50), unique=True, nullable=False)
    license_expiry = db.Column(db.Date, nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default=DriverStatus.AVAILABLE
    )
    daily_rate = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    bookings = db.relationship("Booking", back_populates="driver")

    def __repr__(self) -> str:
        return f"<Driver {self.first_name} {self.last_name}>"
