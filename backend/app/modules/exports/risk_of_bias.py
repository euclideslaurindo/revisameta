"""Exports of the consolidated risk of bias (docs/modulos.md 7.6 and 7.10, stage 2 step 5).

- robvis CSV: the input format of robvis (Study, D1..Dn, Overall, Weight), with the
  judgement words robvis expects. Only for instruments robvis has a template for and
  that the R service draws with it (RoB 2, ROBINS-I 2016; ADR-013). Always "," and
  decimal point, since it is read by R.
- CSV, XLSX and DOCX: the table with labels in the output language, the legend of the
  columns, the justifications of the consensus and the studies left out.
- Never silent (lesson L2): studies without a submitted consensus are listed, and the
  file is only produced when the user acknowledges that they are left out.
"""

import io
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.exports.extraction import CsvStyle, Table, _slug, write_csv, write_xlsx
from app.modules.projects.access import ProjectContext
from app.modules.protocol.models import Outcome
from app.modules.risk_of_bias import consolidated
from app.modules.risk_of_bias.catalog import Template
from app.modules.risk_of_bias.models import RobAnswer, RobJudgement, RobTool


class RobFormat(StrEnum):
    ROBVIS = "robvis"  # CSV in the robvis input format
    CSV = "csv"
    XLSX = "xlsx"
    DOCX = "docx"


# Words robvis expects for each level, per template it has.
ROBVIS_WORDS: dict[str, dict[str, str]] = {
    "rob2": {"low": "Low", "some_concerns": "Some concerns", "high": "High"},
    "robins_i_2016": {
        "low": "Low",
        "moderate": "Moderate",
        "serious": "Serious",
        "critical": "Critical",
        "no_information": "No information",
    },
}

TEXTS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "file": "risco-de-vies",
        "sheet.readme": "Leia-me",
        "sheet.table": "Risco de viés",
        "sheet.legend": "Legenda",
        "sheet.justifications": "Justificativas",
        "title": "Risco de viés: tabela consolidada",
        "project": "Projeto",
        "tool": "Instrumento",
        "version": "Versão",
        "result": "Resultado avaliado",
        "exported_at": "Exportado em",
        "source": "Origem",
        "source.text": "Só avaliações de consenso enviadas (duas avaliações cegas e conflitos "
        "decididos) ou importadas, marcadas como tal.",
        "missing": "Estudos que NÃO estão neste arquivo",
        "none_missing": "Nenhum: todos os estudos com este instrumento estão neste arquivo.",
        "no_score": "Este instrumento não tem nota total; o julgamento geral segue a regra "
        "definida pelo grupo.",
        "study": "Estudo",
        "overall": "Geral",
        "origin": "Origem",
        "column": "Coluna",
        "description": "Descrição",
        "item": "Item",
        "judgement": "Julgamento ou resposta",
        "justification": "Justificativa",
        "imported": "importada",
        "consensus": "consenso",
        "reason.no_assessment": "nenhuma avaliação iniciada",
        "reason.in_progress": "avaliações individuais em andamento",
        "reason.consensus_pending": "consenso ainda não enviado",
    },
    "en": {
        "file": "risk-of-bias",
        "sheet.readme": "Read me",
        "sheet.table": "Risk of bias",
        "sheet.legend": "Legend",
        "sheet.justifications": "Justifications",
        "title": "Risk of bias: consolidated table",
        "project": "Project",
        "tool": "Instrument",
        "version": "Version",
        "result": "Result assessed",
        "exported_at": "Exported at",
        "source": "Source",
        "source.text": "Only submitted consensus assessments (two blind assessments and "
        "conflicts decided) or imported ones, marked as such.",
        "missing": "Studies NOT in this file",
        "none_missing": "None: every study with this instrument is in this file.",
        "no_score": "This instrument has no total score; the overall judgement follows the "
        "rule set by the group.",
        "study": "Study",
        "overall": "Overall",
        "origin": "Source",
        "column": "Column",
        "description": "Description",
        "item": "Item",
        "judgement": "Judgement or answer",
        "justification": "Justification",
        "imported": "imported",
        "consensus": "consensus",
        "reason.no_assessment": "no assessment started",
        "reason.in_progress": "individual assessments in progress",
        "reason.consensus_pending": "consensus not submitted yet",
    },
}


def _t(lang: str, key: str) -> str:
    return TEXTS[lang][key]


def file_name(ctx: ProjectContext, lang: str, fmt: RobFormat) -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    kind = _t(lang, "file") + ("-robvis" if fmt == RobFormat.ROBVIS else "")
    ext = "csv" if fmt in (RobFormat.ROBVIS, RobFormat.CSV) else fmt.value
    return f"{_slug(ctx.project.title)}_{kind}_{day}.{ext}"


