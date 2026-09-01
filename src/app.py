"""Flask application factory for Secure Bank Manager."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, abort, g, redirect, render_template, request, session, url_for

from src.config import Config


def _validate_security_config(app: Flask) -> None:
    if app.config.get("TESTING"):
        return
    errors = []
    known_placeholders = {
        "change-me", "changeme", "dev-secret-key-change-in-production",
        "change-this-hmac-key", "replace-with-a-random-secret",
    }
    for name in ("SECRET_KEY", "HMAC_SECRET_KEY"):
        value = app.config.get(name, "")
        if (not value or len(value) < 32 or value.lower() in known_placeholders
                or len(set(value)) < 8):
            errors.append(f"{name} must be an explicit random value of at least 32 characters")
    if app.config.get("SECRET_KEY") == app.config.get("HMAC_SECRET_KEY"):
        errors.append("SECRET_KEY and HMAC_SECRET_KEY must be different")
    if errors:
        raise RuntimeError("Invalid security configuration: " + "; ".join(errors))


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    _validate_security_config(app)

    from src import db
    database_path = app.config.get("DATABASE_PATH", Config.DATABASE_PATH)
    if database_path != db.DATABASE_PATH:
        db.configure_database(database_path)

    from src.accounts import accounts_bp
    from src.audit_logger import audit_bp
    from src.auth import auth_bp, login_required
    from src.checker import checker_bp
    from src.clients import clients_bp
    from src.operations import operations_bp
    from src.policies import policies_bp
    from src.users import users_bp

    for blueprint in (auth_bp, clients_bp, accounts_bp, operations_bp, audit_bp, users_bp, policies_bp, checker_bp):
        app.register_blueprint(blueprint)

    try:
        from flask_wtf import CSRFProtect
        csrf = CSRFProtect()
        csrf.init_app(app)
        app.extensions["csrf"] = csrf
    except ImportError as exc:  # Flask-WTF is a required dependency.
        raise RuntimeError("Flask-WTF is required") from exc

    limiter = None
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(key_func=get_remote_address, storage_uri=app.config["RATE_LIMIT_STORAGE_URI"])
        limiter.init_app(app)
        if app.config.get("TESTING"):
            limiter.enabled = app.config.get("RATELIMIT_ENABLED", False)
        endpoint_limits = {
            "auth.login": app.config["LOGIN_RATE_LIMIT"],
            "auth.mfa_verify": app.config["MFA_RATE_LIMIT"],
            "auth.mfa_recovery": app.config["RECOVERY_RATE_LIMIT"],
        }
        for endpoint, limit in endpoint_limits.items():
            if endpoint in app.view_functions:
                app.view_functions[endpoint] = limiter.limit(limit)(app.view_functions[endpoint])
    except ImportError as exc:
        raise RuntimeError("Flask-Limiter is required") from exc
    app.extensions["limiter"] = limiter

    @app.before_request
    def maintenance_panic_guard():
        """Enforce panic mode independently of whichever CSRF extension is active."""
        from src.policy import get_policy
        if not get_policy("maintenance.panic_mode", False):
            return None
        allowed = {"health", "panic", "auth.login", "static"}
        if request.endpoint in allowed or (request.endpoint or "").startswith("static"):
            return None
        user = getattr(g, "user", None)
        if user is not None and user.role.value in {"admin", "superadmin"}:
            return None
        if request.method == "GET":
            return redirect(url_for("panic"))
        abort(503, description=str(get_policy("maintenance.panic_message")))

    @app.teardown_appcontext
    def shutdown_session(_exception=None):
        db.Session.remove()

    @app.template_filter("decode_json")
    def decode_json_filter(value):
        if not value:
            return "-"
        try:
            return json.dumps(json.loads(value), ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return value

    def local_timezone():
        try:
            return ZoneInfo(app.config["TIMEZONE"])
        except ZoneInfoNotFoundError:
            # Windows installations may not ship the IANA database. The
            # dependency list includes tzdata, but retain a safe Pakistan
            # fallback for already-created environments.
            if app.config["TIMEZONE"] == "Asia/Karachi":
                return timezone(timedelta(hours=5), name="PKT")
            raise

    @app.template_filter("to_local_time")
    def to_local_time_filter(value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(local_timezone())

    @app.template_filter("status_label")
    def status_label(value):
        return {
            "active": "Active", "inactive": "Inactive", "suspended": "Suspended",
            "archived": "Archived", "closed": "Closed",
            "PENDING": "Pending", "APPROVED": "Approved", "REJECTED": "Rejected",
            "CANCELLED": "Cancelled", "operator": "Operator",
        }.get(str(value), str(value).replace("_", " ").title())

    @app.context_processor
    def global_context():
        from src.auth import has_permission
        from src.models import PendingOperation, PendingStatus
        from src.policy import get_policy
        pending_approvals_count = 0
        if has_permission(getattr(g, "user", None), "approvals.view"):
            context_session = db.session_factory()
            try:
                pending_approvals_count = context_session.query(PendingOperation).filter_by(
                    status=PendingStatus.PENDING
                ).count()
            finally:
                context_session.close()
        return {
            "now": lambda: datetime.now(local_timezone()),
            "has_permission": has_permission,
            "CURRENCY": app.config["CURRENCY"],
            "WITHDRAWAL_LIMIT": get_policy("withdrawal.per_operation_limit"),
            "MAKER_CHECKER_THRESHOLD": get_policy("maker_checker.threshold"),
            "PANIC_MODE": get_policy("maintenance.panic_mode"),
            "PANIC_MESSAGE": get_policy("maintenance.panic_message"),
            "MAINTENANCE_MODE": get_policy("maintenance.enabled"),
            "MAINTENANCE_MESSAGE": get_policy("maintenance.message"),
            "pending_approvals_count": pending_approvals_count,
        }

    @app.route("/")
    def home():
        return redirect(url_for("dashboard") if getattr(g, "user", None) else url_for("auth.login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        from sqlalchemy import func
        from sqlalchemy.orm import joinedload
        from src.models import Client, Account, Operation, AccountStatus
        db_session = db.session_factory()
        try:
            query = db_session.query(Operation)
            if g.user.role.value == "operator":
                query = query.filter(Operation.user_id == g.user.id)
            stats = {
                "total_clients": db_session.query(Client).count(),
                "total_accounts": db_session.query(Account).count(),
                "active_accounts": db_session.query(Account).filter_by(status=AccountStatus.ACTIVE).count(),
                "total_operations": query.count(),
                "total_balance": db_session.query(func.sum(Account.balance)).scalar() or 0,
            }
            operations = query.options(joinedload(Operation.account), joinedload(Operation.user)).order_by(
                Operation.operation_date.desc()).limit(5).all()
            return render_template("dashboard.html", stats=stats, operations=operations)
        finally:
            db_session.close()

    @app.route("/health")
    def health():
        return ({"status": "ok"}, 200) if db.check_connection() else ({"status": "unavailable"}, 503)

    @app.route("/panic")
    def panic():
        from src.policy import get_policy
        active = bool(get_policy("maintenance.panic_mode"))
        message = get_policy("maintenance.panic_message" if active else "maintenance.panic_public_message")
        return render_template("panic.html", active=active, message=message), 503 if active else 200

    @app.route("/profile", methods=("GET", "POST"))
    def profile():
        return app.view_functions["users.profile"]()

    @app.errorhandler(400)
    def bad_request(_error):
        return "The request could not be processed.", 400

    @app.errorhandler(403)
    def forbidden(_error):
        return "Access denied.", 403

    @app.errorhandler(500)
    def internal_error(_error):
        db.Session.remove()
        return "The request could not be completed.", 500

    if app.config.get("AUTO_INITIALIZE_DATABASE"):
        with app.app_context():
            db.initialize_database()
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
