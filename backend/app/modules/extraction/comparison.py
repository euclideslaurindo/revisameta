"""Double extraction comparison, block D of docs/modulos.md 7.5.1.

Pure functions: they line up what two extractors typed for the same study and say,
field by field, where they agree. Numbers are compared as numbers, so "92,50" and
"92.5" are the same value (only formatting differs) while 92.5 and 92.6 diverge.

Decided with the project owner (2026-11-14): only numbers and categories can
diverge. Texts (country, funding, page of origin...) are shown side by side for the
consensus but never count as a divergence nor enter the agreement figures.

Arms are matched by the protocol group they are linked to; arms without a link are
matched by their label (ignoring case and spaces).
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.extraction.models import OutcomeData, OutcomeMeasure, StudyArm
from app.modules.extraction.schemas import FormSchema

# Fields of one outcome row, by how they are compared.
ROW_NUMBERS = (
    "n",
    "mean",
    "sd",
    "se",
    "ci_low",
    "ci_high",
    "median",
    "q1",
    "q3",
    "min",
    "max",
    "events",
    "total",
    "t_stat",
    "p_value",
)
ROW_CATEGORIES = ("value_type", "dispersion_type", "adjusted")
ROW_TEXTS = ("dispersion_source", "adjusted_for", "source_location")
# Choosing one extractor's dispersion type without its numbers would leave the row
# inconsistent, so these fields are always decided together.
DISPERSION_GROUP = (
    "dispersion_type",
    "dispersion_source",
    "sd",
    "se",
    "ci_low",
    "ci_high",
    "q1",
    "q3",
    "min",
    "max",
)
MEASURE_FIELDS = (
    ("scale_min", "number"),
    ("scale_max", "number"),
    ("higher_is_better", "category"),
    ("scale_name", "text"),
)
SEP = "|"


@dataclass
class Snapshot:
    """Everything one extractor typed for a study."""

    characteristics: dict[str, Any]
    arms: list[StudyArm]
    measures: list[OutcomeMeasure]
    rows: list[OutcomeData]


@dataclass
class Item:
    key: str
    section: str  # characteristics | arm | measure | row
    kind: str  # number | category | text
    field: str
    value_a: Any
    value_b: Any
    agree: bool
    outcome_id: str | None = None
    arm_key: str | None = None
    arm_label: str | None = None
    group_id: str | None = None
    timepoint: str | None = None
    label_key: str | None = None
    label: str | None = None
    source_a: dict[str, Any] | None = None
    source_b: dict[str, Any] | None = None

    @property
    def counts(self) -> bool:
        """Enters the agreement figures: numbers and categories someone filled in."""
        return self.kind != "text" and not (self.value_a is None and self.value_b is None)

    @property
    def divergent(self) -> bool:
        return self.counts and not self.agree


@dataclass
class Comparison:
    items: list[Item] = field(default_factory=list)

    @property
    def divergences(self) -> list[Item]:
        return [i for i in self.items if i.divergent]

    def codes(self, categories_only: bool = False) -> tuple[list[str], list[str]]:
        """The two extractors' answers as codes, one per compared item (for R)."""
        chosen = [
            i for i in self.items if i.counts and (not categories_only or i.kind == "category")
        ]
        return [code(i.value_a) for i in chosen], [code(i.value_b) for i in chosen]


# ---- Normalisation -------------------------------------------------------------------


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return None


