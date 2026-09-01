from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from src.models import Account, AuditLog, Operation, OperationType


def test_two_withdrawals_compete_for_last_balance(app, seeded):
    from src.operations import perform_operation
    barrier = Barrier(2)

    def withdraw():
        with app.app_context():
            barrier.wait()
            return perform_operation(seeded["account"], "100.00", OperationType.WITHDRAWAL, seeded["maker"])[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _value: withdraw(), range(2)))
    assert sorted(outcomes) == [False, True]
    from src.db import session_factory
    session = session_factory()
    try:
        assert session.get(Account, seeded["account"]).balance == Decimal("0.00")
        assert session.query(Operation).count() == 1
        assert session.query(AuditLog).filter_by(action="WITHDRAWAL").count() == 1
    finally:
        session.close()


def test_audit_failure_rolls_back_everything(app, seeded, monkeypatch):
    import src.operations as operations
    monkeypatch.setattr(operations, "log_action", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("injected")))
    with app.app_context():
        success, message = operations.perform_operation(
            seeded["account"], "10.00", OperationType.WITHDRAWAL, seeded["maker"]
        )
    assert success is False
    assert "could not" in message.lower()
    from src.db import session_factory
    session = session_factory()
    try:
        assert session.get(Account, seeded["account"]).balance == Decimal("100.00")
        assert session.query(Operation).count() == 0
        assert session.query(AuditLog).count() == 0
    finally:
        session.close()


def test_deposit_operation_and_audit_commit_together(app, seeded):
    from src.operations import perform_operation
    with app.app_context():
        success, operation = perform_operation(
            seeded["account"], "25.00", OperationType.DEPOSIT, seeded["maker"]
        )
    assert success is True
    from src.db import session_factory
    session = session_factory()
    try:
        assert session.get(Operation, operation.id).balance_after == Decimal("125.00")
        assert session.query(AuditLog).filter_by(action="DEPOSIT").count() == 1
    finally:
        session.close()

