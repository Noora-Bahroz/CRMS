"""Car photo lookup for the public fleet UI.

Pure design helper: maps each fleet car (by make + model) to its matching
photograph in ``app/static/img/cars/``.  Cars without a photo fall back to
the existing ``car-placeholder.svg``.  No database changes are involved.
"""

import re

from flask import url_for

# Normalized ``make model`` -> static photograph filename (hyphen slug).
_CAR_PHOTOS = {
    "toyota-corolla": "toyota-corolla.jpg",
    "honda-civic": "honda-civic.jpg",
    "toyota-fortuner": "toyota-fortuner.jpg",
    "kia-sportage": "kia-sportage.jpg",
    "hyundai-tucson": "hyundai-tucson.jpg",
    "suzuki-wagon-r": "suzuki-wagon-r.jpg",
}


def _slug(value) -> str:
    """Lowercase a value and collapse spaces/other separators to hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def car_image_url(car) -> str:
    """Return the best available photograph URL for *car*.

    An admin-provided ``image_url`` always wins, then the name-based photo
    for the car's make + model, then the placeholder.
    """
    if car.image_url:
        return car.image_url
    key = _slug(f"{car.make} {car.model}")
    filename = _CAR_PHOTOS.get(key)
    if filename is not None:
        return url_for("static", filename=f"img/cars/{filename}")
    return url_for("static", filename="img/car-placeholder.svg")