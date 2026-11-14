"""Official risk-of-bias algorithms, transcribed from the instruments' flowcharts.

Each case follows one path of the official flowchart (ROBINS-I V2, revised draft of
20 Nov 2025, pages 20-47) and checks the judgement at its end.
"""

import random

import pytest

from app.modules.risk_of_bias.algorithm import (
    is_asked,
    overall_warnings,
    suggest_domain,
    suggest_overall,
)
from app.modules.risk_of_bias.catalog import Template, catalog


def _v2() -> Template:
    return catalog()["robins_i_v2"]


def _judge(domain_key: str, answers: dict[str, str], variant: str | None = None) -> str | None:
    template = _v2()
    domain = next(d for d in template.domains if d.key == domain_key)
    return suggest_domain(domain, answers, template.judgement.levels, variant)


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"A1.1": "Y", "A1.3": "N", "A1.2": "Y", "A1.4": "N"}, "low_except_confounding"),
        ({"A1.1": "PY", "A1.3": "NI", "A1.2": "PY", "A1.4": "PY"}, "serious"),
        ({"A1.1": "Y", "A1.3": "PN", "A1.2": "WN", "A1.4": "PN"}, "moderate"),
        ({"A1.1": "Y", "A1.3": "N", "A1.2": "SN", "A1.4": "N"}, "serious"),
        ({"A1.1": "WN", "A1.3": "N", "A1.2": "WN", "A1.4": "N"}, "moderate"),
        ({"A1.1": "WN", "A1.3": "N", "A1.2": "NI", "A1.4": "N"}, "serious"),
        ({"A1.1": "Y", "A1.3": "Y", "A1.4": "Y", "A1.2": "Y"}, "critical"),
        ({"A1.1": "WN", "A1.3": "PY", "A1.4": "N", "A1.2": "Y"}, "serious"),
        ({"A1.1": "Y", "A1.3": "Y", "A1.4": "PN", "A1.2": "WN"}, "critical"),
        ({"A1.1": "SN", "A1.4": "N"}, "serious"),
        ({"A1.1": "NI", "A1.4": "PY"}, "critical"),
    ],
)
def test_domain_1_variant_a(answers: dict[str, str], expected: str) -> None:
    assert _judge("d1", answers, "A") == expected


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"B1.1": "Y", "B1.2": "Y", "B1.3": "PY", "B1.5": "N"}, "low_except_confounding"),
        ({"B1.1": "Y", "B1.2": "Y", "B1.3": "WN", "B1.5": "N"}, "moderate"),
        ({"B1.1": "Y", "B1.2": "PY", "B1.3": "SN", "B1.5": "N"}, "serious"),
        ({"B1.1": "PY", "B1.2": "WN", "B1.3": "WN", "B1.5": "PN"}, "moderate"),
        ({"B1.1": "Y", "B1.2": "WN", "B1.3": "Y", "B1.5": "Y"}, "serious"),
        ({"B1.1": "Y", "B1.2": "SN", "B1.5": "N"}, "serious"),
        ({"B1.1": "Y", "B1.2": "SN", "B1.5": "PY"}, "critical"),
        ({"B1.1": "N", "B1.4": "Y", "B1.5": "N"}, "critical"),
        ({"B1.1": "NI", "B1.4": "NI", "B1.5": "N"}, "serious"),
    ],
)
def test_domain_1_variant_b(answers: dict[str, str], expected: str) -> None:
    assert _judge("d1", answers, "B") == expected


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"2.1": "Y", "2.4": "N", "2.5": "N"}, "low"),
        ({"2.1": "Y", "2.4": "N", "2.5": "NI"}, "moderate"),
        ({"2.1": "Y", "2.4": "WY", "2.5": "PN"}, "moderate"),
        ({"2.1": "Y", "2.4": "SY", "2.5": "N"}, "serious"),
        ({"2.1": "Y", "2.4": "SY", "2.5": "Y"}, "critical"),
        ({"2.1": "N", "2.2": "Y", "2.4": "N", "2.5": "N"}, "low"),
        ({"2.1": "N", "2.2": "N", "2.3": "SY", "2.4": "N", "2.5": "N"}, "low"),
        ({"2.1": "N", "2.2": "N", "2.3": "WY", "2.4": "N", "2.5": "N"}, "moderate"),
        ({"2.1": "N", "2.2": "N", "2.3": "WY", "2.4": "SY", "2.5": "N"}, "critical"),
        ({"2.1": "N", "2.2": "N", "2.3": "N", "2.4": "N", "2.5": "N"}, "serious"),
        ({"2.1": "N", "2.2": "N", "2.3": "N", "2.4": "WY", "2.5": "N"}, "critical"),
    ],
)
def test_domain_2(answers: dict[str, str], expected: str) -> None:
    assert _judge("d2", answers) == expected


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"3.1": "Y", "3.2": "N", "3.3": "N"}, "low"),
        ({"3.1": "Y", "3.2": "Y", "3.3": "N"}, "moderate"),
        ({"3.1": "WN", "3.3": "Y", "3.4": "N"}, "moderate"),
        ({"3.1": "Y", "3.2": "N", "3.3": "NI"}, "moderate"),
        ({"3.1": "Y", "3.2": "N", "3.3": "Y", "3.4": "Y", "3.5": "N"}, "moderate"),
        ({"3.1": "SN", "3.3": "N", "3.6": "Y"}, "moderate"),
        (
            {"3.1": "Y", "3.2": "N", "3.3": "Y", "3.4": "Y", "3.5": "Y", "3.6": "N", "3.7": "PY"},
            "moderate",
        ),
        ({"3.1": "SN", "3.3": "N", "3.6": "N", "3.7": "N", "3.8": "N"}, "serious"),
        ({"3.1": "SN", "3.3": "N", "3.6": "NI", "3.7": "NI", "3.8": "Y"}, "critical"),
    ],
)
def test_domain_3(answers: dict[str, str], expected: str) -> None:
    assert _judge("d3", answers) == expected


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"4.1": "Y", "4.2": "PY", "4.3": "Y"}, "low"),
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "N"}, "low"),
        (
            {"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "Y", "4.6": "Y", "4.11": "N"},
            "moderate",
        ),
        (
            {
                "4.1": "NI",
                "4.2": "Y",
                "4.3": "Y",
                "4.4": "NI",
                "4.5": "NI",
                "4.6": "WN",
                "4.11": "Y",
            },
            "moderate",
        ),
        (
            {"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "Y", "4.6": "SN", "4.11": "N"},
            "critical",
        ),
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "N", "4.7": "Y", "4.8": "N"}, "serious"),
        (
            {"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "N", "4.7": "Y", "4.8": "Y", "4.9": "Y"},
            "low",
        ),
        (
            {
                "4.1": "N",
                "4.2": "Y",
                "4.3": "Y",
                "4.4": "PN",
                "4.7": "N",
                "4.10": "SN",
                "4.11": "Y",
            },
            "serious",
        ),
        (
            {
                "4.1": "N",
                "4.2": "Y",
                "4.3": "Y",
                "4.4": "PN",
                "4.7": "NI",
                "4.10": "WN",
                "4.11": "N",
            },
            "serious",
        ),
    ],
)
def test_domain_4(answers: dict[str, str], expected: str) -> None:
    assert _judge("d4", answers) == expected


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"5.1": "N", "5.2": "N"}, "low"),
        ({"5.1": "N", "5.2": "Y", "5.3": "PN"}, "low"),
        ({"5.1": "PN", "5.2": "NI", "5.3": "WY"}, "moderate"),
        ({"5.1": "N", "5.2": "Y", "5.3": "SY"}, "serious"),
        ({"5.1": "NI", "5.2": "N"}, "moderate"),
        ({"5.1": "NI", "5.2": "Y", "5.3": "N"}, "moderate"),
        ({"5.1": "NI", "5.2": "Y", "5.3": "SY"}, "serious"),
        ({"5.1": "Y"}, "serious"),
    ],
)
def test_domain_5(answers: dict[str, str], expected: str) -> None:
    assert _judge("d5", answers) == expected


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"6.1": "Y"}, "low"),
        ({"6.1": "N", "6.2": "N", "6.3": "PN", "6.4": "N"}, "low"),
        ({"6.1": "N", "6.2": "NI", "6.3": "N", "6.4": "N"}, "moderate"),
        ({"6.1": "PN", "6.2": "Y", "6.3": "NI", "6.4": "N"}, "serious"),
        ({"6.1": "NI", "6.2": "NI", "6.3": "NI", "6.4": "NI"}, "serious"),
        ({"6.1": "N", "6.2": "Y", "6.3": "PY", "6.4": "N"}, "critical"),
    ],
)
def test_domain_6(answers: dict[str, str], expected: str) -> None:
    assert _judge("d6", answers) == expected


