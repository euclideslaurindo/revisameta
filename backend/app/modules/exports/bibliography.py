"""Bibliography of the included studies (docs/modulos.md 7.10; stage 6 step 5).

Every report (article) of every study of the project, primary report first, in RIS,
BibTeX or Vancouver text. Fields come exactly as stored; nothing is invented. A
record without authors, journal or year is still exported, and the screen says how
many records lack something, so the group can complete them before citing.
"""

import re
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.exports.extraction import _slug
from app.modules.projects.access import ProjectContext
from app.modules.studies.models import Reference, Report, Study

ET_AL = 6  # Vancouver: list up to six authors, then "et al."


class BibFormat(StrEnum):
    RIS = "ris"
    BIBTEX = "bibtex"
    VANCOUVER = "vancouver"


class BibStatus(BaseModel):
    records: int
    incomplete: list[str]  # study labels with a record missing authors, year or journal


async def _records(session: AsyncSession, ctx: ProjectContext) -> list[tuple[str, Reference]]:
    rows = await session.execute(
        select(Study.label, Reference)
        .join(Report, Report.study_id == Study.id)
        .join(Reference, Reference.id == Report.reference_id)
        .where(Study.project_id == ctx.project.id, Report.project_id == ctx.project.id)
        .order_by(Study.label, Report.is_primary.desc(), Reference.year, Reference.title)
    )
    return [(label, ref) for label, ref in rows.all()]


def _authors(ref: Reference) -> list[str]:
    return [a.strip() for a in (ref.authors or "").split(";") if a.strip()]


async def status(session: AsyncSession, ctx: ProjectContext) -> BibStatus:
    records = await _records(session, ctx)
    incomplete = sorted(
        {label for label, r in records if not (_authors(r) and r.year and r.journal)}
    )
    return BibStatus(records=len(records), incomplete=incomplete)


def _ris(ref: Reference) -> str:
    lines = ["TY  - JOUR"]
    lines += [f"AU  - {a}" for a in _authors(ref)]
    for tag, value in (
        ("TI", ref.title),
        ("PY", ref.year),
        ("JO", ref.journal),
        ("VL", ref.volume),
        ("IS", ref.issue),
        ("SP", ref.pages),
        ("DO", ref.doi),
        ("UR", ref.url),
        ("AN", ref.pmid),
    ):
        if value not in (None, ""):
            lines.append(f"{tag}  - {value}")
    lines.append("ER  - ")
    return "\n".join(lines)


def _ascii(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", plain)


def _bib_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _bibtex(ref: Reference, key: str) -> str:
    fields = [
        ("author", " and ".join(_authors(ref)) or None),
        ("title", ref.title),
        ("journal", ref.journal),
        ("year", ref.year),
        ("volume", ref.volume),
        ("number", ref.issue),
        ("pages", (ref.pages or "").replace("-", "--") or None),
        ("doi", ref.doi),
        ("url", ref.url),
        ("pmid", ref.pmid),
    ]
    body = ",\n".join(
        f"  {k} = {{{_bib_escape(str(v))}}}" for k, v in fields if v not in (None, "")
    )
    return f"@article{{{key},\n{body}\n}}"


def _vancouver_name(name: str) -> str:
    """ "Silva, João Pedro" -> "Silva JP"; names already as "Silva JP" stay as they are."""
    if "," not in name:
        return name
    last, first = (p.strip() for p in name.split(",", 1))
    initials = "".join(part[0].upper() for part in re.split(r"[\s\-.]+", first) if part)
    return f"{last} {initials}".strip()


def _vancouver(ref: Reference, n: int) -> str:
    names = [_vancouver_name(a) for a in _authors(ref)]
    if len(names) > ET_AL:
        names = [*names[:ET_AL], "et al"]
    parts = []
    if names:
        parts.append(", ".join(names) + ".")
    parts.append(ref.title.rstrip(".") + ".")
    source = ref.journal or ""
    if ref.year:
        source += f"{'. ' if source else ''}{ref.year}"
    if ref.volume:
        source += f";{ref.volume}"
    if ref.issue:
        source += f"({ref.issue})"
    if ref.pages:
        source += f":{ref.pages}"
    if source:
        parts.append(source + ".")
    if ref.doi:
        parts.append(f"doi:{ref.doi}")
    return f"{n}. " + " ".join(parts)


async def export(
    session: AsyncSession, ctx: ProjectContext, fmt: BibFormat
) -> tuple[bytes, str, str]:
    records = await _records(session, ctx)
    if not records:
        raise AppError("exports.bibliography_empty", status_code=409)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    base = f"{_slug(ctx.project.title)}_bibliography_{day}"
    if fmt == BibFormat.RIS:
        text = "\n".join(_ris(r) for _, r in records) + "\n"
        return text.encode(), f"{base}.ris", "application/x-research-info-systems"
    if fmt == BibFormat.BIBTEX:
        used: dict[str, int] = {}
        entries = []
        for _, r in records:
            first = _authors(r)[0].split(",")[0] if _authors(r) else "anon"
            key = f"{_ascii(first).lower() or 'anon'}{r.year or ''}"
            used[key] = used.get(key, 0) + 1
            if used[key] > 1:
                key += chr(ord("a") + used[key] - 2)
            entries.append(_bibtex(r, key))
        return ("\n\n".join(entries) + "\n").encode(), f"{base}.bib", "application/x-bibtex"
    text = "\n".join(_vancouver(r, i) for i, (_, r) in enumerate(records, start=1)) + "\n"
    return text.encode("utf-8-sig"), f"{base}_vancouver.txt", "text/plain; charset=utf-8"
