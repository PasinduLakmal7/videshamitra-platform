"""Upload validation: MIME, extension, size, page count."""

from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfWriter

from app.core.exceptions import PayloadTooLarge, UnprocessableEntity
from app.utils.file_processing import validate_audio, validate_document

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_valid_pdf() -> None:
    result = validate_document(_pdf(2), "offer.pdf", "application/pdf")
    assert result.mime_type == "application/pdf"
    assert result.page_count == 2
    assert len(result.sha256) == 64


def test_valid_png() -> None:
    result = validate_document(PNG_1X1, "screenshot.png", "image/png")
    assert result.mime_type == "image/png"
    assert result.page_count == 1


def test_spoofed_content_rejected() -> None:
    with pytest.raises(UnprocessableEntity) as exc:
        validate_document(b"MZ\x90\x00 definitely not a pdf", "offer.pdf", "application/pdf")
    assert exc.value.code == "unsupported_file_type"


def test_extension_mismatch_rejected() -> None:
    with pytest.raises(UnprocessableEntity) as exc:
        validate_document(_pdf(), "offer.exe", "application/pdf")
    assert exc.value.code == "extension_mismatch"


def test_declared_mime_mismatch_rejected() -> None:
    with pytest.raises(UnprocessableEntity) as exc:
        validate_document(_pdf(), "offer.pdf", "image/png")
    assert exc.value.code == "mime_mismatch"


def test_empty_file_rejected() -> None:
    with pytest.raises(UnprocessableEntity) as exc:
        validate_document(b"", "empty.pdf", "application/pdf")
    assert exc.value.code == "empty_file"


def test_oversized_file_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "MAX_UPLOAD_MB", 0)
    with pytest.raises(PayloadTooLarge):
        validate_document(_pdf(), "offer.pdf", "application/pdf")


def test_missing_extension_rejected() -> None:
    with pytest.raises(UnprocessableEntity):
        validate_document(_pdf(), "offer", "application/pdf")


def test_audio_validation() -> None:
    content, mime, filename = validate_audio(b"RIFF....WAVEfmt ", "voice.wav", "audio/wav")
    assert mime.startswith("audio/")
    assert filename == "voice.wav"


def test_audio_rejects_document() -> None:
    with pytest.raises(UnprocessableEntity):
        validate_audio(_pdf(), "voice.wav", "audio/wav")
