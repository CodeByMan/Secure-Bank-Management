from decimal import Decimal

from src.models import Account, Operation, OperationType
from src.operations import perform_operation
from src.policy import set_policy


def test_withdrawal_velocity_policy_is_enforced_atomically(app, seeded):
    with app.app_context():
        set_policy("velocity.enabled", True)
        set_policy("velocity.withdrawals_per_minute", 2)

        first_ok, _ = perform_operation(
            seeded["account"], Decimal("10.00"), OperationType.WITHDRAWAL, seeded["maker"]
        )
        second_ok, _ = perform_operation(
            seeded["account"], Decimal("10.00"), OperationType.WITHDRAWAL, seeded["maker"]
        )
        third_ok, message = perform_operation(
            seeded["account"], Decimal("10.00"), OperationType.WITHDRAWAL, seeded["maker"]
        )

        assert first_ok is True
        assert second_ok is True
        assert third_ok is False
        assert "velocity limit" in message

        from src.db import session_factory

        session = session_factory()
        try:
            account = session.get(Account, seeded["account"])
            withdrawals = session.query(Operation).filter_by(
                account_id=seeded["account"],
                operation_type=OperationType.WITHDRAWAL,
            ).count()
            assert Decimal(account.balance) == Decimal("80.00")
            assert withdrawals == 2
        finally:
            session.close()
