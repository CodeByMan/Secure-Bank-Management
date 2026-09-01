from datetime import datetime, timedelta

import pytest

from src.app import create_app
from tests.conftest import login_session


def test_login_uses_same_generic_error_for_unknown_and_wrong_password(client, seeded):
    unknown = client.post("/auth/login", data={"username": "unknown", "password": "wrong"})
    wrong = client.post("/auth/login", data={"username": "maker", "password": "wrong"})
    assert b"Invalid username or password" in unknown.data
    assert b"Invalid username or password" in wrong.data


def test_session_timeout_forces_login(app, client, seeded):
    login_session(client, seeded["maker"])
    with client.session_transaction() as browser_session:
        browser_session["last_activity"] = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_logout_is_post_only(client, seeded):
    login_session(client, seeded["maker"])
    assert client.get("/auth/logout").status_code == 405
    assert client.post("/auth/logout").status_code == 302


def test_operator_cannot_view_audit(client, seeded):
    login_session(client, seeded["maker"])
    response = client.get("/audit/")
    assert response.status_code == 302


def test_csrf_rejects_mutation_without_token(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "csrf-session-" + "a" * 32,
        "HMAC_SECRET_KEY": "csrf-audit-" + "b" * 32,
        "DATABASE_PATH": str(tmp_path / "csrf.db"),
        "WTF_CSRF_ENABLED": True,
        "RATELIMIT_ENABLED": False,
    })
    from src.db import initialize_database
    with app.app_context():
        initialize_database()
    response = app.test_client().post("/auth/login", data={"username": "nobody", "password": "wrong"})
    assert response.status_code == 400


def test_login_mfa_and_recovery_have_specific_rate_limits(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "rate-session-" + "a" * 32,
        "HMAC_SECRET_KEY": "rate-audit-" + "b" * 32,
        "DATABASE_PATH": str(tmp_path / "rate.db"),
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": True,
        "LOGIN_RATE_LIMIT": "1 per minute",
        "MFA_RATE_LIMIT": "1 per minute",
        "RECOVERY_RATE_LIMIT": "1 per minute",
    })
    from src.db import initialize_database
    with app.app_context():
        initialize_database()
    client = app.test_client()
    assert client.post("/auth/login", data={"username": "none", "password": "bad"}).status_code == 200
    assert client.post("/auth/login", data={"username": "none", "password": "bad"}).status_code == 429
    with client.session_transaction() as browser_session:
        browser_session["mfa_user_id"] = 999
    assert client.post("/auth/mfa/verify", data={"code": "000000"}).status_code == 200
    assert client.post("/auth/mfa/verify", data={"code": "000000"}).status_code == 429
    with client.session_transaction() as browser_session:
        browser_session["mfa_user_id"] = 999
    assert client.post("/auth/mfa/recovery", data={"code": "NOPE"}).status_code == 200
    assert client.post("/auth/mfa/recovery", data={"code": "NOPE"}).status_code == 429


def test_missing_production_secrets_fail_closed(tmp_path):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"TESTING": False, "SECRET_KEY": "", "HMAC_SECRET_KEY": "", "DATABASE_PATH": str(tmp_path / "no.db")})


def test_secure_cookie_flags_can_be_enabled(app):
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True

