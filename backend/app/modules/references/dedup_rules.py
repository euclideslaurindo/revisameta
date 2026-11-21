"""Multi-criteria duplicate detection rules (docs/modulos.md 7.2, lesson L4).

Approved at stage 5 (docs/roteiro.md):
- certain: same DOI or same PMID;
- probable: ALL together: whole normalized title with similarity >= 0.95 (rapidfuzz
  token_sort_ratio), same year (not counted when one of them has no year), same first
  author surname (no accents), and journal, volume and pages equal when both have them;
- related, never a duplicate: titles that differ in numbers or in words such as Part,
  Erratum, Correction, Comment, Reply, Retraction (an erratum may matter).

Pure functions: no database, so every rule is tested on its own.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from rapidfuzz import fuzz


class DedupSettings(BaseModel):
    title_threshold: float = Field(default=0.95, ge=0.8, le=1.0)


# Words that make two similar titles different records (pt, en, es).
MARKERS = {
    "part": "part",
    "parte": "part",
    "erratum": "erratum",
    "errata": "erratum",
    "correction": "correction",
    "correcao": "correction",
    "corrigendum": "correction",
    "comment": "comment",
    "commentary": "comment",
    "comentario": "comment",
    "reply": "reply",
    "response": "reply",
    "resposta": "reply",
    "retraction": "retraction",
    "retracted": "retraction",
    "retratacao": "retraction",
}


def plain(text: str | None) -> str:
    """Lower case, no accents, no punctuation, single spaces."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def first_author_surname(authors: str | None) -> str:
    """'Silva, Ana; Souza, B' -> 'silva'; 'Ana Silva and ...' -> 'silva'; 'Lima D' -> 'lima'."""
    if not authors:
        return ""
    first = re.split(r";| and ", authors)[0].strip()
    if "," in first:
        surname = first.split(",")[0]
    else:
        words = first.split()
        # "Lima D" (MEDLINE AU) keeps the first word; "Ana Silva" keeps the last.
        surname = (
            words[0] if len(words) > 1 and len(words[-1]) <= 2 else (words[-1] if words else "")
        )
    return plain(surname)


def _numbers(title: str) -> set[str]:
    return set(re.findall(r"\d+", title))


def _core(title: str) -> str:
    return " ".join(w for w in title.split() if w not in MARKERS and not w.isdigit())


def _markers(title: str) -> set[str]:
    return {MARKERS[w] for w in title.split() if w in MARKERS}


@dataclass
class Candidate:
    id: Any
    title: str  # plain
    year: int | None
    surname: str
    journal: str
    volume: str
    pages: str
    doi: str | None
    pmid: str | None


def candidate(
    id_: Any,
    title: str,
    authors: str | None,
    year: int | None,
    journal: str | None,
    volume: str | None,
    pages: str | None,
    doi: str | None,
    pmid: str | None,
) -> Candidate:
    return Candidate(
        id=id_,
        title=plain(title),
        year=year,
        surname=first_author_surname(authors),
        journal=plain(journal),
        volume=plain(volume),
        pages=plain(pages).replace(" ", ""),
        doi=doi,
        pmid=pmid,
    )


def compare(
    a: Candidate, b: Candidate, settings: DedupSettings
) -> tuple[str, dict[str, Any], float] | None:
    """(kind, criteria, title score) or None when the pair is not worth showing."""
    score = fuzz.token_sort_ratio(a.title, b.title) / 100
    criteria: dict[str, Any] = {"title_score": round(score, 4)}
    if a.doi and a.doi == b.doi:
        criteria["same_doi"] = True
    if a.pmid and a.pmid == b.pmid:
        criteria["same_pmid"] = True
    if criteria.get("same_doi") or criteria.get("same_pmid"):
        return "certain", criteria, score
    numbers = _numbers(a.title) != _numbers(b.title)
    words = _markers(a.title) ^ _markers(b.title)
    if numbers or words:
        # Same title once numbers and marker words are set aside: related, never a
        # duplicate ("Part 1" x "Part 2", erratum x article).
        core = fuzz.token_sort_ratio(_core(a.title), _core(b.title)) / 100
        if core < settings.title_threshold:
            return None
        if numbers:
            criteria["differs_in_numbers"] = True
        if words:
            criteria["differs_in_words"] = sorted(words)
        return "related", criteria, score
    if score < settings.title_threshold:
        return None
    # Every criterion must hold; one that cannot be checked is recorded as such.
    if a.year is None or b.year is None:
        criteria["year"] = "missing"
    elif a.year == b.year:
        criteria["year"] = "same"
    else:
        return None
    if not a.surname or a.surname != b.surname:
        return None
    criteria["first_author"] = "same"
    for name in ("journal", "volume", "pages"):
        x, y = getattr(a, name), getattr(b, name)
        if x and y:
            if x != y:
                return None
            criteria[name] = "same"
    return "probable", criteria, score


def blocks(items: list[Candidate]) -> dict[str, list[Candidate]]:
    """Groups that may hold duplicates, so 20 thousand records are never compared all
    against all: same DOI, same PMID, or same first author surname."""
    groups: dict[str, list[Candidate]] = {}
    for c in items:
        if c.doi:
            groups.setdefault("doi:" + c.doi, []).append(c)
        if c.pmid:
            groups.setdefault("pmid:" + c.pmid, []).append(c)
        if c.surname:
            groups.setdefault("au:" + c.surname, []).append(c)
    return {k: v for k, v in groups.items() if len(v) > 1}
