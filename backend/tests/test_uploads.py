"""Resumable uploads straight to storage (docs/arquivos.md 10.7; Etapa 0 exit criterion)."""

import hashlib
import json
import random
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.integrations.storage import Storage
from app.modules.uploads.models import StoredFile, UploadSession
from tests.conftest import LoggedUser

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]
MB = 1024 * 1024


def pdf_parts(size: int, part_size: int, seed: int = 1) -> Iterator[bytes]:
    """Deterministic synthetic PDF, produced part by part (never whole in memory)."""
    rng = random.Random(seed)  # noqa: S311 - test data, not security
    sent = 0
    first = True
    while sent < size:
        n = min(part_size, size - sent)
        chunk = rng.randbytes(n)
        if first:
            header = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            chunk = header + chunk[len(header) :]
            first = False
        sent += n
        yield chunk


async def _project(client: AsyncClient, user: LoggedUser) -> str:
    r = await client.post("/api/v1/projects", json={"title": "PDFs"}, headers=user.headers)
    return str(r.json()["id"])


async def _start(
    client: AsyncClient, user: LoggedUser, project_id: str, size: int, name: str = "artigo.pdf"
) -> dict[str, Any]:
    r = await client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={"filename": name, "size_bytes": size},
        headers=user.headers,
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _put_parts(
    client: AsyncClient,
    user: LoggedUser,
    project_id: str,
    upload: dict[str, Any],
    parts: dict[int, bytes],
) -> None:
    r = await client.post(
        f"/api/v1/projects/{project_id}/uploads/{upload['id']}/parts",
        json={"part_numbers": sorted(parts)},
        headers=user.headers,
    )
    assert r.status_code == 200, r.text
    async with httpx.AsyncClient(timeout=60) as raw:
        for item in r.json():
            put = await raw.put(item["url"], content=parts[item["part_number"]])
            assert put.status_code == 200, put.text


async def _upload_whole(
    client: AsyncClient, user: LoggedUser, project_id: str, size: int, seed: int = 1
) -> tuple[dict[str, Any], dict[str, Any], str]:
    upload = await _start(client, user, project_id, size)
    digest = hashlib.sha256()
    for number, chunk in enumerate(pdf_parts(size, upload["part_size"], seed), start=1):
        digest.update(chunk)
        await _put_parts(client, user, project_id, upload, {number: chunk})
    r = await client.post(
        f"/api/v1/projects/{project_id}/uploads/{upload['id']}/complete", headers=user.headers
    )
    assert r.status_code == 202, r.text
    return upload, r.json(), digest.hexdigest()


async def _job(
    client: AsyncClient, user: LoggedUser, project_id: str, job_id: str
) -> dict[str, Any]:
    r = await client.get(f"/api/v1/projects/{project_id}/jobs/{job_id}", headers=user.headers)
    return dict(r.json())