def _robvis_csv(tool: RobTool, data: consolidated.TableOut) -> bytes:
    words = ROBVIS_WORDS.get(tool.template_key)
    if words is None:
        raise AppError("rob.no_robvis_template", status_code=422)
    table = Table(
        name="robvis",
        header=["Study", *[c.short for c in data.columns], "Overall", "Weight"],
    )
    for row in data.rows:
        table.rows.append(
            [
                row.label,
                *[
                    words.get(row.values.get(c.key) or "no_information", "No information")
                    for c in data.columns
                ],
                words.get(row.overall or "no_information", "No information"),
                1,
            ]
        )
    return write_csv(table, CsvStyle.R)


def _main_table(data: consolidated.TableOut, lang: str) -> Table:
    table = Table(
        name=_t(lang, "sheet.table"),
        header=[
            _t(lang, "study"),
            *[c.short for c in data.columns],
            _t(lang, "overall"),
            _t(lang, "origin"),
        ],
    )
    for row in data.rows:
        table.rows.append(
            [
                row.label,
                *[
                    consolidated.level_label(v, lang) if (v := row.values.get(c.key)) else None
                    for c in data.columns
                ],
                consolidated.level_label(row.overall, lang) if row.overall else None,
                _t(lang, "imported" if row.kind == "imported" else "consensus"),
            ]
        )
    return table


def _legend(data: consolidated.TableOut, lang: str) -> Table:
    table = Table(
        name=_t(lang, "sheet.legend"), header=[_t(lang, "column"), _t(lang, "description")]
    )
    for c in data.columns:
        table.rows.append([c.short, consolidated._localized(c.name, lang)])
    return table


async def _justifications(session: AsyncSession, data: consolidated.TableOut, lang: str) -> Table:
    table = Table(
        name=_t(lang, "sheet.justifications"),
        header=[
            _t(lang, "study"),
            _t(lang, "item"),
            _t(lang, "judgement"),
            _t(lang, "justification"),
        ],
    )
    short = {c.key: c.short for c in data.columns}
    ids = [r.assessment_id for r in data.rows]
    label_of = {r.assessment_id: r.label for r in data.rows}
    judgements = list(
        await session.scalars(select(RobJudgement).where(RobJudgement.assessment_id.in_(ids)))
    )
    answers = list(await session.scalars(select(RobAnswer).where(RobAnswer.assessment_id.in_(ids))))
    for row in data.rows:
        for j in judgements:
            if j.assessment_id == row.assessment_id and (j.justification or "").strip():
                item = (
                    short.get(j.domain_key or "", _t(lang, "overall"))
                    if j.domain_key
                    else _t(lang, "overall")
                )
                table.rows.append(
                    [
                        label_of[row.assessment_id],
                        item,
                        consolidated.level_label(j.final, lang) if j.final else None,
                        j.justification,
                    ]
                )
        for a in answers:
            if a.assessment_id == row.assessment_id and (a.justification or "").strip():
                value = row.values.get(a.question_key)
                if a.question_key not in short:
                    continue
                table.rows.append(
                    [
                        label_of[row.assessment_id],
                        short[a.question_key],
                        consolidated.level_label(value, lang) if value else a.answer,
                        a.justification,
                    ]
                )
    return table


def _readme(
    ctx: ProjectContext,
    tool: RobTool,
    template: Template,
    data: consolidated.TableOut,
    outcome_name: str | None,
    lang: str,
) -> list[tuple[str, str]]:
    lines = [
        (_t(lang, "title"), ""),
        (_t(lang, "project"), ctx.project.title),
        (_t(lang, "tool"), consolidated._localized(template.name.model_dump(by_alias=True), lang)),
        (_t(lang, "version"), tool.template_version),
    ]
    if data.timepoint:
        lines.append((_t(lang, "result"), f"{outcome_name} · {data.timepoint}"))
    lines += [
        (_t(lang, "exported_at"), datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")),
        (_t(lang, "source"), _t(lang, "source.text")),
    ]
    if template.judgement.kind == "group_rule":
        lines.append(("", _t(lang, "no_score")))
    lines.append((_t(lang, "missing"), "" if data.pending else _t(lang, "none_missing")))
    lines += [(p.label, _t(lang, f"reason.{p.reason}")) for p in data.pending]
    return lines


def _shade(cell: object, colour: str) -> None:
    props = cell._tc.get_or_add_tcPr()  # type: ignore[attr-defined]
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), colour)
    props.append(shading)


