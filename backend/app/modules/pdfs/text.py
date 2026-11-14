"""Extracts the text of every page with pypdfium2 (ADR-012), in the worker.

The object is streamed from storage to a temporary file (never held whole in memory),
parsed in a thread, and one row per page is stored. PDFs without a text layer
(scanned) are marked `no_text`; OCR is a later stage.
"""

import asyncio
import logging
import os
import tempfile
import unicodedata
import uuid
from collections.abc import Awaitable, Callable

import pypdfium2 as pdfium
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.storage import Storage
from app.modules.uploads.models import PdfPageText, StoredFile

logger = logging.getLogger(__name__)

CHUNK = 8 * 1024 * 1024


class TextStatus:
    PENDING = "pending"
    READY = "ready"
    NO_TEXT = "no_text"
    FAILED = "failed"


# PDFium marks a hyphen that splits a word at the end of a line with U+FFFE (or \x02)
# and joins the two lines; removing the marker restores the whole word.
_LINE_HYPHENS = ("￾", "\x02")


def _clean(text: str) -> str:
    # pdfium returns \r\n and form feeds; NUL bytes are not allowed in Postgres text.
    for marker in _LINE_HYPHENS:
        text = text.replace(marker, "")
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()


def read_pages(path: str) -> list[str]:
    document = pdfium.PdfDocument(path)
    try:
        pages: list[str] = []
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            try:
                pages.append(_clean(textpage.get_text_range()))
            finally:
                textpage.close()
                page.close()
        return pages
    finally:
        document.close()


async def extract_text(
    maker: async_sessionmaker[AsyncSession],
    storage: Storage,
    stored_file_id: uuid.UUID,
    on_progress: Callable[[int], Awaitable[None]] | None = None,
) -> str:
    async with maker() as session:
        stored = await session.get(StoredFile, stored_file_id)
        if stored is None:
            return TextStatus.FAILED
        key = stored.storage_key

    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as handle:
            async for chunk in storage.iter_chunks(key, CHUNK):
                handle.write(chunk)
        try:
            pages = await asyncio.to_thread(read_pages, path)
            status = TextStatus.READY if any(pages) else TextStatus.NO_TEXT
        except pdfium.PdfiumError as exc:
            logger.warning("pdf_text_failed", extra={"extra_fields": {"error": str(exc)}})
            pages, status = [], TextStatus.FAILED
    finally:
        os.unlink(path)

    async with maker() as session:
        await session.execute(
            delete(PdfPageText).where(PdfPageText.stored_file_id == stored_file_id)
        )
        session.add_all(
            PdfPageText(stored_file_id=stored_file_id, page=number, content=content)
            for number, content in enumerate(pages, start=1)
        )
        stored = await session.get(StoredFile, stored_file_id)
        if stored is not None:
            stored.page_count = len(pages) or None
            stored.text_status = status
        await session.commit()
    if on_progress is not None:
        await on_progress(95)
    return status


def normalize_for_search(text: str) -> str:
    """Lower case, no accents, hyphenated line breaks joined, whitespace collapsed."""
    text = text.replace("-\n", "").replace("­", "")
    for marker in _LINE_HYPHENS:
        text = text.replace(marker, "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())
