"""Create an account for a tester without e-mail (useful while no SMTP is set up).

The account is created already confirmed, with a random temporary password printed
once. The terms are NOT accepted here: on the first sign-in the person reads and
accepts them, and should change the password on the profile page.

Usage (inside the backend container):
    python -m app.scripts.create_user --email someone@example.org --name "Full name"
"""

import argparse
import asyncio
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select

import app.db.models  # noqa: F401 - registers every table for the foreign keys
from app.core.security import hash_password
from app.db.base import new_id
from app.db.session import get_sessionmaker
from app.modules.auth.models import User


def temporary_password() -> str:
    # Letters and digits, easy to type, strong enough (passes is_strong_password).
    return f"{secrets.token_urlsafe(9)}-{secrets.randbelow(90) + 10}a"


async def create(email: str, name: str, language: str) -> str:
    async with get_sessionmaker()() as session:
        exists = (
            await session.scalars(
                select(User).where(
                    func.lower(User.email) == email.lower(), User.deleted_at.is_(None)
                )
            )
        ).first()
        if exists is not None:
            raise SystemExit(f"there is already an account with e-mail {email}")
        password = temporary_password()
        session.add(
            User(
                id=new_id(),
                name=name.strip(),
                email=email.strip(),
                password_hash=hash_password(password),
                ui_language=language,
                email_verified_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--language", choices=["pt-BR", "en"], default="pt-BR")
    args = parser.parse_args()
    password = asyncio.run(create(args.email, args.name, args.language))
    print(f"Account created for {args.email}.")
    print(f"Temporary password (shown only now): {password}")
    print("On first sign-in the person accepts the terms; ask them to change the password.")


if __name__ == "__main__":
    main()
