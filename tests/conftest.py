from decimal import Decimal

import pytest
from passlib.hash import bcrypt

from src.app import create_app
from src.models import Client, Account, UserRole, ClientStatus, AccountStatus, User


@pytest.fixture
def app(tmp_path):
    database = tmp_path / "isolated-test.db"
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-session-key-" + "a" * 32,
        "HMAC_SECRET_KEY": "test-audit-key-" + "b" * 32,
        "DATABASE_PATH": str(database),
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "CURRENCY": "PKR",
        "TIMEZONE": "Asia/Karachi",
    })
    from src.db import initialize_database
    with application.app_context():
        initialize_database()
    yield application
    from src.db import Session, engine
    Session.remove()
    engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded(app):
    from src.db import serialized_session
    with serialized_session() as session:
        maker = User(username="maker", password_hash=bcrypt.hash("A-safe-demo-password!"), role=UserRole.OPERATOR)
        checker1 = User(username="checker1", password_hash=bcrypt.hash("A-safe-demo-password!"), role=UserRole.ADMIN)
        checker2 = User(username="checker2", password_hash=bcrypt.hash("A-safe-demo-password!"), role=UserRole.ADMIN)
        session.add_all([maker, checker1, checker2])
        session.flush()
        person = Client(
            last_name="Khan", first_name="Areeba", cin="SYN-KHI-0001", phone="000-000-0000",
            email="areeba@example.invalid", address="Fictional Block, Karachi", status=ClientStatus.ACTIVE,
        )
        session.add(person)
        session.flush()
        account = Account(account_number="DEMO-KHI-0001", client_id=person.id, balance=Decimal("100.00"), status=AccountStatus.ACTIVE)
        session.add(account)
        session.flush()
        ids = {"maker": maker.id, "checker1": checker1.id, "checker2": checker2.id, "account": account.id}
    return ids


def login_session(client, user_id):
    with client.session_transaction() as browser_session:
        browser_session.clear()
        browser_session["user_id"] = user_id

