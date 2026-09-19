"""HTTP error handlers.

Renders styled error pages instead of Flask's plain defaults.  The page
is chosen from the request path so a public visitor never sees an
admin-branded error page (with Dashboard / Admin Login links), while the
admin panel keeps its own consistent layout.
"""

from flask import render_template, request


def _is_admin_area() -> bool:
    """Return True when the current request targets the admin panel."""
    return request.path.startswith("/admin")


def register_error_handlers(app) -> None:
    """Attach centralized HTTP error handlers to the application."""

    @app.errorhandler(403)
    def forbidden(error):
        """Render a styled "forbidden" page."""
        if _is_admin_area():
            return (
                render_template(
                    "admin/error.html",
                    code=403,
                    message="You do not have permission to access this page.",
                ),
                403,
            )
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        """Render a styled "not found" page."""
        if _is_admin_area():
            return (
                render_template(
                    "admin/error.html",
                    code=404,
                    message="The page you were looking for could not be found.",
                ),
                404,
            )
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        """Render a friendly page instead of a bare internal error."""
        return render_template("errors/500.html"), 500
