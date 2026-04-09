from __future__ import annotations

from pathlib import Path
from flask import Flask, redirect, url_for

from src.config import Config
from src.startup import ensure_directories
from src.db.session import build_engine, init_session_factory
from src.web.routes.decisions import bp as decisions_bp
from src.web.routes.ingestion import bp as ingestion_bp
from src.web.routes.auth import bp as auth_bp
from src.web.routes.exports import bp as exports_bp
from src.web.routes.sessions import bp as sessions_bp


def create_app() -> Flask:
    templates_dir = Path(__file__).resolve().parent / "web" / "templates"
    app = Flask(__name__, template_folder=str(templates_dir))

    # Load app config
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    # Ensure local directories exist
    ensure_directories()

    # Init DB engine/session factory
    engine = build_engine(echo=False)
    init_session_factory(engine)

    # Init DB tables
    from src.db.init_db import init_db
    init_db(engine)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(ingestion_bp)
    app.register_blueprint(decisions_bp)
    app.register_blueprint(exports_bp)
    app.register_blueprint(sessions_bp)

    @app.after_request
    def add_no_cache_headers(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/")
    def index():
        return redirect(url_for("auth.login"))

    return app