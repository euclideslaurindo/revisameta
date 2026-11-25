"""Import an extraction spreadsheet the group already has (docs/modulos.md 7.2, P0).

Layout ("long"): one row per study x group x outcome x time point, with the numbers of
that group. Two calls with the same file, as in the study list import:

- `preview` reads the header and a sample, suggests which column is which field, and lists
  the distinct study, group and outcome names with the project item each one matches.
- `run` validates every row (dry run or for real). The person may fix the column mapping
  and the name matches before running.

Nothing bypasses the extraction rules: the numbers go into the importing person's own
individual extraction, as a draft, through the same service functions the form uses.
Impossible values are rejected, the dispersion type is required, and the plausibility
checks, direction sentence, double extraction and consensus all apply afterwards. A study
with any invalid row is skipped whole (never half imported) and reported row by row.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.extraction import service
from app.modules.extraction.checks import impossible_arm_values, impossible_row_values
from app.modules.extraction.models import (
    DispersionType,
    Extraction,
    ExtractionKind,
    StudyArm,
    ValueType,
)
from app.modules.extraction.schemas import ArmIn, MeasureIn, OutcomeDataIn
from app.modules.projects.access import ProjectContext
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.studies.importer import MAX_ROWS, SAMPLE_ROWS, _plain, read_table
from app.modules.studies.models import Study

Field = Literal[
    "study",
    "group",
    "group_n",
    "outcome",
    "timepoint",
    "value_type",
    "n",
    "mean",
    "sd",
    "se",
    "ci_low",
    "ci_high",
    "median",
    "q1",
    "q3",
    "min",
    "max",
    "events",
    "total",
    "dispersion_source",
    "source_location",
    "scale_name",
    "scale_min",
    "scale_max",
    "higher_is_better",
]
FIELDS: tuple[Field, ...] = Field.__args__  # type: ignore[attr-defined]
REQUIRED: tuple[Field, ...] = ("study", "group", "outcome")

# Header words (pt/en, accents, case and "_" ignored) used to suggest the mapping.
_HINTS: dict[str, tuple[str, ...]] = {
    "study": ("estudo", "study", "id do estudo", "study id"),
    "group": ("grupo", "group", "braco", "arm"),
    "group_n": ("n do grupo", "n grupo", "group n", "arm n"),
    "outcome": ("desfecho", "outcome"),
    "timepoint": ("momento", "tempo", "timepoint", "time point", "seguimento"),
    "value_type": ("tipo de valor", "tipo valor", "value type", "final ou mudanca"),
    "n": ("n", "n analisado", "n analyzed", "n analysed"),
    "mean": ("media", "mean"),
    "sd": ("dp", "sd", "desvio padrao", "standard deviation"),
    "se": ("ep", "se", "erro padrao", "standard error"),
    "ci_low": ("ic inferior", "ic inf", "ic95 inf", "ci low", "ci lower", "lower ci"),
    "ci_high": ("ic superior", "ic sup", "ic95 sup", "ci high", "ci upper", "upper ci"),
    "median": ("mediana", "median"),
    "q1": ("q1", "p25", "quartil 1"),
    "q3": ("q3", "p75", "quartil 3"),
    "min": ("minimo", "min", "minimum"),
    "max": ("maximo", "max", "maximum"),
    "events": ("eventos", "events"),
    "total": ("total",),
    "dispersion_source": (
        "onde diz a dispersao",
        "fonte da dispersao",
        "dispersion source",
        "where dispersion",
    ),
    "source_location": ("pagina", "fonte", "onde no artigo", "page", "source", "location"),
    "scale_name": ("escala", "instrumento", "scale"),
    "scale_min": ("escala min", "escala minimo", "scale min"),
    "scale_max": ("escala max", "escala maximo", "scale max"),
    "higher_is_better": ("maior e melhor", "higher is better"),
}

_DECIMALS: tuple[Field, ...] = (
    "mean",
    "sd",
    "se",
    "ci_low",
    "ci_high",
    "median",
    "q1",
    "q3",
    "min",
    "max",
    "scale_min",
    "scale_max",
)
_INTEGERS: tuple[Field, ...] = ("group_n", "n", "events", "total")
# Which dispersion columns go together (one type per row, as in the form).
_DISPERSION: tuple[tuple[DispersionType, tuple[str, ...]], ...] = (
    (DispersionType.SD, ("sd",)),
    (DispersionType.SE, ("se",)),
    (DispersionType.CI95, ("ci_low", "ci_high")),
    (DispersionType.IQR, ("q1", "q3")),
    (DispersionType.RANGE, ("min", "max")),
)
_YES = {"sim", "s", "yes", "y", "true", "verdadeiro", "1", "x"}
_NO = {"nao", "n", "no", "false", "falso", "0"}
_CHANGE = {"mudanca", "change", "mudanca desde a linha de base", "change from baseline", "delta"}
_FINAL = {"final", "valor final", "final value", "pos", "post"}


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    plain = {c: _plain(c) for c in columns}
    for target in FIELDS:
        for column, value in plain.items():
            if column in mapping.values():
                continue
            if value in _HINTS[target]:
                mapping[target] = column
                break
    return mapping


def parse_number(text: str) -> Decimal:
    """Accepts "1,5", "1.5", "1.234,5" and "1,234.5" (the last separator is the decimal)."""
    raw = re.sub(r"\s", "", text)  # also drops non-breaking spaces (Excel thousands)
    if "," in raw and "." in raw:
        decimal_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        raw = raw.replace(thousands, "").replace(decimal_sep, ".")
    else:
        raw = raw.replace(",", ".")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError from exc
    if not value.is_finite():
        raise ValueError
    return value


# ---- Project items the names point to -----------------------------------------------


@dataclass
class _Project:
    studies: dict[uuid.UUID, Study]
    groups: dict[uuid.UUID, ComparisonGroup]
    outcomes: dict[uuid.UUID, Outcome]


async def _project(session: AsyncSession, ctx: ProjectContext) -> _Project:
    pid = ctx.project.id
    studies = await session.scalars(
        select(Study).where(Study.project_id == pid, Study.deleted_at.is_(None))
    )
    groups = await session.scalars(
        select(ComparisonGroup).where(
            ComparisonGroup.project_id == pid, ComparisonGroup.deleted_at.is_(None)
        )
    )
    outcomes = await session.scalars(
        select(Outcome).where(Outcome.project_id == pid, Outcome.deleted_at.is_(None))
    )
    return _Project(
        studies={s.id: s for s in studies},
        groups={g.id: g for g in groups},
        outcomes={o.id: o for o in outcomes},
    )


def _match(text: str, names: dict[uuid.UUID, str]) -> uuid.UUID | None:
    wanted = _plain(text)
    return next((i for i, name in names.items() if _plain(name) == wanted), None)


class NameMatch(BaseModel):
    text: str  # as written in the spreadsheet
    match_id: uuid.UUID | None  # suggested project item; None = no match found
    rows: int


class ImportMatches(BaseModel):
    """Spreadsheet text -> project item id (null = no match; for groups, arm without group)."""

    studies: dict[str, uuid.UUID | None] = {}
    groups: dict[str, uuid.UUID | None] = {}
    outcomes: dict[str, uuid.UUID | None] = {}


class ExtractionImportPreview(BaseModel):
    columns: list[str]
    sample: list[list[str | None]]
    row_count: int
    suggested_mapping: dict[str, str]
    studies: list[NameMatch]
    groups: list[NameMatch]
    outcomes: list[NameMatch]


def _rows(filename: str, content: bytes) -> tuple[list[str], list[tuple[int, list[str | None]]]]:
    table = read_table(filename, content)
    rows: list[tuple[int, list[str | None]]] = []
    for i, row in enumerate(table.rows):
        if any(row):
            rows.append((i + 2, row))
            if len(rows) > MAX_ROWS:
                raise AppError("import.too_many_rows", status_code=413, limit=MAX_ROWS)
    return table.columns, rows


def _distinct(
    rows: list[tuple[int, list[str | None]]], index: int | None, names: dict[uuid.UUID, str]
) -> list[NameMatch]:
    if index is None:
        return []
    counts: dict[str, int] = defaultdict(int)
    for _, row in rows:
        value = row[index] if index < len(row) else None
        if value:
            counts[value] += 1
    return [NameMatch(text=t, match_id=_match(t, names), rows=n) for t, n in counts.items()]


async def preview(
    session: AsyncSession, ctx: ProjectContext, filename: str, content: bytes
) -> ExtractionImportPreview:
    columns, rows = _rows(filename, content)
    mapping = suggest_mapping(columns)
    project = await _project(session, ctx)

    def index(name: str) -> int | None:
        return columns.index(mapping[name]) if name in mapping else None

    return ExtractionImportPreview(
        columns=columns,
        sample=[row for _, row in rows[:SAMPLE_ROWS]],
        row_count=len(rows),
        suggested_mapping=mapping,
        studies=_distinct(rows, index("study"), {i: s.label for i, s in project.studies.items()}),
        groups=_distinct(rows, index("group"), {i: g.label for i, g in project.groups.items()}),
        outcomes=_distinct(
            rows, index("outcome"), {i: o.name for i, o in project.outcomes.items()}
        ),
    )


# ---- Validation ----------------------------------------------------------------------


class ExtractionRowError(BaseModel):
    row: int  # spreadsheet row number (header = 1)
    field: str | None
    code: str


class ImportStudyResult(BaseModel):
    study_id: uuid.UUID
    label: str
    rows: int
    status: Literal["imported", "ready", "skipped"]  # ready = valid in a dry run
    code: str | None = None  # why it was skipped
    extraction_id: uuid.UUID | None = None


class ExtractionImportReport(BaseModel):
    dry_run: bool
    total_rows: int
    valid_rows: int
    imported_rows: int
    studies: list[ImportStudyResult]
    errors: list[ExtractionRowError]


@dataclass
class _Row:
    number: int
    group_text: str
    group_id: uuid.UUID | None
    group_n: int | None
    outcome: Outcome
    timepoint: str
    value_type: ValueType
    values: dict[str, Any]
    scale: dict[str, Any]


@dataclass
class _Bundle:
    study: Study
    rows: list[_Row] = field(default_factory=list)
    invalid: bool = False


def _resolve(
    text: str, chosen: dict[str, uuid.UUID | None], names: dict[uuid.UUID, str]
) -> uuid.UUID | None:
    if text in chosen:
        return chosen[text]
    return _match(text, names)


def _timepoint(outcome: Outcome, text: str | None) -> str | None:
    """The time point as the protocol spells it; free text when the outcome lists none."""
    if not outcome.timepoints:
        return text.strip()[:60] if text else None
    if not text:
        return outcome.timepoints[0] if len(outcome.timepoints) == 1 else None
    wanted = _plain(text)
    return next((t for t in outcome.timepoints if _plain(t) == wanted), None)


def _parse_row(
    number: int,
    cell: dict[str, str | None],
    project: _Project,
    matches: ImportMatches,
    errors: list[ExtractionRowError],
) -> tuple[uuid.UUID, _Row] | None:
    """One spreadsheet row, or None (with its errors recorded)."""
    before = len(errors)

    def fail(field_name: str | None, code: str) -> None:
        errors.append(ExtractionRowError(row=number, field=field_name, code=code))

    for name in REQUIRED:
        if not cell.get(name):
            fail(name, "import.required")
    if len(errors) > before:
        return None
    study_id = _resolve(
        cell["study"] or "", matches.studies, {i: s.label for i, s in project.studies.items()}
    )
    if study_id is None or study_id not in project.studies:
        fail("study", "extraction_import.unknown_study")
    group_text = cell["group"] or ""
    group_id = _resolve(group_text, matches.groups, {i: g.label for i, g in project.groups.items()})
    if group_id is not None and group_id not in project.groups:
        fail("group", "extraction_import.unknown_group")
    outcome_id = _resolve(
        cell["outcome"] or "", matches.outcomes, {i: o.name for i, o in project.outcomes.items()}
    )
    outcome = project.outcomes.get(outcome_id) if outcome_id else None
    if outcome is None:
        fail("outcome", "extraction_import.unknown_outcome")

    numbers: dict[str, Any] = {}
    for name in (*_DECIMALS, *_INTEGERS):
        text = cell.get(name)
        if not text:
            continue
        try:
            value = parse_number(text)
        except ValueError:
            fail(name, "import.invalid_number")
            continue
        if name in _INTEGERS:
            if value != value.to_integral_value():
                fail(name, "import.invalid_integer")
                continue
            numbers[name] = int(value)
        else:
            numbers[name] = value

    kinds = [k for k, cols in _DISPERSION if any(numbers.get(c) is not None for c in cols)]
    if len(kinds) > 1:
        fail(None, "extraction_import.several_dispersions")
    dispersion = kinds[0] if len(kinds) == 1 else None

    value_type = ValueType.FINAL
    if cell.get("value_type"):
        plain = _plain(cell["value_type"] or "")
        if plain in _CHANGE:
            value_type = ValueType.CHANGE
        elif plain not in _FINAL:
            fail("value_type", "extraction_import.invalid_value_type")

    higher: bool | None = None
    if cell.get("higher_is_better"):
        plain = _plain(cell["higher_is_better"] or "")
        if plain in _YES:
            higher = True
        elif plain in _NO:
            higher = False
        else:
            fail("higher_is_better", "extraction_import.invalid_yes_no")

    timepoint = _timepoint(outcome, cell.get("timepoint")) if outcome else None
    if outcome is not None and timepoint is None:
        fail("timepoint", "extraction_import.unknown_timepoint")
    if len(errors) > before or outcome is None or study_id is None or timepoint is None:
        return None

    values: dict[str, Any] = {
        k: numbers.get(k)
        for k in (
            "n",
            "mean",
            "sd",
            "se",
            "ci_low",
            "ci_high",
            "median",
            "q1",
            "q3",
            "min",
            "max",
            "events",
            "total",
        )
    }
    values["dispersion_type"] = dispersion
    values["dispersion_source"] = (cell.get("dispersion_source") or None) if dispersion else None
    values["source_location"] = cell.get("source_location") or None
    try:
        payload = OutcomeDataIn(
            arm_id=uuid.uuid4(),
            outcome_id=outcome.id,
            timepoint=timepoint,
            value_type=value_type,
            **values,
        )
    except ValidationError:
        fail(None, "extraction_import.invalid_values")
        return None
    impossible = impossible_row_values(payload.model_dump())
    if impossible:
        fail(None, impossible)
        return None
    group_n = numbers.get("group_n")
    arm_problem = impossible_arm_values(group_n)
    if arm_problem:
        fail("group_n", arm_problem)
        return None
    scale = {
        "scale_name": (cell.get("scale_name") or None),
        "scale_min": numbers.get("scale_min"),
        "scale_max": numbers.get("scale_max"),
        "higher_is_better": higher,
    }
    return study_id, _Row(
        number=number,
        group_text=group_text.strip(),
        group_id=group_id,
        group_n=group_n,
        outcome=outcome,
        timepoint=timepoint,
        value_type=value_type,
        values=values,
        scale=scale,
    )


def _check_bundle(bundle: _Bundle, errors: list[ExtractionRowError]) -> None:
    """Rules across rows of the same study."""
    seen: dict[tuple[str, uuid.UUID, str], int] = {}
    for r in bundle.rows:
        key = (_plain(r.group_text), r.outcome.id, r.timepoint)
        if key in seen:
            errors.append(
                ExtractionRowError(row=r.number, field=None, code="extraction_import.duplicate")
            )
            bundle.invalid = True
        seen[key] = r.number
    group_ids: dict[str, uuid.UUID | None] = {}
    for r in bundle.rows:
        name = _plain(r.group_text)
        if name in group_ids and group_ids[name] != r.group_id:
            errors.append(
                ExtractionRowError(
                    row=r.number, field="group", code="extraction_import.group_conflict"
                )
            )
            bundle.invalid = True
        group_ids[name] = r.group_id
    mapped = [g for g in group_ids.values() if g is not None]
    if len(mapped) != len(set(mapped)):
        # Two arms of one study pointing to the same comparison group must be combined
        # by the R service (Cochrane formula), never imported as two copies.
        errors.append(
            ExtractionRowError(
                row=bundle.rows[0].number, field="group", code="extraction_import.same_group"
            )
        )
        bundle.invalid = True


async def _existing(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID
) -> tuple[Extraction | None, int]:
    mine = (
        await session.scalars(
            select(Extraction).where(
                Extraction.project_id == ctx.project.id,
                Extraction.study_id == study_id,
                Extraction.kind == ExtractionKind.INDIVIDUAL,
                Extraction.extractor_id == ctx.user.id,
            )
        )
    ).first()
    if mine is None:
        return None, 0
    arms = await session.scalar(
        select(func.count()).select_from(StudyArm).where(StudyArm.extraction_id == mine.id)
    )
    return mine, int(arms or 0)


async def _write(session: AsyncSession, ctx: ProjectContext, bundle: _Bundle) -> uuid.UUID:
    summary = await service.start(session, ctx, bundle.study.id)
    extraction_id = summary.id
    arms: dict[str, uuid.UUID] = {}
    for r in bundle.rows:
        name = _plain(r.group_text)
        if name in arms:
            continue
        same = [x for x in bundle.rows if _plain(x.group_text) == name]
        # The group's n: its own column, else the n analysed in its rows (first one given).
        n = next((x.group_n for x in same if x.group_n), None) or next(
            (x.values["n"] for x in same if x.values.get("n")), None
        )
        arm = await service.add_arm(
            session,
            ctx,
            extraction_id,
            ArmIn(label=r.group_text[:120], n=n, mapped_group_id=r.group_id, position=len(arms)),
        )
        arms[name] = arm.id
    measured: set[uuid.UUID] = set()
    for r in bundle.rows:
        if r.outcome.id in measured:
            continue
        scales = [x.scale for x in bundle.rows if x.outcome.id == r.outcome.id]
        if not any(any(v is not None for v in s.values()) for s in scales):
            continue
        pick = {k: next((s[k] for s in scales if s[k] is not None), None) for k in scales[0]}
        higher = pick["higher_is_better"]
        await service.set_measure(
            session,
            ctx,
            extraction_id,
            r.outcome.id,
            MeasureIn(
                scale_name=pick["scale_name"],
                scale_min=pick["scale_min"],
                scale_max=pick["scale_max"],
                higher_is_better=r.outcome.higher_is_better if higher is None else higher,
            ),
        )
        measured.add(r.outcome.id)
    for r in bundle.rows:
        await service.add_outcome_data(
            session,
            ctx,
            extraction_id,
            OutcomeDataIn(
                arm_id=arms[_plain(r.group_text)],
                outcome_id=r.outcome.id,
                timepoint=r.timepoint,
                value_type=r.value_type,
                **r.values,
            ),
        )
    return extraction_id


async def run(
    session: AsyncSession,
    ctx: ProjectContext,
    filename: str,
    content: bytes,
    mapping: dict[str, str],
    matches: ImportMatches,
    dry_run: bool,
) -> ExtractionImportReport:
    columns, rows = _rows(filename, content)
    unknown = [k for k in mapping if k not in FIELDS]
    missing_cols = [v for v in mapping.values() if v not in columns]
    if unknown or missing_cols or any(r not in mapping for r in REQUIRED):
        raise AppError("import.invalid_mapping", status_code=422)
    index = {name: columns.index(col) for name, col in mapping.items()}
    project = await _project(session, ctx)
    errors: list[ExtractionRowError] = []
    bundles: dict[uuid.UUID, _Bundle] = {}
    bad_studies: set[uuid.UUID] = set()
    for number, row in rows:
        cell = {k: (row[i] if i < len(row) else None) for k, i in index.items()}
        parsed = _parse_row(number, cell, project, matches, errors)
        if parsed is None:
            study_id = _resolve(
                cell.get("study") or "",
                matches.studies,
                {i: s.label for i, s in project.studies.items()},
            )
            if study_id in project.studies:
                bad_studies.add(study_id)
            continue
        study_id, item = parsed
        bundles.setdefault(study_id, _Bundle(project.studies[study_id])).rows.append(item)
    for study_id in bad_studies:
        if study_id in bundles:
            bundles[study_id].invalid = True
        else:
            bundles[study_id] = _Bundle(project.studies[study_id], invalid=True)

    results: list[ImportStudyResult] = []
    imported_rows = 0
    for bundle in sorted(bundles.values(), key=lambda b: b.study.label):
        if bundle.rows:
            _check_bundle(bundle, errors)
        result = ImportStudyResult(
            study_id=bundle.study.id,
            label=bundle.study.label,
            rows=len(bundle.rows),
            status="ready",
        )
        if bundle.invalid:
            result.status, result.code = "skipped", "extraction_import.study_has_errors"
        else:
            existing, arms = await _existing(session, ctx, bundle.study.id)
            if existing is not None and (arms or existing.status != "draft"):
                result.status, result.code = "skipped", "extraction_import.already_extracted"
        if result.status == "ready" and not dry_run:
            try:
                result.extraction_id = await _write(session, ctx, bundle)
            except AppError as exc:
                # Every row was validated above, so this is the stage being locked or the
                # extractor limit reached meanwhile; both happen before anything is written.
                await session.rollback()
                result.status, result.code = "skipped", exc.code
            else:
                result.status = "imported"
                imported_rows += len(bundle.rows)
        results.append(result)
    errors.sort(key=lambda e: e.row)
    return ExtractionImportReport(
        dry_run=dry_run,
        total_rows=len(rows),
        valid_rows=sum(len(b.rows) for b in bundles.values() if not b.invalid),
        imported_rows=imported_rows,
        studies=results,
        errors=errors,
    )
