"""Instruments of a project: enabling templates, pasting official text, choosing per study.

- Admins enable instruments from the catalog (a frozen copy with its version).
- The official wording of each question is pasted by the admin (never shipped).
- Each study gets an instrument suggested by its design; only an admin confirms it.
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Stage
from app.modules.projects.stages import ensure_open
from app.modules.risk_of_bias.catalog import FAMILY_PREFERENCE, Template, catalog
from app.modules.risk_of_bias.models import RobAssessment, RobStudyTool, RobTool
from app.modules.risk_of_bias.rules import GroupRule, check_rule
from app.modules.studies.service import get_study

# ---- Schemas -------------------------------------------------------------------------


class CatalogItem(BaseModel):
    key: str
    family: str
    name: dict[str, str]
    version: str
    citation: str
    source_url: str
    designs: list[str]
    scope: str
    domains: int
    questions: int


class ToolOut(BaseModel):
    id: uuid.UUID
    template_key: str
    family: str
    template_version: str
    structure: dict[str, Any]
    texts: dict[str, str]
    overall_rule: dict[str, Any] | None
    texts_filled: int
    questions: int
    version: int


class EnableIn(BaseModel):
    template_key: str = Field(min_length=1, max_length=40)


class TextsIn(BaseModel):
    version: int
    # "domain.question" -> official wording pasted by the admin (null/"" clears it)
    texts: dict[str, str | None]


class GenericDomainIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    questions: int = Field(ge=1, le=40)


class GenericStructureIn(BaseModel):
    version: int
    domains: list[GenericDomainIn] = Field(min_length=1, max_length=20)


class StudyToolOut(BaseModel):
    study_id: uuid.UUID
    design: str
    suggested_tool_id: uuid.UUID | None
    tool_id: uuid.UUID | None
    confirmed: bool


class StudyToolIn(BaseModel):
    tool_id: uuid.UUID


MAX_TEXT = 4000


# ---- Helpers -------------------------------------------------------------------------


def _require_admin(ctx: ProjectContext) -> None:
    if not ctx.is_admin:
        raise ForbiddenError()


def _template_of(tool: RobTool) -> Template:
    return Template.model_validate(tool.structure)


def tool_out(tool: RobTool) -> ToolOut:
    keys = _template_of(tool).question_keys()
    return ToolOut(
        id=tool.id,
        template_key=tool.template_key,
        family=tool.family,
        template_version=tool.template_version,
        structure=tool.structure,
        texts=tool.texts or {},
        overall_rule=tool.overall_rule,
        texts_filled=len([k for k in keys if (tool.texts or {}).get(k)]),
        questions=len(keys),
        version=tool.version,
    )


def catalog_items() -> list[CatalogItem]:
    order = {family: i for i, family in enumerate(FAMILY_PREFERENCE)}
    templates = sorted(catalog().values(), key=lambda t: (order.get(t.family, 99), t.name.pt_br))
    return [
        CatalogItem(
            key=t.key,
            family=t.family,
            name=t.name.model_dump(by_alias=True),
            version=t.version,
            citation=t.citation,
            source_url=t.source_url,
            designs=t.designs,
            scope=t.scope,
            domains=len(t.domains),
            questions=sum(len(d.questions) for d in t.domains),
        )
        for t in templates
    ]


async def project_tools(session: AsyncSession, ctx: ProjectContext) -> list[RobTool]:
    return list(
        await session.scalars(
            select(RobTool).where(RobTool.project_id == ctx.project.id).order_by(RobTool.created_at)
        )
    )


async def get_tool(session: AsyncSession, ctx: ProjectContext, tool_id: uuid.UUID) -> RobTool:
    tool = (
        await session.scalars(
            select(RobTool).where(RobTool.id == tool_id, RobTool.project_id == ctx.project.id)
        )
    ).first()
    if tool is None:
        raise NotFoundError()
    return tool


# ---- Enabling and editing instruments --------------------------------------------------


async def enable(session: AsyncSession, ctx: ProjectContext, data: EnableIn) -> ToolOut:
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    template = catalog().get(data.template_key)
    if template is None:
        raise AppError("rob.unknown_template", status_code=422)
    existing = [
        t
        for t in await project_tools(session, ctx)
        if t.template_key == template.key and t.template_version == template.version
    ]
    if existing:
        raise AppError("rob.already_enabled", status_code=409)
    tool = RobTool(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        template_key=template.key,
        family=template.family,
        template_version=template.version,
        structure=template.model_dump(by_alias=True),
        texts={},
    )
    session.add(tool)
    await session.commit()
    return tool_out(tool)


async def set_texts(
    session: AsyncSession, ctx: ProjectContext, tool_id: uuid.UUID, data: TextsIn
) -> ToolOut:
    """Stores the official wording pasted by the admin (only for known questions)."""
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    tool = await get_tool(session, ctx, tool_id)
    if tool.version != data.version:
        raise ConflictError()
    keys = set(_template_of(tool).question_keys())
    texts = dict(tool.texts or {})
    for key, value in data.texts.items():
        if key not in keys:
            raise AppError("rob.unknown_question", status_code=422, key=key)
        text = (value or "").strip()
        if len(text) > MAX_TEXT:
            raise AppError("rob.text_too_long", status_code=422, key=key)
        if text:
            texts[key] = text
        else:
            texts.pop(key, None)
    tool.texts = texts
    await session.commit()
    return tool_out(tool)


async def set_generic_structure(
    session: AsyncSession, ctx: ProjectContext, tool_id: uuid.UUID, data: GenericStructureIn
) -> ToolOut:
    """The generic instrument: the group names its domains and how many questions each has."""
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    tool = await get_tool(session, ctx, tool_id)
    if tool.family != "generic":
        raise AppError("rob.not_generic", status_code=422)
    if tool.version != data.version:
        raise ConflictError()
    if await _has_assessments(session, RobAssessment.tool_id == tool.id):
        raise AppError("rob.tool_in_use", status_code=409)
    structure = dict(tool.structure)
    structure["domains"] = [
        {
            "key": f"d{i}",
            "name": {"pt-BR": d.name.strip(), "en": d.name.strip()},
            "questions": [
                {"key": str(n), "answers": "generic", "level": "study"}
                for n in range(1, d.questions + 1)
            ],
        }
        for i, d in enumerate(data.domains, start=1)
    ]
    Template.model_validate(structure)
    tool.structure = structure
    keys = set(Template.model_validate(structure).question_keys())
    tool.texts = {k: v for k, v in (tool.texts or {}).items() if k in keys}
    await session.commit()
    return tool_out(tool)


class OverallRuleIn(BaseModel):
    version: int
    rule: dict[str, Any] | None  # None removes the rule: the overall judgement is free


async def _has_assessments(session: AsyncSession, condition: Any) -> bool:
    found = await session.scalar(select(RobAssessment.id).where(condition).limit(1))
    return found is not None


async def set_overall_rule(
    session: AsyncSession, ctx: ProjectContext, tool_id: uuid.UUID, data: OverallRuleIn
) -> ToolOut:
    """The group's rule for the overall judgement (JBI, Newcastle-Ottawa, generic)."""
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    tool = await get_tool(session, ctx, tool_id)
    template = _template_of(tool)
    if template.judgement.kind != "group_rule":
        raise AppError("rob.has_official_rule", status_code=422)
    if tool.version != data.version:
        raise ConflictError()
    if data.rule is None:
        tool.overall_rule = None
    else:
        try:
            rule = GroupRule.model_validate(data.rule)
            check_rule(rule, template)
        except ValueError as exc:
            raise AppError("rob.invalid_rule", status_code=422) from exc
        tool.overall_rule = rule.model_dump(by_alias=True)
    await session.commit()
    return tool_out(tool)