def number_text(value: Any) -> str | None:
    """A number as plain text without formatting noise: 92.50 -> "92.5"."""
    number = _decimal(value)
    if number is None:
        return None if value is None else str(value)
    text = format(number.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _effect(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {k: (v if k == "measure" else number_text(v)) for k, v in value.items()}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def code(value: Any) -> str:
    """Code sent to R for agreement: an explicit marker for empty values."""
    if value is None:
        return "<empty>"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return ";".join(f"{k}={value[k]}" for k in sorted(value))
    return str(value)


def _same(kind: str, a: Any, b: Any) -> bool:
    if kind == "text":
        return (a or "").casefold() == (b or "").casefold()
    return bool(a == b)


def arm_key(arm: StudyArm) -> str:
    if arm.mapped_group_id is not None:
        return f"g:{arm.mapped_group_id}"
    label = " ".join(arm.label.split()).casefold().replace(SEP, " ")
    return f"l:{label}"


def _source(row: OutcomeData | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "location": row.source_location,
        "annotation_id": str(row.annotation_id) if row.annotation_id else None,
        "dispersion_source": row.dispersion_source,
    }


# ---- Comparison ----------------------------------------------------------------------


def _arms_by_key(arms: list[StudyArm]) -> dict[str, StudyArm]:
    out: dict[str, StudyArm] = {}
    for arm in sorted(arms, key=lambda a: (a.position, a.created_at)):
        out.setdefault(arm_key(arm), arm)
    return out


def compare(a: Snapshot, b: Snapshot, form: FormSchema) -> Comparison:
    result = Comparison()
    add = result.items.append

    # Characteristics, in the order of the form.
    for f in form.fields:
        kind = {"number": "number", "select": "category"}.get(f.type, "text")
        va, vb = a.characteristics.get(f.key), b.characteristics.get(f.key)
        if kind == "number":
            va, vb = number_text(va), number_text(vb)
        else:
            va, vb = _text(va), _text(vb)
        add(
            Item(
                key=SEP.join(("char", f.key)),
                section="characteristics",
                kind=kind,
                field=f.key,
                value_a=va,
                value_b=vb,
                agree=_same(kind, va, vb),
                label_key=f.label_key,
                label=f.label,
            )
        )

    # Arms.
    arms_a, arms_b = _arms_by_key(a.arms), _arms_by_key(b.arms)
    arm_keys = list(arms_a) + [k for k in arms_b if k not in arms_a]
    for key in arm_keys:
        arm_a, arm_b = arms_a.get(key), arms_b.get(key)
        shown = arm_a or arm_b
        assert shown is not None  # noqa: S101 - key comes from one of the two
        common: dict[str, Any] = {
            "section": "arm",
            "arm_key": key,
            "arm_label": shown.label,
            "group_id": str(shown.mapped_group_id) if shown.mapped_group_id else None,
        }
        present_a, present_b = arm_a is not None, arm_b is not None
        add(
            Item(
                key=SEP.join(("arm", key, "present")),
                kind="category",
                field="present",
                value_a=present_a,
                value_b=present_b,
                agree=present_a == present_b,
                **common,
            )
        )
        if arm_a is not None and arm_b is not None:
            add(
                Item(
                    key=SEP.join(("arm", key, "n")),
                    kind="number",
                    field="n",
                    value_a=arm_a.n,
                    value_b=arm_b.n,
                    agree=arm_a.n == arm_b.n,
                    **common,
                )
            )

    # Scales per outcome.
    measures_a = {str(m.outcome_id): m for m in a.measures}
    measures_b = {str(m.outcome_id): m for m in b.measures}
    for outcome_id in list(measures_a) + [k for k in measures_b if k not in measures_a]:
        ma, mb = measures_a.get(outcome_id), measures_b.get(outcome_id)
        for name, kind in MEASURE_FIELDS:
            va = getattr(ma, name) if ma else None
            vb = getattr(mb, name) if mb else None
            if kind == "number":
                va, vb = number_text(va), number_text(vb)
            elif kind == "text":
                va, vb = _text(va), _text(vb)
            add(
                Item(
                    key=SEP.join(("measure", outcome_id, name)),
                    section="measure",
                    kind=kind,
                    field=name,
                    value_a=va,
                    value_b=vb,
                    agree=_same(kind, va, vb),
                    outcome_id=outcome_id,
                )
            )

    # Outcome rows, matched by outcome, arm and time point.
    def rows_by_key(
        snapshot: Snapshot, arms: dict[str, StudyArm]
    ) -> dict[tuple[str, str, str], OutcomeData]:
        key_of_arm = {str(arm.id): k for k, arm in arms.items()}
        out: dict[tuple[str, str, str], OutcomeData] = {}
        for row in snapshot.rows:
            k = key_of_arm.get(str(row.arm_id))
            if k is not None:
                out.setdefault((str(row.outcome_id), k, row.timepoint), row)
        return out

    rows_a, rows_b = rows_by_key(a, arms_a), rows_by_key(b, arms_b)
    for rk in list(rows_a) + [k for k in rows_b if k not in rows_a]:
        outcome_id, akey, timepoint = rk
        ra, rb = rows_a.get(rk), rows_b.get(rk)
        arm = arms_a.get(akey) or arms_b.get(akey)
        row_common: dict[str, Any] = {
            "section": "row",
            "outcome_id": outcome_id,
            "arm_key": akey,
            "arm_label": arm.label if arm else None,
            "group_id": str(arm.mapped_group_id) if arm and arm.mapped_group_id else None,
            "timepoint": timepoint,
            "source_a": _source(ra),
            "source_b": _source(rb),
        }

        def row_key(
            name: str, akey: str = akey, outcome_id: str = outcome_id, timepoint: str = timepoint
        ) -> str:
            # The time point is free text and goes last, so the key can be split back.
            return SEP.join(("row", outcome_id, akey, name, timepoint))

        add(
            Item(
                key=row_key("present"),
                kind="category",
                field="present",
                value_a=ra is not None,
                value_b=rb is not None,
                agree=(ra is None) == (rb is None),
                **row_common,
            )
        )
        if ra is None or rb is None:
            continue
        for name in ROW_CATEGORIES:
            va, vb = getattr(ra, name), getattr(rb, name)
            add(
                Item(
                    key=row_key(name),
                    kind="category",
                    field=name,
                    value_a=va,
                    value_b=vb,
                    agree=va == vb,
                    **row_common,
                )
            )
        for name in ROW_NUMBERS:
            va, vb = number_text(getattr(ra, name)), number_text(getattr(rb, name))
            add(
                Item(
                    key=row_key(name),
                    kind="number",
                    field=name,
                    value_a=va,
                    value_b=vb,
                    agree=va == vb,
                    **row_common,
                )
            )
        ea, eb = _effect(ra.effect_reported), _effect(rb.effect_reported)
        add(
            Item(
                key=row_key("effect_reported"),
                kind="number",
                field="effect_reported",
                value_a=ea,
                value_b=eb,
                agree=ea == eb,
                **row_common,
            )
        )
        for name in ROW_TEXTS:
            va, vb = _text(getattr(ra, name)), _text(getattr(rb, name))
            add(
                Item(
                    key=row_key(name),
                    kind="text",
                    field=name,
                    value_a=va,
                    value_b=vb,
                    agree=_same("text", va, vb),
                    **row_common,
                )
            )
    return result


def parse_key(key: str) -> list[str]:
    """Splits an item key back into its parts (the row time point may hold anything)."""
    kind = key.split(SEP, 1)[0]
    maxsplit = {"char": 1, "arm": 2, "measure": 2, "row": 4}.get(kind)
    if maxsplit is None:
        raise ValueError(key)
    parts = key.split(SEP, maxsplit)
    if len(parts) != maxsplit + 1:
        raise ValueError(key)
    return parts
