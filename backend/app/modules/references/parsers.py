"""Readers of search exports: RIS, PubMed (.nbib/MEDLINE), BibTeX and CSV.

Every reader takes an iterator of text lines and yields one record at a time (a dict
with the fields below, or a RecordError), so a file with 20 thousand records is never
held in memory (docs/arquivos.md 10.7). No dependency is needed: RIS and MEDLINE are
"TAG - value" lines, BibTeX entries are read brace by brace and CSV uses the standard
library.
"""

import csv
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Literal

from app.modules.studies.schemas import normalize_doi, normalize_pmid

Format = Literal["ris", "nbib", "bibtex", "csv"]
FIELDS = (
    "title",
    "authors",
    "year",
    "doi",
    "pmid",
    "journal",
    "abstract",
    "keywords",
    "volume",
    "issue",
    "pages",
    "url",
)
LIMITS = {"journal": 300, "volume": 40, "issue": 40, "pages": 60, "url": 1000}


@dataclass
class Record:
    number: int  # position in the file, from 1
    values: dict[str, str | int | None] = field(default_factory=dict)
    # Fields that could not be read and were left empty; the record is still imported.
    warnings: list[str] = field(default_factory=list)


@dataclass
class RecordError:
    """A record that could not be imported (no title)."""

    number: int
    code: str


Item = Record | RecordError


# ---- Format detection ---------------------------------------------------------------


def detect_format(filename: str, head: str) -> Format | None:
    name = filename.lower()
    if name.endswith((".ris", ".enw")):
        return "ris"
    if name.endswith((".nbib", ".medline")):
        return "nbib"
    if name.endswith(".bib"):
        return "bibtex"
    if name.endswith(".csv"):
        return "csv"
    text = head.lstrip("﻿ \r\n\t")
    if re.match(r"^TY  -", text):
        return "ris"
    if re.match(r"^PMID-", text):
        return "nbib"
    if text.startswith("@"):
        return "bibtex"
    return None


# ---- Cleaning (shared) ----------------------------------------------------------------


def _year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(1[5-9]\d\d|20\d\d|21\d\d)", value)
    if not match:
        raise ValueError("bad year")
    return int(match.group(1))


def _finish(number: int, raw: dict[str, list[str]]) -> Item:
    def joined(key: str, sep: str = " ") -> str | None:
        parts = [p.strip() for p in raw.get(key, []) if p and p.strip()]
        return sep.join(parts) if parts else None

    title = joined("title")
    if not title:
        return RecordError(number, "import.no_title")
    values: dict[str, str | int | None] = {
        "title": re.sub(r"\s+", " ", title),
        "authors": joined("authors", "; "),
        "journal": joined("journal"),
        "abstract": joined("abstract"),
        "keywords": joined("keywords", "; "),
        "volume": joined("volume"),
        "issue": joined("issue"),
        "url": raw["url"][0] if raw.get("url") else None,
    }
    start, end = joined("start_page"), joined("end_page")
    values["pages"] = joined("pages") or (f"{start}-{end}" if start and end else start)
    warnings: list[str] = []
    try:
        values["year"] = _year(joined("year"))
    except ValueError:
        values["year"] = None
        warnings.append("import.bad_year")
    doi_text = joined("doi")
    try:
        values["doi"] = normalize_doi(_first_doi(raw.get("doi", [])))
    except ValueError:
        values["doi"] = None
    if doi_text and values["doi"] is None:
        warnings.append("import.bad_doi")
    try:
        values["pmid"] = normalize_pmid(joined("pmid"))
    except ValueError:
        values["pmid"] = None
        warnings.append("import.bad_pmid")
    for key, limit in LIMITS.items():
        text = values.get(key)
        if isinstance(text, str) and len(text) > limit:
            values[key] = text[:limit]
    return Record(number, values, warnings)


def _first_doi(candidates: list[str]) -> str | None:
    for c in candidates:
        c = c.strip()
        match = re.search(r"10\.\d{4,9}/\S+", c)
        if match:
            return match.group(0).rstrip(".,;")
    return None


# ---- RIS ------------------------------------------------------------------------------

