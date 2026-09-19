"""Admin maintenance management blueprint.

CRUD routes for fleet maintenance records, all guarded by the
admin_required page guard.  Records link to real cars chosen from the
database and follow the existing scheduled / in_progress / completed
statuses.  Closing is done by marking a record completed; deletion is
blocked while linked expenses depend on the record.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import maintenance_repository
from app.repositories.car_repository import list_active as list_cars
from app.services.maintenance_service import (
    MaintenanceError,
    complete_maintenance,
    create_maintenance,
    delete_maintenance,
    update_maintenance,
)
from app.utils.constants import MaintenanceStatus, MaintenanceType
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_maintenance", __name__, url_prefix="/admin/maintenance")


def _form_from_maintenance(maintenance):
    """Render a maintenance record's current values as a form dict."""
    return {
        "car_id": maintenance.car_id,
        "maintenance_type": maintenance.maintenance_type,
        "status": maintenance.status,
        "description": maintenance.description,
        "cost": maintenance.cost,
        "scheduled_date": maintenance.scheduled_date.strftime("%Y-%m-%d"),
        "completed_date": maintenance.completed_date.strftime("%Y-%m-%d")
        if maintenance.completed_date
        else "",
        "service_provider": maintenance.service_provider or "",
        "notes": maintenance.notes or "",
    }


def _form_context(maintenance=None, form=None, errors=None):
    """Common template variables for the maintenance forms."""
    return {
        "cars": list_cars(),
        "types": MaintenanceType.ALL,
        "statuses": MaintenanceStatus.ALL,
        "maintenance": maintenance,
        "form": form or {},
        "errors": errors or [],
    }


@blueprint.get("")
@admin_required
def index():
    """List maintenance records, optionally filtered by ``q`` + ``status``."""
    term = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip() or None
    if term or status:
        records = maintenance_repository.search(term, status)
    else:
        records = maintenance_repository.list_all()
    return render_template(
        "admin/maintenance/index.html",
        records=records,
        search_term=term,
        status_filter=status or "",
        statuses=MaintenanceStatus.ALL,
    )


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new maintenance record."""
    if request.method == "POST":
        record, errors = create_maintenance(request.form)
        if not errors:
            flash("Maintenance record created successfully.", "success")
            return redirect(
                url_for("admin_maintenance.detail", maintenance_id=record.id)
            )
        return render_template(
            "admin/maintenance/form.html",
            **_form_context(form=request.form, errors=errors),
        )

    return render_template("admin/maintenance/form.html", **_form_context())


@blueprint.get("/<int:maintenance_id>")
@admin_required
def detail(maintenance_id):
    """Show a maintenance record's details and its linked car."""
    record = maintenance_repository.find_by_id(maintenance_id)
    if record is None:
        abort(404)
    return render_template("admin/maintenance/detail.html", record=record)


@blueprint.route("/<int:maintenance_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(maintenance_id):
    """Show the edit form, or persist changes to a maintenance record."""
    record = maintenance_repository.find_by_id(maintenance_id)
    if record is None:
        abort(404)

    if request.method == "POST":
        record, errors = update_maintenance(record, request.form)
        if not errors:
            flash(f"Maintenance #{record.id} updated successfully.", "success")
            return redirect(
                url_for("admin_maintenance.detail", maintenance_id=record.id)
            )
        return render_template(
            "admin/maintenance/form.html",
            **_form_context(maintenance=record, form=request.form, errors=errors),
        )

    return render_template(
        "admin/maintenance/form.html",
        **_form_context(
            maintenance=record, form=_form_from_maintenance(record)
        ),
    )


@blueprint.post("/<int:maintenance_id>/complete")
@admin_required
def complete(maintenance_id):
    """Close a maintenance record by marking it completed."""
    record = maintenance_repository.find_by_id(maintenance_id)
    if record is None:
        abort(404)

    try:
        complete_maintenance(record)
    except MaintenanceError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Maintenance #{record.id} completed.", "success")
    return redirect(
        url_for("admin_maintenance.detail", maintenance_id=maintenance_id)
    )


@blueprint.post("/<int:maintenance_id>/delete")
@admin_required
def delete(maintenance_id):
    """Safely delete a maintenance record (blocked while expenses link it)."""
    record = maintenance_repository.find_by_id(maintenance_id)
    if record is None:
        abort(404)

    try:
        delete_maintenance(record)
    except MaintenanceError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Maintenance #{maintenance_id} deleted.", "success")
    return redirect(url_for("admin_maintenance.index"))