"""End-to-end tests for the async inspection pipeline: upload -> poll ->
completed -> report, all against the mock vision engine."""
from __future__ import annotations

import asyncio

import pytest


async def _wait_until_completed(client, inspection_id: str, timeout: float = 15.0):
    elapsed = 0.0
    while elapsed < timeout:
        res = await client.get(f"/api/v1/inspections/{inspection_id}")
        assert res.status_code == 200
        data = res.json()
        if data["status"] in ("COMPLETED", "FAILED"):
            return data
        await asyncio.sleep(0.5)
        elapsed += 0.5
    raise TimeoutError("Inspection did not complete in time.")


@pytest.mark.asyncio
async def test_full_inspection_lifecycle(client, sample_jpeg_bytes):
    files = {"file": ("valve.jpg", sample_jpeg_bytes, "image/jpeg")}
    upload_res = await client.post(
        "/api/v1/inspections/upload",
        files=files,
        data={"inspector_name": "Test Inspector", "site_location": "Test Site"},
    )
    assert upload_res.status_code == 202
    inspection_id = upload_res.json()["inspection_id"]

    data = await _wait_until_completed(client, inspection_id)

    assert data["status"] == "COMPLETED"
    assert data["asset"] is not None
    assert data["asset"]["asset_type"]
    assert 0.0 <= data["asset"]["confidence_score"] <= 1.0
    assert isinstance(data["defects"], list)
    assert data["overall_condition"] in ("GOOD", "ACCEPTABLE", "POOR", "CRITICAL")
    assert data["overall_summary"]
    assert data["is_compliant"] in (True, False)


@pytest.mark.asyncio
async def test_report_endpoint_returns_html_after_completion(client, sample_jpeg_bytes):
    files = {"file": ("panel.jpg", sample_jpeg_bytes, "image/jpeg")}
    upload_res = await client.post("/api/v1/inspections/upload", files=files)
    inspection_id = upload_res.json()["inspection_id"]

    await _wait_until_completed(client, inspection_id)

    report_res = await client.get(f"/api/v1/inspections/{inspection_id}/report")
    assert report_res.status_code == 200
    assert "text/html" in report_res.headers["content-type"]
    assert "Field Inspection Report" in report_res.text
    assert inspection_id in report_res.text


@pytest.mark.asyncio
async def test_report_endpoint_409_before_completion(client):
    """The report should not be servable while the inspection is still
    PENDING/PROCESSING.

    Note: FastAPI `BackgroundTasks` run to completion as part of the same
    ASGI call, so under the in-process test transport a normal upload's
    background task would already be finished by the time `client.post`
    returns. To exercise the "not ready yet" path deterministically, we
    insert a PENDING Inspection row directly rather than racing the
    pipeline.
    """
    import uuid

    from app.database import AsyncSessionLocal
    from app.models.inspection import Inspection, InspectionStatus

    unique_name = f"{uuid.uuid4()}.jpg"
    async with AsyncSessionLocal() as session:
        inspection = Inspection(
            original_filename="pending.jpg",
            stored_filename=unique_name,
            file_path=f"uploads/{unique_name}",
            mime_type="image/jpeg",
            file_size_bytes=1234,
            status=InspectionStatus.PENDING,
        )
        session.add(inspection)
        await session.commit()
        await session.refresh(inspection)
        inspection_id = inspection.id

    report_res = await client.get(f"/api/v1/inspections/{inspection_id}/report")
    assert report_res.status_code == 409


@pytest.mark.asyncio
async def test_unknown_inspection_id_returns_404(client):
    res = await client.get("/api/v1/inspections/does-not-exist")
    assert res.status_code == 404
    body = res.json()
    assert body["status_code"] == 404


@pytest.mark.asyncio
async def test_list_inspections(client, sample_jpeg_bytes):
    files = {"file": ("gauge.jpg", sample_jpeg_bytes, "image/jpeg")}
    await client.post("/api/v1/inspections/upload", files=files)
    res = await client.get("/api/v1/inspections?limit=5")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_health_check(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_upload_with_inspector_email_sends_mock_report_email(client, sample_jpeg_bytes):
    """End-to-end: providing inspector_email at upload time should, once the
    (mock) analysis completes, flip email_status to SENT via the mock-outbox
    path (EMAIL_MOCK_MODE defaults to true in tests)."""
    files = {"file": ("valve.jpg", sample_jpeg_bytes, "image/jpeg")}
    upload_res = await client.post(
        "/api/v1/inspections/upload",
        files=files,
        data={"inspector_name": "Test Inspector", "inspector_email": "inspector@example.com"},
    )
    assert upload_res.status_code == 202
    inspection_id = upload_res.json()["inspection_id"]

    data = await _wait_until_completed(client, inspection_id)

    assert data["status"] == "COMPLETED"
    assert data["inspector_email"] == "inspector@example.com"
    assert data["email_status"] == "SENT"
    assert data["email_sent_at"] is not None


@pytest.mark.asyncio
async def test_upload_with_malformed_inspector_email_is_rejected(client, sample_jpeg_bytes):
    files = {"file": ("valve.jpg", sample_jpeg_bytes, "image/jpeg")}
    upload_res = await client.post(
        "/api/v1/inspections/upload",
        files=files,
        data={"inspector_email": "not-an-email"},
    )
    assert upload_res.status_code == 400


@pytest.mark.asyncio
async def test_upload_without_inspector_email_leaves_email_not_requested(client, sample_jpeg_bytes):
    files = {"file": ("valve.jpg", sample_jpeg_bytes, "image/jpeg")}
    upload_res = await client.post("/api/v1/inspections/upload", files=files)
    inspection_id = upload_res.json()["inspection_id"]

    data = await _wait_until_completed(client, inspection_id)
    assert data["email_status"] == "NOT_REQUESTED"
