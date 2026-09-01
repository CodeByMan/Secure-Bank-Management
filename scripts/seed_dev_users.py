#!/usr/bin/env python3
"""Explicitly create local demo users with random one-time passwords."""

import argparse
import os
import secrets
import sys
from pathlib import Path

from passlib.hash import bcrypt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import initialize_database, serialized_session
from src.models import UserRole, User


def main() -> int:
    parser = argparse.ArgumentParser(description="Create local educational demo users.")
    parser.add_argument("--strength", action="store_true", help="Acknowledge local development seeding")
    args = parser.parse_args()
    if not args.strength:
        parser.error("--strength is required")
    if os.getenv("APP_ENV", "development").lower() == "production":
        parser.error("Development user seeding is disabled in production")

    initialize_database()
    credentials = []
    with serialized_session() as session:
        for username, role in (
            ("superadmin", UserRole.SUPERADMIN),
            ("admin", UserRole.ADMIN),
            ("operator", UserRole.OPERATOR),
        ):
            if session.query(User).filter_by(username=username).first():
                continue
            password = secrets.token_urlsafe(18)
            session.add(User(
                username=username,
                display_name=username.title(),
                password_hash=bcrypt.hash(password),
                role=role,
            ))
            credentials.append((username, password))

    if not credentials:
        print("No users were created; the demo identities already exist.")
        return 0
    print("One-time local credentials (store them now; they are not logged again):")
    for username, password in credentials:
        print(f"  {username}: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

