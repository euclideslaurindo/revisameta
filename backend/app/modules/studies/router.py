"""Studies: members read; admins and extractors register and organize them."""

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.modules.projects.access import ProjectContext, member_access, project_access
from app.modules.projects.models import Role
from app.modules.studies import importer, service
from app.modules.studies.schemas import (
    MergeIn,
    ReferenceOut,
    ReferenceUpdate,
    ReportCreate,
    StudyCreate,
    StudyOut,
    StudyUpdate,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["studies"])

editor_access = project_access(Role.EXTRACTOR)


async def _read(file: UploadFile) -> bytes:
    content = await file.read(importer.MAX_FILE_BYTES + 1)
    if len(content) > importer.MAX_FILE_BYTES:
        raise AppError(
            "import.too_large", status_code=413, limit=importer.MAX_FILE_BYTES // (1024 * 1024)
        )
    return content


@router.get("/studies")
async def list_studies(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[StudyOut]:
    return await service.list_studies(session, ctx)


@router.post("/studies", status_code=status.HTTP_201_CREATED)
async def create_study(
    body: StudyCreate,
    ctx: ProjectContext = Depends(editor_access),
    session: AsyncSession = Depends(get_session),
) -> StudyOut:
    return await service.create_study(session, ctx, body)


@router.get("/studies/{study_id}")
async def get_study(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> StudyOut:
    return await service.study_out(session, await service.get_study(session, ctx, study_id))


@router.patch("/studies/{study_id}")
async def update_study(
    study_id: uuid.UUID,
    body: StudyUpdate,
    ctx: ProjectContext = Depends(editor_access),
    session: AsyncSession = Depends(get_session),
) -> StudyOut:
    return await service.update_study(session, ctx, study_id, body)


@router.delete("/studies/{study_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_study(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(project_access(Role.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_study(session, ctx, study_id)


@router.post("/studies/{study_id}/reports", status_code=status.HTTP_201_CREATED)
async def add_report(
    study_id: uuid.UUID,
    body: ReportCreate,
    ctx: ProjectContext = Depends(editor_access),
    session: AsyncSession = Depends(get_session),
) -> StudyOut:
    """Another article about the same patients."""
    return await service.add_report(session, ctx, study_id, body.reference, body.is_primary)


@router.delete("/studies/{study_id}/reports/{report_id}")
async def remove_report(
    study_id: uuid.UUID,
    report_id: uuid.UUID,
    ctx: ProjectContext = Depends(editor_access),
    session: AsyncSession = Depends(get_session),
) -> StudyOut:
    return await service.remove_report(session, ctx, study_id, report_id)


@router.post("/studies/{study_id}/merge")
async def merge_studies(
    study_id: uuid.UUID,
    body: MergeIn,
    ctx: ProjectContext = Depends(editor_access),
    session: AsyncSession = Depends(get_session),
) -> StudyOut:
    return await service.merge_studies(session, ctx, study_id, body.other_study_id)


@router.patch("/references/{reference_id}")
async def update_reference(
    reference_id: uuid.UUID,
    body: ReferenceUpdate,
    ctx: ProjectContext = Depends(editor_access),
    session: AsyncSession = Depends(get_session),
) -> ReferenceOut:
    return await service.update_reference(session, ctx, reference_id, body)


@router.post("/study-imports/preview")
async def preview_import(
    file: UploadFile = File(...),
    _ctx: ProjectContext = Depends(editor_access),
) -> importer.Preview:
    """Columns, a sample and a suggested mapping. Nothing is saved."""
    return importer.preview(file.filename or "", await _read(file))


@router.post("/study-imports")
async def run_import(
    file: UploadFile = File(...),
    mapping: str = Form(..., description='JSON: {"title": "Column name", ...}'),
    dry_run: bool = Form(True),
    ctx: ProjectContext = Depends(editor_access),
    session: AsyncSession = Depends(get_session),
) -> importer.ImportReport:
    """Validates every row; with dry_run=false imports the valid rows and reports the rest."""
    try:
        parsed = json.loads(mapping)
    except json.JSONDecodeError as exc:
        raise AppError("import.invalid_mapping", status_code=422) from exc
    if not isinstance(parsed, dict) or not all(isinstance(v, str) for v in parsed.values()):
        raise AppError("import.invalid_mapping", status_code=422)
    return await importer.run(session, ctx, file.filename or "", await _read(file), parsed, dry_run)
