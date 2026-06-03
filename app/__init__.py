from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

db = SQLAlchemy()


def create_app(config=None):
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///laborsuche.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_ENSURE_ASCII"] = False

    if config:
        app.config.update(config)

    db.init_app(app)
    CORS(app)

    from .api import api_bp

    app.register_blueprint(api_bp)

    from .views import views_bp

    app.register_blueprint(views_bp)

    with app.app_context():
        db.create_all()
        _seed_database()

    return app


def _seed_database():
    """Seed the DB from JSON if empty."""
    from .models import Provider
    import json, os

    if Provider.query.count() > 0:
        return

    data_path = os.path.join(os.path.dirname(__file__), "data", "providers.json")
    with open(data_path, encoding="utf-8") as f:
        providers = json.load(f)

    for p in providers:
        obj = Provider.from_dict(p)
        db.session.add(obj)
    db.session.commit()
    print(f"[seed] {len(providers)} providers imported.")
