from __future__ import annotations

from flask import Flask

from src.db.session import build_engine, init_session_factory
from src.web.routes.decisions import bp as decisions_bp
from dotenv import load_dotenv


def create_app() -> Flask:
    load_dotenv()
    app = Flask(__name__)
    app.secret_key = "dev"  
    # ---- Database init ----
    engine = build_engine(echo=False)
    init_session_factory(engine)

    # ---- Register blueprints ----
    app.register_blueprint(decisions_bp)
    print(app.url_map)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
