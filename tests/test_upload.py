"""Tests for the upload endpoint & file-sanitization behavior."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_upload_valid_jpeg_returns_pending(client, sample_jpeg_bytes):
    files = {"file": ("gauge.jpg", sample_jpeg_bytes, "image/jpeg")}
    res = await client.post("/api/v1/inspections/upload", files=files)
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "PENDING"
    assert "inspection_id" in body


@pytest.mark.asyncio
async def test_upload_valid_png_returns_pending(client, sample_png_bytes):
    files = {"file": ("panel.png", sample_png_bytes, "image/png")}
    res = await client.post("/api/v1/inspections/upload", files=files)
    assert res.status_code == 202
    assert res.json()["status"] == "PENDING"


@pytest.mark.asyncio
async def test_upload_rejects_non_image_mime(client):
    files = {"file": ("malware.exe", b"MZ\x90\x00" + b"\x00" * 100, "application/octet-stream")}
    res = await client.post("/api/v1/inspections/upload", files=files)
    assert res.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_fake_image_extension(client):
    """A text file renamed to .jpg should still be rejected — the server
    sniffs real magic bytes, it doesn't trust the filename or header."""
    files = {"file": ("fake.jpg", b"not actually an image, just text bytes " * 10, "image/jpeg")}
    res = await client.post("/api/v1/inspections/upload", files=files)
    assert res.status_code in (400, 415)


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "max_upload_size_mb", 0)  # 0MB effective cap
    big_payload = b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024)  # starts like a JPEG but oversized
    files = {"file": ("huge.jpg", big_payload, "image/jpeg")}
    res = await client.post("/api/v1/inspections/upload", files=files)
    assert res.status_code == 413


@pytest.mark.asyncio
async def test_upload_stored_filename_is_not_original_filename(client, sample_jpeg_bytes):
    """Regression guard for path-traversal safety: stored files must use a
    server-generated UUID name, never the client-supplied filename."""
    files = {"file": ("../../etc/passwd.jpg", sample_jpeg_bytes, "image/jpeg")}
    res = await client.post("/api/v1/inspections/upload", files=files)
    assert res.status_code == 202
    inspection_id = res.json()["inspection_id"]

    detail = await client.get(f"/api/v1/inspections/{inspection_id}")
    assert detail.status_code == 200
    assert detail.json()["original_filename"] == "../../etc/passwd.jpg"
    # image_url should point at our own safe endpoint, not a raw path
    assert detail.json()["image_url"].endswith(f"/inspections/{inspection_id}/image")