def test_missing_answers_give_no_suggestion() -> None:
    assert _judge("d2", {"2.1": "Y"}) is None
    assert _judge("d1", {"A1.1": "Y"}, None) is None  # variant not chosen yet


def test_overall_is_the_worst_domain_with_a_warning_for_several() -> None:
    levels = _v2().judgement.levels
    domains = ["low_except_confounding", "low", "low", "low", "low", "low"]
    assert suggest_overall("worst", domains, levels) == "low_except_confounding"
    domains = ["low_except_confounding", "moderate", "low", "moderate", "low", "low"]
    overall = suggest_overall("worst", domains, levels)
    assert overall == "moderate"
    assert overall_warnings(domains, ["moderate", "serious"], overall) == ["several_moderate"]
    assert suggest_overall("worst", ["moderate", "critical", "low"], levels) == "critical"


def _rob2(domain_key: str, answers: dict[str, str], variant: str | None = None) -> str | None:
    template = catalog()["rob2"]
    domain = next(d for d in template.domains if d.key == domain_key)
    return suggest_domain(domain, answers, template.judgement.levels, variant)


@pytest.mark.parametrize(
    ("domain", "variant", "answers", "expected"),
    [
        # Domain 1 (cribsheet p. 6)
        ("d1", None, {"1.2": "Y", "1.1": "Y", "1.3": "N"}, "low"),
        ("d1", None, {"1.2": "PY", "1.1": "NI", "1.3": "Y"}, "some_concerns"),
        ("d1", None, {"1.2": "Y", "1.1": "N", "1.3": "N"}, "some_concerns"),
        ("d1", None, {"1.2": "NI", "1.1": "Y", "1.3": "N"}, "some_concerns"),
        ("d1", None, {"1.2": "NI", "1.1": "Y", "1.3": "PY"}, "high"),
        ("d1", None, {"1.2": "N", "1.1": "Y", "1.3": "N"}, "high"),
        # Domain 2, effect of assignment (p. 10): worst of parts 1 and 2
        ("d2", "S", {"S2.1": "N", "S2.2": "PN", "S2.6": "Y"}, "low"),
        ("d2", "S", {"S2.1": "Y", "S2.2": "N", "S2.3": "N", "S2.6": "Y"}, "low"),
        ("d2", "S", {"S2.1": "Y", "S2.2": "N", "S2.3": "NI", "S2.6": "Y"}, "some_concerns"),
        (
            "d2",
            "S",
            {"S2.1": "Y", "S2.2": "N", "S2.3": "Y", "S2.4": "N", "S2.6": "Y"},
            "some_concerns",
        ),
        (
            "d2",
            "S",
            {"S2.1": "Y", "S2.2": "N", "S2.3": "Y", "S2.4": "Y", "S2.5": "Y", "S2.6": "Y"},
            "some_concerns",
        ),
        (
            "d2",
            "S",
            {"S2.1": "Y", "S2.2": "N", "S2.3": "Y", "S2.4": "NI", "S2.5": "N", "S2.6": "Y"},
            "high",
        ),
        ("d2", "S", {"S2.1": "N", "S2.2": "N", "S2.6": "N", "S2.7": "N"}, "some_concerns"),
        ("d2", "S", {"S2.1": "N", "S2.2": "N", "S2.6": "NI", "S2.7": "NI"}, "high"),
        # Domain 2, effect of adhering (p. 13)
        ("d2", "H", {"H2.1": "N", "H2.2": "N", "H2.4": "NA", "H2.5": "N"}, "low"),
        (
            "d2",
            "H",
            {"H2.1": "N", "H2.2": "N", "H2.4": "Y", "H2.5": "N", "H2.6": "Y"},
            "some_concerns",
        ),
        ("d2", "H", {"H2.1": "Y", "H2.2": "N", "H2.3": "PY", "H2.4": "N", "H2.5": "PN"}, "low"),
        (
            "d2",
            "H",
            {"H2.1": "Y", "H2.2": "N", "H2.3": "N", "H2.4": "N", "H2.5": "N", "H2.6": "N"},
            "high",
        ),
        # Domain 3 (p. 16)
        ("d3", None, {"3.1": "Y"}, "low"),
        ("d3", None, {"3.1": "N", "3.2": "PY"}, "low"),
        ("d3", None, {"3.1": "N", "3.2": "N", "3.3": "PN"}, "low"),
        ("d3", None, {"3.1": "NI", "3.2": "N", "3.3": "Y", "3.4": "N"}, "some_concerns"),
        ("d3", None, {"3.1": "N", "3.2": "N", "3.3": "NI", "3.4": "NI"}, "high"),
        # Domain 4 (p. 19)
        ("d4", None, {"4.1": "Y", "4.2": "N"}, "high"),
        ("d4", None, {"4.1": "N", "4.2": "Y"}, "high"),
        ("d4", None, {"4.1": "N", "4.2": "N", "4.3": "N"}, "low"),
        ("d4", None, {"4.1": "N", "4.2": "N", "4.3": "Y", "4.4": "PN"}, "low"),
        ("d4", None, {"4.1": "N", "4.2": "N", "4.3": "Y", "4.4": "Y", "4.5": "N"}, "some_concerns"),
        ("d4", None, {"4.1": "NI", "4.2": "PN", "4.3": "Y", "4.4": "Y", "4.5": "NI"}, "high"),
        ("d4", None, {"4.1": "N", "4.2": "NI", "4.3": "N"}, "some_concerns"),
        ("d4", None, {"4.1": "N", "4.2": "NI", "4.3": "NI", "4.4": "N"}, "some_concerns"),
        ("d4", None, {"4.1": "N", "4.2": "NI", "4.3": "Y", "4.4": "Y", "4.5": "Y"}, "high"),
        # Domain 5 (p. 23)
        ("d5", None, {"5.1": "Y", "5.2": "N", "5.3": "PN"}, "low"),
        ("d5", None, {"5.1": "NI", "5.2": "N", "5.3": "N"}, "some_concerns"),
        ("d5", None, {"5.1": "Y", "5.2": "NI", "5.3": "N"}, "some_concerns"),
        ("d5", None, {"5.1": "Y", "5.2": "N", "5.3": "Y"}, "high"),
    ],
)
def test_rob2_domains(
    domain: str, variant: str | None, answers: dict[str, str], expected: str
) -> None:
    assert _rob2(domain, answers, variant) == expected


