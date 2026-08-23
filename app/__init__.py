import os

from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    os.makedirs(app.instance_path, exist_ok=True)
    default_db_path = os.path.join(app.instance_path, "app.db")

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", f"sqlite:///{default_db_path}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    CSRFProtect(app)

    from app import models  # noqa: F401
    from app.admin import init_admin
    from app.auth import bp as auth_bp
    from app.cli import register_cli
    from app.routes import bp as routes_bp

    app.register_blueprint(routes_bp)
    app.register_blueprint(auth_bp)
    init_admin(app)
    register_cli(app)

    return app
