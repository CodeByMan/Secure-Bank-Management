#!/usr/bin/env python3
"""Migration helper: add Policy and PolicyHistory tables (dev helper).

For production, use Alembic to generate a proper migration.
"""
from src.db import engine
from src.models import Base, Policy, PolicyHistory

if __name__ == '__main__':
    print("Creating policy tables if needed...")
    Base.metadata.create_all(engine)
    print("Done. Use an Alembic migration in production.")
