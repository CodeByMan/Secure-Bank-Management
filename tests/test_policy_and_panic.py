import re

from src.models import OperationType
from tests.conftest import login_session


def test_policy_change_drives_ui_and_enforcement(app, client, seeded):
    from src.policy import set_policy
    with app.app_context():
        set_policy("withdrawal.per_operation_limit", 50, "int", changed_by=seeded["checker1"])
    login_session(client, seeded["checker1"])
    response = client.get("/admin/policies/")
    assert response.status_code == 200
    assert b"withdrawal.per_operation_limit" in response.data
    assert b"50" in response.data
    from src.operations import perform_operation
    with app.app_context():
        success, message = perform_operation(
            seeded["account"], "60.00", OperationType.WITHDRAWAL, seeded["maker"]
        )
    assert success is False
    assert "50" in message


def test_panic_guard_runs_with_flask_wtf_enabled(tmp_path):
    from src.app import create_app
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "panic-session-" + "a" * 32,
        "HMAC_SECRET_KEY": "panic-audit-" + "b" * 32,
        "DATABASE_PATH": str(tmp_path / "panic.db"),
        "WTF_CSRF_ENABLED": True,
        "RATELIMIT_ENABLED": False,
    })
    from src.db import initialize_database
    with app.app_context():
        initialize_database()
    client = app.test_client()
    assert "csrf" in app.extensions
    from src.policy import set_policy
    with app.app_context():
        set_policy("maintenance.panic_mode", True, "bool")
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/panic")
    login_page = client.get("/auth/login")
    token = re.search(rb'name="csrf_token" value="([^"]+)"', login_page.data).group(1).decode()
    response = client.post("/auth/logout", data={"csrf_token": token})
    assert response.status_code == 503


def test_admin_can_access_during_panic(app, client, seeded):
    from src.policy import set_policy
    with app.app_context():
        set_policy("maintenance.panic_mode", True, "bool", changed_by=seeded["checker1"])
    login_session(client, seeded["checker1"])
    assert client.get("/admin/policies/").status_code == 200


def test_panic_status_page_reports_service_unavailable(app, client, seeded):
    from src.policy import set_policy
    with app.app_context():
        set_policy("maintenance.panic_mode", True, "bool", changed_by=seeded["checker1"])
    response = client.get("/panic")
    assert response.status_code == 503
    assert b"temporarily suspended" in response.data