RIS_TAGS = {
    "TI": "title",
    "T1": "title",
    "AU": "authors",
    "A1": "authors",
    "PY": "year",
    "Y1": "year",
    "DA": "year",
    "DO": "doi",
    "JO": "journal",
    "JF": "journal",
    "T2": "journal",
    "AB": "abstract",
    "N2": "abstract",
    "KW": "keywords",
    "VL": "volume",
    "IS": "issue",
    "SP": "start_page",
    "EP": "end_page",
    "UR": "url",
    "AN": "pmid_an",
}
_RIS_LINE = re.compile(r"^([A-Z][A-Z0-9])  -( (.*))?$")


def read_ris(lines: Iterable[str]) -> Iterator[Item]:
    raw: dict[str, list[str]] | None = None
    last: str | None = None
    number = 0
    for line in lines:
        line = line.rstrip("\r\n").lstrip("﻿")
        match = _RIS_LINE.match(line)
        if not match:
            if raw is not None and last and line.strip():
                raw[last][-1] += " " + line.strip()  # continuation line
            continue
        tag, value = match.group(1), (match.group(3) or "").strip()
        if tag == "TY":
            raw, last = {}, None
            continue
        if raw is None:
            continue
        if tag == "ER":
            number += 1
            # Some databases (PubMed's RIS) put the PMID in AN; only digits count.
            an = raw.pop("pmid_an", [])
            if not raw.get("pmid") and an and an[0].isdigit():
                raw["pmid"] = an[:1]
            yield _finish(number, raw)
            raw, last = None, None
            continue
        key = RIS_TAGS.get(tag)
        if key is None:
            last = None
            continue
        if key == "year" and raw.get("year"):
            continue  # PY wins over DA
        if key == "journal" and raw.get("journal"):
            continue
        raw.setdefault(key, []).append(value)
        last = key


# ---- PubMed / MEDLINE (.nbib) ---------------------------------------------------------

NBIB_TAGS = {
    "PMID": "pmid",
    "TI": "title",
    "FAU": "authors_full",
    "AU": "authors",
    "DP": "year",
    "JT": "journal",
    "TA": "journal_short",
    "AB": "abstract",
    "MH": "keywords",
    "OT": "keywords",
    "VI": "volume",
    "IP": "issue",
    "PG": "pages",
    "LID": "doi",
    "AID": "doi",
}
_NBIB_LINE = re.compile(r"^([A-Z]{2,4})\s*- (.*)$")


def read_nbib(lines: Iterable[str]) -> Iterator[Item]:
    raw: dict[str, list[str]] = {}
    last: str | None = None
    number = 0

    def flush() -> Item:
        if raw.get("authors_full"):  # full names (FAU) are clearer than initials (AU)
            raw["authors"] = raw["authors_full"]
        if not raw.get("journal") and raw.get("journal_short"):
            raw["journal"] = raw["journal_short"]
        raw["doi"] = [d for d in raw.get("doi", []) if "[doi]" in d]
        return _finish(number, raw)

    for line in lines:
        line = line.rstrip("\r\n").lstrip("﻿")
        if not line.strip():
            continue
        match = _NBIB_LINE.match(line)
        if match is None:
            if last and line.startswith("      "):
                raw[last][-1] += " " + line.strip()
            continue
        tag, value = match.group(1), match.group(2).strip()
        if tag == "PMID" and raw:
            number += 1
            yield flush()
            raw = {}
        key = NBIB_TAGS.get(tag)
        last = key
        if key is not None:
            raw.setdefault(key, []).append(value)
    if raw:
        number += 1
        yield flush()


# ---- BibTeX ---------------------------------------------------------------------------

BIB_FIELDS = {
    "title": "title",
    "author": "authors",
    "year": "year",
    "doi": "doi",
    "journal": "journal",
    "booktitle": "journal",
    "abstract": "abstract",
    "keywords": "keywords",
    "volume": "volume",
    "number": "issue",
    "pages": "pages",
    "url": "url",
    "pmid": "pmid",
}
_LATEX = {r"\&": "&", "--": "-", "~": " ", r"\%": "%", r"\_": "_"}


