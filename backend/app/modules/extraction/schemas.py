import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.extraction.models import DataSource, DispersionType, ValueType

FieldType = Literal["text", "textarea", "number", "select", "date"]
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


class FormField(BaseModel):
    key: str
    type: FieldType
    # Built-in fields use an i18n key; fields added by the admin carry a free label.
    label_key: str | None = None
    label: str | None = Field(default=None, max_length=200)
    help: str | None = Field(default=None, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not _KEY.match(value):
            raise ValueError("key must be snake_case")
        return value

    @model_validator(mode="after")
    def _checks(self) -> "FormField":
        if not self.label_key and not self.label:
            raise ValueError("label is required")
        if self.type == "select" and not self.options:
            raise ValueError("select needs options")
        return self


class FormSchema(BaseModel):
    fields: list[FormField] = Field(max_length=80)

    @field_validator("fields")
    @classmethod
    def _unique(cls, fields: list[FormField]) -> list[FormField]:
        keys = [f.key for f in fields]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate field key")
        return fields


DEFAULT_FORM = FormSchema(
    fields=[
        FormField(key="country", type="text", label_key="extraction.fields.country"),
        FormField(key="period", type="text", label_key="extraction.fields.period"),
        FormField(key="centers", type="number", label_key="extraction.fields.centers"),
        FormField(key="n_total", type="number", label_key="extraction.fields.n_total"),
        FormField(key="eligibility", type="textarea", label_key="extraction.fields.eligibility"),
        FormField(key="cutoff_used", type="text", label_key="extraction.fields.cutoff_used"),
        FormField(key="surgery_type", type="text", label_key="extraction.fields.surgery_type"),
        FormField(key="follow_up", type="text", label_key="extraction.fields.follow_up"),
        FormField(key="funding", type="text", label_key="extraction.fields.funding"),
        FormField(
            key="conflict_of_interest",
            type="text",
            label_key="extraction.fields.conflict_of_interest",
        ),
    ]
)


class FormOut(BaseModel):
    id: uuid.UUID
    form_version: int
    schema_: FormSchema = Field(alias="schema")
    version: int

    model_config = ConfigDict(populate_by_name=True)


class FormUpdate(BaseModel):
    version: int
    schema_: FormSchema = Field(alias="schema")

    model_config = ConfigDict(populate_by_name=True)


def validate_characteristics(schema: FormSchema, values: dict[str, Any]) -> dict[str, Any]:
    """Keeps only known fields and checks their types. Raises ValueError(key)."""
    by_key = {f.key: f for f in schema.fields}
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        field = by_key.get(key)
        if field is None:
            raise ValueError(key)
        if value is None or value == "":
            cleaned[key] = None
            continue
        if field.type == "number":
            try:
                cleaned[key] = float(str(value).replace(",", "."))
            except ValueError as exc:
                raise ValueError(key) from exc
        elif field.type == "select":
            if value not in field.options:
                raise ValueError(key)
            cleaned[key] = value
        elif field.type == "date":
            try:
                cleaned[key] = date.fromisoformat(str(value)).isoformat()
            except ValueError as exc:
                raise ValueError(key) from exc
        else:
            text = str(value)
            if len(text) > 5000:
                raise ValueError(key)
            cleaned[key] = text
    return cleaned


class ExtractionSummary(BaseModel):
    id: uuid.UUID
    study_id: uuid.UUID
    extractor_id: uuid.UUID | None
    extractor_name: str | None
    kind: str
    status: str
    form_id: uuid.UUID
    outdated_form: bool
    data_version: int
    version: int
    updated_at: datetime


class ArmIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    n: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    mapped_group_id: uuid.UUID | None = None
    position: int = 0


class ArmUpdate(BaseModel):
    version: int
    label: str | None = Field(default=None, min_length=1, max_length=120)
    n: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    mapped_group_id: uuid.UUID | None = None
    position: int | None = None


class ArmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    n: int | None
    description: str | None
    mapped_group_id: uuid.UUID | None
    position: int
    version: int


class MeasureIn(BaseModel):
    scale_name: str | None = Field(default=None, max_length=200)
    scale_min: Decimal | None = None
    scale_max: Decimal | None = None
    higher_is_better: bool = True


class MeasureOut(MeasureIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outcome_id: uuid.UUID
    version: int


# Which value columns each dispersion type uses (bloco A, item 1).
DISPERSION_FIELDS: dict[DispersionType, tuple[str, ...]] = {
    DispersionType.SD: ("sd",),
    DispersionType.SE: ("se",),
    DispersionType.CI95: ("ci_low", "ci_high"),
    DispersionType.IQR: ("q1", "q3"),
    DispersionType.RANGE: ("min", "max"),
    DispersionType.NOT_REPORTED: (),
}
_ALL_DISPERSION = ("sd", "se", "ci_low", "ci_high", "q1", "q3", "min", "max")


class EffectReported(BaseModel):
    """Effect already computed by the article (e.g. adjusted OR/HR with CI)."""

    measure: Literal["OR", "RR", "HR", "MD", "SMD", "other"]
    estimate: Decimal
    ci_low: Decimal | None = None
    ci_high: Decimal | None = None
    se: Decimal | None = None


class OutcomeDataFields(BaseModel):
    n: int | None = None
    mean: Decimal | None = None
    dispersion_type: DispersionType | None = None
    dispersion_source: str | None = Field(default=None, max_length=300)
    sd: Decimal | None = None
    se: Decimal | None = None
    ci_low: Decimal | None = None
    ci_high: Decimal | None = None
    median: Decimal | None = None
    q1: Decimal | None = None
    q3: Decimal | None = None
    min: Decimal | None = None
    max: Decimal | None = None
    events: int | None = None
    total: int | None = None
    t_stat: Decimal | None = None
    p_value: Decimal | None = None
    effect_reported: EffectReported | None = None
    adjusted: bool = False
    adjusted_for: str | None = Field(default=None, max_length=1000)
    source: DataSource = DataSource.ARTICLE
    source_location: str | None = Field(default=None, max_length=300)
    annotation_id: uuid.UUID | None = None


def check_dispersion(data: dict[str, Any]) -> None:
    """A dispersion number needs its type, and the type decides which columns are filled."""
    given = [f for f in _ALL_DISPERSION if data.get(f) is not None]
    kind = data.get("dispersion_type")
    if given and kind is None:
        raise ValueError("dispersion_type_required")
    if kind is None:
        return
    expected = DISPERSION_FIELDS[DispersionType(kind)]
    if any(f not in expected for f in given):
        raise ValueError("dispersion_mismatch")


class OutcomeDataIn(OutcomeDataFields):
    arm_id: uuid.UUID
    outcome_id: uuid.UUID
    timepoint: str = Field(min_length=1, max_length=60)
    value_type: ValueType = ValueType.FINAL

    @model_validator(mode="after")
    def _dispersion(self) -> "OutcomeDataIn":
        check_dispersion(self.model_dump())
        return self


class OutcomeDataUpdate(BaseModel):
    """Full replacement of the numbers of a row (keeps autosave simple and explicit)."""

    version: int
    timepoint: str | None = Field(default=None, min_length=1, max_length=60)
    value_type: ValueType | None = None
    values: OutcomeDataFields

    @model_validator(mode="after")
    def _dispersion(self) -> "OutcomeDataUpdate":
        check_dispersion(self.values.model_dump())
        return self


class OutcomeDataOut(OutcomeDataFields):
    model_config = ConfigDict(from_attributes=True)

    # Set only by confirming the direction sentence; cleared by the server when the
    # sentence changes (mean, scale direction or group link).
    direction_confirmed: bool = False

    id: uuid.UUID
    arm_id: uuid.UUID
    outcome_id: uuid.UUID
    timepoint: str
    value_type: ValueType
    version: int


class ExtractionDetail(ExtractionSummary):
    characteristics: dict[str, Any]
    arms: list[ArmOut]
    measures: list[MeasureOut]
    outcome_data: list[OutcomeDataOut]


class CharacteristicsUpdate(BaseModel):
    version: int
    characteristics: dict[str, Any]
