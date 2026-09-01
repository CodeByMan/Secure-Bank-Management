"""Atomic maker-checker workflow for sensitive withdrawals."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import update
from sqlalchemy.orm import joinedload

from src.audit_logger import log_action
from src.auth import has_permission, login_required, permission_required
from src.models import PendingOperation, PendingStatus, OperationType

checker_bp = Blueprint("checker", __name__, url_prefix="/approvals")


def _mask(value, keep=4):
    text = str(value)
    return "*" * max(0, len(text) - keep) + text[-keep:]


def _sanitize_payload(payload):
    result = {}
    for key, value in dict(payload).items():
        result[key] = _mask(value) if key in {"account_number", "cnic", "cin", "token"} else str(value)[:1000]
    return result


def _append_approval(session, operation_type, payload, user_id):
    approval = PendingOperation(
        operation_type=operation_type,
        payload=dict(payload),
        created_by_id=user_id,
        status=PendingStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    session.add(approval)
    session.flush()
    log_action(user_id, "APPROVAL_SUBMITTED", operation_type,
               {"approval_id": approval.id, "payload": _sanitize_payload(payload)}, session=session)
    return approval


def submit_approval(operation_type, payload, user_id, *, session=None):
    """Create an approval in the caller's transaction when supplied.

    Without a session, this helper owns a serialized SQLite transaction. This
    keeps the public compatibility API while ensuring there is only one
    implementation of approval creation.
    """
    if session is not None:
        return _append_approval(session, operation_type, payload, user_id)
    from src.db import serialized_session
    with serialized_session() as own_session:
        return _append_approval(own_session, operation_type, payload, user_id)


def _execute_payload(session, approval, checker_id):
    if approval.operation_type not in {"EXCEPTIONAL_WITHDRAWAL", "EXCEPTIONAL_WITHDRAWAL"}:
        raise ValueError("Unsupported approval type.")
    from src.operations import perform_operation
    success, result = perform_operation(
        approval.payload["account_id"], approval.payload["amount"], OperationType.WITHDRAWAL,
        approval.created_by_id, approval.payload.get("description", "Approved withdrawal"),
        approved_by=checker_id, session=session,
    )
    if not success:
        raise ValueError(str(result))


def execute_approval(approval_id, admin_id, reason=None, comment=None):
    from src.db import serialized_session
    try:
        with serialized_session() as session:
            approval = session.get(PendingOperation, approval_id)
            if approval is None or approval.status != PendingStatus.PENDING:
                return False, "The request was already handled or does not exist."
            if approval.created_by_id == admin_id:
                log_action(admin_id, "APPROVAL_DENIED", "Self approval",
                           {"approval_id": approval_id}, session=session)
                return False, "The maker cannot approve their own request."

            # The serialized write transaction makes this conditional claim
            # deterministic under SQLite. The affected-row check prevents reuse.
            claimed = session.execute(
                update(PendingOperation)
                .where(PendingOperation.id == approval_id,
                       PendingOperation.status == PendingStatus.PENDING)
                .values(status=PendingStatus.APPROVED, approved_by_id=admin_id,
                        approved_at=datetime.now(timezone.utc), decision_reason=reason,
                        decision_comment=comment)
            )
            if claimed.rowcount != 1:
                return False, "The request was already handled."
            session.flush()
            _execute_payload(session, approval, admin_id)
            log_action(admin_id, "APPROVAL_EXECUTED", approval.operation_type,
                       {"approval_id": approval.id, "reason": reason, "comment": comment}, session=session)
        return True, "The request was approved and executed."
    except ValueError as exc:
        return False, str(exc)
    except Exception:
        current_app.logger.exception("Approval transaction rolled back")
        return False, "The request could not be processed."


def reject_approval(approval_id, admin_id, reason=None, comment=None):
    from src.db import serialized_session
    try:
        with serialized_session() as session:
            approval = session.get(PendingOperation, approval_id)
            if approval is None or approval.status != PendingStatus.PENDING:
                return False, "The request was already handled or does not exist."
            if approval.created_by_id == admin_id:
                return False, "The maker cannot reject their own request."
            claimed = session.execute(
                update(PendingOperation)
                .where(PendingOperation.id == approval_id,
                       PendingOperation.status == PendingStatus.PENDING)
                .values(status=PendingStatus.REJECTED, approved_by_id=admin_id,
                        approved_at=datetime.now(timezone.utc), decision_reason=reason,
                        decision_comment=comment)
            )
            if claimed.rowcount != 1:
                return False, "The request was already handled."
            log_action(admin_id, "APPROVAL_REJECTED", approval.operation_type,
                       {"approval_id": approval.id, "reason": reason}, session=session)
        return True, "The request was rejected."
    except Exception:
        current_app.logger.exception("Rejection transaction rolled back")
        return False, "The request could not be processed."


def withdraw_approval(approval_id, user_id, reason=None, comment=None):
    from src.db import serialized_session
    try:
        with serialized_session() as session:
            approval = session.get(PendingOperation, approval_id)
            if approval is None or approval.status != PendingStatus.PENDING:
                return False, "The request was already handled or does not exist."
            if approval.created_by_id != user_id:
                return False, "Only the maker can withdraw this request."
            approval.status = PendingStatus.CANCELLED
            approval.approved_at = datetime.now(timezone.utc)
            approval.decision_reason = reason or "withdrawn"
            approval.decision_comment = comment
            log_action(user_id, "APPROVAL_WITHDRAWN", approval.operation_type,
                       {"approval_id": approval.id}, session=session)
        return True, "The request was withdrawn."
    except Exception:
        return False, "The request could not be processed."


@checker_bp.route("/")
@checker_bp.route("")
@permission_required("approvals.view")
def index():
    from src.db import session_factory
    session = session_factory()
    try:
        query = session.query(PendingOperation).options(joinedload(PendingOperation.created_by))
        if request.args.get("filter") == "mine":
            query = query.filter(PendingOperation.created_by_id == g.user.id)
        else:
            query = query.filter(PendingOperation.status == PendingStatus.PENDING)
        rows = query.order_by(PendingOperation.created_at.desc()).all()
        return render_template("admin/approvals.html", requests=rows, filter=request.args.get("filter"))
    finally:
        session.close()


@checker_bp.route("/my")
@login_required
def my():
    from src.db import session_factory
    session = session_factory()
    try:
        rows = session.query(PendingOperation).filter_by(created_by_id=g.user.id).order_by(PendingOperation.created_at.desc()).all()
        return render_template("checker/my_requests.html", requests=rows)
    finally:
        session.close()


@checker_bp.route("/decide/<int:id>", methods=("POST",))
@permission_required("approvals.view")
def decide(id):
    action = request.form.get("action")
    permission = "approvals.approve" if action == "approve" else "approvals.reject"
    if not has_permission(g.user, permission):
        flash("Insufficient permission.", "danger")
        return redirect(url_for("checker.index"))
    handler = execute_approval if action == "approve" else reject_approval
    success, message = handler(id, g.user.id, request.form.get("reason"), request.form.get("comment"))
    flash(message, "success" if success else "danger")
    return redirect(url_for("checker.index"))


@checker_bp.route("/withdraw/<int:id>", methods=("POST",))
@login_required
def withdraw(id):
    success, message = withdraw_approval(id, g.user.id, request.form.get("reason"), request.form.get("comment"))
    flash(message, "success" if success else "danger")
    return redirect(url_for("checker.my"))