def test_rob2_overall_rule() -> None:
    levels = catalog()["rob2"].judgement.levels
    assert suggest_overall("rob2", ["low"] * 5, levels) == "low"
    assert (
        suggest_overall("rob2", ["low", "some_concerns", "low", "low", "low"], levels)
        == "some_concerns"
    )
    assert suggest_overall("rob2", ["low", "some_concerns", "high", "low", "low"], levels) == "high"
    several = ["some_concerns", "some_concerns", "low", "low", "low"]
    assert overall_warnings(several, ["some_concerns"], "some_concerns") == [
        "several_some_concerns"
    ]


ALGORITHM_TEMPLATES = [k for k, t in catalog().items() if t.judgement.kind == "algorithm"]


@pytest.mark.parametrize("key", ALGORITHM_TEMPLATES)
def test_skip_rules_never_hide_a_question_the_algorithm_needs(key: str) -> None:
    """Random answer sets: answering only what the skip rules ask always reaches a judgement."""
    template = catalog()[key]
    levels = template.judgement.levels
    rng = random.Random(2025)  # noqa: S311 - reproducible test sampling, not security
    for domain in template.domains:
        variants = [v.key for v in domain.variants] or [None]
        for variant in variants:
            questions = [q for q in domain.questions if q.variant == variant]
            for _ in range(3000):
                answers: dict[str, str] = {}
                for q in questions:  # in order, like the reviewer fills them in
                    if is_asked(q.ask_if, answers):
                        options = [a for a in template.answer_sets[q.answers] if a != "NA"]
                        answers[q.key] = rng.choice(options)
                    else:
                        answers[q.key] = "NA"
                judgement = suggest_domain(domain, answers, levels, variant)
                assert judgement in levels, (domain.key, variant, answers)