async def test_small_pdf_upload_process_and_download(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    upload, job, sha = await _upload_whole(client, ana, pid, 7 * MB)
    assert upload["part_count"] == 2

    done = await _job(client, ana, pid, job["id"])
    assert done["status"] == "succeeded"
    assert done["progress"] == 100
    assert done["result"]["sha256"] == sha
    assert done["result"]["deduplicated"] is False

    state = (
        await client.get(f"/api/v1/projects/{pid}/uploads/{upload['id']}", headers=ana.headers)
    ).json()
    assert state["status"] == "done"

    r = await client.get(
        f"/api/v1/projects/{pid}/uploads/{upload['id']}/download-url", headers=ana.headers
    )
    async with httpx.AsyncClient(timeout=60) as raw:
        downloaded = await raw.get(r.json()["url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/pdf"
    assert hashlib.sha256(downloaded.content).hexdigest() == sha


async def test_100mb_pdf_resumes_after_connection_drop(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, storage: Storage
) -> None:
    """Exit criterion of Etapa 0: a 100 MB upload resumes after a drop."""
    ana = await make_user()
    pid = await _project(client, ana)
    size = 100 * MB
    upload = await _start(client, ana, pid, size, "grande.pdf")
    part_size = upload["part_size"]
    digest = hashlib.sha256()
    chunks = list(enumerate(pdf_parts(size, part_size, seed=7), start=1))
    for _, chunk in chunks:
        digest.update(chunk)

    first_half = upload["part_count"] // 2
    for number, chunk in chunks[:first_half]:
        await _put_parts(client, ana, pid, upload, {number: chunk})
    # The connection drops here: the browser loses every URL it had.

    state = (
        await client.get(f"/api/v1/projects/{pid}/uploads/{upload['id']}", headers=ana.headers)
    ).json()
    assert state["uploaded_parts"] == list(range(1, first_half + 1))
    missing = [n for n in range(1, upload["part_count"] + 1) if n not in state["uploaded_parts"]]

    incomplete = await client.post(
        f"/api/v1/projects/{pid}/uploads/{upload['id']}/complete", headers=ana.headers
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["code"] == "upload.incomplete"

    for number, chunk in chunks:
        if number in missing:
            await _put_parts(client, ana, pid, upload, {number: chunk})
    del chunks

    r = await client.post(
        f"/api/v1/projects/{pid}/uploads/{upload['id']}/complete", headers=ana.headers
    )
    job = await _job(client, ana, pid, r.json()["id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["sha256"] == digest.hexdigest()
    assert job["result"]["size_bytes"] == size

    stored = (await session.scalars(select(StoredFile))).one()
    assert stored.size_bytes == size
    assert await storage.size(stored.storage_key) == size
    row = (await session.scalars(select(UploadSession))).one()
    assert not await storage.exists(row.storage_key)  # temporary object removed


async def test_same_pdf_is_stored_once(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    _, first, _ = await _upload_whole(client, ana, pid, 6 * MB, seed=3)
    _, second, _ = await _upload_whole(client, ana, pid, 6 * MB, seed=3)
    second_job = await _job(client, ana, pid, second["id"])
    assert second_job["result"]["deduplicated"] is True
    assert (
        second_job["result"]["stored_file_id"]
        == (await _job(client, ana, pid, first["id"]))["result"]["stored_file_id"]
    )

    stored = (await session.scalars(select(StoredFile))).one()
    assert stored.ref_count == 2
    usage = (await client.get("/api/v1/me/usage", headers=ana.headers)).json()
    assert usage["storage_mb"]["used"] == 6.0


async def test_file_that_is_not_really_a_pdf_is_rejected(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, storage: Storage
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    content = b"PK\x03\x04" + b"\x00" * 1000  # a ZIP renamed to .pdf
    upload = await _start(client, ana, pid, len(content), "falso.pdf")
    await _put_parts(client, ana, pid, upload, {1: content})
    r = await client.post(
        f"/api/v1/projects/{pid}/uploads/{upload['id']}/complete", headers=ana.headers
    )
    job = await _job(client, ana, pid, r.json()["id"])
    assert job["status"] == "failed"
    assert job["error_code"] == "upload.not_pdf"
    row = (await session.scalars(select(UploadSession))).one()
    assert row.status == "failed"
    assert not await storage.exists(row.storage_key)
    assert (await session.scalars(select(StoredFile))).all() == []


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"filename": "a.pdf", "size_bytes": 101 * MB}, 413, "upload.too_large"),
        ({"filename": "a.docx", "size_bytes": 10}, 415, "upload.not_pdf"),
        (
            {"filename": "a.pdf", "size_bytes": 10, "content_type": "text/html"},
            415,
            "upload.not_pdf",
        ),
    ],
)
async def test_invalid_uploads_are_refused_up_front(
    client: AsyncClient, make_user: MakeUser, body: dict[str, Any], status: int, code: str
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    r = await client.post(f"/api/v1/projects/{pid}/uploads", json=body, headers=ana.headers)
    assert r.status_code == status
    assert r.json()["code"] == code


async def test_storage_quota_counts_open_uploads(
    client: AsyncClient, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "quota_storage_mb_per_user", 50)
    ana = await make_user()
    pid = await _project(client, ana)
    await _start(client, ana, pid, 40 * MB)
    r = await client.post(
        f"/api/v1/projects/{pid}/uploads",
        json={"filename": "b.pdf", "size_bytes": 20 * MB},
        headers=ana.headers,
    )
    assert r.status_code == 403
    assert r.json()["code"] == "quota.storage_exceeded"


async def test_cancel_frees_the_reservation(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    upload = await _start(client, ana, pid, 10 * MB)
    base = f"/api/v1/projects/{pid}/uploads/{upload['id']}"
    assert (await client.delete(base, headers=ana.headers)).status_code == 204
    assert (await client.get("/api/v1/me/usage", headers=ana.headers)).json()["storage_mb"][
        "used"
    ] == 0
    r = await client.post(f"{base}/parts", json={"part_numbers": [1]}, headers=ana.headers)
    assert r.status_code == 409


async def test_part_numbers_are_validated(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    upload = await _start(client, ana, pid, 6 * MB)
    r = await client.post(
        f"/api/v1/projects/{pid}/uploads/{upload['id']}/parts",
        json={"part_numbers": [3]},
        headers=ana.headers,
    )
    assert r.status_code == 422


async def test_readers_cannot_upload_and_other_projects_cannot_see(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    reader = await make_user()
    pid = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{pid}/invitations", json={"roles": ["reader"]}, headers=ana.headers
    )
    token = r.json()["link"].split("token=")[1]
    await client.post(f"/api/v1/invitations/{token}/accept", headers=reader.headers)
    r = await client.post(
        f"/api/v1/projects/{pid}/uploads",
        json={"filename": "a.pdf", "size_bytes": 10},
        headers=reader.headers,
    )
    assert r.status_code == 403

    upload = await _start(client, ana, pid, 10)
    bia = await make_user()
    other = await _project(client, bia)
    r = await client.get(f"/api/v1/projects/{other}/uploads/{upload['id']}", headers=bia.headers)
    assert r.status_code == 404


async def test_progress_stream_ends_with_final_state(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    _, job, _ = await _upload_whole(client, ana, pid, 6 * MB)
    events: list[dict[str, Any]] = []
    async with client.stream(
        "GET", f"/api/v1/projects/{pid}/jobs/{job['id']}/events", headers=ana.headers
    ) as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        async for line in stream.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    assert events[-1]["status"] == "succeeded"
    assert events[-1]["progress"] == 100


async def test_stale_uploads_expire(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, storage: Storage
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.modules.uploads.service import expire_stale_uploads

    ana = await make_user()
    pid = await _project(client, ana)
    upload = await _start(client, ana, pid, 10)
    row = await session.get(UploadSession, upload["id"])
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.commit()
    assert await expire_stale_uploads(session, storage) == 1
    await session.refresh(row)
    assert row.status == "expired"
