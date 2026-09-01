"""English module documentation."""
from functools import wraps
from typing import Callable, Any
from flask import abort

from src.policy import get_policy


def get_policy_int(key: str, default: Any = None) -> Any:
    """English module documentation."""
    val = get_policy(key, default=default)
    try:
        return int(val)
    except Exception:
        return default


def get_policy_bool(key: str, default: bool = False) -> bool:
    """English module documentation."""
    val = get_policy(key, default=default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes", "on")
    return bool(val)


def require_policy_max(key: str, amount_getter: Callable[..., Any]):
    """English module documentation."""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limit = get_policy_int(key, default=None)
            if limit is None:
                return f(*args, **kwargs)
            amount = amount_getter(*args, **kwargs)
            try:
                amount = float(amount)
            except Exception:
                # English implementation note.
                abort(400)
            if amount > limit:
                # English implementation note.
                abort(403)
            return f(*args, **kwargs)

        return wrapped

    return decorator


def enforce_withdrawal_limit(amount: Any) -> bool:
    """English module documentation."""
    limit = get_policy_int('withdrawal.daily_limit', default=None)
    if limit is None:
        return True
    try:
        return float(amount) <= limit
    except Exception:
        return False
