"""GRADE suggestions and judgements (stage 6 step 1), with the real R service.

Data: the public dat.bcg set (13 studies, RR). Numbers are compared with what the
R service returns for the same analysis, never typed by hand.
"""

import io
import math

from docx import Document
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_analysis_subgroups import _bcg
from tests.test_consensus import MakeUser

BODY = {"timepoint": "5 anos", "measure": "RR", "method": "REML", "test": "z"}
ZERO = {
    k: {"change": 0}
    for k in (
        "risk_of_bias",
        "inconsistency",
        "indirectness",
        "imprecision",
        "publication_bias",
        "large_effect",
        "dose_response",
        "plausible_confounding",
    )
}


async def test_suggestions_follow_the_approved_thresholds(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    body = {**BODY, "outcome_id": outcome}
    run = (await client.post(f"{p['base']}/analyses/run", headers=ana.headers, json=body)).json()
    egger = (
        await client.post(f"{p['base']}/analyses/egger", headers=ana.headers, json=body)
    ).json()
    r = await client.post(f"{p['base']}/grade/suggest", headers=ana.headers, json=body)
    assert r.status_code == 200, r.text
    s = r.json()
    het, pooled = run["result"]["heterogeneity"], run["result"]["pooled"]
    assert s["k"] == 13 and s["ratio"] is True
    assert math.isclose(s["i2"], het["i2"]) and math.isclose(s["estimate"], pooled["estimate"])
    d = s["domains"]
    assert d["inconsistency"]["suggested"] == (-1 if het["i2"] >= 50 else 0)
    crosses = pooled["ci_lb"] < 0 < pooled["ci_ub"]
    assert d["imprecision"]["suggested"] == (-1 if crosses else 0)
    assert d["publication_bias"]["suggested"] == (-1 if egger["result"]["p_value"] < 0.10 else 0)
    assert d["risk_of_bias"]["reason"] == "rob_no_tool"
    # Large effect is only suggested when nothing was rated down.
    downgraded = any(v["suggested"] < 0 for k, v in d.items() if k != "large_effect")
    if downgraded:
        assert d["large_effect"]["suggested"] == 0
    assert d["dose_response"]["reason"] == "human_only"


async def test_save_needs_justifications_and_computes_the_final_level(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    base = {**BODY, "outcome_id": outcome, "approach": "classic", "start_certainty": "low"}
    sug = (
        await client.post(
            f"{p['base']}/grade/suggest", headers=ana.headers, json={**BODY, "outcome_id": outcome}
        )
    ).json()["domains"]
    # Accepting a non-zero suggestion still needs a justification.
    accepted = {k: {"change": v["suggested"]} for k, v in sug.items()}
    r = await client.put(
        f"{p['base']}/grade", headers=ana.headers, json={**base, "domains": accepted}
    )
    if any(v["suggested"] for v in sug.values()):
        assert r.status_code == 422 and r.json()["code"] == "grade.justification_required"
    domains = {**ZERO, "inconsistency": {"change": -1, "justification": "I² alto"}}
    domains["large_effect"] = {"change": 2, "justification": "efeito grande"}
    for k, v in sug.items():
        if v["suggested"] != domains[k]["change"] and not domains[k].get("justification"):
            domains[k] = {"change": 0, "justification": "o grupo discorda"}
    r = await client.put(
        f"{p['base']}/grade", headers=ana.headers, json={**base, "domains": domains}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["final_certainty"] == "moderate"  # low - 1 + 2
    assert out["summary"]["k"] == 13 and out["suggestions"]["inconsistency"]["suggested"] in (0, -1)
    # Stale version conflicts; the right version updates the same row.
    r = await client.put(
        f"{p['base']}/grade", headers=ana.headers, json={**base, "domains": domains}
    )
    assert r.status_code == 409
    r = await client.put(
        f"{p['base']}/grade",
        headers=ana.headers,
        json={**base, "domains": domains, "version": out["version"], "start_certainty": "high"},
    )
    assert r.status_code == 200 and r.json()["final_certainty"] == "high"
    assert len((await client.get(f"{p['base']}/grade", headers=ana.headers)).json()) == 1
    bad = {**domains, "imprecision": {"change": -3, "justification": "x"}}
    r = await client.put(f"{p['base']}/grade", headers=ana.headers, json={**base, "domains": bad})
    assert r.status_code == 422
    r = await client.delete(f"{p['base']}/grade/{out['id']}", headers=ana.headers)
    assert r.status_code == 204
    assert (await client.get(f"{p['base']}/grade", headers=ana.headers)).json() == []


async def test_settings_default_and_change(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, _ = await _bcg(client, make_user, session)
    r = await client.get(f"{p['base']}/grade/settings", headers=ana.headers)
    assert r.json()["i2_threshold"] == 50 and r.json()["egger_min_k"] == 10
    r = await client.put(
        f"{p['base']}/grade/settings", headers=ana.headers, json={"i2_threshold": 40}
    )
    assert r.status_code == 200 and r.json()["i2_threshold"] == 40


async def test_summary_of_findings_has_effect_certainty_and_justifications(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    url = f"{p['base']}/grade/summary-of-findings"
    r = await client.get(url, headers=ana.headers)
    assert r.status_code == 409 and r.json()["code"] == "grade.sof_empty"
    body = {**BODY, "outcome_id": outcome}
    sug = (await client.post(f"{p['base']}/grade/suggest", headers=ana.headers, json=body)).json()
    domains = {
        k: {"change": v["suggested"], "justification": f"motivo {k}"}
        for k, v in sug["domains"].items()
    }
    domains["inconsistency"] = {"change": -1, "justification": "I² alto entre os estudos"}
    r = await client.put(
        f"{p['base']}/grade",
        headers=ana.headers,
        json={**body, "approach": "classic", "start_certainty": "high", "domains": domains},
    )
    assert r.status_code == 200, r.text
    natural = sug["natural"]
    r = await client.get(url, headers=ana.headers, params={"format": "docx", "lang": "pt-BR"})
    assert r.status_code == 200 and "summary-of-findings" in r.headers["content-disposition"]
    text = " | ".join(
        c.text for t in Document(io.BytesIO(r.content)).tables for row in t.rows for c in row.cells
    )
    full = text + " | ".join(p_.text for p_ in Document(io.BytesIO(r.content)).paragraphs)
    assert f"{natural['estimate']:.2f}".replace(".", ",") in text
    assert "I² alto entre os estudos" in full and "inconsistência" in text
    r = await client.get(url, headers=ana.headers, params={"format": "xlsx", "lang": "en"})
    ws = load_workbook(io.BytesIO(r.content)).active
    values = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    assert "Outcome" in values and any(f"{natural['estimate']:.2f}" in v for v in values)
    assert any("inconsistency" in v for v in values)
