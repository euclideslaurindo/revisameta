import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.i18n import Language, translate
from app.core.security import hash_token, new_opaque_token
from app.db.base import new_id
from app.integrations.email import Email, EmailSender
from app.modules.auth.models import User
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Invitation, Project, ProjectMember, Role
from app.modules.projects.schemas import (
    InvitationCreate,
    MemberOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from app.modules.quotas.service import ensure_can_create_project


def _now() -> datetime:
    return datetime.now(UTC)


def _check_version(current: int, sent: int) -> None:
    if current != sent:
        raise ConflictError()


def project_out(project: Project, roles: list[str]) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    out.my_roles = [Role(r) for r in roles]
    return out


async def create_project(session: AsyncSession, user: User, data: ProjectCreate) -> ProjectOut:
    await ensure_can_create_project(session, user.id)
    project = Project(id=new_id(), owner_id=user.id, created_by=user.id, **data.model_dump())
    session.add(project)
    await session.flush()
    session.add(
        ProjectMember(
            project_id=project.id, user_id=user.id, roles=[Role.ADMIN], created_by=user.id
        )
    )
    await session.commit()
    return project_out(project, [Role.ADMIN])


async def list_projects(session: AsyncSession, user: User) -> list[ProjectOut]:
    rows = await session.execute(
        select(Project, ProjectMember.roles)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    return [project_out(project, roles) for project, roles in rows.all()]


async def update_project(
    session: AsyncSession, ctx: ProjectContext, data: ProjectUpdate
) -> ProjectOut:
    _check_version(ctx.project.version, data.version)
    was_double = ctx.project.double_extraction
    for key, value in data.model_dump(exclude_unset=True, exclude={"version"}).items():
        if value is None and key in {"title", "report_language", "double_extraction", "double_rob"}:
            continue  # required fields: null means "leave as is", never "erase"
        setattr(ctx.project, key, value)
    if was_double and not ctx.project.double_extraction:
        # Studies already extracted once must not get stuck waiting for a second person.
        from app.modules.extraction.consensus import drafts_after_single_mode

        await session.flush()
        await drafts_after_single_mode(session, ctx)
    await session.commit()
    return project_out(ctx.project, ctx.member.roles)


async def delete_project(session: AsyncSession, ctx: ProjectContext) -> None:
    """Soft delete: the project disappears for everyone but nothing is erased."""
    ctx.project.deleted_at = _now()
    await session.commit()


async def list_members(session: AsyncSession, ctx: ProjectContext) -> list[MemberOut]:
    rows = await session.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == ctx.project.id)
        .order_by(ProjectMember.created_at)
    )
    return [
        MemberOut(
            id=member.id,
            user_id=user.id,
            name=user.name,
            email=user.email,
            roles=[Role(r) for r in member.roles],
            is_owner=user.id == ctx.project.owner_id,
            version=member.version,
        )
        for member, user in rows.all()
    ]


async def _get_member(
    session: AsyncSession, ctx: ProjectContext, member_id: uuid.UUID
) -> ProjectMember:
    member = (
        await session.scalars(
            select(ProjectMember).where(
                ProjectMember.id == member_id, ProjectMember.project_id == ctx.project.id
            )
        )
    ).first()
    if member is None:
        raise NotFoundError()
    return member


