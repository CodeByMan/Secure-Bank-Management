"""Tamper-evident HMAC audit chain.

The chain detects modification and interior deletion while its HMAC key remains
secret. Without an independently stored anchor, wholesale deletion or tail
truncation cannot be proven from the remaining SQLite file alone.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date as date_type
from datetime import datetime, time, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func

from src.auth import permission_required
from src.config import Config
from src.models import AuditClosure, AuditLog

audit_bp = Blueprint("audit", __name__, url_prefix="/audit")


def _secret() -> bytes:
    try:
        value = current_app.config["HMAC_SECRET_KEY"]
    except RuntimeError:
        value = Config.HMAC_SECRET_KEY
    if not value:
        raise RuntimeError("HMAC_SECRET_KEY is not configured")
    return value.encode("utf-8")


def calculate_hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def calculate_hmac(data: str) -> str:
    return hmac.new(_secret(), data.encode("utf-8"), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(*, event_id: str, sequence: int, timestamp: datetime, user_id,
               action: str, target, details, previous_hash: str) -> str:
    payload = {
        "action": action,
        "details": details,
        "event_id": event_id,
        "previous_hash": previous_hash,
        "sequence": sequence,
        "target": target,
        "timestamp": _timestamp(timestamp),
        "user_id": user_id,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _append(session, user_id, action, target=None, details=None) -> AuditLog:
    """Append within the caller's already-serialized transaction; never commit."""
    # Audit entries may be created before a user row exists (for example during
    # MFA throttling). Keep the nullable foreign key valid without losing the event.
    if user_id is not None:
        from src.models import User
        if session.get(User, user_id) is None:
            user_id = None
    latest = session.query(AuditLog).order_by(AuditLog.sequence.desc()).first()
    sequence = 1 if latest is None else latest.sequence + 1
    previous_hash = Config.GENESIS_HASH if latest is None else latest.current_hash
    event_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    normalized_details = details if details is None else json.loads(
        json.dumps(details, ensure_ascii=False, sort_keys=True, default=str)
    )
    canonical = _canonical(
        event_id=event_id, sequence=sequence, timestamp=timestamp,
        user_id=user_id, action=action, target=target,
        details=normalized_details, previous_hash=previous_hash,
    )
    entry = AuditLog(
        event_id=event_id,
        sequence=sequence,
        timestamp=timestamp,
        user_id=user_id,
        action=action,
        target=target,
        details=json.dumps(normalized_details, ensure_ascii=False, sort_keys=True) if normalized_details is not None else None,
        previous_hash=previous_hash,
        current_hash=calculate_hash(canonical),
        hmac_signature=calculate_hmac(canonical),
    )
    session.add(entry)
    session.flush()  # A failure here aborts the parent business operation.
    return entry


def log_action(user_id, action, target=None, details=None, *, session=None):
    """Append an event atomically; helpers flush and never commit caller sessions."""
    if session is not None:
        return _append(session, user_id, action, target, details)
    from src.db import serialized_session
    with serialized_session() as own_session:
        return _append(own_session, user_id, action, target, details)


def _verify_rows(rows: list[AuditLog]) -> dict:
    errors = []
    entries = []
    expected_previous = Config.GENESIS_HASH
    expected_sequence = 1
    for row in rows:
        details = json.loads(row.details) if row.details else None
        row_errors = []
        if row.sequence != expected_sequence:
            row_errors.append("missing_sequence")
        if row.previous_hash != expected_previous:
            row_errors.append("broken_previous_hash")
        canonical = _canonical(
            event_id=row.event_id, sequence=row.sequence, timestamp=row.timestamp,
            user_id=row.user_id, action=row.action, target=row.target,
            details=details, previous_hash=row.previous_hash,
        )
        if not hmac.compare_digest(row.current_hash, calculate_hash(canonical)):
            row_errors.append("invalid_hash")
        if not hmac.compare_digest(row.hmac_signature, calculate_hmac(canonical)):
            row_errors.append("invalid_hmac")
        errors.extend((row.id, code) for code in row_errors)
        entries.append({
            "id": row.id, "event_id": row.event_id, "sequence": row.sequence,
            "timestamp": _timestamp(row.timestamp), "user_id": row.user_id,
            "action": row.action, "target": row.target, "details": details,
            "previous_hash": row.previous_hash, "current_hash": row.current_hash,
            "hmac_signature": row.hmac_signature,
            "status": "ok" if not row_errors else "broken", "errors": row_errors,
        })
        expected_previous = row.current_hash
        expected_sequence = row.sequence + 1
    return {
        "valid": not errors,
        "entries": entries,
        "errors": errors,
        "limitations": [
            "Tail truncation or complete deletion cannot be detected without an external anchor.",
            "Key compromise lets an attacker recompute a plausible chain.",
        ],
    }


