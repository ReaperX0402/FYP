from __future__ import annotations

from pathlib import Path
from flask import Flask, redirect, url_for
from dotenv import load_dotenv

from src.db.session import build_engine, init_session_factory
from src.web.routes.decisions import bp as decisions_bp
from src.web.routes.ingestion import bp as ingestion_bp
from src.web.routes.auth import bp as auth_bp


def create_app() -> Flask:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env", override=True)

    templates_dir = Path(__file__).resolve().parent / "web" / "templates"
    app = Flask(__name__, template_folder=str(templates_dir))
    app.secret_key = "dev" 

    engine = build_engine(echo=False)
    init_session_factory(engine)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(ingestion_bp)
    app.register_blueprint(decisions_bp)

    @app.get("/")
    def index():
        return redirect(url_for("auth.login"))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
