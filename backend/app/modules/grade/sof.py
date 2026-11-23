# ruff: noqa: E501  (bilingual text table reads better on one line per string)
"""Summary of Findings table (docs/modulos.md 7.8; stage 6 step 2).

One row per saved GRADE judgement: result, number of studies and participants, the
pooled effect with its 95% CI (as returned by R when the judgement was saved; RR/OR on
their own scale), the certainty and the reasons, with the group's justifications as
footnotes. DOCX and XLSX, in Portuguese or English (independent of the interface).
"""

import io
from datetime import UTC, datetime
from typing import Any, Literal

from docx import Document
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.exports.extraction import _slug
from app.modules.grade.service import DOWN, UP, GradeOut, assessments
from app.modules.projects.access import ProjectContext

Lang = Literal["pt-BR", "en"]

TEXTS: dict[str, dict[str, Any]] = {
    "pt-BR": {
        "title": "Resumo dos achados (Summary of Findings)",
        "cols": (
            "Desfecho",
            "Momento",
            "Estudos",
            "Participantes",
            "Efeito (IC 95%)",
            "Certeza",
            "Motivos",
        ),
        "level": {
            "very_low": "Muito baixa",
            "low": "Baixa",
            "moderate": "Moderada",
            "high": "Alta",
        },
        "domain": {
            "risk_of_bias": "risco de viés",
            "inconsistency": "inconsistência",
            "indirectness": "evidência indireta",
            "imprecision": "imprecisão",
            "publication_bias": "viés de publicação",
            "large_effect": "efeito grande",
            "dose_response": "dose-resposta",
            "plausible_confounding": "confundimento plausível",
        },
        "approach": {
            "classic": "GRADE clássico (observacionais começam em baixa)",
            "robins_i": "Com ROBINS-I (começam em alta)",
        },
        "start": "Certeza inicial",
        "none": "Sem rebaixamentos ou elevações",
        "notes": "Justificativas",
        "note": "Observação",
        "footer": "Certeza avaliada pelo grupo com a abordagem GRADE; os efeitos vêm do serviço R (metafor).",
        "sheet": "SoF",
        "file": "summary-of-findings",
        "decimal": ",",
    },
    "en": {
        "title": "Summary of Findings",
        "cols": (
            "Outcome",
            "Timepoint",
            "Studies",
            "Participants",
            "Effect (95% CI)",
            "Certainty",
            "Reasons",
        ),
        "level": {"very_low": "Very low", "low": "Low", "moderate": "Moderate", "high": "High"},
        "domain": {
            "risk_of_bias": "risk of bias",
            "inconsistency": "inconsistency",
            "indirectness": "indirectness",
            "imprecision": "imprecision",
            "publication_bias": "publication bias",
            "large_effect": "large effect",
            "dose_response": "dose-response",
            "plausible_confounding": "plausible confounding",
        },
        "approach": {
            "classic": "Classic GRADE (observational studies start at low)",
            "robins_i": "With ROBINS-I (start at high)",
        },
        "start": "Starting certainty",
        "none": "No downgrade or upgrade",
        "notes": "Justifications",
        "note": "Note",
        "footer": "Certainty rated by the group with the GRADE approach; effects come from the R service (metafor).",
        "sheet": "SoF",
        "file": "summary-of-findings",
        "decimal": ".",
    },
}


def _n(value: float | None, t: dict[str, Any]) -> str:
    return "—" if value is None else f"{value:.2f}".replace(".", t["decimal"])


def _effect(g: GradeOut, t: dict[str, Any]) -> str:
    s = g.summary
    natural = s.get("natural")
    if s.get("ratio") and natural:
        est, lb, ub = natural.get("estimate"), natural.get("ci_lb"), natural.get("ci_ub")
    else:
        est, lb, ub = s.get("estimate"), s.get("ci_lb"), s.get("ci_ub")
    sep = "; " if t["decimal"] == "," else ", "
    return f"{s.get('measure', '')} {_n(est, t)} ({_n(lb, t)}{sep}{_n(ub, t)})"


def _reasons(g: GradeOut, t: dict[str, Any], marks: list[str]) -> str:
    parts = []
    for key in [*DOWN, *UP]:
        item = g.domains.get(key) or {}
        change = item.get("change", 0)
        if change:
            mark = f"[{len(marks) + 1}]"
            marks.append(f"{mark} {t['domain'][key]}: {item.get('justification') or ''}")
            parts.append(f"{'+' if change > 0 else ''}{change} {t['domain'][key]} {mark}")
    return "; ".join(parts) or t["none"]


def _rows(items: list[GradeOut], t: dict[str, Any]) -> tuple[list[list[Any]], list[str]]:
    marks: list[str] = []
    rows = []
    for g in items:
        level = t["level"][g.final_certainty]
        start = f"{t['start']}: {t['level'][g.start_certainty]} — {t['approach'][g.approach]}"
        rows.append(
            [
                g.outcome_name,
                g.timepoint,
                g.summary.get("k"),
                g.summary.get("participants"),
                _effect(g, t),
                f"{level} ({start})",
                _reasons(g, t, marks),
            ]
        )
        if g.note:
            marks.append(f"{g.outcome_name} ({g.timepoint}) — {t['note']}: {g.note}")
    return rows, marks


async def sof(
    session: AsyncSession, ctx: ProjectContext, fmt: Literal["docx", "xlsx"], lang: Lang
) -> tuple[bytes, str, str]:
    items = await assessments(session, ctx)
    if not items:
        raise AppError("grade.sof_empty", status_code=409)
    t = TEXTS[lang]
    rows, marks = _rows(items, t)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    name = f"{_slug(ctx.project.title)}_{t['file']}_{day}.{fmt}"
    buffer = io.BytesIO()
    if fmt == "docx":
        doc = Document()
        doc.add_heading(t["title"], level=1)
        doc.add_paragraph(ctx.project.title)
        table = doc.add_table(rows=1, cols=len(t["cols"]))
        table.style = "Table Grid"
        for cell, text in zip(table.rows[0].cells, t["cols"], strict=True):
            cell.text = text
        for row in rows:
            cells = table.add_row().cells
            for cell, value in zip(cells, row, strict=True):
                cell.text = "—" if value is None else str(value)
        if marks:
            doc.add_heading(t["notes"], level=2)
            for m in marks:
                doc.add_paragraph(m)
        doc.add_paragraph(t["footer"])
        doc.save(buffer)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        wb = Workbook()
        ws = wb.active
        if ws is None:  # a new workbook always has one sheet
            ws = wb.create_sheet()
        ws.title = t["sheet"]
        ws.append([t["title"]])
        ws["A1"].font = Font(bold=True)
        ws.append(list(t["cols"]))
        for row in rows:
            ws.append(row)
        ws.append([])
        for m in [t["notes"], *marks, t["footer"]]:
            ws.append([m])
        for column in "ABCDEFG":
            ws.column_dimensions[column].width = 28
            for cell in ws[column]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        wb.save(buffer)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return buffer.getvalue(), media, name
