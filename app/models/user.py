"""User model.

Internal system accounts (admin and staff). Passwords are stored only as
werkzeug password hashes — never plaintext.
"""

from datetime import datetime

from app.extensions import db
from app.utils.constants import UserRole


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30))
    role = db.Column(db.String(20), nullable=False, default=UserRole.STAFF)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    customer = db.relationship("Customer", back_populates="user", uselist=False)

    def __repr__(self) -> str:
        return f"<User {self.username!r} role={self.role!r}>"
