"""Import of an existing consolidated risk-of-bias table (docs/modulos.md 7.2, stage 2 step 6).

For projects already under way: the group's table (robvis format, or any CSV/XLSX
with a column mapping) becomes "imported" assessments, marked as such in every screen
and export (data model decision 7).

- Same two calls as the study list import: `preview` (columns, sample, suggested
  mapping) and `run` (dry run or for real), with errors per row; invalid rows are
  skipped, valid rows are imported together.
- Each row belongs to a study that already exists in the project, found by its label.
  Studies are never created here.
- Values must be levels of the instrument (or its answers, for checklists), written as
  the system shows them in Portuguese or English, as robvis writes them, or as the
  internal codes. Anything else is an error on that row, never a guess.
- Nothing is overwritten: a study that already has a consensus or an import for that
  result, or another confirmed instrument, is refused with the reason.
"""

import re
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Stage
from app.modules.projects.stages import ensure_open
from app.modules.protocol.models import Outcome
from app.modules.risk_of_bias import consolidated
from app.modules.risk_of_bias.catalog import Template
from app.modules.risk_of_bias.models import (
    RobAnswer,
    RobAssessment,
    RobJudgement,
    RobStudyTool,
    RobTool,
)
from app.modules.risk_of_bias.rules import group_levels
from app.modules.studies.importer import (
    MAX_ROWS,
    SAMPLE_ROWS,
    ImportReport,
    RowError,
    _plain,
    read_table,
)
from app.modules.studies.models import Study

STUDY = "study"
OVERALL = "overall"
OVERALL_JUSTIFICATION = "overall_justification"

# Extra spellings people use for the same level (robvis web, Cochrane tables).
SYNONYMS: dict[str, str] = {
    "some concern": "some_concerns",
    "algumas preocupacoes": "some_concerns",
    "ni": "no_information",
    "no info": "no_information",
    "sem info": "no_information",
    "serio": "serious",
    "very high": "very_high",
    "sim": "Y",
    "yes": "Y",
    "nao": "N",
    "no": "N",
    "incerto": "U",
    "unclear": "U",
    "n/a": "NA",
    "na": "NA",
    "nao se aplica": "NA",
    "not applicable": "NA",
}


class TargetColumn(BaseModel):
    key: str
    short: str
    name: dict[str, str]
    required: bool


class RobPreview(BaseModel):
    columns: list[str]
    sample: list[list[str | None]]
    row_count: int
    targets: list[TargetColumn]
    suggested_mapping: dict[str, str]


