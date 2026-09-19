"""RentalAgreement model.

Signed rental agreement linked to a booking.  Records vehicle condition
at pickup/return (mileage, fuel level) and T&C acceptance.
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import AgreementStatus


class RentalAgreement(db.Model):
    __tablename__ = "rental_agreements"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False
    )
    agreement_number = db.Column(
        db.String(30), unique=True, nullable=False, index=True
    )
    status = db.Column(
        db.String(20), nullable=False, default=AgreementStatus.DRAFT, index=True
    )

    # Signatures
    signed_by_customer = db.Column(db.Boolean, nullable=False, default=False)
    signed_by_staff = db.Column(db.Boolean, nullable=False, default=False)
    signed_at = db.Column(db.DateTime)

    # Terms
    terms_and_conditions = db.Column(db.Text, nullable=False)

    # Vehicle condition
    pickup_mileage = db.Column(db.Integer, nullable=False)
    return_mileage = db.Column(db.Integer)
    fuel_level_pickup = db.Column(
        db.Numeric(5, 2), nullable=False,
        comment="Fuel level at pickup (0-100 %)"
    )
    fuel_level_return = db.Column(
        db.Numeric(5, 2),
        comment="Fuel level at return (0-100 %)"
    )

    notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    booking = db.relationship("Booking", back_populates="rental_agreement")

    def __repr__(self) -> str:
        return f"<RentalAgreement {self.agreement_number!r}>"
