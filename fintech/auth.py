"""Session-based authentication helpers (signed-cookie sessions).

Users are stored in InfluxDB (measurement ``users``) and created manually by
the administrator from the /quan-tri page. Regular users log in with email +
password; the advanced analysis section and the trading journal require a
session.
"""
from __future__ import annotations

import hmac
from functools import wraps

from flask import jsonify, session

from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .config import ADMIN_PASSWORD

SESSION_UID = "uid"
SESSION_EMAIL = "email"
SESSION_NAME = "name"
SESSION_ROLE = "role"
SESSION_ADMIN = "admin_ok"


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return check_password_hash(password_hash or "", password or "")
    except (TypeError, ValueError):
        return False


def check_admin_password(password: str) -> bool:
    """Constant-time compare against the ADMIN_PASSWORD env var."""
    expected = ADMIN_PASSWORD or ""
    if not expected:
        return False
    return hmac.compare_digest(str(password or ""), expected)


def current_user() -> dict | None:
    """The logged-in user snapshot carried in the signed session cookie."""
    if not session.get(SESSION_UID):
        return None
    return {
        "id": session.get(SESSION_UID),
        "email": session.get(SESSION_EMAIL),
        "name": session.get(SESSION_NAME),
        "role": session.get(SESSION_ROLE) or "user",
    }


def is_authenticated() -> bool:
    return current_user() is not None


def is_admin() -> bool:
    """True for the ADMIN_PASSWORD session flag or a logged-in user with role ``admin``."""
    return bool(session.get(SESSION_ADMIN)) or session.get(SESSION_ROLE) == "admin"


def login_user(user: dict) -> None:
    session[SESSION_UID] = user.get("id")
    session[SESSION_EMAIL] = user.get("email")
    session[SESSION_NAME] = user.get("name")
    session[SESSION_ROLE] = user.get("role") or "user"


def logout_user() -> None:
    session.clear()


def login_admin() -> None:
    session[SESSION_ADMIN] = True


def logout_admin() -> None:
    session.pop(SESSION_ADMIN, None)


def login_required(view):
    """JSON APIs: respond 401 instead of redirecting (the UI shows a lock)."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            return jsonify({"error": "Cần đăng nhập để xem nội dung này", "auth_required": True}), 401
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            return jsonify({"error": "Cần quyền quản trị viên", "auth_required": True}), 401
        return view(*args, **kwargs)

    return wrapped


def authenticate(email: str, password: str) -> dict | None:
    user = db.user_by_email(email or "")
    if user is None or not user.get("active", 1):
        return None
    if not verify_password(user.get("password_hash"), password):
        return None
    return user
