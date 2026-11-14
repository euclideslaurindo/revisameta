import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.studies.models import StudyDesign

_DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DOI_SHAPE = re.compile(r"^10\.\d{4,9}/\S+$")


def normalize_doi(value: str | None) -> str | None:
    """'https://doi.org/10.1000/ABC ' -> '10.1000/abc'. Raises ValueError if not a DOI."""
    if value is None or not value.strip():
        return None
    doi = _DOI_PREFIX.sub("", value.strip()).strip().lower()
    if not _DOI_SHAPE.match(doi):
        raise ValueError("invalid DOI")
    return doi


def normalize_pmid(value: str | int | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    pmid = str(value).strip()
    if pmid.endswith(".0"):  # spreadsheets store numbers as floats
        pmid = pmid[:-2]
    if not pmid.isdigit() or len(pmid) > 9:
        raise ValueError("invalid PMID")
    return pmid


class ReferenceIn(BaseModel):
    title: str = Field(min_length=1, max_length=2000)
    authors: str | None = Field(default=None, max_length=5000)
    year: int | None = Field(default=None, ge=1800, le=2100)
    doi: str | None = None
    pmid: str | None = None
    journal: str | None = Field(default=None, max_length=300)

    _doi = field_validator("doi")(normalize_doi)
    _pmid = field_validator("pmid")(normalize_pmid)


class ReferenceUpdate(BaseModel):
    version: int
    title: str | None = Field(default=None, min_length=1, max_length=2000)
    authors: str | None = Field(default=None, max_length=5000)
    year: int | None = Field(default=None, ge=1800, le=2100)
    doi: str | None = None
    pmid: str | None = None
    journal: str | None = Field(default=None, max_length=300)

    _doi = field_validator("doi")(normalize_doi)
    _pmid = field_validator("pmid")(normalize_pmid)


class ReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    authors: str | None
    year: int | None
    doi: str | None
    pmid: str | None
    journal: str | None
    version: int


class ReportOut(BaseModel):
    id: uuid.UUID
    is_primary: bool
    reference: ReferenceOut


class StudyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    design: StudyDesign
    notes: str | None = Field(default=None, max_length=5000)
    reference: ReferenceIn


class StudyUpdate(BaseModel):
    version: int
    label: str | None = Field(default=None, min_length=1, max_length=120)
    design: StudyDesign | None = None
    notes: str | None = Field(default=None, max_length=5000)


class StudyOut(BaseModel):
    id: uuid.UUID
    label: str
    design: StudyDesign
    notes: str | None
    version: int
    reports: list[ReportOut]


class ReportCreate(BaseModel):
    reference: ReferenceIn
    is_primary: bool = False


class MergeIn(BaseModel):
    """Moves every report of `other_study_id` into this study (same patients)."""

    other_study_id: uuid.UUID
