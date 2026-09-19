"""Database seeding script.

Creates a stable set of reference records used during development and
testing: default login accounts, car categories, branches, fleet cars,
drivers, a small maintenance history, and a few expenses.

The script is idempotent: existing records are looked up by their unique
natural keys and left untouched, nothing is ever deleted, and it is safe
to run repeatedly.

Bookings, payments, invoices, and rental agreements are intentionally NOT
seeded - they are exercise data created through the application.

Run as a standalone script:

    python scripts/seed_data.py

The module is also importable (``from scripts.seed_data import seed``) so
tests can seed an in-memory test database through the app factory.
"""

import os
import sys
from datetime import date
from decimal import Decimal

# Make ``import app`` work when this file is executed directly, regardless
# of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    Branch,
    Car,
    CarCategory,
    Customer,
    Driver,
    Expense,
    Maintenance,
    User,
)
from app.utils.constants import (  # noqa: E402
    CarStatus,
    DriverStatus,
    ExpenseCategory,
    MaintenanceStatus,
    MaintenanceType,
    UserRole,
)
from app.utils.security import hash_password  # noqa: E402

_SYSTEM_ADMIN = {
    "username": "admin",
    "email": "admin@example.com",
    "password": "Admin@123",
    "first_name": "System",
    "last_name": "Administrator",
    "phone": "+92 300 000 0001",
}

_CUSTOMER_ACCOUNT = {
    "username": "customer",
    "email": "customer@example.com",
    "password": "Customer@123",
    "first_name": "Fatima",
    "last_name": "Khan",
    "phone": "+92 300 987 6543",
}

_CUSTOMER = {
    "email": "customer@example.com",
    "driver_license_number": "DL-2023-0099",
    "driver_license_expiry": date(2031, 5, 14),
    "date_of_birth": date(1990, 5, 14),
    "address": "12-B, Gulberg III",
    "city": "Lahore",
    "state": "Punjab",
    "zip_code": "54660",
    "emergency_contact_name": "Imran Khan",
    "emergency_contact_phone": "+92 300 555 1212",
    "notes": "Primary demo customer for development.",
}

_CATEGORIES = [
    {
        "name": "Economy",
        "description": (
            "Affordable, fuel-efficient compact cars ideal for city "
            "driving and daily commutes."
        ),
        "daily_rate": "2500.00",
        "weekly_rate": "16000.00",
        "monthly_rate": "60000.00",
        "deposit_amount": "10000.00",
    },
    {
        "name": "Sedan",
        "description": (
            "Comfortable mid-size sedans with ample space, suitable for "
            "individuals, families, and business trips."
        ),
        "daily_rate": "4000.00",
        "weekly_rate": "26000.00",
        "monthly_rate": "95000.00",
        "deposit_amount": "15000.00",
    },
    {
        "name": "SUV",
        "description": (
            "Robust sport-utility vehicles with generous space and ground "
            "clearance, great for families and longer trips."
        ),
        "daily_rate": "6000.00",
        "weekly_rate": "38000.00",
        "monthly_rate": "140000.00",
        "deposit_amount": "25000.00",
    },
    {
        "name": "Luxury",
        "description": (
            "Premium executive vehicles offering top-tier comfort, style, "
            "and performance."
        ),
        "daily_rate": "12000.00",
        "weekly_rate": "78000.00",
        "monthly_rate": "280000.00",
        "deposit_amount": "60000.00",
    },
    {
        "name": "Van",
        "description": (
            "Spacious passenger vans ideal for groups, families, and "
            "corporate transport."
        ),
        "daily_rate": "7000.00",
        "weekly_rate": "44000.00",
        "monthly_rate": "160000.00",
        "deposit_amount": "20000.00",
    },
]

_BRANCHES = [
    {
        "name": "Head Office",
        "address": "Main Shahrah-e-Faisal, PECHS",
        "city": "Karachi",
        "state": "Sindh",
        "zip_code": "75530",
        "phone": "+92 21 111 222 333",
        "email": "headoffice@crms.pk",
    },
    {
        "name": "Airport Branch",
        "address": "Airport Road, Allama Iqbal International Airport",
        "city": "Lahore",
        "state": "Punjab",
        "zip_code": "54000",
        "phone": "+92 42 111 444 555",
        "email": "airport@crms.pk",
    },
]

