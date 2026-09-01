"""Typed, authoritative policy service used by UI and enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.models import PolicyHistory, Policy


@dataclass(frozen=True)
class PolicySpec:
    value_type: str
    default: Any
    description: str
    minimum: int | None = None
    maximum: int | None = None


DEFAULT_POLICIES = {
    "password.minimum_length": PolicySpec("int", 12, "Minimum password length", 12, 128),
    "session.timeout_seconds": PolicySpec("int", 1800, "Inactive session timeout", 60, 86400),
    "withdrawal.per_operation_limit": PolicySpec("int", 250000, "Absolute per-operation withdrawal limit in PKR", 1, 10_000_000),
    "withdrawal.daily_limit": PolicySpec("int", 500000, "Rolling daily withdrawal limit in PKR", 1, 20_000_000),
    "maker_checker.threshold": PolicySpec("int", 50000, "Withdrawal amount above which approval is required in PKR", 1, 20_000_000),
    "mfa.required_roles": PolicySpec("json", ["admin", "superadmin"], "Roles that require TOTP MFA"),
    "velocity.enabled": PolicySpec("bool", True, "Enable completed-withdrawal velocity checks"),
    "velocity.withdrawals_per_minute": PolicySpec(
        "int", 3, "Maximum completed withdrawals per operator in a rolling minute", 1, 100
    ),
    "audit.retention_days": PolicySpec("int", 365, "Documented audit retention period", 1, 3650),
    "maintenance.enabled": PolicySpec("bool", False, "Maintenance banner state"),
    "maintenance.message": PolicySpec("string", "Scheduled maintenance is active.", "Maintenance banner text"),
    "maintenance.panic_mode": PolicySpec("bool", False, "Emergency operation suspension"),
    "maintenance.panic_message": PolicySpec("string", "Operations are temporarily suspended.", "Public panic-mode text"),
    "maintenance.panic_public_message": PolicySpec("string", "No emergency state is active.", "Normal status text"),
}

ALIASES = {}


def canonical_key(key: str) -> str:
    return ALIASES.get(key, key)


def encode_policy_value(value: Any, value_type: str) -> tuple[str, str]:
    if value_type == "json":
        if isinstance(value, str):
            value = json.loads(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True), "json"
    if value_type == "int":
        return str(int(value)), "int"
    if value_type == "bool":
        if isinstance(value, str):
            value = value.strip().lower() in {"1", "true", "yes", "on"}
        return ("true" if bool(value) else "false"), "bool"
    value = str(value).strip()
    if not value or len(value) > 2000:
        raise ValueError("Policy text must contain 1 to 2000 characters")
    return value, "string"


def _decode(row: Policy) -> Any:
    if row.type == "json":
        return json.loads(row.value)
    if row.type == "int":
        return int(row.value)
    if row.type == "bool":
        return row.value.lower() == "true"
    return row.value


def get_policy(key: str, default: Any = None, *, session=None) -> Any:
    from src.db import session_factory

    key = canonical_key(key)
    own_session = session is None
    db_session = session or session_factory()
    try:
        row = db_session.query(Policy).filter_by(key=key, active=True).first()
        if row is not None:
            return _decode(row)
        spec = DEFAULT_POLICIES.get(key)
        return spec.default if spec else default
    finally:
        if own_session:
            db_session.close()


def validate_policy(key: str, value: Any, type_: str = "string") -> tuple[str, str]:
    key = canonical_key(key)
    spec = DEFAULT_POLICIES.get(key)
    expected_type = spec.value_type if spec else type_
    encoded, encoded_type = encode_policy_value(value, expected_type)
    decoded = json.loads(encoded) if encoded_type == "json" else int(encoded) if encoded_type == "int" else encoded
    if spec and encoded_type == "int":
        if spec.minimum is not None and decoded < spec.minimum:
            raise ValueError(f"{key} must be at least {spec.minimum}")
        if spec.maximum is not None and decoded > spec.maximum:
            raise ValueError(f"{key} must be at most {spec.maximum}")
    if key == "mfa.required_roles":
        allowed = {"operator", "operator", "admin", "superadmin"}
        if not isinstance(decoded, list) or any(role not in allowed for role in decoded):
            raise ValueError("mfa.required_roles must contain known roles")
    return encoded, encoded_type


def set_policy(key: str, value: Any, type_: str = "string", description: str | None = None,
               changed_by: int | None = None, comment: str | None = None, *, session=None) -> bool:
    from src.audit_logger import log_action
    from src.db import serialized_session

    key = canonical_key(key)
    encoded, encoded_type = validate_policy(key, value, type_)

    def _apply(db_session):
        row = db_session.query(Policy).filter_by(key=key).first()
        old = row.value if row else None
        if row is None:
            row = Policy(key=key, value=encoded, type=encoded_type, description=description, created_by=changed_by)
            db_session.add(row)
            db_session.flush()
        else:
            row.value = encoded
            row.type = encoded_type
            row.description = description or row.description
            row.updated_at = datetime.utcnow()
        db_session.add(PolicyHistory(
            policy_id=row.id, key=key, value=encoded, type=encoded_type,
            updated_by=changed_by, comment=comment,
        ))
        log_action(changed_by, "POLICY_CHANGED", key, {"old": old, "new": encoded, "comment": comment}, session=db_session)

    if session is not None:
        _apply(session)
    else:
        with serialized_session() as db_session:
            _apply(db_session)
    return True


def invalidate_cache() -> None:
    """Compatibility no-op: authoritative reads intentionally avoid a stale cache."""
