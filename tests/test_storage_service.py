"""Unit tests for storage_service sanitization helpers that don't require
the full FastAPI app (pure function tests)."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services.storage_service import _sniff_mime_type, _validate_is_real_image, InvalidImageError


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (10, 10), color=(1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _png_bytes() -> bytes:
    img = Image.new("RGB", (10, 10), color=(1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_sniff_mime_type_jpeg():
    assert _sniff_mime_type(_jpeg_bytes()) == "image/jpeg"


def test_sniff_mime_type_png():
    assert _sniff_mime_type(_png_bytes()) == "image/png"


def test_validate_is_real_image_accepts_valid_jpeg():
    _validate_is_real_image(_jpeg_bytes())  # should not raise


def test_validate_is_real_image_rejects_garbage():
    with pytest.raises(InvalidImageError):
        _validate_is_real_image(b"this is definitely not an image")
