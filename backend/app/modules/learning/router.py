from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.learning.demo import create_demo

router = APIRouter(tags=["learning"])


class DemoIn(BaseModel):
    language: Literal["pt-BR", "en"] = "pt-BR"


class DemoOut(BaseModel):
    project_id: str


@router.post("/demo-projects", status_code=status.HTTP_201_CREATED)
async def create_demo_project(
    body: DemoIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DemoOut:
    """A new demonstration project with public data (metafor::dat.normand1999), owned by
    the person who asked. Counts towards their project quota."""
    return DemoOut(project_id=str(await create_demo(session, user, body.language)))