# Light versions of the robvis colours, so the text stays readable.
CELL_COLOURS = {
    "low": "C6EFCE",
    "good": "C6EFCE",
    "Y": "C6EFCE",
    "SY": "C6EFCE",
    "low_except_confounding": "DFF5D8",
    "PY": "DFF5D8",
    "WY": "DFF5D8",
    "some_concerns": "FFF2B3",
    "moderate": "FFF2B3",
    "fair": "FFF2B3",
    "U": "FFF2B3",
    "PN": "FCE4C4",
    "WN": "FCE4C4",
    "high": "F4C7C3",
    "serious": "F4C7C3",
    "poor": "F4C7C3",
    "N": "F4C7C3",
    "SN": "F4C7C3",
    "critical": "E0A8A8",
    "very_high": "E0A8A8",
    "no_information": "D2E3FC",
    "NI": "D2E3FC",
}


def _cell_colour(key: str | None) -> str | None:
    if not key:
        return None
    if key.startswith("stars_"):
        _, n, _, top = key.split("_")
        return "C6EFCE" if n == top else "F4C7C3" if n == "0" else "FFF2B3"
    return CELL_COLOURS.get(key)


def _docx(
    readme: list[tuple[str, str]],
    data: consolidated.TableOut,
    main: Table,
    legend: Table,
    justifications: Table,
    lang: str,
) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    doc.add_heading(readme[0][0], level=1)
    for key, value in readme[1:]:
        p = doc.add_paragraph()
        if key:
            p.add_run(f"{key}: ").bold = True
        p.add_run(value)

    grid = doc.add_table(rows=1, cols=len(main.header))
    grid.style = "Table Grid"
    for i, text in enumerate(main.header):
        grid.rows[0].cells[i].text = text
        grid.rows[0].cells[i].paragraphs[0].runs[0].bold = True
    for row, raw in zip(main.rows, data.rows, strict=True):
        cells = grid.add_row().cells
        keys = [None, *[raw.values.get(c.key) for c in data.columns], raw.overall, None]
        for i, cell_value in enumerate(row):
            cells[i].text = "" if cell_value is None else str(cell_value)
            if (colour := _cell_colour(keys[i])) is not None:
                _shade(cells[i], colour)
    for row in grid.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)

    doc.add_heading(_t(lang, "sheet.legend"), level=2)
    for short, name in legend.rows:
        doc.add_paragraph(f"{short}: {name}", style="List Bullet")
    if justifications.rows:
        doc.add_heading(_t(lang, "sheet.justifications"), level=2)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        for i, text in enumerate(justifications.header):
            table.rows[0].cells[i].text = text
        for values in justifications.rows:
            cells = table.add_row().cells
            for i, cell_value in enumerate(values):
                cells[i].text = "" if cell_value is None else str(cell_value)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


async def export(
    session: AsyncSession,
    ctx: ProjectContext,
    *,
    tool_id: uuid.UUID,
    outcome_id: uuid.UUID | None,
    timepoint: str | None,
    fmt: RobFormat,
    csv_style: CsvStyle,
    lang: str,
    acknowledge_missing: bool,
) -> tuple[bytes, str, str]:
    data = await consolidated.table(session, ctx, tool_id, outcome_id, timepoint)
    if not data.rows:
        raise AppError("rob.nothing_to_export", status_code=409)
    if data.pending and not acknowledge_missing:
        raise AppError("rob.export_missing_studies", status_code=409, count=len(data.pending))
    tool = await session.get(RobTool, tool_id)
    assert tool is not None  # noqa: S101 - checked by table()
    if fmt == RobFormat.ROBVIS:
        return _robvis_csv(tool, data), file_name(ctx, lang, fmt), "text/csv; charset=utf-8"
    main = _main_table(data, lang)
    if fmt == RobFormat.CSV:
        return write_csv(main, csv_style), file_name(ctx, lang, fmt), "text/csv; charset=utf-8"
    template = Template.model_validate(tool.structure)
    outcome_name = None
    if data.outcome_id:
        outcome = await session.get(Outcome, data.outcome_id)
        outcome_name = outcome.name if outcome else None
    readme = _readme(ctx, tool, template, data, outcome_name, lang)
    legend = _legend(data, lang)
    justifications = await _justifications(session, data, lang)
    if fmt == RobFormat.XLSX:
        readme_table = Table(
            name=_t(lang, "sheet.readme"), header=["", ""], rows=[list(r) for r in readme]
        )
        content = write_xlsx([readme_table, main, legend, justifications])
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return content, file_name(ctx, lang, fmt), media
    content = _docx(readme, data, main, legend, justifications, lang)
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return content, file_name(ctx, lang, fmt), media
