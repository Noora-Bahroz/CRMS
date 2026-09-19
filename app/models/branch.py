"""Branch model.

Physical rental locations/offices.  A branch serves as both the pickup
and return point for bookings.
"""

from datetime import datetime

from app.extensions import db


class Branch(db.Model):
    __tablename__ = "branches"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False, index=True)
    state = db.Column(db.String(100))
    zip_code = db.Column(db.String(20))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    cars = db.relationship("Car", back_populates="branch")
    pickup_bookings = db.relationship(
        "Booking",
        foreign_keys="Booking.pickup_branch_id",
        back_populates="pickup_branch",
    )
    return_bookings = db.relationship(
        "Booking",
        foreign_keys="Booking.return_branch_id",
        back_populates="return_branch",
    )
    expenses = db.relationship("Expense", back_populates="branch")

    def __repr__(self) -> str:
        return f"<Branch {self.name!r}>"
