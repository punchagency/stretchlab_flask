from flask import Flask
from .utils.config import Config
from .stretchnote.routes import init_routes
from sqlalchemy import create_engine
from supabase import create_client, Client
import os
from .stretchnote.auth_routes import init_stretchnote_auth_routes
from .admin.auth_routes import init_admin_auth_routes
from .admin.admin_routes import init_admin_routes
from .admin.settings import init_settings_routes
import logging
from logging.handlers import RotatingFileHandler
from flask_mail import Mail
from .utils.logging import init_logging
from .payment.webhook import init_payment_webhook_routes
from .admin.payment_routes import init_payment_routes
from .notification import init_notification
from .admin.dashboard_routes import init_dashboard_routes
from .admin.analytics_routes import init_analytics_routes


def create_app():

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(
        MAIL_SERVER="smtp.gmail.com",
        MAIL_PORT=465,
        MAIL_USE_SSL=True,
        MAIL_USE_TLS=False,
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.environ.get("MAIL_USERNAME"),
    )

    try:
        app.config["SQLALCHEMY_ENGINE"] = create_engine(os.environ.get("DATABASE_URL"))
    except Exception as e:
        raise RuntimeError(f"Database connection failed: {str(e)}")

    try:
        supabase: Client = create_client(
            app.config["SUPABASE_URL"], app.config["SUPABASE_KEY"]
        )
        app.config["SUPABASE"] = supabase
    except Exception as e:
        raise RuntimeError(f"Supabase client initialization failed: {str(e)}")

    if not app.debug:
        handler = RotatingFileHandler("flask_app.log", maxBytes=10000, backupCount=1)
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
    mail = Mail(app)

    @app.route("/")
    def root():
        return {"status": "health check"}, 200

    init_routes(app)
    init_stretchnote_auth_routes(app)
    init_admin_auth_routes(app)
    init_admin_routes(app)
    init_logging()
    init_payment_routes(app)
    init_payment_webhook_routes(app)
    init_settings_routes(app)
    init_notification(app)
    init_dashboard_routes(app)
    init_analytics_routes(app)
    return app
