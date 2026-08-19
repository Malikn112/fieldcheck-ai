"""
Strict Pydantic schemas for the Vision LLM's structured output.

These models are passed directly as the JSON-schema target for the vision
provider's "structured outputs" / tool-use feature, so the LLM's response is
validated (and rejected/retried) if it doesn't conform. Keep field
descriptions tight — they're surfaced to the model as schema documentation.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DefectSeverityEnum(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class OverallConditionEnum(str, Enum):
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    POOR = "POOR"
    CRITICAL = "CRITICAL"


class AssetMetadata(BaseModel):
    """OCR / visual identification of the asset's nameplate data."""

    model_config = ConfigDict(protected_namespaces=())

    asset_type: str = Field(
        description="Type of industrial asset, e.g. 'Pressure Gauge', 'Control Valve', "
        "'Electrical Panel'. Use 'Unknown' if it cannot be determined."
    )
    manufacturer: str | None = Field(
        default=None, description="Manufacturer/brand name as printed on the nameplate, if visible."
    )
    model_number: str | None = Field(
        default=None, description="Model number as printed on the nameplate, if visible."
    )
    serial_or_tag_number: str | None = Field(
        default=None, description="Serial number or asset tag number, if visible."
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence (0.0-1.0) in the extracted metadata's accuracy."
    )

    @field_validator("confidence_score")
    @classmethod
    def _round_confidence(cls, v: float) -> float:
        return round(v, 2)


class VisualDefect(BaseModel):
    """A single visually-detected physical defect on the asset."""

    defect_type: str = Field(
        description="Short defect category, e.g. 'Corrosion', 'Leak', 'Loose Bolt', "
        "'Cracked Housing', 'Illegible Gauge Face', 'Missing Guard'."
    )
    severity: DefectSeverityEnum = Field(description="Severity of the defect.")
    location_description: str = Field(
        description="Where on the asset the defect is located, e.g. 'Top-left flange bolt'."
    )
    impact_explanation: str = Field(
        description="Plain-language explanation of the PAIN POINT this defect causes: the "
        "likely root cause, and the concrete operational, safety, or cost consequence if it "
        "is left unaddressed (e.g. 'Corrosion is actively thinning the fitting wall; if it "
        "progresses it can lead to a pressure leak and unplanned downtime'). Write for a "
        "non-technical supervisor, not a fellow engineer."
    )
    recommendation: str = Field(
        description="Concrete, actionable recommendation for the maintenance/inspection team — "
        "what to do and by when."
    )


class ComplianceCheck(BaseModel):
    """Safety/compliance assessment derived from the visual inspection."""

    is_compliant: bool = Field(
        description="Whether the asset appears to meet baseline safety/operational compliance."
    )
    safety_hazards_detected: list[str] = Field(
        default_factory=list,
        description="List of specific safety hazards observed (empty list if none).",
    )
    immediate_action_required: bool = Field(
        description="True if a hazard requires immediate shutdown/escalation before continued operation."
    )


class InspectionReportSchema(BaseModel):
    """Complete structured inspection report returned by the vision model."""

    asset_metadata: AssetMetadata
    defects: list[VisualDefect] = Field(default_factory=list)
    compliance: ComplianceCheck
    overall_condition: OverallConditionEnum = Field(
        description="Overall asset condition rating synthesizing defects + compliance."
    )
    overall_summary: str = Field(
        description="3-5 sentence plain-language summary for a quality supervisor. Must "
        "connect the dots: what condition is the asset in, what is the single biggest pain "
        "point driving that rating, and what is the real-world consequence (safety, "
        "downtime, cost) of not acting on it soon."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "asset_metadata": {
                        "asset_type": "Pressure Gauge",
                        "manufacturer": "Ashcroft",
                        "model_number": "1279",
                        "serial_or_tag_number": "PG-1042",
                        "confidence_score": 0.92,
                    },
                    "defects": [
                        {
                            "defect_type": "Corrosion",
                            "severity": "Medium",
                            "location_description": "Base fitting threads",
                            "impact_explanation": "Surface corrosion has started eating into "
                            "the fitting threads; left alone this typically progresses to "
                            "thread seizure or a slow leak, which would take the gauge out of "
                            "service unexpectedly.",
                            "recommendation": "Clean and inspect threads; monitor for progression "
                            "at next scheduled inspection.",
                        }
                    ],
                    "compliance": {
                        "is_compliant": True,
                        "safety_hazards_detected": [],
                        "immediate_action_required": False,
                    },
                    "overall_condition": "ACCEPTABLE",
                    "overall_summary": "Gauge is functional with minor surface corrosion on the "
                    "base fitting threads. The main pain point is early-stage thread corrosion "
                    "that, if ignored, risks a slow leak and unplanned downtime. No immediate "
                    "safety concerns identified — routine monitoring is sufficient for now.",
                }
            ]
        }
    }


def get_vision_json_schema() -> dict:
    """Return the strict JSON schema used for provider structured-output calls."""
    return InspectionReportSchema.model_json_schema()
