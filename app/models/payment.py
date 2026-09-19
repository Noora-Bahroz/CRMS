"""Payment model.

Individual payment transactions against a booking (deposits, partial
payments, full settlements, refunds).
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import PaymentMethod, PaymentStatus


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id"), nullable=False
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    method = db.Column(
        db.String(20), nullable=False, default=PaymentMethod.CASH, index=True
    )
    status = db.Column(
        db.String(20), nullable=False, default=PaymentStatus.PENDING, index=True
    )
    reference_number = db.Column(db.String(100), index=True)
    notes = db.Column(db.Text)
    received_by = db.Column(db.String(150))
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    booking = db.relationship("Booking", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment id={self.id} amount={self.amount} status={self.status!r}>"
