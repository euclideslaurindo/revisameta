import logging

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotAuthenticatedError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.modules.audit.recorder import current_user_id_var
from app.modules.auth.models import User

_bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Authenticated, active and verified user. Also tags audit rows with this user."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise NotAuthenticatedError()
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise NotAuthenticatedError("auth.session_expired")
    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        reason = "missing" if user is None else "deleted" if user.deleted_at else "inactive"
        logger.info("access_user_rejected", extra={"extra_fields": {"reason": reason}})
        raise NotAuthenticatedError("auth.session_expired")
    if user.email_verified_at is None:
        raise NotAuthenticatedError("auth.email_not_verified")
    current_user_id_var.set(user.id)
    return user
