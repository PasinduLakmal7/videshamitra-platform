"""Upload validation: extension + magic bytes + PDF page count."""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from dataclasses import dataclass

import filetype
from pypdf import PdfReader

from app.core.config import settings
from app.core.exceptions import PayloadTooLarge, UnprocessableEntity
from app.utils.hashing import sha256_bytes

logger = logging.getLogger(__name__)

ALLOWED_DOCUMENT_TYPES = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
}

ALLOWED_AUDIO_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
}


@dataclass(frozen=True)
class ValidatedDocument:
    content: bytes
    mime_type: str
    filename: str
    size_bytes: int
    page_count: int
    sha256: str


def _extension(filename: str) -> str:
    name = filename.rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def validate_document(
    content: bytes,
    filename: str,
    declared_mime: str | None,
) -> ValidatedDocument:
    if not content:
        raise UnprocessableEntity("File is empty", code="empty_file")
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLarge(
            f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit",
            code="file_too_large",
        )

    safe_name = _safe_filename(filename)
    extension = _extension(filename)
    kind = filetype.guess(content)
    detected = kind.mime if kind else None
    declared = (declared_mime or "").split(";")[0].strip().lower()

    if detected not in ALLOWED_DOCUMENT_TYPES:
        raise UnprocessableEntity(
            "Unsupported file type. Allowed: PDF, JPEG, PNG",
            code="unsupported_file_type",
            details={"detected": detected, "declared": declared},
        )
    if extension not in ALLOWED_DOCUMENT_TYPES[detected]:
        raise UnprocessableEntity(
            "File extension does not match file content",
            code="extension_mismatch",
        )
    if declared and declared != detected:
        raise UnprocessableEntity(
            "Declared content type does not match file content",
            code="mime_mismatch",
        )

    page_count = 1
    if detected == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise UnprocessableEntity("Encrypted PDFs are not supported", code="encrypted_pdf")
            page_count = len(reader.pages)
        except UnprocessableEntity:
            raise
        except Exception as exc:
            raise UnprocessableEntity("PDF could not be parsed", code="invalid_pdf") from exc
        if page_count == 0:
            raise UnprocessableEntity("PDF has no pages", code="empty_pdf")
        if page_count > settings.MAX_PDF_PAGES:
            raise UnprocessableEntity(
                f"PDF exceeds the {settings.MAX_PDF_PAGES}-page limit",
                code="too_many_pages",
                details={"page_count": page_count},
            )

    return ValidatedDocument(
        content=content,
        mime_type=detected,
        filename=safe_name,
        size_bytes=len(content),
        page_count=page_count,
        sha256=sha256_bytes(content),
    )


def validate_audio(
    content: bytes,
    filename: str,
    declared_mime: str | None,
) -> tuple[bytes, str, str]:
    if not content:
        raise UnprocessableEntity("Audio file is empty", code="empty_file")
    if len(content) > settings.max_audio_bytes:
        raise PayloadTooLarge(
            f"Audio exceeds the {settings.MAX_AUDIO_MB} MB limit",
            code="audio_too_large",
        )
    kind = filetype.guess(content)
    detected = kind.mime if kind else None
    declared = (declared_mime or "").split(";")[0].strip().lower()
    mime = detected or declared
    if mime not in ALLOWED_AUDIO_TYPES:
        raise UnprocessableEntity(
            "Unsupported audio type",
            code="unsupported_audio_type",
            details={"detected": detected, "declared": declared},
        )
    safe_name = _safe_filename(filename)
    return content, mime, safe_name


def _safe_filename(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base)
    base = base.strip("-._")
    return base[:120] or "document"


def sanitize_filename(filename: str) -> str:
    return _safe_filename(filename)
