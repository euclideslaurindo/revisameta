"""Final study list import from CSV/XLSX (docs/modulos.md 7.2).

Two calls with the same file: `preview` reads the header and a sample and suggests a
column mapping; `run` validates every row (dry run or for real). Invalid rows are
reported with row number and reason and are skipped; valid rows are imported together.
The file is read as a stream and never kept on disk.
"""

import csv
import io
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from openpyxl import load_workbook
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.projects.access import ProjectContext
from app.modules.studies.models import StudyDesign
from app.modules.studies.schemas import ReferenceIn
from app.modules.studies.service import add_study, doi_taken, label_taken

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
SAMPLE_ROWS = 10

Field = Literal["label", "title", "authors", "year", "doi", "pmid", "journal", "design", "notes"]
FIELDS: tuple[Field, ...] = (
    "label",
    "title",
    "authors",
    "year",
    "doi",
    "pmid",
    "journal",
    "design",
    "notes",
)
REQUIRED: tuple[Field, ...] = ("title",)

# Header words (pt/en, accents and case ignored) used to suggest the mapping.
_HINTS: dict[Field, tuple[str, ...]] = {
    "label": ("estudo", "study", "id do estudo", "study id", "rotulo", "label"),
    "title": ("titulo", "title", "article title"),
    "authors": ("autores", "autor", "authors", "author"),
    "year": ("ano", "year", "publication year"),
    "doi": ("doi",),
    "pmid": ("pmid", "pubmed id"),
    "journal": ("revista", "periodico", "journal", "source"),
    "design": ("desenho", "tipo de estudo", "design", "study design", "study type"),
    "notes": ("observacoes", "notas", "notes", "comments"),
}

# Design values accepted in spreadsheets (pt/en).
_DESIGNS: dict[str, StudyDesign] = {
    "ecr": StudyDesign.RCT,
    "ensaio clinico randomizado": StudyDesign.RCT,
    "rct": StudyDesign.RCT,
    "randomized controlled trial": StudyDesign.RCT,
    "coorte prospectiva": StudyDesign.COHORT_PROSPECTIVE,
    "prospective cohort": StudyDesign.COHORT_PROSPECTIVE,
    "coorte retrospectiva": StudyDesign.COHORT_RETROSPECTIVE,
    "retrospective cohort": StudyDesign.COHORT_RETROSPECTIVE,
    "coorte": StudyDesign.COHORT_RETROSPECTIVE,
    "cohort": StudyDesign.COHORT_RETROSPECTIVE,
    "caso-controle": StudyDesign.CASE_CONTROL,
    "caso controle": StudyDesign.CASE_CONTROL,
    "case-control": StudyDesign.CASE_CONTROL,
    "case control": StudyDesign.CASE_CONTROL,
    "transversal": StudyDesign.CROSS_SECTIONAL,
    "cross-sectional": StudyDesign.CROSS_SECTIONAL,
    "cross sectional": StudyDesign.CROSS_SECTIONAL,
    "serie de casos": StudyDesign.CASE_SERIES,
    "case series": StudyDesign.CASE_SERIES,
    "outro": StudyDesign.OTHER,
    "other": StudyDesign.OTHER,
}
_DESIGNS.update({d.value: d for d in StudyDesign})


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip().lower()


def parse_design(value: str | None) -> StudyDesign | None:
    if value is None or not str(value).strip():
        return None
    return _DESIGNS.get(_plain(str(value)))


def _cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


@dataclass
class Table:
    columns: list[str]
    rows: Iterator[list[str | None]]


