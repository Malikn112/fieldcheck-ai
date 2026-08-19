"""
Storage service — safe handling of inspector-uploaded field images.

Security responsibilities (per spec):
  1. MIME-type validation restricted to JPEG/PNG, verified by *sniffing
     magic bytes* (not trusting the client-supplied Content-Type header).
  2. Maximum file size enforcement (default 15MB), checked while streaming
     to avoid buffering unbounded request bodies in memory.
  3. Safe filenames: server-generated UUIDv4 names, never the client's
     original filename, to eliminate path-traversal / injection risk.
  4. Basic image integrity validation via Pillow (rejects corrupt/non-image
     payloads that merely spoof the right magic bytes).
"""
from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings

try:
    import magic  # python-magic (libmagic binding)

    _HAS_MAGIC = True
except Exception:  # pragma: no cover - environment without libmagic
    _HAS_MAGIC = False


class UnsupportedFileTypeError(Exception):
    """Raised when the uploaded file is not an allowed image MIME type."""


class FileTooLargeError(Exception):
    """Raised when the uploaded file exceeds the configured size limit."""


class InvalidImageError(Exception):
    """Raised when the file cannot be decoded as a valid image."""


# Map sniffed MIME type -> safe file extension. Never derive the extension
# from the client-supplied filename.
_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


@dataclass
class StoredFile:
    stored_filename: str
    file_path: Path
    mime_type: str
    file_size_bytes: int
    sha256_hash: str


def _sniff_mime_type(data: bytes) -> str:
    """Detect the true MIME type from file content (magic bytes), not the
    client-supplied header, which is trivially spoofable."""
    if _HAS_MAGIC:
        try:
            detected = magic.from_buffer(data, mime=True)
            if detected:
                return detected
        except Exception:
            pass

    # Fallback: sniff via Pillow, which parses real image headers.
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "").upper()
            if fmt == "JPEG":
                return "image/jpeg"
            if fmt == "PNG":
                return "image/png"
            return f"image/{fmt.lower()}"
    except UnidentifiedImageError:
        return "application/octet-stream"


def _validate_is_real_image(data: bytes) -> None:
    """Fully decode the image to guard against polyglot / corrupt files
    that merely have a valid-looking header."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception as exc:
        raise InvalidImageError(f"File is not a valid, decodable image: {exc}") from exc


async def save_upload(file: UploadFile) -> StoredFile:
    """Read, validate, and safely persist an uploaded field photo.

    Raises UnsupportedFileTypeError / FileTooLargeError / InvalidImageError
    on validation failure. Never writes anything derived from the client's
    original filename to disk.
    """
    max_bytes = settings.max_upload_size_bytes
    allowed_types = set(settings.allowed_mime_type_list)

    # Stream-read with a hard cap so a malicious/oversized upload can't
    # exhaust memory before we reject it.
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(
                f"File exceeds maximum allowed size of {settings.max_upload_size_mb}MB."
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    if total == 0:
        raise InvalidImageError("Uploaded file is empty.")

    mime_type = _sniff_mime_type(data)
    if mime_type not in allowed_types:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{mime_type}'. Allowed types: {', '.join(sorted(allowed_types))}."
        )

    _validate_is_real_image(data)

    ext = _MIME_TO_EXT.get(mime_type, ".bin")
    stored_filename = f"{uuid.uuid4()}{ext}"
    dest_path = settings.upload_path / stored_filename

    # Defense-in-depth: ensure the resolved path is still inside the
    # upload directory (protects against any future refactor that might
    # reintroduce user-controlled path segments).
    resolved = dest_path.resolve()
    if settings.upload_path.resolve() not in resolved.parents and resolved.parent != settings.upload_path.resolve():
        raise InvalidImageError("Resolved upload path escapes the upload directory.")

    dest_path.write_bytes(data)

    sha256_hash = hashlib.sha256(data).hexdigest()

    return StoredFile(
        stored_filename=stored_filename,
        file_path=dest_path,
        mime_type=mime_type,
        file_size_bytes=total,
        sha256_hash=sha256_hash,
    )


def delete_stored_file(stored_filename: str) -> None:
    """Best-effort delete of a previously stored upload (e.g. on rollback)."""
    path = settings.upload_path / stored_filename
    try:
        if path.exists() and path.parent == settings.upload_path:
            path.unlink()
    except OSError:
        pass
