#!/usr/bin/env python3
"""Create the initial admin user for CivilPDF-DX.

The application has no public registration endpoint, so the first admin must be
seeded out-of-band. Run this once after the database is up.

Repository root (dev / SQLite or any reachable DATABASE_URL):
    PYTHONPATH=src/console/backend python scripts/create_admin.py

Inside the backend container (production docker-compose):
    docker compose -f docker-compose.prod.yml cp scripts/create_admin.py backend:/app/create_admin.py
    docker compose -f docker-compose.prod.yml exec -w /app backend python create_admin.py

Configuration (CLI flag > environment variable > default):
    --email      ADMIN_EMAIL      (default: admin@example.com)
    --username   ADMIN_USERNAME   (default: admin)
    --password   ADMIN_PASSWORD   (default: AdminPass123!)
    --full-name  ADMIN_FULL_NAME  (default: Administrator)

If a user with the given email already exists the script reports it and exits 0
(idempotent — safe to re-run).
"""

import argparse
import os
import sys

# Allow running from the repository root without exporting PYTHONPATH.
# (Inside the container the modules already sit next to this file on sys.path.)
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "src", "console", "backend"
    ),
)

from database import SessionLocal, Base, engine  # noqa: E402
from models.user import User, UserRole, UserStatus  # noqa: E402
from auth.jwt import get_password_hash  # noqa: E402

_DEFAULT_PASSWORD = "AdminPass123!"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the initial admin user.")
    parser.add_argument(
        "--email", default=os.environ.get("ADMIN_EMAIL", "admin@example.com")
    )
    parser.add_argument("--username", default=os.environ.get("ADMIN_USERNAME", "admin"))
    parser.add_argument(
        "--password", default=os.environ.get("ADMIN_PASSWORD", _DEFAULT_PASSWORD)
    )
    parser.add_argument(
        "--full-name", default=os.environ.get("ADMIN_FULL_NAME", "Administrator")
    )
    args = parser.parse_args()

    # No-op if Alembic migrations already created the schema.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            print(
                f"[skip] User already exists: {args.email} (role={existing.role.value})"
            )
            return 0

        user = User(
            email=args.email,
            username=args.username,
            full_name=args.full_name,
            hashed_password=get_password_hash(args.password),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        db.commit()
        print(f"[ok] Admin user created: {args.email} (login with this email)")
        if args.password == _DEFAULT_PASSWORD:
            print(
                "[warn] Default password in use — change it immediately after first login."
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
