"""Invoice model.

Financial invoice generated from a booking, containing line-item totals,
tax, and payment status.  One invoice per booking.
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import InvoiceStatus


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False
    )
    invoice_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    tax_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    paid_date = db.Column(db.Date)
    status = db.Column(
        db.String(20), nullable=False, default=InvoiceStatus.PENDING, index=True
    )
    notes = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    booking = db.relationship("Booking", back_populates="invoice")

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number!r} status={self.status!r}>"
