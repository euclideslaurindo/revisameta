"""The group's rule for the overall judgement of JBI, Newcastle-Ottawa and generic tools.

These instruments have no official overall rule (docs/modulos.md 7.6): JBI has no cut-off
and Newcastle-Ottawa no universal quality bands. The group may define one; without it,
the overall judgement is free and mandatory. A rule is evaluated in order:

    {"levels": ["low", "moderate", "high"],
     "cases": [
        {"then": "high", "count": {"answers": ["N", "U"], "at_least": 2,
                                   "questions": ["selection.1", "confounding.4"]}},
        {"then": "good", "stars_at_least": 7}],
     "else": "low"}

`count` counts answers (every target of per-outcome questions included); `questions`
empty = all questions. `stars_at_least` sums Newcastle-Ottawa stars. Nothing is shown as
a total score for JBI (rule 0.2): the rule only places the study in a level.
"""

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from app.modules.risk_of_bias.catalog import Template
    from app.modules.risk_of_bias.models import RobAnswer

DEFAULT_LEVELS = ["low", "moderate", "high"]


class CountCase(BaseModel):
    answers: list[str] = Field(min_length=1)
    at_least: int = Field(ge=1, le=100)
    questions: list[str] = Field(default_factory=list)


class Case(BaseModel):
    then: str
    count: CountCase | None = None
    stars_at_least: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _one_criterion(self) -> "Case":
        if (self.count is None) == (self.stars_at_least is None):
            raise ValueError("a case needs exactly one criterion")
        return self


class GroupRule(BaseModel):
    levels: list[str] = Field(min_length=2, max_length=6)
    cases: list[Case] = Field(default_factory=list, max_length=10)
    else_: str = Field(alias="else")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _consistent(self) -> "GroupRule":
        cleaned = [level.strip() for level in self.levels]
        if any(not level or len(level) > 30 for level in cleaned) or len(set(cleaned)) != len(
            cleaned
        ):
            raise ValueError("levels must be distinct names of up to 30 characters")
        self.levels = cleaned
        for case in self.cases:
            if case.then not in self.levels:
                raise ValueError("case result must be one of the levels")
        if self.else_ not in self.levels:
            raise ValueError("else must be one of the levels")
        return self


def check_rule(rule: GroupRule, template: "Template") -> None:
    """Answers and questions of the rule exist in the instrument."""
    keys = set(template.question_keys())
    values = {v for values in template.answer_sets.values() for v in values}
    for case in rule.cases:
        if case.count:
            if set(case.count.answers) - values:
                raise ValueError("unknown answer in rule")
            if set(case.count.questions) - keys:
                raise ValueError("unknown question in rule")
        if case.stars_at_least is not None and template.family != "nos":
            raise ValueError("stars apply to Newcastle-Ottawa only")


def group_levels(rule: dict[str, Any] | None) -> list[str]:
    return GroupRule.model_validate(rule).levels if rule else list(DEFAULT_LEVELS)


def evaluate_group_rule(
    rule: dict[str, Any] | None, template: "Template", answers: list["RobAnswer"]
) -> str | None:
    """Suggested overall level, or None without a rule or while study questions are open."""
    if not rule:
        return None
    parsed = GroupRule.model_validate(rule)
    study_keys = [
        f"{d.key}.{q.key}" for d in template.domains for q in d.questions if q.level == "study"
    ]
    plain = {a.question_key: a.answer for a in answers if a.outcome_id is None}
    if any(not plain.get(k) for k in study_keys):
        return None
    for case in parsed.cases:
        if case.count:
            wanted = set(case.count.questions)
            hits = sum(
                1
                for a in answers
                if a.answer in case.count.answers and (not wanted or a.question_key in wanted)
            )
            if hits >= case.count.at_least:
                return case.then
        elif case.stars_at_least is not None:
            stars = sum(int(v) for v in plain.values() if v and v.isdigit())
            if stars >= case.stars_at_least:
                return case.then
    return parsed.else_
