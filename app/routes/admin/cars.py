"""Admin fleet management blueprint.

CRUD routes for cars, all guarded by the admin_required page guard. Uses
flash messages for feedback and follows the service layer for validation
and safe deactivation.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.repositories import branch_repository, car_repository, category_repository
from app.services.car_service import (
    CarError,
    create_car,
    deactivate_car,
    update_car,
)
from app.utils.constants import CarStatus
from app.utils.decorators import admin_required

blueprint = Blueprint("admin_cars", __name__, url_prefix="/admin/cars")


def _form_from_car(car):
    """Render a car's current values as a form dict."""
    return {
        "make": car.make,
        "model": car.model,
        "year": car.year,
        "color": car.color or "",
        "license_plate": car.license_plate,
        "vin": car.vin or "",
        "mileage": car.mileage,
        "fuel_level": car.fuel_level,
        "category_id": car.category_id,
        "branch_id": car.branch_id,
        "status": car.status,
        "image_url": car.image_url or "",
        "notes": car.notes or "",
        "is_active": "1" if car.is_active else "",
    }


@blueprint.get("")
@admin_required
def index():
    """List all cars."""
    cars = car_repository.list_all()
    return render_template("admin/cars/index.html", cars=cars)


@blueprint.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    """Show the create form, or persist a new car."""
    if request.method == "POST":
        car, errors = create_car(request.form)
        if not errors:
            flash(
                f"Car {car.make} {car.model} ({car.license_plate}) created.",
                "success",
            )
            return redirect(url_for("admin_cars.index"))
        return render_template(
            "admin/cars/form.html",
            car=None, form=request.form, errors=errors,
            categories=category_repository.list_active(),
            branches=branch_repository.list_active(),
            statuses=CarStatus.ALL,
        )

    return render_template(
        "admin/cars/form.html",
        car=None, form={}, errors=[],
        categories=category_repository.list_active(),
        branches=branch_repository.list_active(),
        statuses=CarStatus.ALL,
    )


@blueprint.route("/<int:car_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(car_id):
    """Show the edit form, or persist changes to a car."""
    car = car_repository.find_by_id(car_id)
    if car is None:
        abort(404)

    if request.method == "POST":
        car, errors = update_car(car, request.form)
        if not errors:
            flash(f"Car {car.make} {car.model} updated successfully.", "success")
            return redirect(url_for("admin_cars.index"))
        return render_template(
            "admin/cars/form.html",
            car=car, form=request.form, errors=errors,
            categories=category_repository.list_active(),
            branches=branch_repository.list_active(),
            statuses=CarStatus.ALL,
        )

    return render_template(
        "admin/cars/form.html",
        car=car, form=_form_from_car(car), errors=[],
        categories=category_repository.list_active(),
        branches=branch_repository.list_active(),
        statuses=CarStatus.ALL,
    )


@blueprint.post("/<int:car_id>/delete")
@admin_required
def delete(car_id):
    """Safely deactivate a car."""
    car = car_repository.find_by_id(car_id)
    if car is None:
        abort(404)

    try:
        deactivate_car(car)
    except CarError as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Car {car.make} {car.model} ({car.license_plate}) deleted.", "success")
    return redirect(url_for("admin_cars.index"))