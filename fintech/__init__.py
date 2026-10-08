"""FinViet Pro - Vietnamese stock investment analysis app (Flask)."""
import secrets

from flask import Flask

from . import db, routes
from .config import ON_VERCEL, SECRET_KEY, SITE_URL


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    # Signed-cookie sessions (login state). A stable SECRET_KEY env var is
    # required on Vercel; locally fall back to a random per-process key.
    app.secret_key = SECRET_KEY or secrets.token_hex(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if ON_VERCEL:
        app.config["SESSION_COOKIE_SECURE"] = True

    db.init_db()
    app.register_blueprint(routes.bp)

    @app.context_processor
    def inject_seo_context():
        # Site URL for canonical links, Open Graph and JSON-LD in templates.
        return {"site_url": SITE_URL}

    @app.after_request
    def add_cache_headers(response):
        if response.mimetype == "application/json":
            response.headers["Cache-Control"] = "no-store"
        return response

    return app
