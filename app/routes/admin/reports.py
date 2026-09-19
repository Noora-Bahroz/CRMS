"""Admin reports blueprint.

Read-only aggregated views over existing records: summary cards, booking /
revenue report, expense report, fleet summary, and branch summary.  All
figures come from the reports service, which follows the project's existing
revenue rule (sum of COMPLETED payments) and real relationships.
"""

from flask import Blueprint, render_template, request

from app.repositories import branch_repository
from app.services import reports_service
from app.utils.constants import BookingStatus, ExpenseCategory
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_reports", __name__, url_prefix="/admin/reports")


def _query_param(key: str, allowed: tuple) -> str | None:
    """Return a clean option value, or None when blank/invalid."""
    value = (request.args.get(key) or "").strip()
    return value if value in allowed else None


@blueprint.get("")
@admin_required
def index():
    """Render the reports page honouring the shared filter range."""
    from_raw = request.args.get("from", "")
    to_raw = request.args.get("to", "")
    from_date, to_date, date_error = reports_service.parse_date_range(from_raw, to_raw)

    status = _query_param("status", BookingStatus.ALL)
    category = _query_param("category", ExpenseCategory.ALL)

    branch_value = (request.args.get("branch") or "").strip()
    branch_id = int(branch_value) if branch_value.isdigit() else None

    return render_template(
        "admin/reports.html",
        stats=reports_service.summary_stats(from_date, to_date),
        booking_report=reports_service.booking_report(
            from_date, to_date, status, branch_id
        ),
        expense_report=reports_service.expense_report(
            from_date, to_date, category, branch_id
        ),
        fleet_report=reports_service.fleet_report(from_date, to_date),
        branch_summary=reports_service.branch_summary(from_date, to_date),
        chart=reports_service.chart_data(from_date, to_date, status, branch_id),
        branches=branch_repository.list_active(),
        from_raw=from_raw,
        to_raw=to_raw,
        date_error=date_error,
        status_filter=status or "",
        category_filter=category or "",
        branch_filter=branch_value,
        booking_statuses=BookingStatus.ALL,
        expense_categories=ExpenseCategory.ALL,
    )