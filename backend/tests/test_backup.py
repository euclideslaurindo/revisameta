"""Project backup, re-import and retention (stage 6 step 6). Data are FICTITIOUS."""

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import httpx
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.storage import Storage
from app.modules.audit.models import AuditLog
from app.modules.backup.service import project_tables
from app.modules.projects.retention import archive_inactive
from app.modules.uploads.models import StoredFile
from tests.test_consensus import MakeUser, _join
from tests.test_pdfs import _pdf


async def _counts(session: AsyncSession, pid: str) -> dict[str, int]:
    out = {}
    for t in project_tables():
        if t.name == "audit_log":
            continue  # the import itself writes no audit rows, but the source keeps growing
        out[t.name] = await session.scalar(
            select(func.count()).select_from(t).where(t.c.project_id == uuid.UUID(pid))
        )
    return out


async def _zip(client: AsyncClient, user: object, pid: str) -> bytes:
    headers = user.headers  # type: ignore[attr-defined]
    r = await client.post(f"/api/v1/projects/{pid}/backups", headers=headers)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    job = (await client.get(f"/api/v1/projects/{pid}/jobs/{job_id}", headers=headers)).json()
    assert job["status"] == "succeeded", job
    link = await client.get(f"/api/v1/projects/{pid}/backups/{job_id}/download", headers=headers)
    assert link.status_code == 200 and link.json()["name"].endswith(".zip")
    async with httpx.AsyncClient() as raw:
        return (await raw.get(link.json()["url"])).content


async def test_backup_and_reimport_without_loss(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, storage: Storage
) -> None:
    ana = await make_user("Ana")
    pid, pdf_id = await _pdf(client, ana)
    bia = await make_user("Bia")
    await _join(client, ana, bia, pid, ["reviewer"])
    base = f"/api/v1/projects/{pid}"
    study = (await client.get(f"{base}/studies", headers=ana.headers)).json()
    study = study["items"][0] if isinstance(study, dict) else study[0]
    note = {"entity": "study", "entity_id": study["id"], "text": "FICTITIOUS", "mentions": [bia.id]}
    await client.post(f"{base}/comments", headers=ana.headers, json=note)
    # A soft-deleted comment must survive too.
    gone = (await client.post(f"{base}/comments", headers=ana.headers, json=note)).json()
    await client.delete(f"{base}/comments/{gone['id']}", headers=ana.headers)

    # Only admins back up.
    assert (await client.post(f"{base}/backups", headers=bia.headers)).status_code == 403
    content = await _zip(client, ana, pid)
    zf = zipfile.ZipFile(io.BytesIO(content))
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["files"] == 1 and manifest["counts"]["comments"] == 2
    assert any(n.startswith("files/") for n in zf.namelist())
    assert b"@" not in zf.read("users.jsonl")  # names only, never e-mails

    files_before = await session.scalar(select(func.count()).select_from(StoredFile))
    caio = await make_user("Caio")  # not a member: imports into a new project
    r = await client.post(
        "/api/v1/projects/import",
        headers=caio.headers,
        files={"file": ("backup.zip", content, "application/zip")},
    )
    assert r.status_code == 202, r.text
    new_pid, job_id = r.json()["project_id"], r.json()["job_id"]
    job = (
        await client.get(f"/api/v1/projects/{new_pid}/jobs/{job_id}", headers=caio.headers)
    ).json()
    assert job["status"] == "succeeded", job
    assert job["result"]["absent_users"] == []

    source, copy = await _counts(session, pid), await _counts(session, new_pid)
    source["project_members"] += 1  # Caio became admin of the copy
    assert copy == source
    # Same people keep their records; ids are new; the PDF is stored once.
    new_base = f"/api/v1/projects/{new_pid}"
    copied = (await client.get(f"{new_base}/studies", headers=caio.headers)).json()
    copied = copied["items"][0] if isinstance(copied, dict) else copied[0]
    assert copied["id"] != study["id"] and copied["label"] == study["label"]
    comments = (
        await client.get(
            f"{new_base}/comments",
            headers=caio.headers,
            params={"entity": "study", "entity_id": copied["id"]},
        )
    ).json()
    assert len(comments) == 1 and comments[0]["author_name"] == "Ana"
    assert comments[0]["mentions"][0]["name"] == "Bia"
    assert await session.scalar(select(func.count()).select_from(StoredFile)) == files_before
    stored = (await session.scalars(select(StoredFile))).all()
    assert any(f.ref_count >= 2 for f in stored)
    # Ana is a member of the copy too, with her roles; the original is untouched.
    assert (await client.get(new_base, headers=ana.headers)).status_code == 200
    assert (await client.get(f"{base}/pdfs/{pdf_id}", headers=ana.headers)).status_code == 200


async def test_import_rejects_other_files_and_versions(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    url = "/api/v1/projects/import"
    r = await client.post(
        url, headers=ana.headers, files={"file": ("x.zip", b"nada", "application/zip")}
    )
    assert r.status_code == 422 and r.json()["code"] == "backup.invalid"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({"format": "revisameta-project-backup", "version": 1, "revision": "old"}),
        )
    r = await client.post(
        url, headers=ana.headers, files={"file": ("b.zip", buf.getvalue(), "application/zip")}
    )
    assert r.status_code == 422 and r.json()["code"] == "backup.other_version"


async def test_inactive_projects_are_archived_with_a_notice_and_can_come_back(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    pid = (
        await client.post("/api/v1/projects", json={"title": "Antigo"}, headers=ana.headers)
    ).json()["id"]
    later = datetime.now(UTC) + timedelta(days=366)
    await session.execute(
        update(AuditLog)
        .where(AuditLog.project_id == uuid.UUID(pid))
        .values(created_at=datetime.now(UTC) - timedelta(days=1))
    )
    await session.commit()
    assert await archive_inactive(session, now=later) >= 1
    project = (await client.get(f"/api/v1/projects/{pid}", headers=ana.headers)).json()
    assert project["archived_at"] is not None
    notices = (await client.get("/api/v1/notifications", headers=ana.headers)).json()
    assert any(n["kind"] == "archived" and n["project_id"] == pid for n in notices["items"])
    assert (
        await client.post(f"/api/v1/projects/{pid}/unarchive", headers=ana.headers)
    ).status_code == 204
    project = (await client.get(f"/api/v1/projects/{pid}", headers=ana.headers)).json()
    assert project["archived_at"] is None
    # A project with recent activity is left alone.
    await archive_inactive(session)
    assert (await client.get(f"/api/v1/projects/{pid}", headers=ana.headers)).json()[
        "archived_at"
    ] is None
