"""Extracts the text of every page with pypdfium2 (ADR-012), in the worker.

The object is streamed from storage to a temporary file (never held whole in memory),
parsed in a thread, and one row per page is stored. PDFs without a text layer
(scanned) go through OCR (ocrmypdf + Tesseract, stage 8): the text of the OCR copy is
stored and the file is marked `ocr`, while the viewer keeps showing the original. When
OCR is off, missing or fails, the file stays `no_text`.
"""

import asyncio
import contextlib
import logging
import os
import shutil
import tempfile
import unicodedata
import uuid
from collections.abc import Awaitable, Callable

import pypdfium2 as pdfium
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.integrations.storage import Storage
from app.modules.uploads.models import PdfPageText, StoredFile

logger = logging.getLogger(__name__)

CHUNK = 8 * 1024 * 1024


class TextStatus:
    PENDING = "pending"
    READY = "ready"
    NO_TEXT = "no_text"
    OCR = "ocr"  # text recognised from page images; may contain reading errors
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


def ocr_available() -> bool:
    return get_settings().ocr_enabled and shutil.which("ocrmypdf") is not None


async def ocr_pages(path: str) -> list[str] | None:
    """Runs ocrmypdf on a copy and reads the text it added. None when off or failed."""
    if not ocr_available():
        return None
    settings = get_settings()
    out = f"{path}.ocr.pdf"
    try:
        process = await asyncio.create_subprocess_exec(
            "ocrmypdf",
            "--skip-text",
            "--quiet",
            "-l",
            settings.ocr_languages,
            path,
            out,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, err = await asyncio.wait_for(process.communicate(), settings.ocr_timeout_seconds)
        except TimeoutError:
            process.kill()
            logger.warning("pdf_ocr_timeout")
            return None
        if process.returncode != 0:
            logger.warning("pdf_ocr_failed", extra={"extra_fields": {"error": err.decode()[-500:]}})
            return None
        return await asyncio.to_thread(read_pages, out)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(out)


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
            if status == TextStatus.NO_TEXT:
                recognised = await ocr_pages(path)
                if recognised is not None and any(recognised):
                    pages, status = recognised, TextStatus.OCR
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
