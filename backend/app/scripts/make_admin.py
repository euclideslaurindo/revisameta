"""Grant (or remove) system administration for an existing account.

The first administrator cannot be created through the web, so this is run once on
the server; later administrators can be granted on the administration page.

Usage (inside the backend container):
    python -m app.scripts.make_admin --email someone@example.org
    python -m app.scripts.make_admin --email someone@example.org --remove
"""

import argparse
import asyncio

from sqlalchemy import func, select

import app.db.models  # noqa: F401 - registers every table for the foreign keys
from app.db.session import get_sessionmaker
from app.modules.auth.models import User


async def set_admin(email: str, value: bool) -> str:
    async with get_sessionmaker()() as session:
        user = (
            await session.scalars(
                select(User).where(
                    func.lower(User.email) == email.lower(), User.deleted_at.is_(None)
                )
            )
        ).first()
        if user is None:
            raise SystemExit(f"no account with e-mail {email}")
        user.is_system_admin = value
        await session.commit()
        return user.name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="e-mail of an existing account")
    parser.add_argument("--remove", action="store_true", help="remove administration instead")
    args = parser.parse_args()
    name = asyncio.run(set_admin(args.email, not args.remove))
    state = "is no longer" if args.remove else "is now"
    print(f"{name} {state} a system administrator.")


if __name__ == "__main__":
    main()
