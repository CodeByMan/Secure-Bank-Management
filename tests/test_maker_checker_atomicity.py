from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from src.models import Operation, PendingOperation, PendingStatus


def _approval(app, seeded):
    from src.checker import submit_approval
    with app.app_context():
        return submit_approval(
            "EXCEPTIONAL_WITHDRAWAL",
            {"account_id": seeded["account"], "account_number": "DEMO-KHI-0001", "amount": "75.00"},
            seeded["maker"],
        )


def test_maker_cannot_approve_own_request(app, seeded):
    approval = _approval(app, seeded)
    from src.checker import execute_approval
    with app.app_context():
        success, message = execute_approval(approval.id, seeded["maker"])
    assert success is False
    assert "maker" in message.lower()


def test_two_checkers_cannot_execute_request_twice(app, seeded):
    approval = _approval(app, seeded)
    barrier = Barrier(2)

    def approve(checker_id):
        from src.checker import execute_approval
        with app.app_context():
            barrier.wait()
            return execute_approval(approval.id, checker_id)[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(approve, [seeded["checker1"], seeded["checker2"]]))
    assert sorted(outcomes) == [False, True]
    from src.db import session_factory
    session = session_factory()
    try:
        row = session.get(PendingOperation, approval.id)
        assert row.status == PendingStatus.APPROVED
        assert session.query(Operation).count() == 1
    finally:
        session.close()


def test_rejected_request_is_not_executed(app, seeded):
    approval = _approval(app, seeded)
    from src.checker import reject_approval
    with app.app_context():
        success, _message = reject_approval(approval.id, seeded["checker1"], "policy")
    assert success is True
    from src.db import session_factory
    session = session_factory()
    try:
        assert session.get(PendingOperation, approval.id).status == PendingStatus.REJECTED
        assert session.query(Operation).count() == 0
    finally:
        session.close()

