from collections.abc import Callable, Coroutine
from typing import Any

import httpx
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pdfs.text import normalize_for_search
from app.modules.uploads.models import PdfPageText
from tests.conftest import LoggedUser
from tests.pdf_factory import make_pdf

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]

ARTICLE = make_pdf(
    [
        ["Estudo ficticio para testes", "Resultados da cirurgia precoce."],
        ["O desfecho cogni-", "tivo foi medido aos 5 anos.", "Tabela 2: media e DP por grupo."],
    ]
)
SCANNED = make_pdf([[]])


async def _setup(client: AsyncClient, user: LoggedUser) -> tuple[str, str]:
    pid = (await client.post("/api/v1/projects", json={"title": "P"}, headers=user.headers)).json()[
        "id"
    ]
    study = (
        await client.post(
            f"/api/v1/projects/{pid}/studies",
            json={"label": "Exemplo 2020", "design": "other", "reference": {"title": "Artigo"}},
            headers=user.headers,
        )
    ).json()
    return pid, study["reports"][0]["id"]


async def _upload(
    client: AsyncClient, user: LoggedUser, pid: str, content: bytes
) -> tuple[str, dict[str, Any]]:
    base = f"/api/v1/projects/{pid}/uploads"
    upload = (
        await client.post(
            base, json={"filename": "artigo.pdf", "size_bytes": len(content)}, headers=user.headers
        )
    ).json()
    urls = (
        await client.post(
            f"{base}/{upload['id']}/parts", json={"part_numbers": [1]}, headers=user.headers
        )
    ).json()
    async with httpx.AsyncClient() as raw:
        await raw.put(urls[0]["url"], content=content)
    job = (await client.post(f"{base}/{upload['id']}/complete", headers=user.headers)).json()
    job = (
        await client.get(f"/api/v1/projects/{pid}/jobs/{job['id']}", headers=user.headers)
    ).json()
    return upload["id"], job


def test_search_normalization_joins_hyphenated_words_and_ignores_accents() -> None:
    assert normalize_for_search("O desfecho cogni-\ntivo") == "o desfecho cognitivo"
    assert normalize_for_search("CIRÚRGIA  Precoce") == "cirurgia precoce"


