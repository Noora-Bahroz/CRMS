"""Expense model.

Operational and fleet expenses.  A record is optionally linked to a
branch, car, or maintenance record to provide cost context.
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import ExpenseCategory


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(
        db.String(30), nullable=False, index=True
    )
    branch_id = db.Column(
        db.Integer, db.ForeignKey("branches.id")
    )
    car_id = db.Column(
        db.Integer, db.ForeignKey("cars.id")
    )
    maintenance_id = db.Column(
        db.Integer, db.ForeignKey("maintenance_records.id")
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text, nullable=False)
    receipt_url = db.Column(db.String(500))
    recorded_by = db.Column(db.String(150))
    expense_date = db.Column(db.Date, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    branch = db.relationship("Branch", back_populates="expenses")
    car = db.relationship("Car", back_populates="expenses")
    maintenance = db.relationship("Maintenance", back_populates="expenses")

    def __repr__(self) -> str:
        return f"<Expense id={self.id} cat={self.category!r} amount={self.amount}>"
