import os

from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def normalize_database_url(url):
    """Point Postgres URLs at psycopg 3.

    SQLAlchemy 2.x maps a bare ``postgresql://`` to psycopg2, which we don't
    install - and that bare form is exactly what DigitalOcean hands out. The
    older ``postgres://`` scheme shows up in other hosts' env vars too.
    Anything else (sqlite://, an explicit +driver) is left alone.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    # No SQLite fallback on purpose. A default would let a `flask` command
    # run against a stray local file and look like it worked - which is
    # exactly how a migration once landed on instance/app.db instead of
    # Postgres. Missing configuration should fail where you can see it.
    database_url = os.environ.get("DATABASE_URL")
    if not database_url and not (test_config or {}).get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError(
            "DATABASE_URL is not set. Start Postgres with `docker compose up -d db` "
            "and run commands through the app container "
            "(`docker compose exec web flask --app wsgi ...`), or export "
            "DATABASE_URL yourself."
        )

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        SQLALCHEMY_DATABASE_URI=(
            normalize_database_url(database_url) if database_url else None
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # Managed Postgres drops idle connections; without pre-ping the first
        # request after a quiet spell dies on a stale one.
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},
        # Outgoing mail (password resets). With no MAIL_SERVER, messages are
        # written to the log instead - see app/email.py.
        MAIL_SERVER=os.environ.get("MAIL_SERVER"),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", 587)),
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
        MAIL_USE_SSL=os.environ.get("MAIL_USE_SSL", "").lower()
        in ("1", "true", "yes"),
        MAIL_DEFAULT_SENDER=os.environ.get("MAIL_DEFAULT_SENDER"),
    )

    if test_config is not None:
        app.config.update(test_config)

    # App Platform terminates TLS at its proxy; trust its forwarded scheme and
    # host so emailed reset links come out as https://<real host>.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    CSRFProtect(app)

    from app import color
    from app import models  # noqa: F401
    from app import pitch
    from app.admin import init_admin
    from app.auth import bp as auth_bp
    from app.cli import register_cli
    from app.routes import bp as routes_bp

    app.register_blueprint(routes_bp)
    app.register_blueprint(auth_bp)
    init_admin(app)
    register_cli(app)

    app.jinja_env.globals["flat_name"] = pitch.flat_name
    app.jinja_env.globals["mallet_colors"] = color.MALLET_COLORS

    return app
