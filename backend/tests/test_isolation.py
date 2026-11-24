"""Project isolation (CLAUDE.md 0.1, rule 10; docs/validacao.md, 11.2).

Every project route is listed here. A user who is not a member must get 404 on all
of them, including a system administrator. When a new project route is added,
add it to PROJECT_ROUTES; `test_every_project_route_is_covered` fails otherwise.
"""

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.modules.auth.models import User
from tests.conftest import LoggedUser

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]

PROJECT_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/api/v1/projects/{project_id}", None),
    ("PATCH", "/api/v1/projects/{project_id}", {"version": 1, "title": "hack"}),
    ("DELETE", "/api/v1/projects/{project_id}", None),
    ("POST", "/api/v1/projects/{project_id}/transfer-ownership", {"member_id": "{member_id}"}),
    ("GET", "/api/v1/projects/{project_id}/members", None),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/members/{member_id}",
        {"version": 1, "roles": ["admin"]},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/members/{member_id}", None),
    ("POST", "/api/v1/projects/{project_id}/invitations", {"roles": ["admin"]}),
    ("GET", "/api/v1/projects/{project_id}/invitations", None),
    ("DELETE", "/api/v1/projects/{project_id}/invitations/{invitation_id}", None),
    ("POST", "/api/v1/projects/{project_id}/uploads", {"filename": "a.pdf", "size_bytes": 10}),
    ("GET", "/api/v1/projects/{project_id}/uploads/{upload_id}", None),
    ("DELETE", "/api/v1/projects/{project_id}/uploads/{upload_id}", None),
    ("POST", "/api/v1/projects/{project_id}/uploads/{upload_id}/parts", {"part_numbers": [1]}),
    ("POST", "/api/v1/projects/{project_id}/uploads/{upload_id}/complete", None),
    ("GET", "/api/v1/projects/{project_id}/uploads/{upload_id}/download-url", None),
    ("GET", "/api/v1/projects/{project_id}/jobs/{job_id}", None),
    ("GET", "/api/v1/projects/{project_id}/jobs/{job_id}/events", None),
    ("GET", "/api/v1/projects/{project_id}/outcomes", None),
    ("POST", "/api/v1/projects/{project_id}/outcomes", {"name": "QI", "type": "continuous"}),
    ("PATCH", "/api/v1/projects/{project_id}/outcomes/{outcome_id}", {"version": 1, "name": "x"}),
    ("DELETE", "/api/v1/projects/{project_id}/outcomes/{outcome_id}", None),
    ("GET", "/api/v1/projects/{project_id}/comparison-groups", None),
    ("POST", "/api/v1/projects/{project_id}/comparison-groups", {"label": "< 5 anos"}),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/comparison-groups/{group_id}",
        {"version": 1, "label": "x"},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/comparison-groups/{group_id}", None),
    ("GET", "/api/v1/projects/{project_id}/studies", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/studies",
        {"label": "X", "design": "other", "reference": {"title": "T"}},
    ),
    ("GET", "/api/v1/projects/{project_id}/studies/{study_id}", None),
    ("PATCH", "/api/v1/projects/{project_id}/studies/{study_id}", {"version": 1, "label": "Y"}),
    ("DELETE", "/api/v1/projects/{project_id}/studies/{study_id}", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/studies/{study_id}/reports",
        {"reference": {"title": "T2"}},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/studies/{study_id}/reports/{report_id}", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/studies/{study_id}/merge",
        {"other_study_id": "{study_id}"},
    ),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/references/{reference_id}",
        {"version": 1, "title": "Z"},
    ),
    ("POST", "/api/v1/projects/{project_id}/study-imports/preview", None),
    ("POST", "/api/v1/projects/{project_id}/study-imports", None),
    ("POST", "/api/v1/projects/{project_id}/searches", None),
    ("GET", "/api/v1/projects/{project_id}/searches", None),
    ("GET", "/api/v1/projects/{project_id}/searches/{search_id}", None),
    ("DELETE", "/api/v1/projects/{project_id}/searches/{search_id}", None),
    ("GET", "/api/v1/projects/{project_id}/references", None),
    ("GET", "/api/v1/projects/{project_id}/deduplication/settings", None),
    ("PUT", "/api/v1/projects/{project_id}/deduplication/settings", {"title_threshold": 0.95}),
    ("POST", "/api/v1/projects/{project_id}/deduplication/run", None),
    ("GET", "/api/v1/projects/{project_id}/deduplication/pairs", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/deduplication/pairs/{pair_id}",
        {"action": "reject", "version": 1},
    ),
    ("POST", "/api/v1/projects/{project_id}/deduplication/confirm-certain", None),
    ("GET", "/api/v1/projects/{project_id}/deduplication/report", None),
    ("GET", "/api/v1/projects/{project_id}/deduplication/report.csv", None),
    ("GET", "/api/v1/projects/{project_id}/screening/settings", None),
    ("PUT", "/api/v1/projects/{project_id}/screening/settings", {"blind": True}),
    ("GET", "/api/v1/projects/{project_id}/screening/queue", None),
    ("GET", "/api/v1/projects/{project_id}/screening/counts", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/screening/references/{reference_id}/decision",
        {"decision": "include"},
    ),
    ("POST", "/api/v1/projects/{project_id}/screening/undo", None),
    ("GET", "/api/v1/projects/{project_id}/screening/references/{reference_id}/history", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/screening/references/{reference_id}/resolution",
        {"decision": "include", "reason": "ok ok"},
    ),
    (
        "DELETE",
        "/api/v1/projects/{project_id}/screening/references/{reference_id}/resolution",
        None,
    ),
    (
        "PUT",
        "/api/v1/projects/{project_id}/screening/references/{reference_id}/useful",
        {"useful": True},
    ),
    ("GET", "/api/v1/projects/{project_id}/screening/assignments", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/screening/assignments",
        {"user_id": "{study_id}", "count": 1},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/screening/assignments/{user_id}", None),
    ("GET", "/api/v1/projects/{project_id}/screening/agreement", None),
    ("GET", "/api/v1/projects/{project_id}/screening/exclusion-reasons", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/screening/exclusion-reasons",
        {"label": "Outro motivo"},
    ),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/screening/exclusion-reasons/{reason_id}",
        {"label": "Novo", "version": 1},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/screening/exclusion-reasons/{reason_id}", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/screening/exclusion-reasons/{reason_id}/merge",
        {"into_id": "{study_id}", "version": 1},
    ),
    ("GET", "/api/v1/projects/{project_id}/screening/included", None),
    ("GET", "/api/v1/projects/{project_id}/screening/priority", None),
    ("GET", "/api/v1/projects/{project_id}/prisma/counts", None),
    (
        "PUT",
        "/api/v1/projects/{project_id}/prisma/adjustments/{key}",
        {"value": 1, "justification": "lista final"},
    ),
    ("POST", "/api/v1/projects/{project_id}/prisma/flow", {"format": "svg"}),
    ("GET", "/api/v1/projects/{project_id}/prisma/flow.docx", None),
    ("GET", "/api/v1/projects/{project_id}/prisma/checklist", None),
    ("PUT", "/api/v1/projects/{project_id}/prisma/checklist/{code}", {"status": "reported"}),
    ("GET", "/api/v1/projects/{project_id}/prisma/checklist.docx", None),
    ("GET", "/api/v1/projects/{project_id}/comments?entity=study&entity_id={study_id}", None),
    ("GET", "/api/v1/projects/{project_id}/comments/members", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/comments",
        {"entity": "study", "entity_id": "{study_id}", "text": "x"},
    ),
    ("PUT", "/api/v1/projects/{project_id}/comments/{comment_id}", {"text": "x", "version": 1}),
    ("DELETE", "/api/v1/projects/{project_id}/comments/{comment_id}", None),
    ("GET", "/api/v1/projects/{project_id}/exports/bibliography/status", None),
    ("GET", "/api/v1/projects/{project_id}/exports/bibliography", None),
    ("POST", "/api/v1/projects/{project_id}/backups", None),
    ("GET", "/api/v1/projects/{project_id}/backups/{job_id}/download", None),
    ("POST", "/api/v1/projects/{project_id}/unarchive", None),
    ("GET", "/api/v1/projects/{project_id}/ai/settings", None),
    ("PUT", "/api/v1/projects/{project_id}/ai/settings", {"enabled": False}),
    ("POST", "/api/v1/projects/{project_id}/ai/tutor", {"question": "O que é I²?"}),
    (
        "POST",
        "/api/v1/projects/{project_id}/ai/locate",
        {"pdf_id": "{pdf_id}", "question": "cegamento"},
    ),
    ("GET", "/api/v1/projects/{project_id}/ai/suggestions?target_id={pdf_id}", None),
    ("GET", "/api/v1/projects/{project_id}/ai/metrics", None),
    ("GET", "/api/v1/projects/{project_id}/ai/statement.docx", None),
    (
        "PUT",
        "/api/v1/projects/{project_id}/ai/suggestions/{suggestion_id}/decision",
        {"status": "accepted"},
    ),
    ("GET", "/api/v1/projects/{project_id}/grade/settings", None),
    ("PUT", "/api/v1/projects/{project_id}/grade/settings", {}),
    (
        "POST",
        "/api/v1/projects/{project_id}/grade/suggest",
        {"outcome_id": "{outcome_id}", "timepoint": "x"},
    ),
    ("GET", "/api/v1/projects/{project_id}/grade", None),
    ("GET", "/api/v1/projects/{project_id}/grade/summary-of-findings", None),
    (
        "PUT",
        "/api/v1/projects/{project_id}/grade",
        {
            "outcome_id": "{outcome_id}",
            "timepoint": "x",
            "approach": "classic",
            "start_certainty": "low",
            "domains": {},
        },
    ),
    ("DELETE", "/api/v1/projects/{project_id}/grade/{assessment_id}", None),
    ("POST", "/api/v1/projects/{project_id}/screening/priority", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/screening/included/{reference_id}/study",
        {"mode": "attach", "study_id": "{study_id}"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/reports/{report_id}/pdfs",
        {"upload_id": "{upload_id}"},
    ),
    ("GET", "/api/v1/projects/{project_id}/reports/{report_id}/pdfs", None),
    ("GET", "/api/v1/projects/{project_id}/pdfs/{pdf_id}", None),
    ("DELETE", "/api/v1/projects/{project_id}/pdfs/{pdf_id}", None),
    ("GET", "/api/v1/projects/{project_id}/pdfs/{pdf_id}/search?q=teste", None),
    ("GET", "/api/v1/projects/{project_id}/pdfs/{pdf_id}/annotations", None),
    ("POST", "/api/v1/projects/{project_id}/pdfs/{pdf_id}/annotations", {"page": 1, "quote": "x"}),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/annotations/{annotation_id}",
        {"version": 1, "note": "x"},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/annotations/{annotation_id}", None),
    ("GET", "/api/v1/projects/{project_id}/extraction-form", None),
    (
        "PUT",
        "/api/v1/projects/{project_id}/extraction-form",
        {"version": 1, "schema": {"fields": []}},
    ),
    ("GET", "/api/v1/projects/{project_id}/studies/{study_id}/extractions", None),
    ("POST", "/api/v1/projects/{project_id}/studies/{study_id}/extractions", None),
    ("GET", "/api/v1/projects/{project_id}/extractions/{extraction_id}", None),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/extractions/{extraction_id}",
        {"version": 1, "characteristics": {}},
    ),
    ("POST", "/api/v1/projects/{project_id}/extractions/{extraction_id}/submit", None),
    ("POST", "/api/v1/projects/{project_id}/extractions/{extraction_id}/arms", {"label": "x"}),
    ("PATCH", "/api/v1/projects/{project_id}/arms/{arm_id}", {"version": 1, "n": 5}),
    ("DELETE", "/api/v1/projects/{project_id}/arms/{arm_id}", None),
    (
        "PUT",
        "/api/v1/projects/{project_id}/extractions/{extraction_id}/measures/{outcome_id}",
        {"scale_name": "x"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/extractions/{extraction_id}/outcome-data",
        {"arm_id": "{arm_id}", "outcome_id": "{outcome_id}", "timepoint": "x"},
    ),
    ("PUT", "/api/v1/projects/{project_id}/outcome-data/{row_id}", {"version": 1, "values": {}}),
    ("DELETE", "/api/v1/projects/{project_id}/outcome-data/{row_id}", None),
    ("GET", "/api/v1/projects/{project_id}/extractions/{extraction_id}/alerts", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/alerts/{alert_id}/justify",
        {"justification": "conferido no artigo"},
    ),
    ("GET", "/api/v1/projects/{project_id}/pending-checks", None),
    ("GET", "/api/v1/projects/{project_id}/extractions/{extraction_id}/direction", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/extractions/{extraction_id}/direction/confirm",
        {"outcome_id": "{outcome_id}", "timepoint": "1"},
    ),
    ("GET", "/api/v1/projects/{project_id}/studies/{study_id}/comparison", None),
    ("POST", "/api/v1/projects/{project_id}/studies/{study_id}/consensus", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/studies/{study_id}/decisions",
        {"key": "char|country", "choice": "a"},
    ),
    ("GET", "/api/v1/projects/{project_id}/extraction-review", None),
    ("POST", "/api/v1/projects/{project_id}/extraction-review/lock", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/extraction-review/unlock",
        {"justification": "motivo de teste"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/extractions/{extraction_id}/reopen",
        {"justification": "motivo de teste"},
    ),
    ("GET", "/api/v1/projects/{project_id}/exports/extraction/status", None),
    ("GET", "/api/v1/projects/{project_id}/exports/extraction", None),
    ("GET", "/api/v1/projects/{project_id}/rob/catalog", None),
    ("GET", "/api/v1/projects/{project_id}/rob/tools", None),
    ("POST", "/api/v1/projects/{project_id}/rob/tools", {"template_key": "generic"}),
    (
        "PUT",
        "/api/v1/projects/{project_id}/rob/tools/{tool_id}/texts",
        {"version": 1, "texts": {}},
    ),
    (
        "PUT",
        "/api/v1/projects/{project_id}/rob/tools/{tool_id}/structure",
        {"version": 1, "domains": [{"name": "D", "questions": 1}]},
    ),
    ("GET", "/api/v1/projects/{project_id}/rob/studies/{study_id}/tool", None),
    (
        "PUT",
        "/api/v1/projects/{project_id}/rob/studies/{study_id}/tool",
        {"tool_id": "{tool_id}"},
    ),
    (
        "PUT",
        "/api/v1/projects/{project_id}/rob/tools/{tool_id}/overall-rule",
        {"version": 1, "rule": None},
    ),
    ("GET", "/api/v1/projects/{project_id}/rob/studies/{study_id}/assessments", None),
    ("POST", "/api/v1/projects/{project_id}/rob/studies/{study_id}/assessments", {}),
    ("GET", "/api/v1/projects/{project_id}/rob/assessments/{assessment_id}", None),
    (
        "PUT",
        "/api/v1/projects/{project_id}/rob/assessments/{assessment_id}/answers",
        {"answers": [{"question_key": "d1.1", "answer": "Y"}]},
    ),
    (
        "PUT",
        "/api/v1/projects/{project_id}/rob/assessments/{assessment_id}/variants",
        {"variants": {}},
    ),
    (
        "PUT",
        "/api/v1/projects/{project_id}/rob/assessments/{assessment_id}/judgement",
        {"final": "low"},
    ),
    ("POST", "/api/v1/projects/{project_id}/rob/assessments/{assessment_id}/submit", None),
    ("GET", "/api/v1/projects/{project_id}/rob/studies/{study_id}/comparisons", None),
    ("POST", "/api/v1/projects/{project_id}/rob/studies/{study_id}/consensus", {}),
    (
        "POST",
        "/api/v1/projects/{project_id}/rob/assessments/{assessment_id}/decisions",
        {"key": "overall", "choice": "a"},
    ),
    ("GET", "/api/v1/projects/{project_id}/rob/agreement", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses/preview",
        {"outcome_id": "{tool_id}", "timepoint": "x"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses/run",
        {"outcome_id": "{tool_id}", "timepoint": "x"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses/forest-plot",
        {"outcome_id": "{tool_id}", "timepoint": "x"},
    ),
    ("GET", "/api/v1/projects/{project_id}/analyses", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses/narrative",
        {"outcome_id": "{tool_id}", "timepoint": "x"},
    ),
    (
        "PUT",
        "/api/v1/projects/{project_id}/analyses/narrative/{study_id}",
        {"outcome_id": "{tool_id}", "timepoint": "x", "direction": "mixed"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses/egger",
        {"outcome_id": "{tool_id}", "timepoint": "x"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses/funnel-plot",
        {"outcome_id": "{tool_id}", "timepoint": "x"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses/subgroups",
        {"outcome_id": "{tool_id}", "timepoint": "x", "variable": "cutoff"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses/sensitivity",
        {"outcome_id": "{tool_id}", "timepoint": "x", "scenario": "leave_one_out"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/analyses",
        {"outcome_id": "{tool_id}", "timepoint": "x"},
    ),
    ("GET", "/api/v1/projects/{project_id}/analyses/{analysis_id}", None),
    ("DELETE", "/api/v1/projects/{project_id}/analyses/{analysis_id}", None),
    ("GET", "/api/v1/projects/{project_id}/analyses/{analysis_id}/r-script", None),
    ("GET", "/api/v1/projects/{project_id}/analysis-plan", None),
    ("PUT", "/api/v1/projects/{project_id}/analysis-plan", {"version": 1}),
    ("GET", "/api/v1/projects/{project_id}/rob/review", None),
    ("POST", "/api/v1/projects/{project_id}/rob/review/lock", None),
    ("POST", "/api/v1/projects/{project_id}/rob/review/unlock", {"justification": "teste ok"}),
    (
        "POST",
        "/api/v1/projects/{project_id}/rob/assessments/{assessment_id}/reopen",
        {"justification": "teste ok"},
    ),
    (
        "POST",
        "/api/v1/projects/{project_id}/rob/assessments/{assessment_id}/discard-import",
        {"justification": "teste ok"},
    ),
    ("POST", "/api/v1/projects/{project_id}/rob/imports/preview", None),
    ("POST", "/api/v1/projects/{project_id}/rob/imports", None),
    ("GET", "/api/v1/projects/{project_id}/exports/risk-of-bias?tool_id={tool_id}", None),
    ("GET", "/api/v1/projects/{project_id}/rob/table?tool_id={tool_id}", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/rob/plots",
        {"tool_id": "{tool_id}", "kind": "summary", "format": "svg"},
    ),
]


def test_every_project_route_is_covered() -> None:
    paths = app.openapi()["paths"]
    registered = {
        (method.upper(), path)
        for path, operations in paths.items()
        if "{project_id}" in path
        for method in operations
    }
    covered = {(method, path.split("?")[0]) for method, path, _ in PROJECT_ROUTES}
    assert registered == covered


async def _setup(client: AsyncClient, make_user: MakeUser) -> tuple[LoggedUser, dict[str, str]]:
    owner = await make_user()
    project = (
        await client.post("/api/v1/projects", json={"title": "Secreto"}, headers=owner.headers)
    ).json()
    members = (
        await client.get(f"/api/v1/projects/{project['id']}/members", headers=owner.headers)
    ).json()
    invitation = (
        await client.post(
            f"/api/v1/projects/{project['id']}/invitations",
            json={"roles": ["reader"]},
            headers=owner.headers,
        )
    ).json()
    base = f"/api/v1/projects/{project['id']}/uploads"
    content = b"%PDF-1.7 " + b"0" * 100
    upload = (
        await client.post(
            base, json={"filename": "a.pdf", "size_bytes": len(content)}, headers=owner.headers
        )
    ).json()
    urls = (
        await client.post(
            f"{base}/{upload['id']}/parts", json={"part_numbers": [1]}, headers=owner.headers
        )
    ).json()
    async with httpx.AsyncClient() as raw:
        await raw.put(urls[0]["url"], content=content)
    job = (await client.post(f"{base}/{upload['id']}/complete", headers=owner.headers)).json()
    ids = {
        "project_id": project["id"],
        "member_id": members[0]["id"],
        "invitation_id": invitation["id"],
        "upload_id": upload["id"],
        "job_id": job["id"],
        "outcome_id": (
            await client.post(
                f"/api/v1/projects/{project['id']}/outcomes",
                json={"name": "Desfecho", "type": "continuous"},
                headers=owner.headers,
            )
        ).json()["id"],
        **(study_ids := await _study_ids(client, owner, project["id"])),
        **(await _pdf_ids(client, owner, project["id"], study_ids["report_id"], upload["id"])),
        "group_id": (
            await client.post(
                f"/api/v1/projects/{project['id']}/comparison-groups",
                json={"label": "Grupo"},
                headers=owner.headers,
            )
        ).json()["id"],
    }
    ids.update(
        await _extraction_ids(client, owner, project["id"], ids["study_id"], ids["outcome_id"])
    )
    # Any id of this project's kind: the outsider must get 404 before it is even read.
    ids["analysis_id"] = ids["study_id"]
    ids["assessment_id"] = ids["study_id"]
    ids["comment_id"] = ids["study_id"]
    ids["suggestion_id"] = ids["study_id"]
    ids["search_id"] = ids["study_id"]
    ids["pair_id"] = ids["study_id"]
    ids["reference_id"] = ids["study_id"]
    ids["user_id"] = ids["study_id"]
    ids["reason_id"] = ids["study_id"]
    ids["key"] = "duplicates_removed"
    ids["code"] = "7"
    ids["tool_id"] = (
        await client.post(
            f"/api/v1/projects/{project['id']}/rob/tools",
            json={"template_key": "generic"},
            headers=owner.headers,
        )
    ).json()["id"]
    rob = f"/api/v1/projects/{project['id']}/rob"
    await client.put(
        f"{rob}/studies/{ids['study_id']}/tool",
        json={"tool_id": ids["tool_id"]},
        headers=owner.headers,
    )
    ids["assessment_id"] = (
        await client.post(
            f"{rob}/studies/{ids['study_id']}/assessments", json={}, headers=owner.headers
        )
    ).json()["id"]
    return owner, ids


async def _study_ids(client: AsyncClient, owner: LoggedUser, project_id: str) -> dict[str, str]:
    study = (
        await client.post(
            f"/api/v1/projects/{project_id}/studies",
            json={"label": "Estudo A", "design": "other", "reference": {"title": "Artigo A"}},
            headers=owner.headers,
        )
    ).json()
    report = study["reports"][0]
    return {
        "study_id": study["id"],
        "report_id": report["id"],
        "reference_id": report["reference"]["id"],
    }


async def _pdf_ids(
    client: AsyncClient, owner: LoggedUser, project_id: str, report_id: str, upload_id: str
) -> dict[str, str]:
    base = f"/api/v1/projects/{project_id}"
    pdf = (
        await client.post(
            f"{base}/reports/{report_id}/pdfs", json={"upload_id": upload_id}, headers=owner.headers
        )
    ).json()
    annotation = (
        await client.post(
            f"{base}/pdfs/{pdf['id']}/annotations",
            json={"page": 1, "quote": "trecho"},
            headers=owner.headers,
        )
    ).json()
    return {"pdf_id": pdf["id"], "annotation_id": annotation["id"]}


async def _extraction_ids(
    client: AsyncClient, owner: LoggedUser, project_id: str, study_id: str, outcome_id: str
) -> dict[str, str]:
    base = f"/api/v1/projects/{project_id}"
    extraction = (
        await client.post(f"{base}/studies/{study_id}/extractions", headers=owner.headers)
    ).json()
    arm = (
        await client.post(
            f"{base}/extractions/{extraction['id']}/arms",
            json={"label": "A"},
            headers=owner.headers,
        )
    ).json()
    row = (
        await client.post(
            f"{base}/extractions/{extraction['id']}/outcome-data",
            json={"arm_id": arm["id"], "outcome_id": outcome_id, "timepoint": "1", "n": 10},
            headers=owner.headers,
        )
    ).json()
    alerts = (
        await client.get(f"{base}/extractions/{extraction['id']}/alerts", headers=owner.headers)
    ).json()
    return {
        "extraction_id": extraction["id"],
        "arm_id": arm["id"],
        "row_id": row["id"],
        "alert_id": alerts[0]["id"],
    }


def _fill(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: _fill(v, ids) for k, v in value.items()}
    return value


@pytest.mark.parametrize(("method", "path", "body"), PROJECT_ROUTES)
async def test_outsider_gets_404_on_every_project_route(
    client: AsyncClient, make_user: MakeUser, method: str, path: str, body: dict[str, Any] | None
) -> None:
    _owner, ids = await _setup(client, make_user)
    outsider = await make_user()
    r = await client.request(
        method, _fill(path, ids), json=_fill(body, ids), headers=outsider.headers
    )
    assert r.status_code == 404, r.text


@pytest.mark.parametrize(("method", "path", "body"), PROJECT_ROUTES)
async def test_system_admin_is_not_a_backdoor(
    client: AsyncClient,
    make_user: MakeUser,
    session: AsyncSession,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    _owner, ids = await _setup(client, make_user)
    sysadmin = await make_user()
    await session.execute(
        update(User).where(User.id == uuid.UUID(sysadmin.id)).values(is_system_admin=True)
    )
    await session.commit()
    r = await client.request(
        method, _fill(path, ids), json=_fill(body, ids), headers=sysadmin.headers
    )
    assert r.status_code == 404, r.text


async def test_anonymous_gets_401(client: AsyncClient, make_user: MakeUser) -> None:
    _owner, ids = await _setup(client, make_user)
    r = await client.get(f"/api/v1/projects/{ids['project_id']}")
    assert r.status_code == 401


async def test_ids_from_another_project_are_not_reachable(
    client: AsyncClient, make_user: MakeUser
) -> None:
    """Admin of project B cannot touch members/invitations of project A through B's URL."""
    _owner_a, ids_a = await _setup(client, make_user)
    owner_b = await make_user()
    project_b = (
        await client.post("/api/v1/projects", json={"title": "B"}, headers=owner_b.headers)
    ).json()
    base_b = f"/api/v1/projects/{project_b['id']}"
    r = await client.delete(f"{base_b}/members/{ids_a['member_id']}", headers=owner_b.headers)
    assert r.status_code == 404
    r = await client.delete(
        f"{base_b}/invitations/{ids_a['invitation_id']}", headers=owner_b.headers
    )
    assert r.status_code == 404
    listed = (await client.get("/api/v1/projects", headers=owner_b.headers)).json()
    assert [p["id"] for p in listed] == [project_b["id"]]
