"""OCR of scanned PDFs (stage 8 step 3). A FICTITIOUS text PDF is turned into an image-only
PDF with Ghostscript (as a scan would be), then the worker's OCR must read it back."""

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.modules.pdfs.text import TextStatus, ocr_available, ocr_pages, read_pages
from tests.pdf_factory import make_pdf

pytestmark = pytest.mark.skipif(
    shutil.which("ocrmypdf") is None or shutil.which("gs") is None,
    reason="ocrmypdf/ghostscript not installed in this image",
)


def _scanned(tmp: Path) -> Path:
    text = tmp / "text.pdf"
    text.write_bytes(
        make_pdf([["Estudo ficticio de cirurgia precoce", "Cegamento dos avaliadores"]])
    )
    image = tmp / "scan.pdf"
    subprocess.run(  # noqa: S603 - fixed arguments, test-only Ghostscript call
        [
            shutil.which("gs") or "gs",
            "-q",
            "-dNOPAUSE",
            "-dBATCH",
            "-sDEVICE=pdfimage24",
            "-r200",
            f"-sOutputFile={image}",
            str(text),
        ],
        check=True,
    )
    return image


def test_a_scan_has_no_text_until_ocr_reads_it() -> None:
    with tempfile.TemporaryDirectory() as folder:
        scan = _scanned(Path(folder))
        assert not any(read_pages(str(scan)))  # like a scanned article
        pages = asyncio.run(ocr_pages(str(scan)))
        assert pages is not None
        text = " ".join(pages).lower()
        assert "cirurgia" in text and "avaliadores" in text
        assert TextStatus.OCR == "ocr"


def test_ocr_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ocr_enabled", False)
    assert ocr_available() is False
    with tempfile.TemporaryDirectory() as folder:
        assert asyncio.run(ocr_pages(str(_scanned(Path(folder))))) is None
