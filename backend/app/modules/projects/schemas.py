import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.projects.models import Role


def _unique_roles(roles: list[Role]) -> list[Role]:
    if not roles:
        raise ValueError("at least one role is required")
    return sorted(set(roles), key=list(Role).index)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    question: str | None = Field(default=None, max_length=5000)
    pico: dict[str, Any] = Field(default_factory=dict)
    prospero: str | None = Field(default=None, max_length=64)
    deadline: date | None = None
    report_language: Literal["pt-BR", "en"] = "pt-BR"


class ProjectUpdate(BaseModel):
    """Partial update. `version` must match the current one (optimistic lock)."""

    version: int
    title: str | None = Field(default=None, min_length=1, max_length=300)
    question: str | None = Field(default=None, max_length=5000)
    pico: dict[str, Any] | None = None
    prospero: str | None = Field(default=None, max_length=64)
    deadline: date | None = None
    report_language: Literal["pt-BR", "en"] | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    question: str | None
    pico: dict[str, Any]
    prospero: str | None
    deadline: date | None
    report_language: str
    locked_stages: list[str]
    owner_id: uuid.UUID
    version: int
    created_at: datetime
    my_roles: list[Role] = Field(default_factory=list)


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: str
    roles: list[Role]
    is_owner: bool
    version: int


class MemberUpdate(BaseModel):
    version: int
    roles: list[Role]

    _roles = field_validator("roles")(_unique_roles)


class TransferOwnershipIn(BaseModel):
    member_id: uuid.UUID


class InvitationCreate(BaseModel):
    email: EmailStr | None = None
    roles: list[Role]
    expires_in_days: int = Field(default=7, ge=1, le=30)

    _roles = field_validator("roles")(_unique_roles)


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    roles: list[Role]
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class InvitationCreated(InvitationOut):
    link: str


class InvitationPreview(BaseModel):
    project_title: str
    roles: list[Role]
    expires_at: datetime
    email: str | None
