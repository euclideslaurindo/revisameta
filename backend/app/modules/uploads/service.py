import uuid

from sqlalchemy.ext.asyncio import AsyncSession


async def storage_used_bytes(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Bytes stored by the user. Uploads arrive in the next step of Etapa 0."""
    return 0
