"""Test accounts for the interface tests (e2e/, Playwright). Never in production.

Creates (or resets) verified accounts with the given e-mails and one shared test
password, so the browser tests can sign in without e-mail or captcha. With --demo,
also creates the demonstration project (public dat.normand1999 data) for the first
account. The e-mails must be under example.org, a domain reserved for examples.

Usage (inside the backend container, fixtures mounted at /stats-fixtures):
    python -m app.scripts.e2e_users --password PASS a@example.org b@example.org --demo
"""

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

import app.db.models  # noqa: F401 - registers every table for the foreign keys
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.modules.auth.models import User
from app.scripts.seed_demo import seed


async def ensure(emails: list[str], password: str, names: list[str]) -> None:
    async with get_sessionmaker()() as session:
        for email, name in zip(emails, names, strict=True):
            user = (await session.scalars(select(User).where(User.email == email))).first()
            if user is None:
                user = User(email=email, name=name, password_hash="")
                session.add(user)
            user.password_hash = hash_password(password)
            user.is_active = True
            user.email_verified_at = user.email_verified_at or datetime.now(UTC)
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("emails", nargs="+")
    args = parser.parse_args()
    if get_settings().app_env == "production":
        raise SystemExit("refusing to create test accounts in production")
    if not all(e.endswith("@example.org") for e in args.emails):
        raise SystemExit("test accounts must use @example.org")
    names = [f"E2E {chr(ord('A') + i)}" for i in range(len(args.emails))]

    async def run() -> str | None:
        await ensure(args.emails, args.password, names)
        return await seed(args.emails[0]) if args.demo else None

    project_id = asyncio.run(run())
    if project_id:
        print(project_id)


if __name__ == "__main__":
    main()
