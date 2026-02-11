# src/app.py
from __future__ import annotations

from flask import Flask

from db.session import build_engine, init_session_factory
from web.routes.decisions import bp as decisions_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "dev"  # move to env later

    # ---- Database init ----
    engine = build_engine(echo=False)
    init_session_factory(engine)

    # Optional health check on startup
    # from db.session import db_health_check
    # db_health_check(engine)

    # ---- Register blueprints ----
    app.register_blueprint(decisions_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
