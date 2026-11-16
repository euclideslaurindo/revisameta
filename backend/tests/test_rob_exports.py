"""Exports of the consolidated risk of bias: robvis CSV, CSV, XLSX and DOCX (stage 2 step 5)."""

import csv
import io
import uuid
from typing import Any

from docx import Document
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risk_of_bias.models import RobAssessment, RobJudgement
from tests.conftest import FakeR
from tests.test_consensus import MakeUser
from tests.test_rob_consensus import STARS_A, _assess, _team
from tests.test_rob_consolidated import _consensus


def _url(p: dict[str, Any], tool_id: str, **query: Any) -> str:
    params = "&".join(f"{k}={v}" for k, v in {"tool_id": tool_id, **query}.items())
    return f"{p['base']}/exports/risk-of-bias?{params}"


async def test_nos_exports_in_every_format_and_never_silently(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    nos = p["tools"]["nos_cohort"]["id"]
    r = await client.get(_url(p, nos), headers=bia.headers)
    assert r.json()["code"] == "rob.nothing_to_export"

    await _assess(client, bia, p, STARS_A, "low")
    await _assess(client, caio, p, {**STARS_A, "outcome.3": "1"}, "moderate")
    await _consensus(client, ana, p, submit=True)
    # A second study with the same instrument, not assessed yet.
    other = (
        await client.post(
            f"{p['base']}/studies",
            json={
                "label": "Coorte 2022",
                "design": "cohort_prospective",
                "reference": {"title": "X"},
            },
            headers=ana.headers,
        )
    ).json()["id"]
    await client.put(f"{p['rob']}/studies/{other}/tool", json={"tool_id": nos}, headers=ana.headers)

    r = await client.get(_url(p, nos), headers=bia.headers)
    assert r.json()["code"] == "rob.export_missing_studies"
    r = await client.get(
        _url(p, nos, file_format="robvis", acknowledge_missing="true"), headers=bia.headers
    )
    assert r.json()["code"] == "rob.no_robvis_template"

    # XLSX: read-me with what is missing, table, legend and justifications.
    r = await client.get(_url(p, nos, acknowledge_missing="true"), headers=bia.headers)
    assert r.status_code == 200, r.text
    assert "risco-de-vies" in r.headers["content-disposition"]
    book = load_workbook(io.BytesIO(r.content))
    assert book.sheetnames == ["Leia-me", "Risco de viés", "Legenda", "Justificativas"]
    readme = [tuple(row) for row in book["Leia-me"].iter_rows(values_only=True)]
    assert ("Coorte 2022", "nenhuma avaliação iniciada") in readme
    assert any("não tem nota total" in (b or "") for _, b in readme)
    table = list(book["Risco de viés"].iter_rows(values_only=True))
    assert table[0][:3] == ("Estudo", "Q1", "Q2") and table[0][-2:] == ("Geral", "Origem")
    assert table[1][0] == "Coorte 2020"
    assert table[1][5] == "2 de 2 estrela(s)"  # comparability
    assert table[1][-2:] == ("Baixo", "consenso")
    justifications = list(book["Justificativas"].iter_rows(values_only=True))
    assert ("Coorte 2020", "Geral", "Baixo", "Conforme o artigo") in justifications

    # CSV for Portuguese Excel and in English for R.
    r = await client.get(
        _url(p, nos, file_format="csv", acknowledge_missing="true"), headers=bia.headers
    )
    text = r.content.decode("utf-8-sig")
    assert text.startswith("Estudo;Q1;")
    r = await client.get(
        _url(p, nos, file_format="csv", csv_style="r", lang="en", acknowledge_missing="true"),
        headers=bia.headers,
    )
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0][0] == "Study" and rows[1][-2:] == ["Low", "consensus"]

    # DOCX: the same table, with the legend.
    r = await client.get(
        _url(p, nos, file_format="docx", acknowledge_missing="true"), headers=bia.headers
    )
    doc = Document(io.BytesIO(r.content))
    first = doc.tables[0]
    assert first.rows[0].cells[0].text == "Estudo"
    assert first.rows[1].cells[0].text == "Coorte 2020"
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Q1:" in text and "Coorte 2022" in text


async def test_robvis_csv_uses_the_words_robvis_expects(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR, session: AsyncSession
) -> None:
    ana, _bia, _caio, p = await _team(client, make_user)
    tool = (
        await client.post(
            f"{p['rob']}/tools", json={"template_key": "robins_i_2016"}, headers=ana.headers
        )
    ).json()
    study = p["studies"]["cohort_retrospective"]
    await client.put(
        f"{p['rob']}/studies/{study}/tool", json={"tool_id": tool["id"]}, headers=ana.headers
    )
    # A submitted consensus written directly: the assessment flow is covered elsewhere.
    consensus = RobAssessment(
        id=uuid.uuid4(),
        project_id=uuid.UUID(p["pid"]),
        study_id=uuid.UUID(study),
        tool_id=uuid.UUID(tool["id"]),
        outcome_id=uuid.UUID(p["outcome"]),
        timepoint="5 anos",
        kind="consensus",
        status="submitted",
        variants={},
    )
    session.add(consensus)
    levels = ["low", "moderate", "serious", "critical", "no_information", "low", "low"]
    for i, level in enumerate(levels, start=1):
        session.add(
            RobJudgement(
                project_id=consensus.project_id,
                assessment_id=consensus.id,
                domain_key=f"d{i}",
                final=level,
            )
        )
    session.add(
        RobJudgement(
            project_id=consensus.project_id,
            assessment_id=consensus.id,
            domain_key=None,
            final="critical",
        )
    )
    await session.commit()

    r = await client.get(
        _url(p, tool["id"], outcome_id=p["outcome"], timepoint="5 anos", file_format="robvis"),
        headers=ana.headers,
    )
    assert r.status_code == 200, r.text
    assert "-robvis_" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0] == ["Study", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "Overall", "Weight"]
    assert rows[1] == [
        "Coorte 2020",
        "Low",
        "Moderate",
        "Serious",
        "Critical",
        "No information",
        "Low",
        "Low",
        "Critical",
        "1",
    ]