def _clean(value: str) -> str:
    text = _plain(value)
    text = re.sub(r"\b(risk of bias|risco de vies|risk|risco)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_level(value: str, allowed: list[str]) -> str | None:
    """The level of `allowed` that a spreadsheet cell means, or None."""
    wanted = _clean(value)
    if not wanted:
        return None
    for key in allowed:
        spellings = {_clean(key), _clean(key.replace("_", " "))}
        for lang in consolidated.OUTPUT_LANGS:
            spellings.add(_clean(consolidated.level_label(key, lang)))
        if wanted in spellings:
            return key
    synonym = SYNONYMS.get(wanted)
    return synonym if synonym in allowed else None


async def _tool(session: AsyncSession, ctx: ProjectContext, tool_id: uuid.UUID) -> RobTool:
    tool = (
        await session.scalars(
            select(RobTool).where(RobTool.id == tool_id, RobTool.project_id == ctx.project.id)
        )
    ).first()
    if tool is None:
        raise NotFoundError()
    return tool


def _targets(template: Template) -> list[TargetColumn]:
    columns = consolidated._columns(template)
    by_question = template.judgement.kind == "group_rule"
    out = [TargetColumn(key=STUDY, short=STUDY, name={}, required=True)]
    out += [
        TargetColumn(key=c.key, short=c.short, name=c.name, required=not by_question)
        for c in columns
    ]
    out += [
        TargetColumn(key=OVERALL, short=OVERALL, name={}, required=True),
        TargetColumn(
            key=OVERALL_JUSTIFICATION, short=OVERALL_JUSTIFICATION, name={}, required=False
        ),
    ]
    return out


_HEADER_HINTS = {
    STUDY: ("study", "estudo", "author", "autor", "study id"),
    OVERALL: ("overall", "geral", "julgamento geral", "overall judgement", "overall risk of bias"),
    OVERALL_JUSTIFICATION: ("justification", "justificativa", "comments", "comentarios"),
}


def suggest_mapping(columns: list[str], targets: list[TargetColumn]) -> dict[str, str]:
    plain = {c: _plain(c) for c in columns}
    mapping: dict[str, str] = {}
    for target in targets:
        hints = set(_HEADER_HINTS.get(target.key, ()))
        if target.key not in _HEADER_HINTS:
            hints |= {_plain(target.short)}
            hints |= {_plain(n) for n in target.name.values()}
            hints.add(_plain(target.key))
        for column, value in plain.items():
            if column not in mapping.values() and value in hints:
                mapping[target.key] = column
                break
    return mapping


async def preview(
    session: AsyncSession, ctx: ProjectContext, tool_id: uuid.UUID, filename: str, content: bytes
) -> RobPreview:
    tool = await _tool(session, ctx, tool_id)
    targets = _targets(Template.model_validate(tool.structure))
    table = read_table(filename, content)
    sample: list[list[str | None]] = []
    count = 0
    for row in table.rows:
        if not any(row):
            continue
        count += 1
        if len(sample) < SAMPLE_ROWS:
            sample.append(row)
    return RobPreview(
        columns=table.columns,
        sample=sample,
        row_count=count,
        targets=targets,
        suggested_mapping=suggest_mapping(table.columns, targets),
    )


def _allowed(template: Template, tool: RobTool, key: str) -> list[str]:
    if key == OVERALL:
        if template.judgement.kind == "group_rule":
            return group_levels(tool.overall_rule)
        return list(template.judgement.levels)
    if template.judgement.kind == "group_rule":
        domain_key, question_key = key.split(".", 1)
        domain = next(d for d in template.domains if d.key == domain_key)
        question = next(q for q in domain.questions if q.key == question_key)
        return list(template.answer_sets[question.answers])
    return list(template.judgement.levels)


async def run(
    session: AsyncSession,
    ctx: ProjectContext,
    *,
    tool_id: uuid.UUID,
    outcome_id: uuid.UUID | None,
    timepoint: str | None,
    filename: str,
    content: bytes,
    mapping: dict[str, str],
    dry_run: bool,
) -> ImportReport:
    if not ctx.is_admin:
        raise ForbiddenError()
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    tool = await _tool(session, ctx, tool_id)
    template = Template.model_validate(tool.structure)
    targets = {t.key: t for t in _targets(template)}
    if any(k not in targets for k in mapping) or any(
        t.required and t.key not in mapping for t in targets.values()
    ):
        raise AppError("rob_import.invalid_mapping", status_code=422)
    answer_target: tuple[uuid.UUID | None, str | None] = (None, None)
    if consolidated.needs_target(template):
        outcome = (
            await session.scalars(
                select(Outcome).where(
                    Outcome.id == outcome_id, Outcome.project_id == ctx.project.id
                )
            )
        ).first()
        if outcome is None or not timepoint or timepoint not in outcome.timepoints:
            raise AppError("rob.result_required", status_code=422)
        answer_target = (outcome_id, timepoint)
    # Per-result instruments are assessed per result; checklists once per study, with
    # the questions of outcome or result level answered for the result chosen here.
    target = answer_target if template.scope == "result" else (None, None)
    question_level = {f"{d.key}.{q.key}": q.level for d in template.domains for q in d.questions}

    table = read_table(filename, content)
    index = {c: i for i, c in enumerate(table.columns)}
    if any(column not in index for column in mapping.values()):
        raise AppError("rob_import.invalid_mapping", status_code=422)

    studies = {
        _plain(s.label): s
        for s in await session.scalars(
            select(Study).where(Study.project_id == ctx.project.id, Study.deleted_at.is_(None))
        )
    }
    chosen = {
        c.study_id: c.tool_id
        for c in await session.scalars(
            select(RobStudyTool).where(RobStudyTool.project_id == ctx.project.id)
        )
    }
    finals = {
        a.study_id
        for a in await session.scalars(
            select(RobAssessment).where(
                RobAssessment.project_id == ctx.project.id,
                RobAssessment.tool_id == tool.id,
                RobAssessment.kind.in_(consolidated.FINAL_KINDS),
            )
        )
        if (a.outcome_id, a.timepoint) == target
    }

    errors: list[RowError] = []
    seen: set[uuid.UUID] = set()
    total = valid = 0
    now = datetime.now(UTC)
    for offset, row in enumerate(table.rows, start=2):
        if not any(row):
            continue
        total += 1
        if total > MAX_ROWS:
            raise AppError("import.too_many_rows", status_code=413, limit=MAX_ROWS)
        cell = {
            key: (row[index[column]] if index[column] < len(row) else None)
            for key, column in mapping.items()
        }
        row_errors: list[RowError] = []

        def fail(
            field: str | None, code: str, _row: int = offset, _out: list[RowError] = row_errors
        ) -> None:
            _out.append(RowError(row=_row, field=field, code=code))

        study = studies.get(_plain(cell.get(STUDY) or ""))
        if study is None:
            fail(STUDY, "rob_import.unknown_study")
        elif study.id in seen:
            fail(STUDY, "rob_import.duplicate_study")
        elif chosen.get(study.id) not in (None, tool.id):
            fail(STUDY, "rob_import.other_tool")
        elif study.id in finals:
            fail(STUDY, "rob_import.already_assessed")

        levels: dict[str, str | None] = {}
        for key in mapping:
            if key in (STUDY, OVERALL_JUSTIFICATION):
                continue
            raw = cell.get(key)
            if raw is None:
                if targets[key].required:
                    fail(key, "rob_import.missing_value")
                levels[key] = None
                continue
            level = parse_level(raw, _allowed(template, tool, key))
            if level is None:
                fail(key, "rob_import.unknown_value")
            levels[key] = level

        if row_errors:
            errors.extend(row_errors)
            continue
        assert study is not None  # noqa: S101 - checked above
        seen.add(study.id)
        valid += 1
        if dry_run:
            continue
        if study.id not in chosen:
            session.add(
                RobStudyTool(
                    project_id=ctx.project.id,
                    created_by=ctx.user.id,
                    study_id=study.id,
                    tool_id=tool.id,
                    confirmed_by=ctx.user.id,
                )
            )
            chosen[study.id] = tool.id
        assessment = RobAssessment(
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            study_id=study.id,
            tool_id=tool.id,
            outcome_id=target[0],
            timepoint=target[1],
            kind="imported",
            reviewer_id=None,
            status="submitted",
            variants={},
            submitted_by=ctx.user.id,
            submitted_at=now,
        )
        session.add(assessment)
        await session.flush()
        for key, level in levels.items():
            if key == OVERALL:
                session.add(
                    RobJudgement(
                        project_id=ctx.project.id,
                        created_by=ctx.user.id,
                        assessment_id=assessment.id,
                        domain_key=None,
                        final=level,
                        justification=cell.get(OVERALL_JUSTIFICATION),
                    )
                )
            elif template.judgement.kind == "group_rule":
                if level is not None:
                    session.add(
                        RobAnswer(
                            project_id=ctx.project.id,
                            created_by=ctx.user.id,
                            assessment_id=assessment.id,
                            question_key=key,
                            outcome_id=None
                            if question_level[key] == "study" or template.scope == "result"
                            else answer_target[0],
                            timepoint=answer_target[1]
                            if question_level[key] == "result" and template.scope == "study"
                            else None,
                            answer=level,
                        )
                    )
            else:
                session.add(
                    RobJudgement(
                        project_id=ctx.project.id,
                        created_by=ctx.user.id,
                        assessment_id=assessment.id,
                        domain_key=key,
                        final=level,
                    )
                )
    if not dry_run and valid:
        await session.commit()
    return ImportReport(
        dry_run=dry_run,
        total_rows=total,
        valid_rows=valid,
        created=0 if dry_run else valid,
        errors=errors,
    )