# Services a car per its category and branch (both referenced by name).
_CARS = [
    {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2022,
        "color": "White",
        "license_plate": "KHI-1001",
        "vin": "JTDBE32K501234567",
        "mileage": 24500,
        "fuel_level": "75.00",
        "category": "Sedan",
        "branch": "Head Office",
        "notes": "Well-maintained, ready for rent.",
    },
    {
        "make": "Honda",
        "model": "Civic",
        "year": 2023,
        "color": "Grey",
        "license_plate": "KHI-1002",
        "vin": "2HGFB2F95FH234567",
        "mileage": 31800,
        "fuel_level": "15.00",
        "category": "Sedan",
        "branch": "Head Office",
        "status": CarStatus.MAINTENANCE,
        "notes": "In the workshop for routine service.",
    },
    {
        "make": "Toyota",
        "model": "Fortuner",
        "year": 2021,
        "color": "Black",
        "license_plate": "KHI-1003",
        "vin": "MR0FZ29G901234567",
        "mileage": 45000,
        "fuel_level": "85.00",
        "category": "SUV",
        "branch": "Head Office",
    },
    {
        "make": "Kia",
        "model": "Sportage",
        "year": 2023,
        "color": "Blue",
        "license_plate": "LHR-1004",
        "vin": "KNAPH81BMG5123456",
        "mileage": 12700,
        "fuel_level": "90.00",
        "category": "SUV",
        "branch": "Airport Branch",
    },
    {
        "make": "Hyundai",
        "model": "Tucson",
        "year": 2022,
        "color": "Silver",
        "license_plate": "LHR-1005",
        "vin": "KM8JU3AG1HU123456",
        "mileage": 18300,
        "fuel_level": "60.00",
        "category": "SUV",
        "branch": "Airport Branch",
    },
    {
        "make": "Suzuki",
        "model": "Wagon R",
        "year": 2023,
        "color": "Red",
        "license_plate": "KHI-1006",
        "vin": "MA3EYD21S0A123456",
        "mileage": 6800,
        "fuel_level": "55.00",
        "category": "Economy",
        "branch": "Head Office",
    },
]

_DRIVERS = [
    {
        "first_name": "Ahmed",
        "last_name": "Raza",
        "phone": "+92 300 111 2222",
        "email": "ahmed.raza@example.com",
        "license_number": "DRV-1001",
        "license_expiry": date(2029, 12, 31),
        "daily_rate": "3000.00",
        "status": DriverStatus.AVAILABLE,
    },
    {
        "first_name": "Bilal",
        "last_name": "Khan",
        "phone": "+92 321 333 4444",
        "email": "bilal.khan@example.com",
        "license_number": "DRV-1002",
        "license_expiry": date(2030, 6, 30),
        "daily_rate": "3500.00",
        "status": DriverStatus.AVAILABLE,
    },
    {
        "first_name": "Farhan",
        "last_name": "Sheikh",
        "phone": "+92 333 555 6666",
        "email": "farhan.sheikh@example.com",
        "license_number": "DRV-1003",
        "license_expiry": date(2028, 3, 31),
        "daily_rate": "3000.00",
        "status": DriverStatus.OFF_DUTY,
    },
]

# A small historical/future maintenance log keyed to cars by plate.
_MAINTENANCE = [
    {
        "car_plate": "KHI-1001",
        "maintenance_type": MaintenanceType.ROUTINE_SERVICE,
        "status": MaintenanceStatus.COMPLETED,
        "description": "Routine service: oil, filters, brakes, general inspection.",
        "cost": "12000.00",
        "scheduled_date": date(2026, 8, 20),
        "completed_date": date(2026, 8, 22),
        "service_provider": "Master Motors Workshop",
    },
    {
        "car_plate": "KHI-1003",
        "maintenance_type": MaintenanceType.INSPECTION,
        "status": MaintenanceStatus.COMPLETED,
        "description": "45000 km service check, tire rotation and alignment.",
        "cost": "5000.00",
        "scheduled_date": date(2026, 8, 25),
        "completed_date": date(2026, 8, 26),
        "service_provider": "Auto Zone Services",
    },
    {
        "car_plate": "KHI-1002",
        "maintenance_type": MaintenanceType.ROUTINE_SERVICE,
        "status": MaintenanceStatus.IN_PROGRESS,
        "description": "Scheduled routine service before next hire.",
        "cost": "9000.00",
        "scheduled_date": date(2026, 9, 1),
        "completed_date": None,
        "service_provider": "Master Motors Workshop",
    },
]

