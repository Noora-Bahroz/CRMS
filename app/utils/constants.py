"""Domain constants.

Status enums, choices, and fixed values used across models, services,
and templates.
"""


class BookingStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    ALL = (PENDING, CONFIRMED, ONGOING, COMPLETED, CANCELLED)


class PaymentStatus:
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

    ALL = (PENDING, COMPLETED, FAILED, REFUNDED)


class PaymentMethod:
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    MOBILE = "mobile"

    ALL = (CASH, CREDIT_CARD, DEBIT_CARD, BANK_TRANSFER, MOBILE)


class CarStatus:
    AVAILABLE = "available"
    RENTED = "rented"
    MAINTENANCE = "maintenance"
    OUT_OF_SERVICE = "out_of_service"

    ALL = (AVAILABLE, RENTED, MAINTENANCE, OUT_OF_SERVICE)


class MaintenanceStatus:
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

    ALL = (SCHEDULED, IN_PROGRESS, COMPLETED)


class MaintenanceType:
    ROUTINE_SERVICE = "routine_service"
    REPAIR = "repair"
    INSPECTION = "inspection"
    ACCIDENT_REPAIR = "accident_repair"
    CLEANING = "cleaning"

    ALL = (ROUTINE_SERVICE, REPAIR, INSPECTION, ACCIDENT_REPAIR, CLEANING)


class AgreementStatus:
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"

    ALL = (DRAFT, ACTIVE, COMPLETED, TERMINATED)


class ExpenseCategory:
    FUEL = "fuel"
    INSURANCE = "insurance"
    MAINTENANCE = "maintenance"
    CLEANING = "cleaning"
    TOLLS = "tolls"
    PARKING = "parking"
    OTHER = "other"

    ALL = (FUEL, INSURANCE, MAINTENANCE, CLEANING, TOLLS, PARKING, OTHER)


class DriverStatus:
    AVAILABLE = "available"
    ON_TRIP = "on_trip"
    OFF_DUTY = "off_duty"
    INACTIVE = "inactive"

    ALL = (AVAILABLE, ON_TRIP, OFF_DUTY, INACTIVE)


class UserRole:
    ADMIN = "admin"
    STAFF = "staff"

    ALL = (ADMIN, STAFF)


class InvoiceStatus:
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"

    ALL = (PENDING, PAID, OVERDUE, CANCELLED)
