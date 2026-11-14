"""Catalog of risk-of-bias instruments (docs/modulos.md 7.6, docs/modelo-dados-etapa2.md).

Each instrument is a JSON template in `templates/` with its structure only: domains,
question numbers, level of appraisal, answer options, version and citation. The
official wording of the questions is never shipped (copyright, rule 0.1.7); the
project admin pastes it from the official source when the group may use it.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TEMPLATES_DIR = Path(__file__).parent / "templates"

Level = Literal["study", "outcome", "result"]
Family = Literal["jbi", "nos", "rob2", "robins_i", "robins_e", "generic"]
DESIGNS = {
    "rct",
    "cohort_prospective",
    "cohort_retrospective",
    "case_control",
    "cross_sectional",
    "case_series",
    "other",
}
# Order used to suggest an instrument when several enabled ones fit the design.
FAMILY_PREFERENCE: list[str] = ["rob2", "robins_i", "robins_e", "jbi", "nos", "generic"]


class LocalizedText(BaseModel):
    pt_br: str = Field(alias="pt-BR")
    en: str

    model_config = {"populate_by_name": True}


class Question(BaseModel):
    key: str = Field(min_length=1, max_length=20)
    answers: str  # key of an answer set of the template
    level: Level = "study"


class Domain(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: LocalizedText
    questions: list[Question]


class Judgement(BaseModel):
    # group_rule: JBI, NOS and generic (no official overall rule; the group decides).
    kind: Literal["group_rule", "algorithm"]


class Template(BaseModel):
    key: str
    family: Family
    name: LocalizedText
    version: str
    citation: str
    source_url: str
    designs: list[str]
    scope: Literal["study", "result"]
    answer_sets: dict[str, list[str]]
    judgement: Judgement
    domains: list[Domain]

    @model_validator(mode="after")
    def _consistent(self) -> "Template":
        unknown = set(self.designs) - DESIGNS
        if unknown:
            raise ValueError(f"unknown designs: {sorted(unknown)}")
        domain_keys = [d.key for d in self.domains]
        if len(domain_keys) != len(set(domain_keys)):
            raise ValueError("duplicate domain key")
        for domain in self.domains:
            keys = [q.key for q in domain.questions]
            if len(keys) != len(set(keys)):
                raise ValueError(f"duplicate question key in {domain.key}")
            for q in domain.questions:
                if q.answers not in self.answer_sets:
                    raise ValueError(f"unknown answer set {q.answers}")
        return self

    def question_keys(self) -> list[str]:
        """Stable keys of every question, as "domain.question"."""
        return [f"{d.key}.{q.key}" for d in self.domains for q in d.questions]


@lru_cache
def catalog() -> dict[str, Template]:
    out: dict[str, Template] = {}
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        template = Template.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if template.key != path.stem:
            raise ValueError(f"{path.name}: key must match the file name")
        out[template.key] = template
    return out