# Branch-level operational expenses.
_EXPENSES = [
    {
        "category": ExpenseCategory.FUEL,
        "branch": "Head Office",
        "description": "Monthly fuel bulk purchase for Karachi fleet.",
        "amount": "35000.00",
        "expense_date": date(2026, 9, 1),
        "recorded_by": "admin",
    },
    {
        "category": ExpenseCategory.CLEANING,
        "branch": "Airport Branch",
        "description": "Interior deep-cleaning of Airport Branch fleet.",
        "amount": "8000.00",
        "expense_date": date(2026, 9, 5),
        "recorded_by": "admin",
    },
    {
        "category": ExpenseCategory.INSURANCE,
        "branch": "Head Office",
        "description": "Annual fleet insurance premium (Karachi).",
        "amount": "180000.00",
        "expense_date": date(2026, 9, 10),
        "recorded_by": "admin",
    },
]

# Maintenance-linked expense, referencing the completed Corolla service.
_MAINTENANCE_EXPENSES = [
    {
        "car_plate": "KHI-1001",
        "maintenance_type": MaintenanceType.ROUTINE_SERVICE,
        "scheduled_date": date(2026, 8, 20),
        "category": ExpenseCategory.MAINTENANCE,
        "branch": "Head Office",
        "description": "Routine service charges - Toyota Corolla.",
        "amount": "12000.00",
        "expense_date": date(2026, 8, 22),
        "recorded_by": "admin",
    },
]


def _money(value) -> Decimal:
    """Convert a numeric string/simple value to a Decimal for Numeric columns."""
    return Decimal(str(value))


def _seed_users(created):
    """Create (once) the default admin and customer login accounts."""
    admin = User.query.filter_by(email=_SYSTEM_ADMIN["email"]).first()
    if admin is None:
        db.session.add(
            User(
                username=_SYSTEM_ADMIN["username"],
                email=_SYSTEM_ADMIN["email"],
                password_hash=hash_password(_SYSTEM_ADMIN["password"]),
                first_name=_SYSTEM_ADMIN["first_name"],
                last_name=_SYSTEM_ADMIN["last_name"],
                phone=_SYSTEM_ADMIN["phone"],
                role=UserRole.ADMIN,
                is_active=True,
            )
        )
        created["users"] += 1

    account = User.query.filter_by(email=_CUSTOMER_ACCOUNT["email"]).first()
    if account is None:
        account = User(
            username=_CUSTOMER_ACCOUNT["username"],
            email=_CUSTOMER_ACCOUNT["email"],
            password_hash=hash_password(_CUSTOMER_ACCOUNT["password"]),
            first_name=_CUSTOMER_ACCOUNT["first_name"],
            last_name=_CUSTOMER_ACCOUNT["last_name"],
            phone=_CUSTOMER_ACCOUNT["phone"],
            role=UserRole.STAFF,
            is_active=True,
        )
        db.session.add(account)
        db.session.flush()
        created["users"] += 1

    customer = Customer.query.filter_by(
        driver_license_number=_CUSTOMER["driver_license_number"]
    ).first()
    if customer is None:
        db.session.add(
            Customer(
                user_id=account.id,
                driver_license_number=_CUSTOMER["driver_license_number"],
                driver_license_expiry=_CUSTOMER["driver_license_expiry"],
                date_of_birth=_CUSTOMER["date_of_birth"],
                address=_CUSTOMER["address"],
                city=_CUSTOMER["city"],
                state=_CUSTOMER["state"],
                zip_code=_CUSTOMER["zip_code"],
                emergency_contact_name=_CUSTOMER["emergency_contact_name"],
                emergency_contact_phone=_CUSTOMER["emergency_contact_phone"],
                notes=_CUSTOMER["notes"],
            )
        )
        created["customers"] += 1

    return admin, account


def _seed_categories(created):
    for data in _CATEGORIES:
        if CarCategory.query.filter_by(name=data["name"]).first():
            continue
        db.session.add(
            CarCategory(
                name=data["name"],
                description=data["description"],
                daily_rate=_money(data["daily_rate"]),
                weekly_rate=_money(data["weekly_rate"]),
                monthly_rate=_money(data["monthly_rate"]),
                deposit_amount=_money(data["deposit_amount"]),
            )
        )
        created["categories"] += 1


def _seed_branches(created):
    for data in _BRANCHES:
        if Branch.query.filter_by(name=data["name"]).first():
            continue
        db.session.add(Branch(**data))
        created["branches"] += 1


def _seed_cars(created):
    for data in _CARS:
        if Car.query.filter_by(license_plate=data["license_plate"]).first():
            continue
        category = CarCategory.query.filter_by(name=data["category"]).one()
        branch = Branch.query.filter_by(name=data["branch"]).one()
        db.session.add(
            Car(
                category_id=category.id,
                branch_id=branch.id,
                make=data["make"],
                model=data["model"],
                year=data["year"],
                color=data["color"],
                license_plate=data["license_plate"],
                vin=data["vin"],
                mileage=data["mileage"],
                fuel_level=_money(data["fuel_level"]),
                status=data.get("status", CarStatus.AVAILABLE),
                image_url=data.get("image_url"),
                notes=data.get("notes"),
            )
        )
        created["cars"] += 1