# ---- Instrument of each study --------------------------------------------------------


def suggest(design: str, tools: list[RobTool]) -> RobTool | None:
    """The enabled instrument that fits the design, by family preference."""
    fitting = [t for t in tools if design in _template_of(t).designs]
    if not fitting:
        fitting = [t for t in tools if t.family == "generic"]
    order = {family: i for i, family in enumerate(FAMILY_PREFERENCE)}
    fitting.sort(key=lambda t: (order.get(t.family, 99), t.created_at))
    return fitting[0] if fitting else None


async def _choice(session: AsyncSession, study_id: uuid.UUID) -> RobStudyTool | None:
    return (
        await session.scalars(select(RobStudyTool).where(RobStudyTool.study_id == study_id))
    ).first()


async def study_tool(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID
) -> StudyToolOut:
    study = await get_study(session, ctx, study_id)
    tools = await project_tools(session, ctx)
    suggestion = suggest(study.design, tools)
    choice = await _choice(session, study.id)
    return StudyToolOut(
        study_id=study.id,
        design=study.design,
        suggested_tool_id=suggestion.id if suggestion else None,
        tool_id=choice.tool_id if choice else None,
        confirmed=choice is not None,
    )


async def confirm_study_tool(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID, data: StudyToolIn
) -> StudyToolOut:
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    study = await get_study(session, ctx, study_id)
    tool = await get_tool(session, ctx, data.tool_id)
    choice = await _choice(session, study.id)
    if (
        choice is not None
        and choice.tool_id != tool.id
        and await _has_assessments(session, RobAssessment.study_id == study.id)
    ):
        raise AppError("rob.study_has_assessments", status_code=409)
    if choice is None:
        session.add(
            RobStudyTool(
                project_id=ctx.project.id,
                created_by=ctx.user.id,
                study_id=study.id,
                tool_id=tool.id,
                confirmed_by=ctx.user.id,
            )
        )
    else:
        choice.tool_id = tool.id
        choice.confirmed_by = ctx.user.id
    await session.commit()
    return await study_tool(session, ctx, study_id)
