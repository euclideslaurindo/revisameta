import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.protocol.models import OutcomeType


def _clean_timepoints(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        if item and item.lower() not in {c.lower() for c in cleaned}:
            cleaned.append(item)
    return cleaned


class OutcomeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: OutcomeType
    higher_is_better: bool = True
    is_primary: bool = False
    timepoints: list[str] = Field(default_factory=list, max_length=20)
    description: str | None = Field(default=None, max_length=2000)
    position: int = 0

    _timepoints = field_validator("timepoints")(_clean_timepoints)


class OutcomeUpdate(BaseModel):
    version: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: OutcomeType | None = None
    higher_is_better: bool | None = None
    is_primary: bool | None = None
    timepoints: list[str] | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=2000)
    position: int | None = None

    @field_validator("timepoints")
    @classmethod
    def _timepoints(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else _clean_timepoints(values)


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: OutcomeType
    higher_is_better: bool
    is_primary: bool
    timepoints: list[str]
    description: str | None
    position: int
    version: int


class GroupCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    rule_description: str | None = Field(default=None, max_length=2000)
    position: int = 0


class GroupUpdate(BaseModel):
    version: int
    label: str | None = Field(default=None, min_length=1, max_length=120)
    rule_description: str | None = Field(default=None, max_length=2000)
    position: int | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    rule_description: str | None
    position: int
    version: int
