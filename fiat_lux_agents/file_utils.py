"""
Plain-text extraction from uploaded file bytes.

Supported formats:
  .txt / .md / .csv  — UTF-8 decode
  .pdf               — pypdf; falls back to Claude vision via LLMBase for scanned PDFs
  .docx              — python-docx paragraphs + tables
  .html / .htm       — html.parser tag stripping
"""

from __future__ import annotations

import io
import logging
from html.parser import HTMLParser
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_CHARS = 200_000

_PLAIN_TEXT_SUFFIXES = {".txt", ".md", ".csv"}
_HTML_SUFFIXES = {".html", ".htm"}


class _TagStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _extract_pdf(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(p for p in pages if p.strip())
        if text.strip():
            return text
    except ImportError:
        pass

    # Scanned/image-only PDF: send first page to Claude vision
    return _extract_pdf_via_vision(file_bytes)


def _extract_pdf_via_vision(file_bytes: bytes) -> str:
    import base64

    from .base import LLMBase

    b64 = base64.standard_b64encode(file_bytes).decode()
    bot = LLMBase()
    response = bot.client.messages.create(
        model=bot.model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": "Extract all readable text from this document. Output only the text, no commentary."},
                ],
            }
        ],
    )
    return response.content[0].text


def _extract_docx(file_bytes: bytes) -> str:
    try:
        from docx import Document
    except ImportError as e:
        raise ImportError("python-docx is required for .docx files") from e

    doc = Document(io.BytesIO(file_bytes))
    parts: list[str] = []

    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))

    return "\n".join(parts)


def _extract_html(file_bytes: bytes) -> str:
    html = file_bytes.decode("utf-8", errors="replace")
    parser = _TagStripper()
    parser.feed(html)
    return parser.get_text()


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Return plain text extracted from *file_bytes*.

    Args:
        file_bytes: Raw bytes of the uploaded file.
        filename:   Original filename; used only to determine format.

    Returns:
        Extracted plain text, truncated to MAX_CHARS.

    Raises:
        ValueError:  Unsupported file extension.
        ImportError: Required optional library missing.
    """
    suffix = Path(filename).suffix.lower()

    if suffix in _PLAIN_TEXT_SUFFIXES:
        text = file_bytes.decode("utf-8", errors="replace")
    elif suffix == ".pdf":
        text = _extract_pdf(file_bytes)
    elif suffix == ".docx":
        text = _extract_docx(file_bytes)
    elif suffix in _HTML_SUFFIXES:
        text = _extract_html(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {suffix!r}")

    return text[:MAX_CHARS]
