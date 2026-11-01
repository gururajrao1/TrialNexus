"""PDF protocol ingestion: extract text from uploaded PDFs for audit.

Accepts raw PDF bytes (transported as base64 JSON, no multipart dep),
extracts text with pypdf, and caps pages/chars so a scanned brochure
can't blow up the audit path. Deterministic, offline, stdlib + pypdf.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PAGES = 30
MAX_CHARS = 120_000


def extract_pdf_text(data: bytes) -> dict[str, Any]:
    """Extract audit-ready text from PDF bytes.

    Raises ValueError with a user-facing message when the bytes are
    not a readable PDF or contain no extractable text (e.g. scanned
    images without an OCR layer).
    """
    if not data or not data.lstrip().startswith(b"%PDF"):
        raise ValueError("not a PDF file (missing %PDF header)")
    try:
        reader = PdfReader(BytesIO(data))
        pages = len(reader.pages)
    except (PdfReadError, ValueError) as exc:
        raise ValueError(f"unreadable PDF: {exc}") from exc
    if pages == 0:
        raise ValueError("PDF has no pages")
    chunks: list[str] = []
    total = 0
    truncated = pages > MAX_PAGES
    for page in reader.pages[:MAX_PAGES]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        budget = MAX_CHARS - total
        if budget <= 0:
            truncated = True
            break
        if len(text) > budget:
            text = text[:budget]
            truncated = True
        chunks.append(text)
        total += len(text)
    joined = "\n".join(t for t in chunks if t.strip())
    if not joined.strip():
        raise ValueError("no extractable text (scanned image without OCR?)")
    return {
        "pages": pages,
        "pages_read": min(pages, MAX_PAGES),
        "chars": len(joined),
        "truncated": truncated,
        "text": joined,
    }