async def _admin_count(session: AsyncSession, project_id: uuid.UUID) -> int:
    members = await session.scalars(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    return sum(1 for m in members if Role.ADMIN in m.roles)


async def update_member_roles(
    session: AsyncSession,
    ctx: ProjectContext,
    member_id: uuid.UUID,
    roles: list[Role],
    version: int,
) -> None:
    member = await _get_member(session, ctx, member_id)
    _check_version(member.version, version)
    losing_admin = Role.ADMIN in member.roles and Role.ADMIN not in roles
    if losing_admin and member.user_id == ctx.project.owner_id:
        raise AppError("project.creator_cannot_be_removed", status_code=409)
    if losing_admin and await _admin_count(session, ctx.project.id) <= 1:
        raise AppError("project.last_admin", status_code=409)
    member.roles = [r.value for r in roles]
    await session.commit()


async def remove_member(session: AsyncSession, ctx: ProjectContext, member_id: uuid.UUID) -> None:
    member = await _get_member(session, ctx, member_id)
    if member.user_id == ctx.project.owner_id:
        raise AppError("project.creator_cannot_be_removed", status_code=409)
    if Role.ADMIN in member.roles and await _admin_count(session, ctx.project.id) <= 1:
        raise AppError("project.last_admin", status_code=409)
    member.deleted_at = _now()
    await session.commit()


async def transfer_ownership(
    session: AsyncSession, ctx: ProjectContext, member_id: uuid.UUID
) -> ProjectOut:
    """Only the current owner can hand the project over; the new owner becomes admin."""
    if ctx.user.id != ctx.project.owner_id:
        raise AppError("error.forbidden", status_code=403)
    member = await _get_member(session, ctx, member_id)
    if Role.ADMIN not in member.roles:
        member.roles = [Role.ADMIN.value, *member.roles]
    ctx.project.owner_id = member.user_id
    await session.commit()
    return project_out(ctx.project, ctx.member.roles)


def invitation_link(token: str) -> str:
    return f"{get_settings().app_base_url}/convite?token={token}"


async def create_invitation(
    session: AsyncSession, ctx: ProjectContext, data: InvitationCreate, sender: EmailSender
) -> tuple[Invitation, str]:
    token, token_hash = new_opaque_token()
    invitation = Invitation(
        id=new_id(),
        project_id=ctx.project.id,
        email=data.email,
        roles=[r.value for r in data.roles],
        token_hash=token_hash,
        expires_at=_now() + timedelta(days=data.expires_in_days),
        created_by=ctx.user.id,
    )
    session.add(invitation)
    await session.commit()
    link = invitation_link(token)
    if data.email:
        language: Language = "en" if ctx.user.ui_language == "en" else "pt-BR"
        await sender.send(
            Email(
                to=data.email,
                subject=translate("email.invite.subject", language, project=ctx.project.title),
                body=translate(
                    "email.invite.body",
                    language,
                    inviter=ctx.user.name,
                    project=ctx.project.title,
                    link=link,
                    days=data.expires_in_days,
                ),
            )
        )
    return invitation, link


async def list_invitations(session: AsyncSession, ctx: ProjectContext) -> list[Invitation]:
    rows = await session.scalars(
        select(Invitation)
        .where(Invitation.project_id == ctx.project.id)
        .order_by(Invitation.created_at.desc())
    )
    return list(rows)


async def revoke_invitation(
    session: AsyncSession, ctx: ProjectContext, invitation_id: uuid.UUID
) -> None:
    invitation = (
        await session.scalars(
            select(Invitation).where(
                Invitation.id == invitation_id, Invitation.project_id == ctx.project.id
            )
        )
    ).first()
    if invitation is None:
        raise NotFoundError()
    invitation.deleted_at = _now()
    await session.commit()


async def _valid_invitation(session: AsyncSession, token: str, user: User) -> Invitation:
    invitation = (
        await session.scalars(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    ).first()
    if invitation is None:
        raise AppError("auth.invalid_token", status_code=404)
    if invitation.accepted_at is not None:
        raise AppError("invitation.already_accepted", status_code=409)
    if invitation.expires_at < _now():
        raise AppError("invitation.expired", status_code=410)
    if invitation.email and invitation.email.lower() != user.email.lower():
        raise AppError("invitation.wrong_email", status_code=403)
    return invitation


async def preview_invitation(
    session: AsyncSession, token: str, user: User
) -> tuple[Invitation, Project]:
    invitation = await _valid_invitation(session, token, user)
    project = await session.get(Project, invitation.project_id)
    if project is None or project.deleted_at is not None:
        raise AppError("auth.invalid_token", status_code=404)
    return invitation, project


async def accept_invitation(session: AsyncSession, token: str, user: User) -> ProjectOut:
    invitation, project = await preview_invitation(session, token, user)
    member = (
        await session.scalars(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
            )
        )
    ).first()
    if member is None:
        member = ProjectMember(
            project_id=project.id, user_id=user.id, roles=list(invitation.roles), created_by=user.id
        )
        session.add(member)
    else:
        member.roles = [r.value for r in Role if r.value in {*member.roles, *invitation.roles}]
    invitation.accepted_at = _now()
    invitation.accepted_by = user.id
    await session.commit()
    return project_out(project, member.roles)
