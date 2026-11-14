"""Export of the extracted data, XLSX or CSV (docs/modulos.md 7.10).

Rules (lesson L2, never export blank in silence):
- `consensus` mode exports only submitted (or locked) consensus extractions. Studies
  left out are listed, and the export is refused until the user acknowledges them.
- `individual` mode exports every extractor's own extraction, marked
  "pre-consensus" and identified by extractor (admins only: it breaks blinding).
- CSV for Excel in Portuguese: `;`, decimal comma, UTF-8 with BOM. CSV for R: `,`,
  decimal point, UTF-8. The XLSX has every table; the CSV has the data table.

Numbers are exported exactly as typed; nothing is computed here.
"""

import csv
import io
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError
from app.modules.auth.models import User
from app.modules.exports.labels import LANGS, label
from app.modules.extraction.comparison import number_text
from app.modules.extraction.models import (
    AlertStatus,
    CheckAlert,
    Extraction,
    ExtractionKind,
    ExtractionStatus,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.extraction.schemas import FormSchema
from app.modules.extraction.service import current_form
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Stage
from app.modules.projects.stages import is_locked
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.studies.models import Study

Cell = str | int | float | Decimal | None


class ExportMode(StrEnum):
    CONSENSUS = "consensus"
    INDIVIDUAL = "individual"


class FileFormat(StrEnum):
    XLSX = "xlsx"
    CSV = "csv"


class CsvStyle(StrEnum):
    EXCEL = "excel"  # Portuguese Excel: ";" and decimal comma, UTF-8 with BOM
    R = "r"  # "," and decimal point


class MissingStudy(BaseModel):
    study_id: uuid.UUID
    label: str
    reason: str  # no_consensus | consensus_draft | no_extraction


class ExportStatus(BaseModel):
    total: int
    ready: int
    missing: list[MissingStudy]
    locked: bool
    individual_allowed: bool


@dataclass
class Source:
    study: Study
    extraction: Extraction
    origin: str  # consensus | individual
    extractor: str | None


@dataclass
class Table:
    name: str
    header: list[str]
    rows: list[list[Cell]] = field(default_factory=list)


# ---- What goes in the file -----------------------------------------------------------


async def _studies(session: AsyncSession, ctx: ProjectContext) -> list[Study]:
    return list(
        await session.scalars(
            select(Study).where(Study.project_id == ctx.project.id).order_by(Study.label)
        )
    )


async def _extractions_by_study(
    session: AsyncSession, ctx: ProjectContext
) -> dict[uuid.UUID, list[Extraction]]:
    rows = await session.scalars(
        select(Extraction)
        .where(Extraction.project_id == ctx.project.id)
        .order_by(Extraction.created_at)
    )
    out: dict[uuid.UUID, list[Extraction]] = {}
    for e in rows:
        out.setdefault(e.study_id, []).append(e)
    return out


async def _sources(
    session: AsyncSession, ctx: ProjectContext, mode: ExportMode
) -> tuple[list[Source], list[MissingStudy]]:
    studies = await _studies(session, ctx)
    by_study = await _extractions_by_study(session, ctx)
    ids = {e.extractor_id for es in by_study.values() for e in es if e.extractor_id}
    names = (
        {u.id: u.name for u in await session.scalars(select(User).where(User.id.in_(ids)))}
        if ids
        else {}
    )
    sources: list[Source] = []
    missing: list[MissingStudy] = []
    for study in studies:
        extractions = by_study.get(study.id, [])
        if mode == ExportMode.CONSENSUS:
            consensus = next((e for e in extractions if e.kind == ExtractionKind.CONSENSUS), None)
            if consensus is None:
                missing.append(
                    MissingStudy(study_id=study.id, label=study.label, reason="no_consensus")
                )
            elif consensus.status == ExtractionStatus.DRAFT:
                missing.append(
                    MissingStudy(study_id=study.id, label=study.label, reason="consensus_draft")
                )
            else:
                sources.append(Source(study, consensus, "consensus", None))
        else:
            individuals = [e for e in extractions if e.kind == ExtractionKind.INDIVIDUAL]
            if not individuals:
                missing.append(
                    MissingStudy(study_id=study.id, label=study.label, reason="no_extraction")
                )
            for e in individuals:
                name = names.get(e.extractor_id) if e.extractor_id else None
                sources.append(Source(study, e, "individual", name))
    return sources, missing


async def export_status(session: AsyncSession, ctx: ProjectContext) -> ExportStatus:
    sources, missing = await _sources(session, ctx, ExportMode.CONSENSUS)
    return ExportStatus(
        total=len(sources) + len(missing),
        ready=len(sources),
        missing=missing,
        locked=is_locked(ctx, Stage.EXTRACTION),
        individual_allowed=ctx.is_admin,
    )


def _yes_no(lang: str, value: bool | None) -> str | None:
    if value is None:
        return None
    return label(lang, "yes" if value else "no")


def _code(lang: str, prefix: str, value: str | None) -> str | None:
    return label(lang, f"{prefix}.{value}") if value else None


async def build_tables(
    session: AsyncSession,
    ctx: ProjectContext,
    sources: list[Source],
    missing: list[MissingStudy],
    mode: ExportMode,
    lang: str,
) -> list[Table]:
    form = FormSchema.model_validate((await current_form(session, ctx)).schema)
    outcomes = {
        o.id: o
        for o in await session.scalars(select(Outcome).where(Outcome.project_id == ctx.project.id))
    }
    groups = {
        g.id: g.label
        for g in await session.scalars(
            select(ComparisonGroup).where(ComparisonGroup.project_id == ctx.project.id)
        )
    }

    def t(key: str, **params: Any) -> str:
        return label(lang, key, **params)

    readme = Table(t("sheet.readme"), [t("readme.title"), ""])
    readme.rows += [
        [t("readme.project"), ctx.project.title],
        [t("readme.exported_at"), datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")],
        [t("readme.mode"), t(f"readme.mode.{mode}")],
        [t("readme.locked"), _yes_no(lang, is_locked(ctx, Stage.EXTRACTION))],
        [t("readme.studies"), len({s.study.id for s in sources})],
        [t("readme.missing"), "" if missing else t("readme.none_missing")],
    ]
    readme.rows += [[f"  {m.label}", t(f"missing.{m.reason}")] for m in missing]
    readme.rows += [[], [t("readme.values")]]

    base = [t("col.study"), t("col.source"), t("col.extractor")]
    char_labels = [t(f"field.{f.key}") if f.label_key else (f.label or f.key) for f in form.fields]
    studies = Table(t("sheet.studies"), [*base, t("col.design"), t("col.status"), *char_labels])
    arms = Table(t("sheet.arms"), [*base, t("col.arm"), t("col.group"), t("col.n")])
    data = Table(
        t("sheet.data"),
        [
            *base,
            t("col.outcome"),
            t("col.timepoint"),
            t("col.arm"),
            t("col.group"),
            t("col.value_type"),
            t("col.n"),
            t("col.mean"),
            t("col.dispersion_type"),
            *[
                t(f"col.{f}")
                for f in ("sd", "se", "ci_low", "ci_high", "median", "q1", "q3", "min", "max")
            ],
            t("col.events"),
            t("col.total"),
            t("col.t_stat"),
            t("col.p_value"),
            *[t(f"col.effect_{f}") for f in ("measure", "estimate", "ci_low", "ci_high", "se")],
            t("col.adjusted"),
            t("col.adjusted_for"),
            t("col.scale"),
            t("col.scale_min"),
            t("col.scale_max"),
            t("col.higher_is_better"),
            t("col.direction_confirmed"),
            t("col.source_location"),
            t("col.dispersion_source"),
            t("col.data_source"),
        ],
    )
    alerts = Table(t("sheet.alerts"), [*base, t("col.alert"), t("col.justification")])

    for src in sources:
        e = src.extraction
        who = [src.study.label, t(f"source.{src.origin}"), src.extractor]
        characteristics = e.characteristics or {}
        studies.rows.append(
            [
                *who,
                _code(lang, "design", src.study.design),
                _code(lang, "status", e.status),
                *[characteristics.get(f.key) for f in form.fields],
            ]
        )
        arm_list = list(
            await session.scalars(
                select(StudyArm)
                .where(StudyArm.extraction_id == e.id)
                .order_by(StudyArm.position, StudyArm.created_at)
            )
        )
        arm_by_id = {a.id: a for a in arm_list}
        for a in arm_list:
            arms.rows.append(
                [*who, a.label, groups.get(a.mapped_group_id) if a.mapped_group_id else None, a.n]
            )
        measures = {
            m.outcome_id: m
            for m in await session.scalars(
                select(OutcomeMeasure).where(OutcomeMeasure.extraction_id == e.id)
            )
        }
        rows = list(
            await session.scalars(
                select(OutcomeData)
                .where(OutcomeData.extraction_id == e.id)
                .order_by(OutcomeData.created_at)
            )
        )
        order = {oid: i for i, oid in enumerate(outcomes)}
        rows.sort(
            key=lambda r: (
                order.get(r.outcome_id, 0),
                r.timepoint,
                arm_by_id[r.arm_id].position if r.arm_id in arm_by_id else 0,
            )
        )
        for r in rows:
            arm = arm_by_id.get(r.arm_id)
            outcome = outcomes.get(r.outcome_id)
            m = measures.get(r.outcome_id)
            higher = m.higher_is_better if m else (outcome.higher_is_better if outcome else None)
            effect = r.effect_reported or {}
            data.rows.append(
                [
                    *who,
                    outcome.name if outcome else None,
                    r.timepoint,
                    arm.label if arm else None,
                    groups.get(arm.mapped_group_id) if arm and arm.mapped_group_id else None,
                    _code(lang, "value_type", r.value_type),
                    r.n,
                    r.mean,
                    _code(lang, "dispersion", r.dispersion_type),
                    r.sd,
                    r.se,
                    r.ci_low,
                    r.ci_high,
                    r.median,
                    r.q1,
                    r.q3,
                    r.min,
                    r.max,
                    r.events,
                    r.total,
                    r.t_stat,
                    r.p_value,
                    effect.get("measure"),
                    *[_decimal(effect.get(k)) for k in ("estimate", "ci_low", "ci_high", "se")],
                    _yes_no(lang, r.adjusted),
                    r.adjusted_for,
                    m.scale_name if m else None,
                    m.scale_min if m else None,
                    m.scale_max if m else None,
                    _yes_no(lang, higher),
                    _yes_no(lang, r.direction_confirmed),
                    r.source_location,
                    r.dispersion_source,
                    _code(lang, "data_source", r.source),
                ]
            )
        justified = await session.scalars(
            select(CheckAlert).where(
                CheckAlert.extraction_id == e.id, CheckAlert.status == AlertStatus.JUSTIFIED
            )
        )
        for alert in justified:
            short = alert.code.rsplit(".", 1)[-1]
            alerts.rows.append([*who, t(f"alert.{short}", **alert.params), alert.justification])
    return [readme, studies, arms, data, alerts]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


# ---- Writers -------------------------------------------------------------------------


def write_xlsx(tables: list[Table]) -> bytes:
    workbook = Workbook(write_only=True)
    for table in tables:
        sheet = workbook.create_sheet(title=table.name[:31])
        sheet.append(table.header)
        for row in table.rows:
            # Decimals become numeric cells (Excel needs numbers, not text).
            sheet.append([float(c) if isinstance(c, Decimal) else c for c in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _csv_cell(value: Cell, style: CsvStyle) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float | Decimal):
        text = number_text(value) or ""
        return text.replace(".", ",") if style == CsvStyle.EXCEL else text
    return str(value)


def write_csv(table: Table, style: CsvStyle) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(
        buffer, delimiter=";" if style == CsvStyle.EXCEL else ",", lineterminator="\r\n"
    )
    writer.writerow(table.header)
    for row in table.rows:
        writer.writerow([_csv_cell(c, style) for c in row])
    encoding = "utf-8-sig" if style == CsvStyle.EXCEL else "utf-8"
    return buffer.getvalue().encode(encoding)


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", plain).strip("-").lower()[:60] or "projeto"


def file_name(ctx: ProjectContext, lang: str, mode: ExportMode, fmt: FileFormat) -> str:
    kind = label(lang, "file.extraction")
    suffix = "-pre-consenso" if mode == ExportMode.INDIVIDUAL else ""
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"{_slug(ctx.project.title)}_{kind}{suffix}_{day}.{fmt}"


async def export_extraction(
    session: AsyncSession,
    ctx: ProjectContext,
    *,
    mode: ExportMode,
    fmt: FileFormat,
    csv_style: CsvStyle,
    lang: str | None,
    acknowledge_missing: bool,
) -> tuple[bytes, str, str]:
    """Returns (content, file name, media type)."""
    if mode == ExportMode.INDIVIDUAL and not ctx.is_admin:
        raise ForbiddenError()  # individual extractions are blind to other members
    lang = lang if lang in LANGS else ctx.project.report_language
    sources, missing = await _sources(session, ctx, mode)
    if not sources:
        raise AppError("export.empty", status_code=409)
    if missing and not acknowledge_missing:
        raise AppError("export.incomplete", status_code=409, count=len(missing))
    tables = await build_tables(session, ctx, sources, missing, mode, lang)
    name = file_name(ctx, lang, mode, fmt)
    if fmt == FileFormat.XLSX:
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return write_xlsx(tables), name, media
    data = next(t for t in tables if t.name == label(lang, "sheet.data"))
    return write_csv(data, csv_style), name, "text/csv; charset=utf-8"
