"""PRISMA 2020 checklist (docs/modulos.md 7.9; stage 5 step 7).

The group records, for each item, where the manuscript reports it (or that it does not
apply). The system says which items it already has data for ("has_data"), so nobody
forgets them, but it never marks an item as reported: only a person knows what the
manuscript says.
"""

import io
from datetime import UTC, datetime
from typing import Any, Literal

from docx import Document
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.modules.analysis.models import Analysis
from app.modules.exports.extraction import _slug
from app.modules.extraction.models import Extraction
from app.modules.prisma import abstract_items
from app.modules.prisma.checklist_items import CITATION, CODES, ITEMS, SOURCE, Item
from app.modules.prisma.models import PrismaChecklistItem
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.protocol.models import Outcome
from app.modules.references.models import Search
from app.modules.risk_of_bias.models import RobAssessment
from app.modules.screening.models import ScreeningDecision
from app.modules.studies.models import Study

EDITORS = {Role.ADMIN, Role.REVIEWER, Role.EXTRACTOR, Role.STATISTICIAN}
Lang = Literal["pt-BR", "en"]
Kind = Literal["prisma2020", "abstracts"]
KINDS: dict[str, tuple[list[Item], list[str], str]] = {
    "prisma2020": (ITEMS, CODES, SOURCE),
    "abstracts": (abstract_items.ITEMS, abstract_items.CODES, abstract_items.SOURCE),
}


class ChecklistRow(BaseModel):
    code: str
    section: str
    topic: dict[str, str]
    summary: dict[str, str]
    status: str  # pending | reported | not_applicable
    location: str | None
    has_data: bool  # the system has data for this item (a hint, not a decision)
    version: int | None


class ChecklistOut(BaseModel):
    rows: list[ChecklistRow]
    reported: int
    not_applicable: int
    pending: int
    source: str
    citation: str


class ChecklistIn(BaseModel):
    status: Literal["pending", "reported", "not_applicable"]
    location: str | None = Field(default=None, max_length=500)
    version: int | None = None


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    return await session.scalar(select(func.count()).select_from(model).where(*where)) or 0  # type: ignore[arg-type]


async def _hints(session: AsyncSession, ctx: ProjectContext) -> set[str]:
    pid = ctx.project.id
    found = set()
    if ctx.project.question:
        found.add("question")
    if ctx.project.prospero:
        found.add("prospero")
    searches = list(await session.scalars(select(Search).where(Search.project_id == pid)))
    if searches:
        found.add("searches")
        found.add("flow")
    if any(s.strategy for s in searches):
        found.add("strategy")
    if await _count(session, ScreeningDecision, ScreeningDecision.project_id == pid):
        found.add("screening")
    if await _count(
        session,
        ScreeningDecision,
        ScreeningDecision.project_id == pid,
        ScreeningDecision.exclusion_reason_id.is_not(None),
    ):
        found.add("exclusions")
    if await _count(session, Extraction, Extraction.project_id == pid):
        found.add("extraction")
    if await _count(session, Outcome, Outcome.project_id == pid):
        found.add("outcomes")
    if await _count(session, RobAssessment, RobAssessment.project_id == pid):
        found.add("risk_of_bias")
    if await _count(session, Study, Study.project_id == pid):
        found.add("studies")
        found.add("flow")
    if await _count(session, Analysis, Analysis.project_id == pid):
        found |= {"analyses", "r_script"}
    return found


async def checklist(
    session: AsyncSession, ctx: ProjectContext, kind: Kind = "prisma2020"
) -> ChecklistOut:
    items, codes, source = KINDS[kind]
    saved = {
        r.item_code: r
        for r in await session.scalars(
            select(PrismaChecklistItem).where(
                PrismaChecklistItem.project_id == ctx.project.id,
                PrismaChecklistItem.item_code.in_(codes),
            )
        )
    }
    hints = await _hints(session, ctx)
    rows = [
        ChecklistRow(
            code=item["code"],
            section=item["section"],
            topic=item["topic"],
            summary=item["summary"],
            status=saved[item["code"]].status if item["code"] in saved else "pending",
            location=saved[item["code"]].location if item["code"] in saved else None,
            has_data=item["hint"] in hints if item["hint"] else False,
            version=saved[item["code"]].version if item["code"] in saved else None,
        )
        for item in items
    ]
    statuses = [r.status for r in rows]
    return ChecklistOut(
        rows=rows,
        reported=statuses.count("reported"),
        not_applicable=statuses.count("not_applicable"),
        pending=statuses.count("pending"),
        source=source,
        citation=CITATION,
    )