async def test_upload_extracts_text_per_page(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    pid, _ = await _setup(client, ana)
    _, job = await _upload(client, ana, pid, ARTICLE)
    assert job["status"] == "succeeded", job
    assert job["result"]["page_count"] == 2
    assert job["result"]["text_status"] == "ready"
    pages = (await session.scalars(select(PdfPageText).order_by(PdfPageText.page))).all()
    assert [p.page for p in pages] == [1, 2]
    assert "cirurgia precoce" in pages[0].content


async def test_same_pdf_text_is_extracted_once(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    pid, _ = await _setup(client, ana)
    await _upload(client, ana, pid, ARTICLE)
    _, second = await _upload(client, ana, pid, ARTICLE)
    assert second["result"]["deduplicated"] is True
    assert second["result"]["text_status"] == "ready"
    assert await session.scalar(select(func.count()).select_from(PdfPageText)) == 2


async def test_scanned_pdf_is_marked_without_text(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid, _ = await _setup(client, ana)
    _, job = await _upload(client, ana, pid, SCANNED)
    assert job["result"]["text_status"] == "no_text"
    assert job["result"]["page_count"] == 1


async def test_attach_view_search_and_detach(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid, report_id = await _setup(client, ana)
    upload_id, _ = await _upload(client, ana, pid, ARTICLE)
    r = await client.post(
        f"/api/v1/projects/{pid}/reports/{report_id}/pdfs",
        json={"upload_id": upload_id},
        headers=ana.headers,
    )
    assert r.status_code == 201
    pdf = r.json()
    assert pdf["page_count"] == 2
    assert pdf["original_filename"] == "artigo.pdf"

    listed = (
        await client.get(f"/api/v1/projects/{pid}/reports/{report_id}/pdfs", headers=ana.headers)
    ).json()
    assert [p["id"] for p in listed] == [pdf["id"]]

    view = (
        await client.get(f"/api/v1/projects/{pid}/pdfs/{pdf['id']}", headers=ana.headers)
    ).json()
    async with httpx.AsyncClient() as raw:
        body = (await raw.get(view["url"])).content
    assert body == ARTICLE

    hits = (
        await client.get(
            f"/api/v1/projects/{pid}/pdfs/{pdf['id']}/search",
            params={"q": "Cognitivo"},
            headers=ana.headers,
        )
    ).json()
    assert [h["page"] for h in hits] == [2]
    assert "cognitivo" in hits[0]["snippet"]
    accents = (
        await client.get(
            f"/api/v1/projects/{pid}/pdfs/{pdf['id']}/search",
            params={"q": "CIRÚRGIA"},
            headers=ana.headers,
        )
    ).json()
    assert [h["page"] for h in accents] == [1]

    assert (
        await client.delete(f"/api/v1/projects/{pid}/pdfs/{pdf['id']}", headers=ana.headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/projects/{pid}/reports/{report_id}/pdfs", headers=ana.headers)
    ).json() == []


async def test_only_finished_uploads_of_the_same_project_can_be_attached(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid, report_id = await _setup(client, ana)
    pending = (
        await client.post(
            f"/api/v1/projects/{pid}/uploads",
            json={"filename": "a.pdf", "size_bytes": 10},
            headers=ana.headers,
        )
    ).json()
    r = await client.post(
        f"/api/v1/projects/{pid}/reports/{report_id}/pdfs",
        json={"upload_id": pending["id"]},
        headers=ana.headers,
    )
    assert r.json()["code"] == "pdf.upload_not_ready"

    other_pid, _ = await _setup(client, ana)
    foreign_upload, _ = await _upload(client, ana, other_pid, ARTICLE)
    r = await client.post(
        f"/api/v1/projects/{pid}/reports/{report_id}/pdfs",
        json={"upload_id": foreign_upload},
        headers=ana.headers,
    )
    assert r.status_code == 404


async def _pdf(client: AsyncClient, user: LoggedUser) -> tuple[str, str]:
    pid, report_id = await _setup(client, user)
    upload_id, _ = await _upload(client, user, pid, ARTICLE)
    pdf = (
        await client.post(
            f"/api/v1/projects/{pid}/reports/{report_id}/pdfs",
            json={"upload_id": upload_id},
            headers=user.headers,
        )
    ).json()
    return pid, pdf["id"]


async def _join(
    client: AsyncClient, admin: LoggedUser, guest: LoggedUser, pid: str, roles: list[str]
) -> None:
    r = await client.post(
        f"/api/v1/projects/{pid}/invitations", json={"roles": roles}, headers=admin.headers
    )
    await client.post(
        f"/api/v1/invitations/{r.json()['link'].split('token=')[1]}/accept", headers=guest.headers
    )


async def test_annotations_belong_to_their_author(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    bia = await make_user()
    reader = await make_user()
    pid, pdf_id = await _pdf(client, ana)
    await _join(client, ana, bia, pid, ["extractor"])
    await _join(client, ana, reader, pid, ["reader"])
    base = f"/api/v1/projects/{pid}"

    r = await client.post(
        f"{base}/pdfs/{pdf_id}/annotations",
        json={
            "page": 2,
            "quote": "Tabela 2: media e DP por grupo.",
            "rects": [{"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.03}],
            "note": "Fonte do DP",
        },
        headers=bia.headers,
    )
    assert r.status_code == 201
    note = r.json()
    assert note["user_id"] == bia.id

    r = await client.post(
        f"{base}/pdfs/{pdf_id}/annotations", json={"page": 3, "quote": "x"}, headers=bia.headers
    )
    assert r.status_code == 422  # the PDF has 2 pages
    r = await client.post(
        f"{base}/pdfs/{pdf_id}/annotations", json={"page": 1, "quote": "x"}, headers=reader.headers
    )
    assert r.status_code == 403

    listed = (await client.get(f"{base}/pdfs/{pdf_id}/annotations", headers=reader.headers)).json()
    assert [a["quote"] for a in listed] == ["Tabela 2: media e DP por grupo."]

    r = await client.patch(
        f"{base}/annotations/{note['id']}", json={"version": 1, "note": "x"}, headers=reader.headers
    )
    assert r.status_code == 403
    other_extractor = await make_user()
    await _join(client, ana, other_extractor, pid, ["extractor"])
    r = await client.patch(
        f"{base}/annotations/{note['id']}",
        json={"version": 1, "note": "x"},
        headers=other_extractor.headers,
    )
    assert r.status_code == 403
    r = await client.patch(
        f"{base}/annotations/{note['id']}",
        json={"version": 1, "color": "green"},
        headers=bia.headers,
    )
    assert r.json()["color"] == "green"
    assert (
        await client.delete(f"{base}/annotations/{note['id']}", headers=ana.headers)
    ).status_code == 204
    assert (await client.get(f"{base}/pdfs/{pdf_id}/annotations", headers=ana.headers)).json() == []
