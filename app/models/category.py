"""CarCategory model.

Fleet categories (e.g. Economy, SUV, Luxury) that define daily/weekly/
monthly rental rates and deposit amounts.
"""

from datetime import datetime

from app.extensions import db


class CarCategory(db.Model):
    __tablename__ = "car_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    daily_rate = db.Column(db.Numeric(10, 2), nullable=False)
    weekly_rate = db.Column(db.Numeric(10, 2), nullable=False)
    monthly_rate = db.Column(db.Numeric(10, 2), nullable=False)
    deposit_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    cars = db.relationship("Car", back_populates="category")

    def __repr__(self) -> str:
        return f"<CarCategory {self.name!r}>"