def _bib_entries(lines: Iterable[str]) -> Iterator[str]:
    """Yields the body of each @type{...} entry (comments and @string are skipped)."""
    buffer: list[str] = []
    depth = 0
    inside = False
    for line in lines:
        for char in line:
            if not inside:
                if char == "@":
                    inside, buffer, depth = True, ["@"], 0
                continue
            buffer.append(char)
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    inside = False
                    yield "".join(buffer)


def _bib_fields(entry: str) -> dict[str, str]:
    body = entry[entry.index("{") + 1 : -1]
    _, _, rest = body.partition(",")  # drop the citation key
    out: dict[str, str] = {}
    i, n = 0, len(rest)
    while i < n:
        match = re.compile(r"\s*([A-Za-z_-]+)\s*=\s*").match(rest, i)
        if not match:
            break
        name, i = match.group(1).lower(), match.end()
        if i < n and rest[i] in '{"':
            close = "}" if rest[i] == "{" else '"'
            depth, j = 0, i
            while j < n:
                c = rest[j]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                if (close == "}" and depth == 0 and c == "}") or (
                    close == '"' and j > i and c == '"' and depth == 0
                ):
                    break
                j += 1
            value = rest[i + 1 : j]
            i = j + 1
        else:
            j = rest.find(",", i)
            j = n if j == -1 else j
            value = rest[i:j]
            i = j
        comma = rest.find(",", i)
        i = n if comma == -1 else comma + 1
        out[name] = value
    return out


def _bib_clean(value: str) -> str:
    for code, plain in _LATEX.items():
        value = value.replace(code, plain)
    value = re.sub(r"[{}]", "", value)
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", value)).strip()


def read_bibtex(lines: Iterable[str]) -> Iterator[Item]:
    number = 0
    for entry in _bib_entries(lines):
        kind = entry[1 : entry.find("{")].strip().lower()
        if kind in ("comment", "string", "preamble"):
            continue
        number += 1
        raw: dict[str, list[str]] = {}
        for name, value in _bib_fields(entry).items():
            key = BIB_FIELDS.get(name)
            if key is None:
                continue
            text = _bib_clean(value)
            if key == "authors":
                raw[key] = [a.strip() for a in re.split(r"\s+and\s+", text) if a.strip()]
            elif key == "keywords":
                raw[key] = [k.strip() for k in re.split(r"[;,]", text) if k.strip()]
            else:
                raw.setdefault(key, []).append(text)
        yield _finish(number, raw)


# ---- CSV ------------------------------------------------------------------------------

CSV_COLUMNS = {
    "title": ("title", "titulo", "article title", "document title"),
    "authors": ("authors", "author", "autores", "autor", "author full names"),
    "year": ("year", "ano", "publication year", "py"),
    "doi": ("doi",),
    "pmid": ("pmid", "pubmed id"),
    "journal": ("journal", "revista", "source title", "journal/book", "source"),
    "abstract": ("abstract", "resumo"),
    "keywords": ("keywords", "palavras-chave", "author keywords"),
    "volume": ("volume",),
    "issue": ("issue", "numero", "número"),
    "pages": ("pages", "paginas", "páginas"),
    "url": ("url", "link"),
}


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.strip().lower().lstrip("﻿"))
    return "".join(c for c in text if not unicodedata.combining(c))


def read_csv(lines: Iterable[str]) -> Iterator[Item]:
    iterator = iter(lines)
    first = next(iterator, "")
    delimiter = ";" if first.count(";") > first.count(",") else ","
    header = next(csv.reader([first], delimiter=delimiter), [])
    names = [_plain(h) for h in header]
    index: dict[str, int] = {}
    for key, options in CSV_COLUMNS.items():
        for pos, name in enumerate(names):
            if name in {_plain(o) for o in options}:
                index[key] = pos
                break
    for number, row in enumerate(csv.reader(iterator, delimiter=delimiter), start=1):
        if not any(cell.strip() for cell in row):
            continue
        raw: dict[str, list[str]] = {}
        for key, pos in index.items():
            if pos < len(row) and row[pos].strip():
                raw[key] = [row[pos]]
        if "authors" in raw:
            raw["authors"] = [a for a in re.split(r"\s*;\s*", raw["authors"][0]) if a]
        yield _finish(number, raw)


READERS = {"ris": read_ris, "nbib": read_nbib, "bibtex": read_bibtex, "csv": read_csv}
