# CRMS — Car Rental Management System

A single, cohesive Flask web application serving both the customer website
and the admin panel from one deployable codebase.

## Stack

Python · Flask · Jinja2 · SQLAlchemy · Flask-Migrate · Bootstrap 5 ·
Bootstrap Icons · JavaScript (Fetch API) · PostgreSQL

## Architecture

- `app/` — Flask application package (application factory in `app/__init__.py`).
- `app/routes/` — Flask blueprints: public, customer, and `admin/` areas.
- `app/services/` — business logic.
- `app/repositories/` — thin data-access layer.
- `app/models/` — SQLAlchemy models.
- `app/templates/` — Jinja2 templates (base, layouts, components, pages).
- `app/static/` — CSS / JavaScript / images served by Flask.
- `tests/` — unit and integration tests (pytest).
- `scripts/seed_data.py` — database seeding (implemented in a later phase).
- Docs: `docs/` (architecture, database, api, deployment, business-rules).

## Getting started

1. Create and activate a virtual environment:

   ```text
   python -m venv .venv
   .venv\Scripts\activate        (Windows)
   source .venv/bin/activate     (macOS/Linux)
   ```

2. Install dependencies:

   ```text
   pip install -r requirements.txt
   ```

3. Configure environment:

   ```text
   copy .env.example .env   (Windows)
   cp .env.example .env     (macOS/Linux)
   ```

   Set `SECRET_KEY` and `DATABASE_URL` in `.env`.

4. Run locally:

   ```text
   python run.py
   ```

   Or set `FLASK_APP=run.py` and use `flask run`.

## Deployment

The application is a standard WSGI Flask app. Point the WSGI server at the
factory, e.g.:

```text
gunicorn "app:create_app()" --bind 0.0.0.0:8000
```

No frontend build step is required; templates and static assets are served
by Flask itself.

## Project status

Architecture phase complete. Feature implementation (models, auth,
bookings, payments, admin management) follows in later phases.