"""Model package.

Model classes are defined one per module and re-exported here so that
Flask-Migrate autogenerate can discover them and other modules can import
from a single location, e.g.  ``from app.models import Car``.
"""

from app.models.agreement import RentalAgreement
from app.models.booking import Booking
from app.models.branch import Branch
from app.models.car import Car
from app.models.category import CarCategory
from app.models.customer import Customer
from app.models.driver import Driver
from app.models.expense import Expense
from app.models.invoice import Invoice
from app.models.maintenance import Maintenance
from app.models.payment import Payment
from app.models.user import User

__all__ = [
    "User",
    "Customer",
    "CarCategory",
    "Branch",
    "Car",
    "Booking",
    "Payment",
    "Invoice",
    "RentalAgreement",
    "Driver",
    "Maintenance",
    "Expense",
]