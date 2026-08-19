"""Pydantic schemas for the public REST API (request/response bodies)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.defect import DefectSeverity
from app.models.inspection import EmailStatus, InspectionStatus, OverallCondition


# ---------------------------------------------------------------------------
# Response envelopes
# ---------------------------------------------------------------------------
class UploadResponse(BaseModel):
    inspection_id: str
    status: InspectionStatus
    message: str = "Upload received. Analysis in progress."


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    asset_type: str | None = None
    manufacturer: str | None = None
    model_number: str | None = None
    serial_or_tag_number: str | None = None
    confidence_score: float | None = None


class DefectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    defect_type: str
    severity: DefectSeverity
    location_description: str | None = None
    impact_explanation: str | None = None
    recommendation: str | None = None


class InspectionOut(BaseModel):
    """Full inspection status + results payload returned by the poll endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: InspectionStatus
    original_filename: str
    inspector_name: str | None = None
    inspector_email: str | None = None
    site_location: str | None = None
    notes: str | None = None

    error_message: str | None = None
    retry_count: int = 0
    vision_provider_used: str | None = None

    email_status: EmailStatus = EmailStatus.NOT_REQUESTED
    email_error_message: str | None = None
    email_sent_at: datetime | None = None

    overall_condition: OverallCondition | None = None
    overall_summary: str | None = None
    is_compliant: bool | None = None
    safety_hazards_detected: list[str] | None = None
    immediate_action_required: bool | None = None

    asset: AssetOut | None = None
    defects: list[DefectOut] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    image_url: str | None = None


class ErrorResponse(BaseModel):
    """Standardized error envelope returned by global exception handlers."""

    error: str
    detail: str | None = None
    status_code: int
    path: str | None = None
