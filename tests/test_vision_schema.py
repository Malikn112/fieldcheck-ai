"""Unit tests for the strict vision Pydantic schemas."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.vision import (
    AssetMetadata,
    ComplianceCheck,
    InspectionReportSchema,
    VisualDefect,
)


def test_asset_metadata_confidence_bounds():
    with pytest.raises(ValidationError):
        AssetMetadata(asset_type="Valve", confidence_score=1.5)
    with pytest.raises(ValidationError):
        AssetMetadata(asset_type="Valve", confidence_score=-0.1)

    ok = AssetMetadata(asset_type="Valve", confidence_score=0.876)
    assert ok.confidence_score == 0.88  # rounded to 2 dp


def test_visual_defect_requires_valid_severity():
    with pytest.raises(ValidationError):
        VisualDefect(
            defect_type="Corrosion",
            severity="Extreme",  # not a valid enum value
            location_description="Base",
            recommendation="Fix it",
        )

    ok = VisualDefect(
        defect_type="Corrosion",
        severity="High",
        location_description="Base",
        recommendation="Fix it",
    )
    assert ok.severity.value == "High"


def test_full_inspection_report_schema_roundtrip():
    report = InspectionReportSchema(
        asset_metadata=AssetMetadata(asset_type="Pressure Gauge", confidence_score=0.9),
        defects=[
            VisualDefect(
                defect_type="Leak",
                severity="Critical",
                location_description="Base fitting",
                recommendation="Isolate immediately",
            )
        ],
        compliance=ComplianceCheck(
            is_compliant=False,
            safety_hazards_detected=["Active leak"],
            immediate_action_required=True,
        ),
        overall_condition="CRITICAL",
        overall_summary="Critical leak detected; isolate immediately.",
    )
    dumped = report.model_dump(mode="json")
    reloaded = InspectionReportSchema.model_validate(dumped)
    assert reloaded.overall_condition.value == "CRITICAL"
    assert reloaded.compliance.immediate_action_required is True


def test_json_schema_is_generatable():
    schema = InspectionReportSchema.model_json_schema()
    assert schema["title"] == "InspectionReportSchema"
    assert "asset_metadata" in schema["properties"]
    assert "compliance" in schema["properties"]


def _find_strict_mode_violations(schema: dict, path: str = "root") -> list[str]:
    """Walk a JSON schema and report anything that would fail OpenAI's
    strict structured-outputs mode: every object must set
    `additionalProperties: false` and list ALL of its properties (even
    optional/nullable ones) in `required`; `default` is unsupported."""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return errors

    if "default" in schema:
        errors.append(f"{path}: contains unsupported 'default' key")

    if "$ref" in schema and len(schema) > 1:
        errors.append(f"{path}: $ref has sibling keywords {set(schema) - {'$ref'}}")
        return errors  # nothing else about this node is meaningful

    properties = schema.get("properties")
    if isinstance(properties, dict):
        if schema.get("additionalProperties") is not False:
            errors.append(f"{path}: additionalProperties must be False")
        required = set(schema.get("required") or [])
        if required != set(properties.keys()):
            errors.append(f"{path}: required {required} != properties {set(properties.keys())}")
        for key, sub in properties.items():
            errors.extend(_find_strict_mode_violations(sub, f"{path}.{key}"))

    if isinstance(schema.get("items"), dict):
        errors.extend(_find_strict_mode_violations(schema["items"], f"{path}[]"))

    for key in ("anyOf", "oneOf", "allOf"):
        for i, sub in enumerate(schema.get(key, []) or []):
            errors.extend(_find_strict_mode_violations(sub, f"{path}.{key}[{i}]"))

    defs = schema.get("$defs") or schema.get("definitions")
    if isinstance(defs, dict):
        for name, sub in defs.items():
            errors.extend(_find_strict_mode_violations(sub, f"$defs.{name}"))

    return errors


def test_raw_pydantic_schema_is_not_openai_strict_compliant():
    """Documents WHY the transform step exists: Pydantic's default output
    does NOT satisfy OpenAI strict mode (optional/nullable fields are
    omitted from `required`, and nested objects lack
    `additionalProperties: false`). If this test ever starts failing
    because Pydantic's default output changed to already be compliant,
    that's fine — it just means the transform step below has become a
    no-op, not a bug."""
    raw = InspectionReportSchema.model_json_schema()
    assert _find_strict_mode_violations(raw), (
        "expected the raw Pydantic schema to violate OpenAI strict-mode rules"
    )


def test_openai_strict_schema_transform_produces_compliant_schema():
    """Regression test for the bug where OpenAI's real API rejected our
    structured-output schema with: 'additionalProperties' is required to
    be supplied and to be false. Every object in the transformed schema
    (including nested $defs) must set additionalProperties=false and list
    every property in `required`."""
    from app.services.vision_engine import _make_openai_strict_schema

    raw = InspectionReportSchema.model_json_schema()
    strict = _make_openai_strict_schema(raw)

    violations = _find_strict_mode_violations(strict)
    assert not violations, "strict-mode schema violations:\n" + "\n".join(violations)

    # Sanity-check a couple of concrete fields survived the transform correctly.
    asset_props = strict["$defs"]["AssetMetadata"]["properties"]
    assert set(strict["$defs"]["AssetMetadata"]["required"]) == set(asset_props.keys())
    assert strict["$defs"]["AssetMetadata"]["additionalProperties"] is False
    # Nullable/optional field should be expressed via anyOf[..., null], not omitted.
    assert {"type": "null"} in asset_props["manufacturer"]["anyOf"]


def test_openai_strict_schema_strips_description_sibling_from_ref():
    """Regression test for a second real 400 hit from OpenAI's live API:
    'Invalid schema for response_format ...: context=(\"properties\",
    \"severity\"), $ref cannot have keywords {\"description\"}.'

    Pydantic emits `{"$ref": "#/$defs/DefectSeverityEnum", "description":
    "..."}` for `VisualDefect.severity` because it's both enum-typed and
    has `Field(description=...)`. OpenAI's strict validator forbids any
    keyword next to `$ref`, so the transform must strip everything but
    the ref itself. Same pattern applies to
    `InspectionReportSchema.overall_condition`.
    """
    from app.services.vision_engine import _make_openai_strict_schema

    raw = InspectionReportSchema.model_json_schema()

    # Confirm the bug actually reproduces against raw Pydantic output first.
    raw_severity = raw["$defs"]["VisualDefect"]["properties"]["severity"]
    assert "$ref" in raw_severity and len(raw_severity) > 1, (
        "expected raw Pydantic output to attach sibling keywords to $ref "
        "(if this fails, Pydantic's behavior changed and the bug this "
        "guards against may no longer exist)"
    )

    strict = _make_openai_strict_schema(raw)

    strict_severity = strict["$defs"]["VisualDefect"]["properties"]["severity"]
    assert strict_severity == {"$ref": raw_severity["$ref"]}

    strict_condition = strict["properties"]["overall_condition"]
    assert set(strict_condition.keys()) == {"$ref"}
