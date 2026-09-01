"""Application configuration for the local educational prototype."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    ENVIRONMENT = os.getenv("APP_ENV", "development").strip().lower()
    TESTING = False
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    HMAC_SECRET_KEY = os.getenv("HMAC_SECRET_KEY", "")
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(Path("data") / "secure_bank_manager.db"))

    CURRENCY = os.getenv("CURRENCY", "PKR")
    CURRENCY = CURRENCY  # Backwards-compatible template name.
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Karachi")
    TIMEZONE_OFFSET_HOURS = 5  # Compatibility for legacy presentation code only.

    MINIMUM_OPENING_BALANCE = Decimal(os.getenv("MINIMUM_OPENING_BALANCE", "1000.00"))
    MINIMUM_ACCOUNT_BALANCE = Decimal(os.getenv("MINIMUM_ACCOUNT_BALANCE", "0.00"))
    DEFAULT_WITHDRAWAL_LIMIT = Decimal(os.getenv("DEFAULT_WITHDRAWAL_LIMIT", "250000.00"))
    DEFAULT_MAKER_CHECKER_THRESHOLD = Decimal(os.getenv("DEFAULT_MAKER_CHECKER_THRESHOLD", "50000.00"))
    MINIMUM_OPENING_BALANCE = MINIMUM_OPENING_BALANCE
    MINIMUM_ACCOUNT_BALANCE = MINIMUM_ACCOUNT_BALANCE
    WITHDRAWAL_MAXIMUM = DEFAULT_WITHDRAWAL_LIMIT
    MAKER_CHECKER_THRESHOLD = DEFAULT_MAKER_CHECKER_THRESHOLD

    MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))
    SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "1800"))
    LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "10 per minute")
    MFA_RATE_LIMIT = os.getenv("MFA_RATE_LIMIT", "5 per minute")
    RECOVERY_RATE_LIMIT = os.getenv("RECOVERY_RATE_LIMIT", "3 per minute")
    RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")

    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", ENVIRONMENT == "production")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    WTF_CSRF_ENABLED = True
    GENESIS_HASH = os.getenv("GENESIS_HASH", "0" * 64)
    AUTO_INITIALIZE_DATABASE = _bool("AUTO_INITIALIZE_DATABASE", False)

    @classmethod
    def validate(cls) -> None:
        """Reject missing, shared, or predictably weak application secrets."""
        if cls.TESTING:
            return
        errors = []
        weak = {
            "change-me", "changeme", "dev-secret-key-change-in-production",
            "change-this-hmac-key", "flask_session_secret_key",
        }
        for name, value in (("SECRET_KEY", cls.SECRET_KEY), ("HMAC_SECRET_KEY", cls.HMAC_SECRET_KEY)):
            if not value or len(value) < 32 or value.lower() in weak or len(set(value)) < 8:
                errors.append(f"{name} must be an explicit random value of at least 32 characters")
        if cls.SECRET_KEY and cls.SECRET_KEY == cls.HMAC_SECRET_KEY:
            errors.append("SECRET_KEY and HMAC_SECRET_KEY must be different")
        if errors:
            raise RuntimeError("Invalid security configuration: " + "; ".join(errors))
