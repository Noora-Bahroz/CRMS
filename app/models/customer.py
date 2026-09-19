"""Customer model.

Registered rental customers.  A Customer record is linked to a User
account (which handles authentication).
"""

from datetime import datetime

from app.extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False
    )
    driver_license_number = db.Column(db.String(50), unique=True, nullable=False)
    driver_license_expiry = db.Column(db.Date, nullable=False)
    date_of_birth = db.Column(db.Date)
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    zip_code = db.Column(db.String(20))
    emergency_contact_name = db.Column(db.String(150))
    emergency_contact_phone = db.Column(db.String(30))
    notes = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user = db.relationship("User", back_populates="customer")
    bookings = db.relationship("Booking", back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer id={self.id} license={self.driver_license_number!r}>"
