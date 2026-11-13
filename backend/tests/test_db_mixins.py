"""Audit, soft delete, UUID v7 and optimistic locking (docs/modelo-dados.md, 9)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.db.session import get_sessionmaker
from app.modules.audit.models import AuditLog
from app.modules.audit.recorder import current_user_id_var
from app.modules.auth.models import User


def _user(email: str = "ana@example.org") -> User:
    return User(name="Ana", email=email, password_hash="x")


async def _audit(session: AsyncSession, entity_id: object) -> list[AuditLog]:
    rows = await session.scalars(
        select(AuditLog).where(AuditLog.entity_id == entity_id).order_by(AuditLog.created_at)
    )
    return list(rows)


async def test_ids_are_uuid_v7(session: AsyncSession) -> None:
    user = _user()
    session.add(user)
    await session.commit()
    assert user.id.version == 7


async def test_create_and_update_are_audited_without_secrets(session: AsyncSession) -> None:
    user = _user()
    session.add(user)
    await session.commit()

    token = current_user_id_var.set(user.id)
    try:
        user.name = "Ana Maria"
        user.password_hash = "changed"
        await session.commit()
    finally:
        current_user_id_var.reset(token)

    rows = await _audit(session, user.id)
    assert [r.action for r in rows] == ["create", "update"]
    assert "password_hash" not in rows[0].new_value
    assert rows[1].field == "name"
    assert (rows[1].old_value, rows[1].new_value) == ("Ana", "Ana Maria")
    assert rows[1].user_id == user.id


async def test_soft_deleted_rows_are_hidden_but_kept(session: AsyncSession) -> None:
    user = _user()
    session.add(user)
    await session.commit()

    user.deleted_at = datetime.now(UTC)
    await session.commit()

    assert (await session.scalars(select(User))).all() == []
    kept = await session.scalars(select(User).execution_options(include_deleted=True))
    assert [u.id for u in kept] == [user.id]
    assert (await _audit(session, user.id))[-1].action == "delete"


async def test_concurrent_edit_raises_conflict_instead_of_overwriting() -> None:
    maker = get_sessionmaker()
    async with maker() as setup:
        user = _user()
        setup.add(user)
        await setup.commit()
        user_id = user.id

    async with maker() as first, maker() as second:
        a = await first.get(User, user_id)
        b = await second.get(User, user_id)
        assert a is not None and b is not None
        a.name = "First"
        await first.commit()
        b.name = "Second"
        with pytest.raises(StaleDataError):
            await second.commit()

    async with maker() as check:
        final = await check.get(User, user_id)
        assert final is not None
        assert final.name == "First"
        assert final.version == 2
