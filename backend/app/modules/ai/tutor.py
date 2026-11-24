"""Tutor (IA1; docs/ia.md 7.15.1 and 7.15.3 rule 2; stage 7 step 4).

The tutor explains concepts and the project's own results. It never sees an
opportunity to invent a number: the R results are given to it as named facts, it must
write placeholders such as {{pooled_effect}}, and the system replaces them with the
values R computed. Any digit the AI writes by itself, or a placeholder that does not
exist, is flagged on screen as "not verified". Nothing it says is saved as data.

What is sent: the question and, when asked about an analysis, the numbers of that
analysis with the outcome name and the measure. Never member names, comments or notes.
"""

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.ai import AIProvider
from app.integrations.stats_client import StatsClient
from app.modules.ai.gateway import call
from app.modules.analysis.run import RunIn, run
from app.modules.projects.access import ProjectContext

PROMPT_VERSION = "tutor-v1"
SYSTEM = (Path(__file__).parents[2] / "integrations/ai/prompts/tutor-v1.md").read_text("utf-8")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
DIGIT = re.compile(r"\d+(?:[.,]\d+)*")
RATIO = {"OR", "RR"}


class TutorIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    lang: Literal["pt-BR", "en"] = "pt-BR"
    analysis: RunIn | None = None  # explain this analysis (same settings as the wizard)


class TutorAnswer(BaseModel):
    text: str = Field(max_length=4000)


class TutorOut(BaseModel):
    text: str  # placeholders already replaced by the values from R
    unverified: list[str]  # numbers the AI wrote itself or unknown placeholders
    facts_used: list[str]
    cached: bool
    provider: str
    model: str
    prompt_version: str


def _fmt(value: float, lang: str, digits: int = 2) -> str:
    text = f"{value:,.{digits}f}"
    if lang == "pt-BR":
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return text


def _p(value: float, lang: str) -> str:
    if value < 0.001:
        return "< 0,001" if lang == "pt-BR" else "< 0.001"
    return _fmt(value, lang, 3)


def facts_of(result: dict[str, Any], measure: str, lang: str) -> dict[str, str]:
    """Named values from the R result, formatted for the reader (no computation)."""
    pooled = result.get("pooled", {})
    het = result.get("heterogeneity", {})
    shown = pooled.get("exp") if measure in RATIO and pooled.get("exp") else pooled
    facts: dict[str, str] = {"ci_level": "95"}
    for key, source, name in (
        ("pooled_effect", shown, "estimate"),
        ("ci_lower", shown, "ci_lb"),
        ("ci_upper", shown, "ci_ub"),
        ("pi_lower", shown, "pi_lb"),
        ("pi_upper", shown, "pi_ub"),
        ("tau2", het, "tau2"),
        ("q", het, "q"),
    ):
        if isinstance(source.get(name), (int, float)):
            facts[key] = _fmt(float(source[name]), lang)
    if isinstance(het.get("i2"), (int, float)):
        facts["i2"] = _fmt(float(het["i2"]), lang, 1) + "%"
    for key, source, name in (("p_value", pooled, "p_value"), ("q_p_value", het, "q_p")):
        if isinstance(source.get(name), (int, float)):
            facts[key] = _p(float(source[name]), lang)
    if isinstance(result.get("k"), int):
        facts["k"] = str(result["k"])
    return facts


def fill(text: str, facts: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """Replaces placeholders; flags digits written by the AI and unknown placeholders."""
    unverified: list[str] = []
    used: list[str] = []
    for found in DIGIT.findall(PLACEHOLDER.sub(" ", text)):
        unverified.append(found)

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in facts:
            used.append(name)
            return facts[name]
        unverified.append(match.group(0))
        return match.group(0)

    return PLACEHOLDER.sub(replace, text), list(dict.fromkeys(unverified)), used


async def ask(
    session: AsyncSession,
    ctx: ProjectContext,
    stats: StatsClient,
    provider: AIProvider,
    data: TutorIn,
) -> TutorOut:
    facts: dict[str, str] = {}
    context = ""
    if data.analysis is not None:
        main = await run(session, ctx, stats, data.analysis)
        facts = facts_of(main.result, main.assembly.measure, data.lang)
        context = (
            f"Outcome: {main.assembly.outcome_name} ({main.assembly.timepoint}). "
            f"Measure: {main.assembly.measure}. Model: {main.method}, test: {main.test}.\n"
        )
    listed = "\n".join(f"- {{{{{k}}}}}" for k in facts) or "(none)"
    prompt = (
        f"LANGUAGE: {data.lang}\n"
        f"CONTEXT: {context or '(none)'}\n"
        f"FACTS (placeholders you may use):\n{listed}\n"
        f"QUESTION:\n<<<\n{data.question}\n>>>"
    )
    result = await call(
        session,
        ctx,
        provider,
        function="tutor",
        prompt_version=PROMPT_VERSION,
        system=SYSTEM,
        prompt=prompt,
        schema=TutorAnswer,
    )
    text, unverified, used = fill(result.answer.text, facts)
    return TutorOut(
        text=text,
        unverified=unverified,
        facts_used=used,
        cached=result.cached,
        provider=result.provider,
        model=result.model,
        prompt_version=PROMPT_VERSION,
    )
