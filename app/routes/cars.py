"""Cars browsing blueprint.

Public fleet browsing:
  /cars            list with category/branch/availability filters
  /cars/<id>       public car detail

Availability is delegated to ``availability_service`` which reuses the
existing booking-overlap rule.  Only public-safe information is exposed.
"""

from flask import Blueprint, abort, render_template, request

from app.repositories import branch_repository, car_repository, category_repository
from app.services import availability_service

blueprint = Blueprint("cars", __name__, url_prefix="/cars")


def _int_arg(name: str) -> int | None:
    """Return a positive integer query arg, or None when absent/invalid."""
    raw = (request.args.get(name) or "").strip()
    return int(raw) if raw.isdigit() else None


@blueprint.get("")
def index():
    """Browse the fleet, optionally filtered by category/branch/dates."""
    category_id = _int_arg("category")
    branch_id = _int_arg("branch")
    pickup_raw = request.args.get("pickup_datetime", "")
    return_raw = request.args.get("return_datetime", "")

    pickup, ret, errors = availability_service.parse_datetime_range(
        pickup_raw, return_raw
    )
    cars = availability_service.find_available_cars(
        category_id=category_id,
        branch_id=branch_id,
        pickup_datetime=pickup,
        return_datetime=ret,
    )

    return render_template(
        "public/cars.html",
        cars=cars,
        categories=category_repository.list_active(),
        branches=branch_repository.list_active(),
        category_filter=category_id,
        branch_filter=branch_id,
        pickup_raw=pickup_raw,
        return_raw=return_raw,
        errors=errors,
        availability_applied=bool(pickup and ret),
    )


@blueprint.get("/<int:car_id>")
def detail(car_id):
    """Show a public-safe view of one car, or 404 when unavailable."""
    car = car_repository.find_by_id(car_id)
    if car is None or not car.is_active:
        abort(404)

    related_cars = (
        availability_service.find_available_cars(category_id=car.category_id)
    )
    related_cars = [c for c in related_cars if c.id != car.id][:3]

    return render_template(
        "public/car_detail.html",
        car=car,
        related_cars=related_cars,
        availability_reason=availability_service.unavailable_reason(car),
    )