"""Suggested risk-of-bias judgements from the official algorithms (docs/modulos.md 7.6).

Each domain algorithm is stored in the template as a decision tree, transcribed node by
node from the instrument's official flowchart. Node types:

- a string: the judgement reached (e.g. "serious");
- {"q": key, "b": [[answers, node], ...]}: follow the branch holding the answer given;
- {"count": [keys], "cases": [{"answers": [...], "all": true | "at_least": n, "then": node}],
   "else": node}: count answers over several questions (first matching case wins);
- {"worst_of": [node, ...], "then": {judgement: node}}: evaluate parts, take the worst
   and continue from it (e.g. ROBINS-I V2, domain 3, parts A and B).

The suggestion is only a suggestion: the reviewer may disagree with a justification
(rule 0.2). Nothing here is statistics; it is the instrument's own decision logic.

Conditions for asking a question (`ask_if`): {"q": key, "in": [...]},
{"any": [cond, ...]} or {"all": [cond, ...]}.
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.risk_of_bias.catalog import Domain, Template

Answers = Mapping[str, str]


class Incomplete(Exception):  # noqa: N818 - control flow, not an error
    """A question needed by the algorithm has no answer yet."""

    def __init__(self, question: str) -> None:
        super().__init__(question)
        self.question = question


def _answer(answers: Answers, key: str) -> str:
    value = answers.get(key)
    if not value:
        raise Incomplete(key)
    return value


def evaluate(node: Any, answers: Answers, levels: list[str]) -> str:
    """The judgement reached by the tree. Raises Incomplete if an answer is missing."""
    if isinstance(node, str):
        return node
    if "q" in node:
        value = _answer(answers, node["q"])
        for options, child in node["b"]:
            if value in options:
                return evaluate(child, answers, levels)
        raise Incomplete(node["q"])  # e.g. "NA" where the algorithm needs an answer
    if "count" in node:
        values = [_answer(answers, q) for q in node["count"]]
        for case in node["cases"]:
            hits = sum(1 for v in values if v in case["answers"])
            if (case.get("all") and hits == len(values)) or (
                "at_least" in case and hits >= case["at_least"]
            ):
                return evaluate(case["then"], answers, levels)
        return evaluate(node["else"], answers, levels)
    if "worst_of" in node:
        parts = [evaluate(child, answers, levels) for child in node["worst_of"]]
        worst = max(parts, key=levels.index)
        return evaluate(node["then"][worst], answers, levels)
    raise ValueError(f"unknown node: {node}")


def suggest_domain(
    domain: "Domain", answers: Answers, levels: list[str], variant: str | None
) -> str | None:
    """Suggested judgement of a domain, or None while answers are missing."""
    tree = domain.algorithm
    if tree is None:
        return None
    if domain.variants:
        if variant is None or variant not in tree:
            return None
        tree = tree[variant]
    try:
        return evaluate(tree, answers, levels)
    except Incomplete:
        return None


def suggest_overall(rule: str, judgements: list[str], levels: list[str]) -> str | None:
    """Overall judgement from the domain judgements (all domains must be judged)."""
    if not judgements:
        return None
    if rule == "worst":
        return max(judgements, key=levels.index)
    if rule == "robins_2016":
        # ROBINS-I 2016 (Table 3): Critical > Serious > No information > Moderate > Low.
        for level in ("critical", "serious", "no_information", "moderate"):
            if level in judgements:
                return level
        return "low"
    if rule == "rob2":
        # RoB 2: Low if all domains Low; High if any High; Some concerns otherwise.
        if all(j == "low" for j in judgements):
            return "low"
        if any(j == "high" for j in judgements):
            return "high"
        return "some_concerns"
    raise ValueError(rule)


def overall_warnings(
    judgements: list[str], warn_several: list[str], suggested: str | None
) -> list[str]:
    """Situations where the official guidance leaves the decision to the reviewer."""
    warnings = []
    if suggested in warn_several and judgements.count(suggested) >= 2:
        # Several domains at this level may justify a worse overall judgement.
        warnings.append(f"several_{suggested}")
    if suggested == "no_information":
        # ROBINS-I 2016, Table 3: "a judgement is required for this".
        warnings.append("no_information_needs_judgement")
    return warnings


def is_asked(condition: dict[str, Any] | None, answers: Mapping[str, str | None]) -> bool:
    """Whether a question applies, given the answers so far (official "If ... to x.y")."""
    if condition is None:
        return True
    if "any" in condition:
        return any(is_asked(c, answers) for c in condition["any"])
    if "all" in condition:
        return all(is_asked(c, answers) for c in condition["all"])
    return answers.get(condition["q"]) in condition["in"]


# ---- Validation of templates -----------------------------------------------------------


def _walk(node: Any, questions: set[str], levels: list[str], seen: set[str]) -> None:
    if isinstance(node, str):
        if node not in levels:
            raise ValueError(f"unknown judgement {node}")
        return
    if "q" in node:
        if node["q"] not in questions:
            raise ValueError(f"unknown question {node['q']}")
        seen.add(node["q"])
        for _, child in node["b"]:
            _walk(child, questions, levels, seen)
    elif "count" in node:
        for q in node["count"]:
            if q not in questions:
                raise ValueError(f"unknown question {q}")
            seen.add(q)
        for case in node["cases"]:
            _walk(case["then"], questions, levels, seen)
        _walk(node["else"], questions, levels, seen)
    elif "worst_of" in node:
        for child in node["worst_of"]:
            _walk(child, questions, levels, seen)
        for key, child in node["then"].items():
            if key not in levels:
                raise ValueError(f"unknown judgement {key}")
            _walk(child, questions, levels, seen)
    else:
        raise ValueError(f"unknown node: {node}")


def check_template(template: "Template") -> None:
    """Every tree uses known questions and judgements, and reaches every question."""
    levels = template.judgement.levels
    if not levels or template.judgement.overall is None:
        raise ValueError("algorithm templates need levels and an overall rule")
    for domain in template.domains:
        if domain.algorithm is None:
            raise ValueError(f"domain {domain.key} has no algorithm")
        trees = (
            {v.key: domain.algorithm[v.key] for v in domain.variants}
            if domain.variants
            else {"": domain.algorithm}
        )
        for variant, tree in trees.items():
            questions = {
                q.key for q in domain.questions if not domain.variants or q.variant == variant
            }
            seen: set[str] = set()
            _walk(tree, questions, levels, seen)
            if seen != questions:
                raise ValueError(f"{domain.key}{variant}: questions not used {questions - seen}")
