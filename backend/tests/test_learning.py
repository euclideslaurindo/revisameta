"""Learning mode: demonstration project created from the interface."""

import json
from pathlib import Path

from httpx import AsyncClient

from app.modules.learning.demo import normand
from tests.test_extraction import MakeUser


def test_demo_data_is_the_metafor_fixture() -> None:
    """The copy in the backend must match what metafor wrote (never typed by hand)."""
    cases = json.loads(Path("/stats-fixtures/meta-analysis.json").read_text(encoding="utf-8"))
    case = next(c for c in cases["cases"] if c["name"] == "dat.normand1999_MD_REML_knha")
    assert normand() == case["request"]["data"]


async def test_anyone_signed_in_can_create_a_demo_project(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia = await make_user("Ana"), await make_user("Bia")
    r = await client.post("/api/v1/demo-projects", json={"language": "en"}, headers=ana.headers)
    assert r.status_code == 201, r.text
    pid = r.json()["project_id"]
    project = (await client.get(f"/api/v1/projects/{pid}", headers=ana.headers)).json()
    assert project["title"].startswith("Demonstration") and "admin" in project["my_roles"]
    studies = (await client.get(f"/api/v1/projects/{pid}/studies", headers=ana.headers)).json()
    assert len(studies) == 9
    # The demo belongs to whoever created it: nobody else sees it.
    r = await client.get(f"/api/v1/projects/{pid}", headers=bia.headers)
    assert r.status_code in (403, 404)
    r = await client.post("/api/v1/demo-projects", json={})
    assert r.status_code == 401
