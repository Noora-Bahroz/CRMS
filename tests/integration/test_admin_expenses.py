"""Integration tests: admin expense management."""

import pytest

from app.extensions import db
from app.models import Branch, Car, Expense, Maintenance
from app.utils.constants import ExpenseCategory

from scripts.seed_data import seed


@pytest.fixture()
def expenses_db(app):
    """Fresh schema with the seeded reference records."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed(app=app)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _login_admin(client):
    assert _login(client, "admin@example.com", "Admin@123").status_code == 200


def _expense_form(client, **overrides):
    """A valid expense payload linked to the Head Office branch."""
    with client.application.app_context():
        branch_id = Branch.query.filter_by(name="Head Office").one().id
    data = {
        "category": ExpenseCategory.FUEL,
        "amount": "12000.00",
        "description": "Fuel for Karachi fleet.",
        "receipt_url": "",
        "recorded_by": "admin",
        "expense_date": "2026-12-01",
    }
    data.update(overrides)
    if "branch_id" not in overrides and "car_id" not in overrides:
        data["branch_id"] = branch_id
    elif "branch_id" in overrides and not overrides["branch_id"]:
        data["branch_id"] = ""
    return data


def test_unauthenticated_expenses_redirects_to_login(expenses_db, client):
    resp = client.get("/admin/expenses")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/login"


def test_customer_cannot_access_expenses(expenses_db, client):
    assert _login(client, "customer@example.com", "Customer@123").status_code == 200
    resp = client.get("/admin/expenses")
    assert resp.status_code == 403


def test_admin_can_open_expense_list(expenses_db, client):
    _login_admin(client)
    resp = client.get("/admin/expenses")
    assert resp.status_code == 200
    assert b"Expenses" in resp.data
    assert b"FUEL" in resp.data
    assert b"Monthly fuel bulk purchase" in resp.data
    assert b"35000.00" in resp.data
    assert b"Head Office" in resp.data


def test_admin_can_open_expense_detail(expenses_db, client):
    _login_admin(client)
    with expenses_db.app_context():
        expense = Expense.query.order_by(Expense.id.asc()).first()
    resp = client.get(f"/admin/expenses/{expense.id}")
    assert resp.status_code == 200
    assert b"Expense Details" in resp.data
    assert b"Monthly fuel bulk purchase" in resp.data
    assert b"Head Office" in resp.data


def test_admin_can_create_expense(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new", data=_expense_form(client), follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"recorded successfully" in resp.data
    with expenses_db.app_context():
        expense = Expense.query.order_by(Expense.id.desc()).first()
        assert expense.description == "Fuel for Karachi fleet."
        assert expense.category == ExpenseCategory.FUEL
        assert str(expense.amount) == "12000.00"
        assert expense.branch.name == "Head Office"
        assert expense.car is None
        assert expense.maintenance is None


def test_admin_can_edit_expense(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new", data=_expense_form(client), follow_redirects=True
    )
    assert resp.status_code == 200
    with expenses_db.app_context():
        expense = Expense.query.order_by(Expense.id.desc()).first()
        expense_id = expense.id
        branch_id = expense.branch_id
    resp = client.post(
        f"/admin/expenses/{expense_id}/edit",
        data={
            "category": ExpenseCategory.INSURANCE,
            "branch_id": branch_id,
            "car_id": "",
            "maintenance_id": "",
            "amount": "25000.00",
            "description": "Fleet insurance renewal.",
            "receipt_url": "",
            "recorded_by": "admin",
            "expense_date": "2026-12-05",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"updated successfully" in resp.data
    with expenses_db.app_context():
        expense = db.session.get(Expense, expense_id)
        assert expense.category == ExpenseCategory.INSURANCE
        assert str(expense.amount) == "25000.00"
        assert expense.description == "Fleet insurance renewal."


def test_expense_required_fields_validated(expenses_db, client):
    _login_admin(client)
    resp = client.post("/admin/expenses/new", data={})
    assert resp.status_code == 200
    for message in (
        b"Select a valid expense category",
        b"Amount is required",
        b"Description is required",
        b"Expense date is required",
        b"Select a branch, car, or maintenance",
    ):
        assert message in resp.data


def test_expense_invalid_branch_rejected(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new", data=_expense_form(client, branch_id="99999")
    )
    assert resp.status_code == 200
    assert b"Select a valid branch." in resp.data
    assert Expense.query.count() == 4


def test_expense_invalid_car_rejected(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new",
        data=_expense_form(client, branch_id="", car_id="99999"),
    )
    assert resp.status_code == 200
    assert b"Select a valid car." in resp.data
    assert Expense.query.count() == 4


def test_expense_invalid_maintenance_rejected(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new",
        data=_expense_form(client, branch_id="", maintenance_id="99999"),
    )
    assert resp.status_code == 200
    assert b"Select a valid maintenance." in resp.data
    assert Expense.query.count() == 4


def test_expense_invalid_amount_rejected(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new", data=_expense_form(client, amount="abc")
    )
    assert resp.status_code == 200
    assert b"Amount must be a valid number." in resp.data
    resp = client.post(
        "/admin/expenses/new", data=_expense_form(client, amount="0")
    )
    assert b"Amount must be at least 0.01" in resp.data
    assert Expense.query.count() == 4


def test_expense_invalid_date_rejected(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new", data=_expense_form(client, expense_date="not-a-date")
    )
    assert resp.status_code == 200
    assert b"Expense date must be a valid date" in resp.data
    assert Expense.query.count() == 4


def test_expense_links_to_car_and_maintenance(expenses_db, client):
    _login_admin(client)
    with expenses_db.app_context():
        car_id = Car.query.filter_by(license_plate="KHI-1001").one().id
        maintenance_id = Maintenance.query.order_by(Maintenance.id.asc()).first().id
    resp = client.post(
        "/admin/expenses/new",
        data=_expense_form(
            client,
            branch_id="",
            category=ExpenseCategory.MAINTENANCE,
            car_id=str(car_id),
            maintenance_id=str(maintenance_id),
            amount="4500.00",
            description="Part replacement for Corolla.",
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"recorded successfully" in resp.data
    with expenses_db.app_context():
        expense = Expense.query.order_by(Expense.id.desc()).first()
        assert expense.car.license_plate == "KHI-1001"
        assert expense.maintenance.id == maintenance_id
        assert expense.branch is None
        resp = client.get(f"/admin/expenses/{expense.id}")
    assert b"KHI-1001" in resp.data
    assert b"Part replacement" in resp.data


def test_expense_without_context_rejected(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new",
        data=_expense_form(
            client, branch_id="", amount="1000.00",
            description="Misc office cost.",
        ),
    )
    assert resp.status_code == 200
    assert b"Select a branch, car, or maintenance" in resp.data
    assert Expense.query.count() == 4


def test_admin_can_delete_expense(expenses_db, client):
    _login_admin(client)
    resp = client.post(
        "/admin/expenses/new", data=_expense_form(client), follow_redirects=True
    )
    assert resp.status_code == 200
    with expenses_db.app_context():
        count_before = Expense.query.count()
        expense_id = Expense.query.order_by(Expense.id.desc()).first().id
    resp = client.post(
        f"/admin/expenses/{expense_id}/delete", follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"deleted" in resp.data
    with expenses_db.app_context():
        assert Expense.query.count() == count_before - 1


def test_expense_search_filters_results(expenses_db, client):
    _login_admin(client)
    resp = client.get("/admin/expenses?q=fuel")
    assert b"FUEL" in resp.data
    resp = client.get("/admin/expenses?q=zzz-nonexistent")
    assert b"No expenses match" in resp.data
    resp = client.get("/admin/expenses?category=insurance")
    assert b"Annual fleet insurance premium" in resp.data
    resp = client.get("/admin/expenses?category=maintenance")
    assert b"Routine service charges" in resp.data