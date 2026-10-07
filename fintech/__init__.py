"""FinViet Pro - Vietnamese stock investment analysis app (Flask)."""
from flask import Flask

from . import db, routes
from .config import SITE_URL


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

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
