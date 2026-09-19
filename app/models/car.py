"""Car model.

Fleet vehicles.  Each car belongs to a category and is stationed at a
branch.  Status tracks availability, rental, or maintenance state.
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import CarStatus


class Car(db.Model):
    __tablename__ = "cars"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("car_categories.id"), nullable=False
    )
    branch_id = db.Column(
        db.Integer, db.ForeignKey("branches.id"), nullable=False
    )
    make = db.Column(db.String(100), nullable=False, index=True)
    model = db.Column(db.String(100), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    color = db.Column(db.String(50))
    license_plate = db.Column(db.String(30), unique=True, nullable=False, index=True)
    vin = db.Column(db.String(17), unique=True, index=True)
    mileage = db.Column(db.Integer, nullable=False, default=0)
    fuel_level = db.Column(
        db.Numeric(5, 2), nullable=False, default=100,
        comment="Fuel level as percentage (0-100)"
    )
    status = db.Column(
        db.String(20), nullable=False, default=CarStatus.AVAILABLE, index=True
    )
    image_url = db.Column(db.String(500))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    category = db.relationship("CarCategory", back_populates="cars")
    branch = db.relationship("Branch", back_populates="cars")
    bookings = db.relationship("Booking", back_populates="car")
    maintenance_records = db.relationship("Maintenance", back_populates="car")
    expenses = db.relationship("Expense", back_populates="car")

    def __repr__(self) -> str:
        return f"<Car {self.make} {self.model} plate={self.license_plate!r}>"
