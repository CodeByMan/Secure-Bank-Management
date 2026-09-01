from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tests_never_reference_project_database():
    test_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("*.py"))
    forbidden = "data/" + "secure_bank_manager.db"
    legacy = "data/" + "bank.db"
    assert forbidden not in test_text
    assert legacy not in test_text


def test_container_is_non_root_single_worker_with_python_healthcheck():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER app" in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "urllib.request" in dockerfile
    assert "curl" not in dockerfile


def test_debug_and_raw_database_tools_are_absent():
    assert not (ROOT / "src" / "dev.py").exists()
    assert not (ROOT / "scripts" / "rebuild_db.sh").exists()
    app_text = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
    assert 'debug=True' not in app_text
    assert 'host="0.0.0.0"' not in app_text


def test_seed_script_contains_no_fixed_passwords():
    seed = (ROOT / "scripts" / "seed_dev_users.py").read_text(encoding="utf-8")
    assert "token_urlsafe" in seed
    assert "admin123" not in seed
    assert "superadmin123" not in seed


def test_visible_currency_and_timezone_are_pakistan_defaults():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "CURRENCY=PKR" in env_example
    assert "TIMEZONE=Asia/Karachi" in env_example


def test_project_ownership_is_declared():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Muhammad Ali Nawaz" in license_text
    assert "2026" in license_text

