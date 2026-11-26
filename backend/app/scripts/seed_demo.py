"""Demonstration project with a public dataset (docs/modulos.md 7.11; `make seed-demo`).

Creates, for an existing user, a project marked as a demonstration with the nine
studies of `dat.normand1999` (metafor/metadat): stroke rehabilitation, length of
hospital stay in specialist care versus routine care. The project itself is built by
app.modules.learning.demo (also used by the "create demo project" button).

Usage (inside the backend container):
    python -m app.scripts.seed_demo --email someone@example.org
"""

import argparse
import asyncio

from sqlalchemy import select

import app.db.models  # noqa: F401 - registers every table for the foreign keys
from app.db.session import get_sessionmaker
from app.modules.auth.models import User
from app.modules.learning.demo import create_demo


async def seed(email: str) -> str:
    async with get_sessionmaker()() as session:
        user = (await session.scalars(select(User).where(User.email == email))).first()
        if user is None:
            raise SystemExit(f"no user with e-mail {email}")
        return str(await create_demo(session, user, check_quota=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="existing user who will own the project")
    args = parser.parse_args()
    project_id = asyncio.run(seed(args.email))
    print(f"Demo project created: {project_id}")


if __name__ == "__main__":
    main()