async def record(
    session: AsyncSession, ctx: ProjectContext, code: str, data: ChecklistIn
) -> ChecklistRow:
    kind: Kind = "abstracts" if code in abstract_items.CODES else "prisma2020"
    if not (EDITORS & ctx.roles):
        raise ForbiddenError()
    if code not in KINDS[kind][1]:
        raise NotFoundError()
    row = (
        await session.scalars(
            select(PrismaChecklistItem).where(
                PrismaChecklistItem.project_id == ctx.project.id,
                PrismaChecklistItem.item_code == code,
            )
        )
    ).first()
    location = (data.location or "").strip() or None
    if row is None:
        if data.version is not None:
            raise ConflictError()
        row = PrismaChecklistItem(
            project_id=ctx.project.id,
            item_code=code,
            status=data.status,
            location=location,
            created_by=ctx.user.id,
        )
        session.add(row)
    else:
        if data.version != row.version:
            raise ConflictError()
        row.status, row.location = data.status, location
    await session.commit()
    out = await checklist(session, ctx, kind)
    return next(r for r in out.rows if r.code == code)


TEXTS: dict[str, dict[str, Any]] = {
    "pt-BR": {
        "title": "Checklist PRISMA 2020",
        "intro": "Resumo de cada item escrito pelo RevisaMeta; consulte o texto oficial em",
        "cols": ("Item", "Tópico", "O que relatar (resumo)", "Onde no manuscrito"),
        "status": {"pending": "pendente", "reported": "", "not_applicable": "não se aplica"},
        "sections": {
            "title": "Título",
            "abstract": "Resumo",
            "introduction": "Introdução",
            "methods": "Métodos",
            "results": "Resultados",
            "discussion": "Discussão",
            "other": "Outras informações",
            "background": "Introdução",
        },
        "file": "prisma-checklist",
    },
    "en": {
        "title": "PRISMA 2020 checklist",
        "intro": "Summary of each item written by RevisaMeta; see the official wording at",
        "cols": ("Item", "Topic", "What to report (summary)", "Location in the manuscript"),
        "status": {"pending": "pending", "reported": "", "not_applicable": "not applicable"},
        "sections": {
            "title": "Title",
            "abstract": "Abstract",
            "introduction": "Introduction",
            "methods": "Methods",
            "results": "Results",
            "discussion": "Discussion",
            "other": "Other information",
            "background": "Background",
        },
        "file": "prisma-checklist",
    },
}


async def docx(
    session: AsyncSession, ctx: ProjectContext, lang: Lang, kind: Kind = "prisma2020"
) -> tuple[bytes, str]:
    out = await checklist(session, ctx, kind)
    t = TEXTS[lang]
    doc = Document()
    doc.add_heading(t["title"], level=1)
    doc.add_paragraph(f"{t['intro']} {out.source}")
    doc.add_paragraph(CITATION)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, t["cols"], strict=True):
        cell.text = text
    section = None
    for r in out.rows:
        if r.section != section:
            section = r.section
            cells = table.add_row().cells
            cells[0].merge(cells[3]).text = t["sections"][section]
        cells = table.add_row().cells
        cells[0].text = r.code
        cells[1].text = r.topic[lang]
        cells[2].text = r.summary[lang]
        status = t["status"][r.status]
        cells[3].text = r.location or status if r.status != "not_applicable" else status
    buffer = io.BytesIO()
    doc.save(buffer)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    name = t["file"] if kind == "prisma2020" else "prisma-abstracts-checklist"
    return buffer.getvalue(), f"{_slug(ctx.project.title)}_{name}_{day}.docx"
