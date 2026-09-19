"""Maintenance model.

Service / MOT / repair / incident records for fleet vehicles.
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import MaintenanceStatus, MaintenanceType


class Maintenance(db.Model):
    __tablename__ = "maintenance_records"

    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(
        db.Integer, db.ForeignKey("cars.id"), nullable=False
    )
    maintenance_type = db.Column(
        db.String(30), nullable=False, index=True
    )
    status = db.Column(
        db.String(20), nullable=False, default=MaintenanceStatus.SCHEDULED, index=True
    )
    description = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    scheduled_date = db.Column(db.Date, nullable=False, index=True)
    completed_date = db.Column(db.Date)
    service_provider = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    car = db.relationship("Car", back_populates="maintenance_records")
    expenses = db.relationship("Expense", back_populates="maintenance")

    def __repr__(self) -> str:
        return (
            f"<Maintenance id={self.id} type={self.maintenance_type!r} "
            f"status={self.status!r}>"
        )
