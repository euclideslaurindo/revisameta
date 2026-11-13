import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.email import EmailSender, get_email_sender
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.projects import service
from app.modules.projects.access import ProjectContext, admin_access, member_access
from app.modules.projects.models import Role
from app.modules.projects.schemas import (
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    InvitationPreview,
    MemberOut,
    MemberUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    TransferOwnershipIn,
)

router = APIRouter(tags=["projects"])


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectOut:
    return await service.create_project(session, user, body)


@router.get("/projects")
async def list_projects(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[ProjectOut]:
    """Only projects where the user is a member."""
    return await service.list_projects(session, user)


@router.get("/projects/{project_id}")
async def get_project(ctx: ProjectContext = Depends(member_access)) -> ProjectOut:
    return service.project_out(ctx.project, ctx.member.roles)


@router.patch("/projects/{project_id}")
async def update_project(
    body: ProjectUpdate,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> ProjectOut:
    return await service.update_project(session, ctx, body)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    ctx: ProjectContext = Depends(admin_access), session: AsyncSession = Depends(get_session)
) -> None:
    await service.delete_project(session, ctx)


@router.post("/projects/{project_id}/transfer-ownership")
async def transfer_ownership(
    body: TransferOwnershipIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> ProjectOut:
    return await service.transfer_ownership(session, ctx, body.member_id)


@router.get("/projects/{project_id}/members")
async def list_members(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[MemberOut]:
    return await service.list_members(session, ctx)


@router.patch("/projects/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_member(
    member_id: uuid.UUID,
    body: MemberUpdate,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.update_member_roles(session, ctx, member_id, body.roles, body.version)


@router.delete("/projects/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: uuid.UUID,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.remove_member(session, ctx, member_id)


@router.post("/projects/{project_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    body: InvitationCreate,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
    sender: EmailSender = Depends(get_email_sender),
) -> InvitationCreated:
    """Returns the link so the admin can copy it; also e-mails it when an address is given."""
    invitation, link = await service.create_invitation(session, ctx, body, sender)
    return InvitationCreated(**InvitationOut.model_validate(invitation).model_dump(), link=link)


@router.get("/projects/{project_id}/invitations")
async def list_invitations(
    ctx: ProjectContext = Depends(admin_access), session: AsyncSession = Depends(get_session)
) -> list[InvitationOut]:
    return [InvitationOut.model_validate(i) for i in await service.list_invitations(session, ctx)]


@router.delete(
    "/projects/{project_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.revoke_invitation(session, ctx, invitation_id)


@router.get("/invitations/{token}")
async def preview_invitation(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> InvitationPreview:
    invitation, project = await service.preview_invitation(session, token, user)
    return InvitationPreview(
        project_title=project.title,
        roles=[Role(r) for r in invitation.roles],
        expires_at=invitation.expires_at,
        email=invitation.email,
    )


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectOut:
    return await service.accept_invitation(session, token, user)
