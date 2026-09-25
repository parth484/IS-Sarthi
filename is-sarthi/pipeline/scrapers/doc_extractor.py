"""
Unified document extraction utility for IS Sarthi.
Supports PDF (.pdf), Microsoft Word (.docx), and plain text (.txt).
Enforces size limits and provides clean, descriptive error handling
for empty, corrupted, password-protected, or unreadable documents.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum allowed file size for specification documents: 20 MB
MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024


def clean_extracted_text(text: str) -> str:
    """Normalize whitespace and strip non-printable artifacts."""
    if not text:
        return ""
    # Strip null bytes and control chars except newlines and tabs
    cleaned = "".join(ch for ch in text if ch in ("\n", "\r", "\t") or ch.isprintable())
    # Normalize multiple blank lines to double newlines
    lines = [line.strip() for line in cleaned.splitlines()]
    return "\n".join(lines).strip()


def extract_txt(content: bytes) -> str:
    """Extract plain text from uploaded TXT document."""
    if not content or len(content) == 0:
        raise ValueError("The uploaded text file is empty (0 bytes).")

    decoded: Optional[str] = None
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1", "cp1252"):
        try:
            decoded = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if decoded is None:
        raise ValueError("Unable to decode text document. Unsupported text encoding.")

    cleaned = clean_extracted_text(decoded)
    if not cleaned:
        raise ValueError("The uploaded text file contains no readable content.")
    return cleaned


def extract_docx(content: bytes) -> str:
    """
    Extract readable text from uploaded Microsoft Word (.docx) document.
    Detects password-protected Office packages and corrupted zip archives.
    """
    if not content or len(content) == 0:
        raise ValueError("The uploaded DOCX file is empty (0 bytes).")

    # Detect OLE2 header used by password-encrypted Office documents
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise ValueError("This DOCX document is password-protected. Please provide an unencrypted document.")

    try:
        import docx
        import zipfile
    except ImportError:
        raise RuntimeError("python-docx is not installed in the Python environment.")

    try:
        doc = docx.Document(io.BytesIO(content))
        paragraphs: list[str] = []

        # Extract text from paragraphs
        for p in doc.paragraphs:
            t = p.text.strip()
            if t:
                paragraphs.append(t)

        # Extract text from tables (often used for technical parameter specifications)
        for table in doc.tables:
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                # remove duplicate cell texts caused by merged cells
                deduped = []
                for cell_txt in row_cells:
                    if not deduped or deduped[-1] != cell_txt:
                        deduped.append(cell_txt)
                if deduped:
                    paragraphs.append(" | ".join(deduped))

        full_text = "\n\n".join(paragraphs).strip()
        cleaned = clean_extracted_text(full_text)
        if not cleaned:
            raise ValueError("No readable text found in this DOCX document. The file may be empty or contain only images.")
        return cleaned

    except zipfile.BadZipFile:
        raise ValueError("Corrupted or invalid DOCX file. The archive could not be unpacked.")
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        logger.error("DOCX extraction error: %s", exc)
        raise ValueError(f"Could not read DOCX document: {exc}")


def extract_pdf(content: bytes) -> str:
    """
    Extract readable text from uploaded PDF document.
    Reuses pipeline.scrapers.pdf_extractor.extract_text_from_pdf.
    """
    from pipeline.scrapers.pdf_extractor import extract_text_from_pdf
    return extract_text_from_pdf(content)


def extract_document_text(content: bytes, filename: str) -> str:
    """
    Unified entry point for multi-format document text extraction.
    Supports .pdf, .docx, and .txt formats.
    """
    if not filename:
        raise ValueError("Filename is required for document format detection.")

    if not content or len(content) == 0:
        raise ValueError(f"The uploaded file '{filename}' is empty (0 bytes).")

    if len(content) > MAX_DOCUMENT_SIZE_BYTES:
        max_mb = MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)
        actual_mb = round(len(content) / (1024 * 1024), 2)
        raise ValueError(f"File size ({actual_mb} MB) exceeds maximum limit of {max_mb} MB.")

    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        return extract_pdf(content)
    elif lower_name.endswith(".docx"):
        return extract_docx(content)
    elif lower_name.endswith(".txt"):
        return extract_txt(content)
    else:
        raise ValueError(
            f"Unsupported document format for '{filename}'. Supported formats: .pdf, .docx, .txt."
        )