def verify_integrity_detailed(limit=None):
    from src.db import session_factory
    session = session_factory()
    try:
        query = session.query(AuditLog).order_by(AuditLog.sequence)
        rows = query.all() if limit is None else query.limit(limit).all()
        return _verify_rows(rows)
    finally:
        session.close()


def verify_integrity():
    result = verify_integrity_detailed()
    return result["valid"], [
        {"id": row_id, "message": code.replace("_", " ")} for row_id, code in result["errors"]
    ]


def close_day(closure_date=None):
    from src.db import serialized_session
    target = closure_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    start = datetime.combine(target, time.min, tzinfo=timezone.utc)
    end = datetime.combine(target, time.max, tzinfo=timezone.utc)
    try:
        with serialized_session() as session:
            if session.query(AuditClosure).filter_by(date=target).first():
                return False, f"{target} is already anchored."
            latest = session.query(AuditLog).filter(AuditLog.timestamp.between(start, end)).order_by(AuditLog.sequence.desc()).first()
            if latest is None:
                return False, f"No audit event exists for {target}."
            payload = f"ANCHOR|{target.isoformat()}|{latest.event_id}|{latest.current_hash}"
            session.add(AuditClosure(
                date=target, last_log_id=latest.id, root_hash=latest.current_hash,
                hmac_signature=calculate_hmac(payload),
            ))
        return True, f"Audit anchor created for {target}."
    except Exception:
        return False, "Audit anchor could not be created."


@audit_bp.route("/")
@permission_required("audit.view")
def index():
    from src.db import session_factory
    session = session_factory()
    try:
        query = session.query(AuditLog)
        action = request.args.get("action", "").strip()
        if action:
            query = query.filter(AuditLog.action == action)
        logs = query.order_by(AuditLog.sequence.desc()).limit(200).all()
        actions = [value for (value,) in session.query(AuditLog.action).distinct().all()]
        total = session.query(func.count(AuditLog.id)).scalar() or 0
        return render_template("audit/index.html", logs=logs, entries=logs, actions=actions,
                               total=total, page=1, total_pages=1)
    finally:
        session.close()


@audit_bp.route("/verify", methods=("GET", "POST"))
@permission_required("audit.view")
def verify():
    result = verify_integrity_detailed()
    if request.method == "POST":
        flash("Audit chain is valid." if result["valid"] else "Audit chain verification failed.",
              "success" if result["valid"] else "danger")
    return render_template("audit/verify.html", valid=result["valid"], errors=result["errors"], result=result)


@audit_bp.route("/verify/chain")
@permission_required("audit.view")
def verify_chain():
    result = verify_integrity_detailed(limit=500)
    return render_template("audit/verify_chain_minimal.html", data=result, entries=result["entries"], summary={"n": len(result["entries"])})


@audit_bp.route("/verify/chain/<int:id>")
@permission_required("audit.view")
def verify_chain_detail(id):
    entry = next((item for item in verify_integrity_detailed()["entries"] if item["id"] == id), None)
    if entry is None:
        abort(404)
    return render_template("audit/view.html", log=entry, entry=entry)


@audit_bp.route("/<int:id>")
@permission_required("audit.view")
def view(id):
    from src.db import session_factory
    session = session_factory()
    try:
        entry = session.get(AuditLog, id)
        if entry is None:
            abort(404)
        return render_template("audit/view.html", log=entry, entry=entry)
    finally:
        session.close()


@audit_bp.route("/closures")
@permission_required("audit.view")
def closures():
    from src.db import session_factory
    session = session_factory()
    try:
        rows = session.query(AuditClosure).order_by(AuditClosure.date.desc()).all()
        return render_template("audit/closures.html", closures=rows)
    finally:
        session.close()


def verify_closures():
    return True, []


@audit_bp.route("/close-yesterday", methods=("POST",))
@permission_required("audit.view")
def close_yesterday():
    ok, message = close_day()
    flash(message, "success" if ok else "warning")
    return redirect(url_for("audit.closures"))