def _robins_e(domain_key: str, answers: dict[str, str], variant: str | None = None) -> str | None:
    template = catalog()["robins_e"]
    domain = next(d for d in template.domains if d.key == domain_key)
    return suggest_domain(domain, answers, template.judgement.levels, variant)


@pytest.mark.parametrize(
    ("domain", "variant", "answers", "expected"),
    [
        # Domain 1 (pp. 25 and 28)
        ("d1", "a", {"a1.1": "Y", "a1.3": "N", "a1.2": "Y", "a1.4": "N"}, "low_except_confounding"),
        ("d1", "a", {"a1.1": "WN", "a1.3": "N", "a1.2": "WN", "a1.4": "N"}, "some_concerns"),
        ("d1", "a", {"a1.1": "SN", "a1.4": "N"}, "high"),
        ("d1", "a", {"a1.1": "Y", "a1.3": "Y", "a1.4": "Y", "a1.2": "Y"}, "very_high"),
        ("d1", "a", {"a1.1": "Y", "a1.3": "Y", "a1.4": "N", "a1.2": "WN"}, "very_high"),
        ("d1", "b", {"b1.1": "Y", "b1.2": "Y", "b1.3": "Y", "b1.5": "N"}, "low_except_confounding"),
        ("d1", "b", {"b1.1": "Y", "b1.2": "SN", "b1.5": "N"}, "high"),
        ("d1", "b", {"b1.1": "N", "b1.4": "N", "b1.5": "Y"}, "very_high"),
        # Domain 2 (p. 35): the box result is read according to 2.1 and 2.2
        ("d2", "a", {"a2.1": "Y", "a2.2": "N"}, "low"),
        ("d2", "a", {"a2.1": "Y", "a2.2": "WY", "a2.3": "N", "a2.4": "N"}, "low"),
        ("d2", "b", {"b2.1": "Y", "b2.2": "SY", "b2.3": "N", "b2.4": "WY"}, "high"),
        ("d2", "c", {"c2.1": "WN", "c2.2": "WY", "c2.3": "N", "c2.4": "N"}, "some_concerns"),
        ("d2", "a", {"a2.1": "NI", "a2.2": "SY", "a2.3": "SY"}, "very_high"),
        ("d2", "a", {"a2.1": "SN", "a2.2": "PN"}, "high"),
        ("d2", "a", {"a2.1": "SN", "a2.2": "WY", "a2.3": "N", "a2.4": "N"}, "high"),
        # Domain 3 (p. 43)
        ("d3", None, {"3.1": "Y", "3.3": "N"}, "low"),
        ("d3", None, {"3.1": "N", "3.2": "Y", "3.3": "N"}, "some_concerns"),
        ("d3", None, {"3.1": "N", "3.2": "N", "3.3": "N", "3.6": "N", "3.7": "SN"}, "very_high"),
        (
            "d3",
            None,
            {"3.1": "Y", "3.3": "Y", "3.4": "Y", "3.5": "Y", "3.6": "NI", "3.7": "WN"},
            "high",
        ),
        # Domain 4 (p. 46)
        ("d4", None, {"4.1": "NI"}, "some_concerns"),
        ("d4", None, {"4.1": "Y", "4.2": "N"}, "high"),
        # Domain 5 (p. 52)
        ("d5", None, {"5.1": "Y", "5.2": "Y", "5.3": "PY"}, "low"),
        (
            "d5",
            None,
            {"5.1": "N", "5.2": "Y", "5.3": "Y", "5.4": "Y", "5.5": "N", "5.6": "SY"},
            "low",
        ),
        (
            "d5",
            None,
            {"5.1": "N", "5.2": "Y", "5.3": "Y", "5.4": "Y", "5.5": "SY", "5.10": "N"},
            "very_high",
        ),
        (
            "d5",
            None,
            {"5.1": "N", "5.2": "Y", "5.3": "Y", "5.4": "N", "5.7": "N", "5.9": "WN", "5.10": "N"},
            "high",
        ),
        # Domain 6 (p. 55)
        ("d6", None, {"6.1": "N", "6.2": "Y", "6.3": "WY"}, "some_concerns"),
        ("d6", None, {"6.1": "NI", "6.2": "N"}, "some_concerns"),
        ("d6", None, {"6.1": "Y"}, "high"),
        # Domain 7 (p. 62): unlike ROBINS-I V2, three or more Y/PY give very high
        ("d7", None, {"7.1": "N", "7.2": "Y", "7.3": "Y", "7.4": "N", "7.5": "N"}, "high"),
        ("d7", None, {"7.1": "N", "7.2": "Y", "7.3": "Y", "7.4": "Y", "7.5": "N"}, "very_high"),
        (
            "d7",
            None,
            {"7.1": "NI", "7.2": "NI", "7.3": "N", "7.4": "N", "7.5": "N"},
            "some_concerns",
        ),
    ],
)
def test_robins_e_domains(
    domain: str, variant: str | None, answers: dict[str, str], expected: str
) -> None:
    assert _robins_e(domain, answers, variant) == expected


def test_robins_i_2016_overall_follows_table_3() -> None:
    template = catalog()["robins_i_2016"]
    levels = template.judgement.levels
    assert template.judgement.kind == "reviewer"
    assert suggest_overall("robins_2016", ["low"] * 7, levels) == "low"
    assert suggest_overall("robins_2016", ["low", "moderate", "low"], levels) == "moderate"
    assert (
        suggest_overall("robins_2016", ["moderate", "no_information", "low"], levels)
        == "no_information"
    )
    assert suggest_overall("robins_2016", ["serious", "no_information"], levels) == "serious"
    assert suggest_overall("robins_2016", ["serious", "critical", "low"], levels) == "critical"
    assert overall_warnings(["no_information"], [], "no_information") == [
        "no_information_needs_judgement"
    ]
