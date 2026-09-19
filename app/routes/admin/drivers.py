"""Admin driver management blueprint.

CRUD routes for drivers, all guarded by the admin_required page guard.
Uses flash messages for feedback and follows the service layer for
validation and safe deactivation.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import driver_repository
from app.services.driver_service import (
    DriverError,
    create_driver,
    deactivate_driver,
    update_driver,
)
from app.utils.constants import DriverStatus
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_drivers", __name__, url_prefix="/admin/drivers")


def _form_from_driver(driver):
    """Render a driver's current values as a form dict."""
    return {
        "first_name": driver.first_name,
        "last_name": driver.last_name,
        "phone": driver.phone,
        "email": driver.email or "",
        "license_number": driver.license_number,
        "license_expiry": driver.license_expiry.strftime("%Y-%m-%d"),
        "status": driver.status,
        "daily_rate": driver.daily_rate,
        "notes": driver.notes or "",
    }


@blueprint.get("")
@admin_required
def index():
    """List all drivers."""
    drivers = driver_repository.list_all()
    return render_template("admin/drivers/index.html", drivers=drivers)


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new driver."""
    if request.method == "POST":
        driver, errors = create_driver(request.form)
        if not errors:
            flash(
                f"Driver {driver.first_name} {driver.last_name} created successfully.",
                "success",
            )
            return redirect(url_for("admin_drivers.index"))
        return render_template(
            "admin/drivers/form.html",
            driver=None, form=request.form, errors=errors,
            statuses=DriverStatus.ALL,
        )

    return render_template(
        "admin/drivers/form.html",
        driver=None, form={}, errors=[], statuses=DriverStatus.ALL,
    )


@blueprint.route("/<int:driver_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(driver_id):
    """Show the edit form, or persist changes to a driver."""
    driver = driver_repository.find_by_id(driver_id)
    if driver is None:
        abort(404)

    if request.method == "POST":
        driver, errors = update_driver(driver, request.form)
        if not errors:
            flash(
                f"Driver {driver.first_name} {driver.last_name} updated successfully.",
                "success",
            )
            return redirect(url_for("admin_drivers.index"))
        return render_template(
            "admin/drivers/form.html",
            driver=driver, form=request.form, errors=errors,
            statuses=DriverStatus.ALL,
        )

    return render_template(
        "admin/drivers/form.html",
        driver=driver, form=_form_from_driver(driver), errors=[],
        statuses=DriverStatus.ALL,
    )


@blueprint.post("/<int:driver_id>/delete")
@admin_required
def delete(driver_id):
    """Safely deactivate a driver."""
    driver = driver_repository.find_by_id(driver_id)
    if driver is None:
        abort(404)

    try:
        deactivate_driver(driver)
    except DriverError as exc:
        flash(str(exc), "danger")
    else:
        flash(
            f"Driver {driver.first_name} {driver.last_name} deleted.", "success"
        )
    return redirect(url_for("admin_drivers.index"))