"""Atomic deposit and withdrawal operations for the local SQLite prototype."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from src.audit_logger import log_action
from src.auth import permission_required
from src.models import Account, Operation, AccountStatus, OperationType
from src.policy import get_policy

operations_bp = Blueprint("operations", __name__, url_prefix="/operations")
MONEY = Decimal("0.01")


def _money(value) -> Decimal:
    amount = Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be a positive number.")
    return amount


def _apply_operation(session, account_id: int, amount, type_op: OperationType, user_id: int,
                     description: str = "", approved_by=None) -> Operation:
    """Apply one operation inside a caller-owned serialized transaction."""
    amount = _money(amount)
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError("Account not found.")
    if account.status != AccountStatus.ACTIVE:
        raise ValueError("Account is not active.")

    before = Decimal(account.balance).quantize(MONEY)
    if type_op == OperationType.WITHDRAWAL:
        if get_policy("velocity.enabled", session=session):
            minute_start = datetime.now(timezone.utc) - timedelta(minutes=1)
            recent_withdrawals = session.query(Operation).filter(
                Operation.user_id == user_id,
                Operation.operation_type == OperationType.WITHDRAWAL,
                Operation.operation_date >= minute_start,
            ).count()
            velocity_limit = int(get_policy("velocity.withdrawals_per_minute", session=session))
            if recent_withdrawals >= velocity_limit:
                raise ValueError(
                    f"Withdrawal velocity limit reached: no more than {velocity_limit} "
                    "completed withdrawals are allowed per operator in a rolling minute."
                )
        per_operation = Decimal(str(get_policy("withdrawal.per_operation_limit", session=session)))
        if amount > per_operation:
            raise ValueError(f"Withdrawal exceeds the {per_operation} PKR per-operation policy.")
        start = datetime.now(timezone.utc) - timedelta(days=1)
        used = session.query(Operation).filter(
            Operation.account_id == account.id,
            Operation.operation_type == OperationType.WITHDRAWAL,
            Operation.operation_date >= start,
        ).with_entities(Operation.amount).all()
        daily_total = sum((Decimal(row[0]) for row in used), Decimal("0"))
        daily_limit = Decimal(str(get_policy("withdrawal.daily_limit", session=session)))
        if daily_total + amount > daily_limit:
            raise ValueError(f"Withdrawal exceeds the {daily_limit} PKR rolling daily policy.")
        after = before - amount
        if after < Decimal("0"):
            raise ValueError("Insufficient balance.")
    elif type_op == OperationType.DEPOSIT:
        after = before + amount
    else:
        raise ValueError("Unsupported operation type.")

    account.balance = after
    operation = Operation(
        account_id=account.id,
        user_id=user_id,
        operation_type=type_op,
        amount=amount,
        balance_before=before,
        balance_after=after,
        operation_date=datetime.now(timezone.utc),
        description=(description or "")[:1000],
        approved_by_id=int(approved_by) if approved_by is not None else None,
    )
    session.add(operation)
    session.flush()
    log_action(
        user_id,
        "DEPOSIT" if type_op == OperationType.DEPOSIT else "WITHDRAWAL",
        f"Account {account.account_number}",
        {"amount": str(amount), "balance_before": str(before), "balance_after": str(after),
         "checker_id": int(approved_by) if approved_by is not None else None},
        session=session,
    )
    return operation


def perform_operation(account_id, amount, type_op, user_id, description="", approved_by=None, *, session=None):
    """Compatibility service returning ``(success, operation_or_message)``.

    When a session is supplied, the caller owns the transaction. Otherwise this
    function opens one `BEGIN IMMEDIATE` transaction, so competing SQLite writes
    are serialized before reading the balance and audit-chain tail.
    """
    if session is not None:
        return True, _apply_operation(session, account_id, amount, type_op, user_id, description, approved_by)
    from src.db import serialized_session
    try:
        with serialized_session() as own_session:
            operation = _apply_operation(own_session, account_id, amount, type_op, user_id, description, approved_by)
        return True, operation
    except (ValueError, InvalidOperation) as exc:
        return False, str(exc)
    except Exception:
        current_app.logger.exception("Critical operation rolled back")
        return False, "The operation could not be completed."


def _load_account(account_id):
    from src.db import session_factory
    from sqlalchemy.orm import joinedload
    session = session_factory()
    try:
        return session.query(Account).options(joinedload(Account.client)).filter_by(id=account_id).first()
    finally:
        session.close()


@operations_bp.route("/deposit/<int:account_id>", methods=("GET", "POST"))
@permission_required("operations.create")
def deposit(account_id):
    account = _load_account(account_id)
    if account is None:
        flash("Account not found.", "danger")
        return redirect(url_for("clients.index"))
    if request.method == "POST":
        success, result = perform_operation(
            account_id, request.form.get("amount", ""), OperationType.DEPOSIT,
            g.user.id, request.form.get("description", ""),
        )
        if success:
            flash(f"Deposit completed in {current_app.config['CURRENCY']}.", "success")
            return redirect(url_for("accounts.view", account_number=account.account_number))
        flash(str(result), "danger")
    return render_template("operations/deposit.html", account=account, config=current_app.config)


@operations_bp.route("/withdrawal/<int:account_id>", methods=("GET", "POST"))
@permission_required("operations.create")
def withdrawal(account_id):
    account = _load_account(account_id)
    if account is None:
        flash("Account not found.", "danger")
        return redirect(url_for("clients.index"))
    if request.method == "POST":
        try:
            amount = _money(request.form.get("amount", ""))
        except (ValueError, InvalidOperation):
            flash("Enter a valid positive amount.", "danger")
            return render_template("operations/withdrawal.html", account=account, config=current_app.config)

        threshold = Decimal(str(get_policy("maker_checker.threshold")))
        if amount > threshold:
            from src.checker import submit_approval
            try:
                approval = submit_approval(
                    "EXCEPTIONAL_WITHDRAWAL",
                    {"account_id": account.id, "account_number": account.account_number,
                     "amount": str(amount), "description": request.form.get("description", "")},
                    g.user.id,
                )
                flash(f"Approval request #{approval.id} was submitted.", "warning")
                return redirect(url_for("accounts.view", account_number=account.account_number))
            except Exception:
                current_app.logger.exception("Approval submission rolled back")
                flash("The approval request could not be submitted.", "danger")
                return redirect(url_for("accounts.view", account_number=account.account_number))

        success, result = perform_operation(
            account.id, amount, OperationType.WITHDRAWAL, g.user.id,
            request.form.get("description", ""),
        )
        if success:
            flash(f"Withdrawal completed in {current_app.config['CURRENCY']}.", "success")
            return redirect(url_for("accounts.view", account_number=account.account_number))
        flash(str(result), "danger")
    return render_template("operations/withdrawal.html", account=account, config=current_app.config)
