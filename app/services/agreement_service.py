"""Rental agreement service module.

Validation and business rules for managing rental agreements from the
admin panel: create, update, and safe termination.

An agreement is linked one-to-one to a booking and records vehicle
condition (mileage, fuel) at pickup/return plus signature/terms fields.
Agreement numbers are unique.  Termination is the safe soft-delete path
the existing status model supports.
"""

from decimal import Decimal

from app.extensions import db
from app.models import RentalAgreement
from app.repositories import agreement_repository, booking_repository
from app.utils import validators
from app.utils.constants import AgreementStatus


class AgreementError(Exception):
    """Raised when an agreement cannot be modified or terminated."""


def _money(value, default=Decimal("0.00")) -> Decimal:
    """Best-effort conversion for Numeric columns."""
    if value is None:
        return default
    return Decimal(str(value))


def next_agreement_number() -> str:
    """Return a suggested fresh agreement number for the create form."""
    highest = 0
    for agreement in agreement_repository.list_all():
        try:
            highest = max(
                highest, int(str(agreement.agreement_number).split("-")[-1])
            )
        except ValueError:
            continue
    while True:
        highest += 1
        number = f"AGR-{highest:05d}"
        if agreement_repository.find_by_number(number) is None:
            return number


def validate_agreement_form(data, agreement=None):
    """Validate agreement form input.

    Returns ``(values, errors)`` where *values* holds the cleaned
    RentalAgreement attributes and *errors* a list of human-readable
    messages.  Never raises.
    """
    errors = []
    values = {}

    booking_id, error = validators.parse_int(data.get("booking_id"), "Booking")
    if error:
        errors.append(error)
    elif booking_repository.find_by_id(booking_id) is None:
        errors.append("Select a valid booking.")
    else:
        values["booking_id"] = booking_id
        existing = agreement_repository.find_by_booking_id(booking_id)
        if existing is not None and (
            agreement is None or existing.id != agreement.id
        ):
            errors.append(
                "This booking already has a rental agreement. "
                "Choose a different booking."
            )

    agreement_number, error = validators.required_text(
        data.get("agreement_number"), "Agreement number"
    )
    if error:
        errors.append(error)
    else:
        agreement_number = agreement_number.upper()
        existing = agreement_repository.find_by_number(agreement_number)
        if existing is not None and (
            agreement is None or existing.id != agreement.id
        ):
            errors.append("An agreement with this number already exists.")
        else:
            values["agreement_number"] = agreement_number

    status = (data.get("status") or AgreementStatus.DRAFT).strip()
    if status not in AgreementStatus.ALL:
        errors.append("Select a valid status.")
    else:
        values["status"] = status

    values["signed_by_customer"] = validators.parse_bool(
        data.get("signed_by_customer", False)
    )
    values["signed_by_staff"] = validators.parse_bool(data.get("signed_by_staff", False))

    signed_at, error = validators.optional_date(data.get("signed_at"), "Signed date")
    if error:
        errors.append(error)
    else:
        values["signed_at"] = signed_at

    terms_and_conditions, error = validators.required_text(
        data.get("terms_and_conditions"), "Terms and conditions"
    )
    if error:
        errors.append(error)
    else:
        values["terms_and_conditions"] = terms_and_conditions

    pickup_mileage, error = validators.parse_int(
        data.get("pickup_mileage"), "Pickup mileage", min_value=0,
    )
    if error:
        errors.append(error)
    else:
        values["pickup_mileage"] = pickup_mileage

    return_mileage = None
    raw_return_mileage = (data.get("return_mileage") or "").strip()
    if raw_return_mileage:
        return_mileage, error = validators.parse_int(
            data.get("return_mileage"), "Return mileage", min_value=0,
        )
        if error:
            errors.append(error)
        elif "pickup_mileage" in values and return_mileage < values["pickup_mileage"]:
            errors.append("Return mileage must not be less than pickup mileage.")
        else:
            values["return_mileage"] = return_mileage
    else:
        values["return_mileage"] = None

    fuel_level_pickup, error = validators.parse_decimal(
        data.get("fuel_level_pickup"), "Fuel level at pickup",
        min_value=Decimal("0.00"), max_value=Decimal("100.00"),
    )
    if error:
        errors.append(error)
    else:
        values["fuel_level_pickup"] = fuel_level_pickup

    fuel_level_return, error = validators.parse_decimal(
        data.get("fuel_level_return"), "Fuel level at return",
        min_value=Decimal("0.00"), max_value=Decimal("100.00"), required=False,
    )
    if error:
        errors.append(error)
    else:
        values["fuel_level_return"] = (
            fuel_level_return if fuel_level_return is not None else None
        )

    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    return values, errors


def create_agreement(data) -> tuple[RentalAgreement | None, list[str]]:
    """Create a rental agreement for a booking.

    Returns ``(agreement, errors)``; when errors is non-empty nothing is
    persisted and *agreement* is ``None``.
    """
    values, errors = validate_agreement_form(data)
    if errors:
        return None, errors
    agreement = RentalAgreement(**values)
    db.session.add(agreement)
    db.session.commit()
    return agreement, []


def update_agreement(
    agreement, data
) -> tuple[RentalAgreement | None, list[str]]:
    """Update an existing rental agreement."""
    values, errors = validate_agreement_form(data, agreement=agreement)
    if errors:
        return agreement, errors
    for field, value in values.items():
        setattr(agreement, field, value)
    db.session.commit()
    return agreement, []


def terminate_agreement(agreement) -> None:
    """Safely terminate (soft-delete) a rental agreement.

    Raises :class:`AgreementError` when the agreement is already
    terminated.  The row is kept with ``status = terminated`` so signed
    history and booking references remain intact.
    """
    if agreement.status == AgreementStatus.TERMINATED:
        raise AgreementError(
            f"Agreement {agreement.agreement_number} is already terminated."
        )
    agreement.status = AgreementStatus.TERMINATED
    db.session.commit()