def _seed_drivers(created):
    for data in _DRIVERS:
        if Driver.query.filter_by(license_number=data["license_number"]).first():
            continue
        db.session.add(
            Driver(
                first_name=data["first_name"],
                last_name=data["last_name"],
                phone=data["phone"],
                email=data["email"],
                license_number=data["license_number"],
                license_expiry=data["license_expiry"],
                status=data.get("status", DriverStatus.AVAILABLE),
                daily_rate=_money(data["daily_rate"]),
                notes=data.get("notes"),
            )
        )
        created["drivers"] += 1


def _seed_maintenance(created):
    for data in _MAINTENANCE:
        car = Car.query.filter_by(license_plate=data["car_plate"]).one()
        exists = Maintenance.query.filter_by(
            car_id=car.id,
            maintenance_type=data["maintenance_type"],
            scheduled_date=data["scheduled_date"],
            description=data["description"],
        ).first()
        if exists:
            continue
        db.session.add(
            Maintenance(
                car_id=car.id,
                maintenance_type=data["maintenance_type"],
                status=data["status"],
                description=data["description"],
                cost=_money(data["cost"]),
                scheduled_date=data["scheduled_date"],
                completed_date=data["completed_date"],
                service_provider=data["service_provider"],
                notes=data.get("notes"),
            )
        )
        created["maintenance"] += 1


def _seed_expenses(created):
    for data in _EXPENSES:
        amount = _money(data["amount"])
        exists = Expense.query.filter_by(
            category=data["category"],
            amount=amount,
            description=data["description"],
            expense_date=data["expense_date"],
        ).first()
        if exists:
            continue
        branch = Branch.query.filter_by(name=data["branch"]).one()
        db.session.add(
            Expense(
                category=data["category"],
                branch_id=branch.id,
                amount=amount,
                description=data["description"],
                recorded_by=data["recorded_by"],
                expense_date=data["expense_date"],
            )
        )
        created["expenses"] += 1

    for data in _MAINTENANCE_EXPENSES:
        amount = _money(data["amount"])
        exists = Expense.query.filter_by(
            category=data["category"],
            amount=amount,
            description=data["description"],
            expense_date=data["expense_date"],
        ).first()
        if exists:
            continue
        car = Car.query.filter_by(license_plate=data["car_plate"]).one()
        maintenance = Maintenance.query.filter_by(
            car_id=car.id,
            maintenance_type=data["maintenance_type"],
            scheduled_date=data["scheduled_date"],
        ).first()
        if maintenance is None:
            continue
        branch = Branch.query.filter_by(name=data["branch"]).one()
        db.session.add(
            Expense(
                category=data["category"],
                branch_id=branch.id,
                car_id=car.id,
                maintenance_id=maintenance.id,
                amount=amount,
                description=data["description"],
                recorded_by=data["recorded_by"],
                expense_date=data["expense_date"],
            )
        )
        created["expenses"] += 1


def seed(app=None, config_name: str | None = "development") -> dict:
    """Seed the reference data, returning {entity: created_count}.

    *app* may be an existing Flask application (e.g. the test app); when
    omitted a new application is created with *config_name*. Idempotent:
    records already present are left untouched.
    """
    if app is None:
        app = create_app(config_name)

    created = {
        "users": 0,
        "customers": 0,
        "categories": 0,
        "branches": 0,
        "cars": 0,
        "drivers": 0,
        "maintenance": 0,
        "expenses": 0,
    }

    with app.app_context():
        _seed_categories(created)
        _seed_branches(created)
        _seed_users(created)
        _seed_cars(created)
        _seed_drivers(created)
        _seed_maintenance(created)
        _seed_expenses(created)
        db.session.commit()

    return created


def run() -> None:
    """Seed the configured database and print a summary."""
    created = seed()
    print("Seed complete. Records created:")
    for entity, count in created.items():
        print(f"  {entity:12s} {count}")

    with create_app().app_context():
        from app.models import Booking, Payment, RentalAgreement

        print(
            "Empty child records: "
            f"bookings={Booking.query.count()} "
            f"payments={Payment.query.count()} "
            f"rental_agreements={RentalAgreement.query.count()}"
        )


if __name__ == "__main__":
    run()