"""Unit tests for the mock-mode-by-default report email service."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.email_service import is_valid_email


def test_is_valid_email_accepts_plausible_addresses():
    assert is_valid_email("inspector@company.com")
    assert is_valid_email("  j.alvarez+field@sub.example.co  ")


def test_is_valid_email_rejects_garbage():
    assert not is_valid_email(None)
    assert not is_valid_email("")
    assert not is_valid_email("not-an-email")
    assert not is_valid_email("missing-domain@")
    assert not is_valid_email("@missing-local.com")


@pytest.mark.asyncio
async def test_send_inspection_report_email_mock_mode_writes_outbox_file(tmp_path, monkeypatch):
    """In EMAIL_MOCK_MODE (the default), sending must never touch a real
    socket — it should write the rendered report to the mock outbox and
    report success."""
    from app.config import settings
    from app.models.inspection import Inspection, InspectionStatus
    from app.services.email_service import send_inspection_report_email

    monkeypatch.setattr(settings, "email_mock_mode", True)
    monkeypatch.setattr(settings, "report_output_dir", str(tmp_path))
    monkeypatch.setattr(settings, "company_name", "Test Co.")

    inspection = Inspection(
        id="test-inspection-id",
        original_filename="valve.jpg",
        stored_filename="stored-valve.jpg",
        file_path=str(tmp_path / "stored-valve.jpg"),
        mime_type="image/jpeg",
        file_size_bytes=1234,
        inspector_email="inspector@example.com",
        status=InspectionStatus.COMPLETED,
        overall_condition=None,
        overall_summary="Looks fine.",
        created_at=datetime.now(timezone.utc),
    )
    inspection.asset = None
    inspection.defects = []

    result = await send_inspection_report_email(inspection)

    assert result.sent is True
    assert result.mock is True

    outbox_dir = tmp_path / "mock_outbox"
    assert outbox_dir.exists()
    written = list(outbox_dir.glob("*inspector_example.com*"))
    assert written, f"expected a mock outbox file for the recipient, found: {list(outbox_dir.iterdir())}"
    assert "Field Inspection Report" in written[0].read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_send_inspection_report_email_skips_invalid_recipient():
    from app.models.inspection import Inspection, InspectionStatus
    from app.services.email_service import send_inspection_report_email

    inspection = Inspection(
        id="test-inspection-id-2",
        original_filename="gauge.jpg",
        stored_filename="stored-gauge.jpg",
        file_path="uploads/stored-gauge.jpg",
        mime_type="image/jpeg",
        file_size_bytes=1234,
        inspector_email=None,
        status=InspectionStatus.COMPLETED,
    )
    inspection.asset = None
    inspection.defects = []

    result = await send_inspection_report_email(inspection)
    assert result.sent is False