def read_table(filename: str, content: bytes) -> Table:
    if len(content) > MAX_FILE_BYTES:
        raise AppError("import.too_large", status_code=413, limit=MAX_FILE_BYTES // (1024 * 1024))
    name = filename.lower()
    if name.endswith(".xlsx"):
        return _read_xlsx(content)
    if name.endswith((".csv", ".txt")):
        return _read_csv(content)
    raise AppError("import.unsupported_format", status_code=415)


def _read_csv(content: bytes) -> Table:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel on Windows saves CSV as cp1252; latin-1 never fails as a last resort.
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
    sample = text[:4096]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = next(reader, None)
    if not header:
        raise AppError("import.empty_file", status_code=422)
    columns = [h.strip() for h in header]
    return Table(columns, ([_cell(v) for v in row] for row in reader))


def _read_xlsx(content: bytes) -> Table:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # corrupt or not really XLSX
        raise AppError("import.unsupported_format", status_code=415) from exc
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if not header or all(h is None for h in header):
        raise AppError("import.empty_file", status_code=422)
    columns = [_cell(h) or f"#{i + 1}" for i, h in enumerate(header)]
    return Table(columns, ([_cell(v) for v in row] for row in rows))


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


class Preview(BaseModel):
    columns: list[str]
    sample: list[list[str | None]]
    row_count: int
    suggested_mapping: dict[str, str]


def preview(filename: str, content: bytes) -> Preview:
    table = read_table(filename, content)
    sample: list[list[str | None]] = []
    count = 0
    for row in table.rows:
        if not any(row):
            continue
        count += 1
        if len(sample) < SAMPLE_ROWS:
            sample.append(row)
    return Preview(
        columns=table.columns,
        sample=sample,
        row_count=count,
        suggested_mapping=suggest_mapping(table.columns),
    )


class RowError(BaseModel):
    row: int  # row number as the user sees it in the spreadsheet (header = 1)
    field: str | None
    code: str


class ImportReport(BaseModel):
    dry_run: bool
    total_rows: int
    valid_rows: int
    created: int
    errors: list[RowError]


@dataclass
class _Seen:
    labels: set[str] = field(default_factory=set)
    dois: set[str] = field(default_factory=set)


def _label_for(values: dict[str, str | None]) -> str | None:
    if values.get("label"):
        return values["label"]
    authors, year = values.get("authors"), values.get("year")
    if authors and year:
        # Vancouver style: "Surname Initials, Surname Initials" -> first surname.
        first_author = re.split(r"[;,]| and | e ", authors)[0].strip()
        surname = first_author.split(" ")[0] if first_author else ""
        return f"{surname} {year}".strip() or None
    return None


async def run(
    session: AsyncSession,
    ctx: ProjectContext,
    filename: str,
    content: bytes,
    mapping: dict[str, str],
    dry_run: bool,
) -> ImportReport:
    unknown = [k for k in mapping if k not in FIELDS]
    if unknown or any(r not in mapping for r in REQUIRED):
        raise AppError("import.invalid_mapping", status_code=422)
    table = read_table(filename, content)
    index = {c: i for i, c in enumerate(table.columns)}
    if any(column not in index for column in mapping.values()):
        raise AppError("import.invalid_mapping", status_code=422)

    errors: list[RowError] = []
    seen = _Seen()
    total = valid = 0
    for offset, row in enumerate(table.rows, start=2):
        if not any(row):
            continue
        total += 1
        if total > MAX_ROWS:
            raise AppError("import.too_many_rows", status_code=413, limit=MAX_ROWS)
        values = {
            target: (row[index[column]] if index[column] < len(row) else None)
            for target, column in mapping.items()
        }
        row_errors = await _validate_row(session, ctx, values, seen, offset)
        if row_errors:
            errors.extend(row_errors)
            continue
        valid += 1
        if not dry_run:
            await add_study(
                session,
                ctx.project.id,
                ctx.user.id,
                _label_for(values) or "",
                (parse_design(values.get("design")) or StudyDesign.OTHER).value,
                values.get("notes"),
                ReferenceIn(
                    title=values["title"] or "",
                    authors=values.get("authors"),
                    year=int(year_text) if (year_text := values.get("year")) else None,
                    doi=values.get("doi"),
                    pmid=values.get("pmid"),
                    journal=values.get("journal"),
                ),
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


async def _validate_row(
    session: AsyncSession,
    ctx: ProjectContext,
    values: dict[str, str | None],
    seen: _Seen,
    row: int,
) -> list[RowError]:
    errors: list[RowError] = []

    def fail(field_name: str | None, code: str) -> None:
        errors.append(RowError(row=row, field=field_name, code=code))

    if not values.get("title"):
        fail("title", "import.missing_title")
    year = values.get("year")
    if year and not (year.isdigit() and 1800 <= int(year) <= 2100):
        fail("year", "import.invalid_year")
    if values.get("design") and parse_design(values.get("design")) is None:
        fail("design", "import.invalid_design")
    try:
        ref = ReferenceIn(
            title=values.get("title") or "x",
            doi=values.get("doi"),
            pmid=values.get("pmid"),
        )
    except ValidationError as exc:
        for err in exc.errors():
            fail(str(err["loc"][0]), f"import.invalid_{err['loc'][0]}")
        ref = None

    label = _label_for(values)
    if not label:
        fail("label", "import.missing_label")
    elif label.lower() in seen.labels:
        fail("label", "import.duplicate_label_in_file")
    elif await label_taken(session, ctx.project.id, label):
        fail("label", "study.duplicate_label")

    if ref is not None and ref.doi:
        if ref.doi in seen.dois:
            fail("doi", "import.duplicate_doi_in_file")
        elif await doi_taken(session, ctx.project.id, ref.doi):
            fail("doi", "study.duplicate_doi")

    if not errors:
        if label:
            seen.labels.add(label.lower())
        if ref is not None and ref.doi:
            seen.dois.add(ref.doi)
        if ref is not None:
            values["doi"], values["pmid"] = ref.doi, ref.pmid
    return errors
