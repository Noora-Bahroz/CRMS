"""Public pages blueprint.

Customer-facing marketing and account pages:
  /            home
  /about       about
  /contact     contact (GET form, POST validated enquiry)
  /terms       terms & conditions
  /register    customer registration (User + Customer)
  /login       customer login page
  /logout      customer logout

Authentication reuses the existing single ``auth_service`` and the
existing ``customer_service`` (so registration creates the correct
User + Customer pair).  No second auth system is introduced.
"""

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.repositories import branch_repository, category_repository
from app.services import availability_service
from app.services.auth_service import (
    authenticate_user,
    get_current_user,
    login_user,
    logout_user,
)
from app.services.authorization_service import is_customer_account
from app.services.customer_service import create_customer
from app.utils import validators

blueprint = Blueprint("public", __name__, url_prefix="/")


def _safe_next(target):
    """Return a safe local redirect target, or None.

    Only same-site absolute paths are accepted so the ``next`` parameter
    cannot be turned into an open redirect.
    """
    target = (target or "").strip()
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target


@blueprint.get("/")
def home():
    """Landing page: hero search, featured cars, categories, branches."""
    available = availability_service.find_available_cars()
    categories = category_repository.list_active()

    makes = sorted({car.make for car in available})
    category_counts = {}
    for car in available:
        category_counts[car.category_id] = (
            category_counts.get(car.category_id, 0) + 1
        )
    min_rate = min(
        (category.daily_rate for category in categories), default=None
    )

    return render_template(
        "public/home.html",
        featured_cars=available[:8],
        categories=categories,
        branches=branch_repository.list_active(),
        makes=makes,
        category_counts=category_counts,
        min_rate=min_rate,
    )


@blueprint.get("/about")
def about():
    """About the CRMS rental business."""
    return render_template(
        "public/about.html",
        branches=branch_repository.list_active(),
    )


@blueprint.route("/contact", methods=["GET", "POST"])
def contact():
    """Contact page with a validation-only enquiry form (no email service)."""
    errors = []
    form = {}

    if request.method == "POST":
        form = request.form

        name, error = validators.required_text(form.get("name"), "Name")
        if error:
            errors.append(error)
        email, error = validators.parse_email(form.get("email"), "Email")
        if error:
            errors.append(error)
        message, error = validators.required_text(form.get("message"), "Message")
        if error:
            errors.append(error)

        if not errors:
            flash(
                "Thank you for contacting CRMS. Our team will get back to "
                "you shortly.",
                "success",
            )
            return redirect(url_for("public.contact"))

    return render_template("public/contact.html", errors=errors, form=form)


@blueprint.get("/terms")
def terms():
    """Rental terms & conditions (generic demo content)."""
    return render_template("public/terms.html")


@blueprint.route("/register", methods=["GET", "POST"])
def register():
    """Customer registration creating the linked User + Customer pair."""
    next_url = _safe_next(request.values.get("next"))
    if get_current_user() is not None:
        return redirect(next_url or url_for("public.home"))

    errors = []
    form = {}

    if request.method == "POST":
        form = request.form
        password = form.get("password") or ""
        if password != (form.get("confirm_password") or ""):
            errors.append("Passwords do not match.")
        if not errors:
            customer, errors = create_customer(form)
            if not errors:
                login_user(customer.user)
                flash(
                    f"Welcome to CRMS, {customer.user.first_name}! "
                    "Your account has been created.",
                    "success",
                )
                return redirect(next_url or url_for("public.home"))

    return render_template(
        "auth/register.html", errors=errors, form=form, next_url=next_url
    )


@blueprint.route("/login", methods=["GET", "POST"])
def login():
    """Customer login using the shared authentication service.

    Customer accounts continue to the public site; internal admin/staff
    accounts are sent to the admin dashboard rather than being shown the
    customer experience.
    """
    next_url = _safe_next(request.values.get("next"))
    current = get_current_user()
    if current is not None:
        if is_customer_account(current):
            return redirect(next_url or url_for("public.home"))
        return redirect(url_for("admin_dashboard.dashboard"))

    error = None
    email = ""

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        if not email or not password:
            error = "Email and password are required."
        else:
            user, message, _status = authenticate_user(email, password)
            if user is None:
                error = message
            else:
                login_user(user)
                flash(f"Welcome back, {user.first_name}!", "success")
                if is_customer_account(user):
                    return redirect(next_url or url_for("public.home"))
                return redirect(url_for("admin_dashboard.dashboard"))

    return render_template(
        "auth/login.html", error=error, email=email, next_url=next_url
    )


@blueprint.post("/logout")
def logout():
    """End the customer session."""
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("public.home"))