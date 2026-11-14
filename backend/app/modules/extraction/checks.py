"""Extraction safeguards, blocks A and C of docs/modulos.md 7.5.1.

Pure functions over the extraction data: they only compare typed values with each
other and with the scale the extractor entered. No statistics is computed here
(that is the R service, Etapa 3).

- `impossible_*` find values that cannot be true; the API rejects them on write.
- `compute_alerts` lists what deserves a second look. Warnings ask for confirmation
  with a justification; `block` alerts must be justified before submitting.
- `direction_summaries` builds the data of the direction sentence (block C).
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Decimal
from typing import Any

from app.modules.extraction.models import OutcomeData, OutcomeMeasure, StudyArm
from app.modules.protocol.models import ComparisonGroup, Outcome

DIRECTION_UNCONFIRMED = "extraction.alert.direction_unconfirmed"


@dataclass(frozen=True)
class Alert:
    code: str
    severity: str  # "warn" | "block"
    target_type: str  # "row" | "arm" | "extraction" | "outcome"
    target_id: str
    field: str | None = None
    params: dict[str, Any] = dataclass_field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str, str | None]:
        return (self.code, self.target_type, self.target_id, self.field)


def _num(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _fmt(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


# ---- Impossible values (rejected on write) -------------------------------------------


def impossible_row_values(values: dict[str, Any]) -> str | None:
    """Returns the error code of the first impossible value, or None."""
    n, events, total = values.get("n"), values.get("events"), values.get("total")
    sd, se = _num(values.get("sd")), _num(values.get("se"))
    pairs = [
        ("ci_low", "ci_high", "extraction.impossible.ci_inverted"),
        ("q1", "q3", "extraction.impossible.iqr_inverted"),
        ("min", "max", "extraction.impossible.range_inverted"),
    ]
    if n is not None and n <= 0:
        return "extraction.impossible.n_not_positive"
    if sd is not None and sd <= 0:
        return "extraction.impossible.sd_not_positive"
    if se is not None and se <= 0:
        return "extraction.impossible.se_not_positive"
    if events is not None and events < 0:
        return "extraction.impossible.negative_events"
    if total is not None and total <= 0:
        return "extraction.impossible.n_not_positive"
    if events is not None and total is not None and events > total:
        return "extraction.impossible.events_gt_total"
    for low, high, code in pairs:
        a, b = _num(values.get(low)), _num(values.get(high))
        if a is not None and b is not None and a > b:
            return code
    median = _num(values.get("median"))
    for low, high in (("q1", "q3"), ("min", "max")):
        a, b = _num(values.get(low)), _num(values.get(high))
        if median is not None and a is not None and b is not None and not a <= median <= b:
            return "extraction.impossible.median_outside"
    p_value = _num(values.get("p_value"))
    if p_value is not None and not 0 < p_value <= 1:
        return "extraction.impossible.p_out_of_range"
    return impossible_effect(values.get("effect_reported"))


RATIO_MEASURES = {"OR", "RR", "HR"}


def impossible_effect(effect: dict[str, Any] | None) -> str | None:
    """An effect already computed by the article (e.g. adjusted OR with its CI)."""
    if not effect:
        return None
    estimate, low, high = (
        _num(effect.get("estimate")),
        _num(effect.get("ci_low")),
        _num(effect.get("ci_high")),
    )
    se = _num(effect.get("se"))
    if effect.get("measure") in RATIO_MEASURES and any(
        v is not None and v <= 0 for v in (estimate, low, high)
    ):
        # Ratios (OR, RR, HR) are always above zero; they are analysed on the log scale.
        return "extraction.impossible.ratio_not_positive"
    if low is not None and high is not None and low > high:
        return "extraction.impossible.ci_inverted"
    if se is not None and se <= 0:
        return "extraction.impossible.se_not_positive"
    return None


def impossible_arm_values(n: int | None) -> str | None:
    if n is not None and n <= 0:
        return "extraction.impossible.n_not_positive"
    return None


# ---- Alerts --------------------------------------------------------------------------


def compute_alerts(
    *,
    extraction_id: str,
    characteristics: dict[str, Any],
    arms: list[StudyArm],
    measures: list[OutcomeMeasure],
    rows: list[OutcomeData],
    outcomes: list[Outcome],
    groups: list[ComparisonGroup],
) -> list[Alert]:
    alerts: list[Alert] = []
    scale_by_outcome = {str(m.outcome_id): m for m in measures}

    # A2: groups cannot add up to more participants than the study (unless justified).
    n_total = characteristics.get("n_total")
    arm_sum = sum(a.n for a in arms if a.n is not None)
    if isinstance(n_total, int | float) and arm_sum > n_total:
        alerts.append(
            Alert(
                "extraction.alert.arms_exceed_total",
                "block",
                "extraction",
                extraction_id,
                "n_total",
                {"sum": arm_sum, "total": _fmt(_num(n_total))},
            )
        )

    for row in rows:
        rid = str(row.id)
        scale = scale_by_outcome.get(str(row.outcome_id))
        mean = _num(row.mean)
        lo, hi = (_num(scale.scale_min), _num(scale.scale_max)) if scale else (None, None)

        # A3: values outside the scale range, SD larger than half the range.
        if mean is not None and lo is not None and hi is not None and not lo <= mean <= hi:
            alerts.append(
                Alert(
                    "extraction.alert.mean_outside_scale",
                    "warn",
                    "row",
                    rid,
                    "mean",
                    {"value": _fmt(mean), "min": _fmt(lo), "max": _fmt(hi)},
                )
            )
        sd = _num(row.sd)
        if sd is not None and lo is not None and hi is not None and sd > (hi - lo) / 2:
            alerts.append(
                Alert(
                    "extraction.alert.sd_too_large",
                    "warn",
                    "row",
                    rid,
                    "sd",
                    {"value": _fmt(sd), "half": _fmt((hi - lo) / 2)},
                )
            )

        # A4: a 95% CI of the mean must contain the mean.
        ci_low, ci_high = _num(row.ci_low), _num(row.ci_high)
        if (
            mean is not None
            and ci_low is not None
            and ci_high is not None
            and not ci_low <= mean <= ci_high
        ):
            alerts.append(
                Alert(
                    "extraction.alert.ci_excludes_mean",
                    "warn",
                    "row",
                    rid,
                    "mean",
                    {"mean": _fmt(mean), "low": _fmt(ci_low), "high": _fmt(ci_high)},
                )
            )

        # A4 for effects reported by the article: the estimate lies inside its CI.
        effect = row.effect_reported or {}
        est, e_low, e_high = (
            _num(effect.get("estimate")),
            _num(effect.get("ci_low")),
            _num(effect.get("ci_high")),
        )
        if (
            est is not None
            and e_low is not None
            and e_high is not None
            and not e_low <= est <= e_high
        ):
            alerts.append(
                Alert(
                    "extraction.alert.effect_outside_ci",
                    "warn",
                    "row",
                    rid,
                    "effect_reported",
                    {"estimate": _fmt(est), "low": _fmt(e_low), "high": _fmt(e_high)},
                )
            )

        has_numbers = any(
            getattr(row, f) is not None
            for f in ("n", "mean", "sd", "se", "ci_low", "ci_high", "median", "events", "total")
        ) or bool(effect)
        # A1: a dispersion value is only confirmed when we know where the article says its type.
        if (
            row.dispersion_type
            and row.dispersion_type != "not_reported"
            and not row.dispersion_source
        ):
            alerts.append(
                Alert(
                    "extraction.alert.dispersion_unconfirmed",
                    "warn",
                    "row",
                    rid,
                    "dispersion_source",
                )
            )
        # A5: numbers without an origin in the article.
        if has_numbers and not row.source_location and row.annotation_id is None:
            alerts.append(
                Alert("extraction.alert.no_source", "warn", "row", rid, "source_location")
            )

    # C9: every direction sentence must be confirmed by the extractor. Only sentences
    # that exist raise the alert; it is cleared by confirming, never by a justification.
    for summary in direction_summaries(
        arms=arms, groups=groups, measures=measures, rows=rows, outcomes=outcomes
    ):
        if not summary.confirmed:
            alerts.append(
                Alert(
                    DIRECTION_UNCONFIRMED,
                    "warn",
                    "outcome",
                    summary.outcome_id,
                    summary.timepoint,
                    {"outcome": summary.outcome_name, "timepoint": summary.timepoint},
                )
            )
    return alerts


# ---- Direction sentence (block C) ----------------------------------------------------


@dataclass
class DirectionSide:
    arm_id: str
    arm_label: str
    group_label: str
    mean: str


@dataclass
class DirectionSummary:
    outcome_id: str
    outcome_name: str
    timepoint: str
    scale_name: str | None
    higher_is_better: bool
    first: DirectionSide
    second: DirectionSide
    # "first" | "second" | "equal": which side the typed numbers favour.
    favors: str
    confirmed: bool


def direction_summaries(
    *,
    arms: list[StudyArm],
    groups: list[ComparisonGroup],
    measures: list[OutcomeMeasure],
    rows: list[OutcomeData],
    outcomes: list[Outcome],
) -> list[DirectionSummary]:
    """One summary per outcome and time point where both protocol groups have a mean.

    Only arms mapped to a protocol group are compared; studies with more arms are
    combined by the R service in Etapa 3, so they get no sentence until then.
    """
    group_rank = {str(g.id): (g.position, g.label) for g in groups}
    mapped = [
        a for a in arms if a.mapped_group_id is not None and str(a.mapped_group_id) in group_rank
    ]
    by_group: dict[str, list[StudyArm]] = {}
    for arm in mapped:
        by_group.setdefault(str(arm.mapped_group_id), []).append(arm)
    if len(by_group) != 2 or any(len(v) != 1 for v in by_group.values()):
        return []
    ordered = sorted(by_group.items(), key=lambda item: group_rank[item[0]])
    first_arm, second_arm = ordered[0][1][0], ordered[1][1][0]
    scale_by_outcome = {str(m.outcome_id): m for m in measures}

    summaries: list[DirectionSummary] = []
    for outcome in outcomes:
        if outcome.type != "continuous":
            continue
        scale = scale_by_outcome.get(str(outcome.id))
        higher_is_better = scale.higher_is_better if scale else outcome.higher_is_better
        for timepoint in outcome.timepoints:
            pick = {
                str(r.arm_id): r
                for r in rows
                if str(r.outcome_id) == str(outcome.id)
                and r.timepoint == timepoint
                and r.mean is not None
            }
            a, b = pick.get(str(first_arm.id)), pick.get(str(second_arm.id))
            if a is None or b is None:
                continue
            mean_a, mean_b = _num(a.mean), _num(b.mean)
            assert mean_a is not None and mean_b is not None  # noqa: S101 - filtered above
            if mean_a == mean_b:
                favors = "equal"
            elif (mean_a > mean_b) == higher_is_better:
                favors = "first"
            else:
                favors = "second"
            summaries.append(
                DirectionSummary(
                    outcome_id=str(outcome.id),
                    outcome_name=outcome.name,
                    timepoint=timepoint,
                    scale_name=scale.scale_name if scale else None,
                    higher_is_better=higher_is_better,
                    first=DirectionSide(
                        str(first_arm.id),
                        first_arm.label,
                        group_rank[str(first_arm.mapped_group_id)][1],
                        _fmt(mean_a) or "",
                    ),
                    second=DirectionSide(
                        str(second_arm.id),
                        second_arm.label,
                        group_rank[str(second_arm.mapped_group_id)][1],
                        _fmt(mean_b) or "",
                    ),
                    favors=favors,
                    confirmed=a.direction_confirmed and b.direction_confirmed,
                )
            )
    return summaries
