"""Invoice service module.

Validation and business rules for managing invoices from the admin panel:
create, update, and safe cancellation.

An invoice is generated for a booking and stores its own amount snapshot
(subtotal, tax, discount) so history survives later edits.  The grand
total is always recomputed here as ``subtotal + tax - discount`` to keep
the stored value consistent with the model.  A booking can have at most
one invoice, and invoice numbers are unique.
"""

from decimal import Decimal

from app.extensions import db
from app.models import Invoice
from app.repositories import booking_repository, invoice_repository
from app.utils import validators
from app.utils.constants import InvoiceStatus


class InvoiceError(Exception):
    """Raised when an invoice cannot be modified or cancelled."""


def _money(value, default=Decimal("0.00")) -> Decimal:
    """Best-effort conversion for Numeric columns."""
    if value is None:
        return default
    return Decimal(str(value))


def next_invoice_number() -> str:
    """Return a suggested fresh invoice number for the create form."""
    highest = 0
    for invoice in invoice_repository.list_all():
        try:
            highest = max(highest, int(str(invoice.invoice_number).split("-")[-1]))
        except ValueError:
            continue
    while True:
        highest += 1
        number = f"INV-{highest:05d}"
        if invoice_repository.find_by_number(number) is None:
            return number


def calculate_total(subtotal, tax_amount=0, discount_amount=0) -> Decimal:
    """Return ``subtotal + tax - discount`` clamped at zero."""
    total = _money(subtotal) + _money(tax_amount) - _money(discount_amount)
    return max(total, Decimal("0.00"))


def validate_invoice_form(data, invoice=None):
    """Validate invoice form input.

    Returns ``(values, errors)`` where *values* holds the cleaned Invoice
    attributes (``total_amount`` already computed) and *errors* is a list
    of human-readable messages.  Never raises.
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
        existing = invoice_repository.find_by_booking_id(booking_id)
        if existing is not None and (
            invoice is None or existing.id != invoice.id
        ):
            errors.append(
                "This booking already has an invoice. "
                "Choose a different booking."
            )

    invoice_number, error = validators.required_text(
        data.get("invoice_number"), "Invoice number"
    )
    if error:
        errors.append(error)
    else:
        invoice_number = invoice_number.upper()
        existing = invoice_repository.find_by_number(invoice_number)
        if existing is not None and (
            invoice is None or existing.id != invoice.id
        ):
            errors.append("A booking with this invoice number already exists.")
        else:
            values["invoice_number"] = invoice_number

    subtotal, error = validators.parse_decimal(
        data.get("subtotal"), "Subtotal", min_value=Decimal("0.00"),
    )
    if error:
        errors.append(error)
    else:
        values["subtotal"] = subtotal

    tax_amount, error = validators.parse_decimal(
        data.get("tax_amount"), "Tax amount", min_value=Decimal("0.00"),
        required=False,
    )
    if error:
        errors.append(error)
    else:
        values["tax_amount"] = tax_amount if tax_amount is not None else Decimal("0.00")

    discount_amount, error = validators.parse_decimal(
        data.get("discount_amount"), "Discount amount",
        min_value=Decimal("0.00"), required=False,
    )
    if error:
        errors.append(error)
    else:
        values["discount_amount"] = (
            discount_amount if discount_amount is not None else Decimal("0.00")
        )

    due_date, error = validators.parse_date(data.get("due_date"), "Due date")
    if error:
        errors.append(error)
    else:
        values["due_date"] = due_date

    paid_date, error = validators.optional_date(data.get("paid_date"), "Paid date")
    if error:
        errors.append(error)
    else:
        values["paid_date"] = paid_date

    status = (data.get("status") or InvoiceStatus.PENDING).strip()
    if status not in InvoiceStatus.ALL:
        errors.append("Select a valid status.")
    else:
        values["status"] = status

    notes, _ = validators.optional_text(data.get("notes"))
    values["notes"] = notes
    return values, errors


def create_invoice(data) -> tuple[Invoice | None, list[str]]:
    """Create an invoice for a booking.

    Returns ``(invoice, errors)``; when errors is non-empty nothing is
    persisted and *invoice* is ``None``.
    """
    values, errors = validate_invoice_form(data)
    if errors:
        return None, errors

    total = calculate_total(
        values["subtotal"], values["tax_amount"], values["discount_amount"]
    )
    invoice = Invoice(total_amount=total, **values)
    db.session.add(invoice)
    db.session.commit()
    return invoice, []


def update_invoice(invoice, data) -> tuple[Invoice | None, list[str]]:
    """Update an existing invoice, recomputing the total."""
    values, errors = validate_invoice_form(data, invoice=invoice)
    if errors:
        return invoice, errors

    for field, value in values.items():
        setattr(invoice, field, value)
    invoice.total_amount = calculate_total(
        values["subtotal"], values["tax_amount"], values["discount_amount"]
    )
    db.session.commit()
    return invoice, []


def cancel_invoice(invoice) -> None:
    """Safely cancel (soft-delete) an invoice.

    Raises :class:`InvoiceError` when the invoice is already cancelled.
    The row is kept with ``status = cancelled`` so payment history and
    booking references remain intact.
    """
    if invoice.status == InvoiceStatus.CANCELLED:
        raise InvoiceError(f"Invoice {invoice.invoice_number} is already cancelled.")
    invoice.status = InvoiceStatus.CANCELLED
    db.session.commit()