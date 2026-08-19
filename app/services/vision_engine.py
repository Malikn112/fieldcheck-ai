"""
Vision engine — calls the configured multimodal LLM (OpenAI GPT-4o or
Anthropic Claude 3.5 Sonnet) with strict structured-output parsing against
`InspectionReportSchema`, with retry/backoff and timeout handling.

Design notes:
  - The provider call is fully abstracted behind `run_inspection()`; callers
    (Celery task / BackgroundTask) never touch provider SDKs directly.
  - `VISION_MOCK_MODE=true` (or no API key configured) makes this module
    return a deterministic synthetic result so the whole pipeline is
    runnable/demoable without any external API calls or costs.
  - Retries use exponential backoff via `tenacity` and only retry on
    transient errors (timeouts, rate limits, 5xx) — validation errors from
    a malformed model response are NOT retried blindly forever; they are
    retried up to `vision_max_retries` then surfaced as a failure.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
from pathlib import Path

from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.schemas.vision import (
    AssetMetadata,
    ComplianceCheck,
    InspectionReportSchema,
    VisualDefect,
)

logger = logging.getLogger("fieldcheck.vision_engine")

SYSTEM_PROMPT = """You are an expert industrial field inspector and certified safety \
compliance auditor. You are given a photo of an industrial asset (e.g. a pressure \
gauge, control valve, electrical panel, pump, or similar equipment).

Carefully analyze the image and:
1. Read any visible nameplate/label text (OCR) to identify the asset type, \
manufacturer, model number, and serial/tag number. If text is not legible or not \
present, use null and lower the confidence score accordingly.
2. Identify visible physical defects (corrosion, leaks, cracks, loose or missing \
bolts, damaged gauges, exposed wiring, missing safety guards, etc.). For EACH defect \
you must clearly explain the underlying PAIN POINT, not just label it: state the \
likely root cause, and spell out the concrete operational, safety, or cost \
consequence of leaving it unaddressed (e.g. "this corrosion is thinning the fitting \
wall, which risks a pressure leak and unplanned downtime if not repainted soon"). \
Write this for a plant manager who is not an engineer — be specific and concrete, \
never generic filler like "may cause issues." Then give a concrete recommendation \
(what to do, by when).
3. Evaluate safety/regulatory compliance based on what is visually observable and \
flag any hazards that require immediate action.
4. Provide an overall condition rating and a supervisor-facing summary that names \
the single biggest pain point driving that rating and its real-world consequence — \
do not just restate the condition label.

Respond ONLY with data matching the required JSON schema. Do not invent nameplate \
data you cannot actually see in the image — prefer null/low confidence over \
fabrication. Never write a vague or generic explanation when a concrete, specific \
one is possible from what's visible in the image."""


def _make_openai_strict_schema(schema: dict) -> dict:
    """Recursively rewrite a Pydantic-generated JSON schema so it satisfies
    OpenAI's *strict* structured-outputs requirements.

    Strict mode requires that every object schema set
    `"additionalProperties": false` and list ALL of its properties —
    including optional/nullable ones — in `"required"` (optionality is
    instead expressed via an `anyOf` with a `null` branch). It also does
    not support the `default` keyword, and — critically — does not allow
    any sibling keywords alongside `$ref` (Pydantic emits
    `{"$ref": "...", "description": "..."}` for an enum/model-typed field
    that also has `Field(description=...)`, which OpenAI rejects with
    "$ref cannot have keywords"). Pydantic's `model_json_schema()` does
    none of this by default, which surfaces as 400 errors like:
    "'additionalProperties' is required to be supplied and to be false"
    or "$ref cannot have keywords {'description'}". This walks the whole
    schema graph (`$defs`, `properties`, `items`, `anyOf`/`oneOf`/`allOf`)
    and fixes it up in place.
    """
    if not isinstance(schema, dict):
        return schema

    schema.pop("default", None)

    # $ref must stand alone — drop any sibling keys (description, title, ...)
    # that Pydantic sometimes attaches next to a $ref.
    if "$ref" in schema and len(schema) > 1:
        ref = schema["$ref"]
        schema.clear()
        schema["$ref"] = ref
        return schema

    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["additionalProperties"] = False
        schema["required"] = list(properties.keys())
        for prop_schema in properties.values():
            _make_openai_strict_schema(prop_schema)

    items = schema.get("items")
    if isinstance(items, dict):
        _make_openai_strict_schema(items)

    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key, []) or []:
            _make_openai_strict_schema(sub)

    defs = schema.get("$defs") or schema.get("definitions")
    if isinstance(defs, dict):
        for sub in defs.values():
            _make_openai_strict_schema(sub)

    return schema


class VisionAPIError(Exception):
    """Raised for retryable/transient vision-provider failures."""


class VisionValidationError(Exception):
    """Raised when the model's response cannot be validated against the schema
    after all retries are exhausted."""


def _encode_image_b64(image_path: Path) -> tuple[str, str]:
    ext = image_path.suffix.lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return b64, media_type


# ---------------------------------------------------------------------------
# Mock provider — deterministic offline fallback
# ---------------------------------------------------------------------------
def _mock_inspection_result(image_path: Path) -> InspectionReportSchema:
    """Deterministic-ish mock result so the full pipeline (upload -> process
    -> report) is demoable without any API keys configured."""
    seed = sum(image_path.stat().st_size for _ in [0]) if image_path.exists() else 0
    rng = random.Random(seed or 42)

    asset_types = ["Pressure Gauge", "Control Valve", "Electrical Panel"]
    manufacturers = ["Ashcroft", "Honeywell", "Emerson", "Siemens"]
    conditions = ["GOOD", "ACCEPTABLE", "POOR", "CRITICAL"]
    defect_pool = [
        ("Corrosion", "Medium", "Base fitting / housing edge",
         "Surface corrosion is thinning the metal at the fitting edge. Left unaddressed, "
         "this typically progresses to pitting and a slow leak — an unplanned shutdown to "
         "fix later instead of a scheduled repaint now.",
         "Clean corrosion and repaint; re-inspect within 90 days."),
        ("Loose Bolt", "Low", "Lower-left mounting bracket",
         "A loose mounting bolt lets the housing vibrate under normal operation, which "
         "accelerates wear on the mount and can eventually let the unit shift out of "
         "alignment.",
         "Torque bolt to spec at next scheduled maintenance."),
        ("Illegible Dial Markings", "Low", "Gauge face",
         "Worn or fogged dial markings mean an operator can't get a reliable reading at a "
         "glance, which risks a missed early warning if the reading drifts out of range.",
         "Schedule cleaning or replacement of the dial cover."),
        ("Leak Residue", "High", "Threaded connection at base",
         "Residue at the threaded connection indicates fluid is already escaping the seal. "
         "If this is pressurized fluid, continued operation risks a sudden pressure loss "
         "and possible safety exposure to nearby personnel.",
         "Isolate and inspect for active leak before returning to service."),
    ]

    asset_type = asset_types[rng.randrange(len(asset_types))]
    condition = conditions[rng.randrange(len(conditions))]
    num_defects = rng.randrange(0, 3)
    defects = [
        VisualDefect(
            defect_type=d[0],
            severity=d[1],
            location_description=d[2],
            impact_explanation=d[3],
            recommendation=d[4],
        )
        for d in rng.sample(defect_pool, k=num_defects)
    ]

    is_compliant = condition not in ("POOR", "CRITICAL")
    hazards = [] if is_compliant else ["Potential leak/structural hazard observed near fitting."]

    return InspectionReportSchema(
        asset_metadata=AssetMetadata(
            asset_type=asset_type,
            manufacturer=manufacturers[rng.randrange(len(manufacturers))],
            model_number=f"MDL-{rng.randint(1000, 9999)}",
            serial_or_tag_number=f"TAG-{rng.randint(10000, 99999)}",
            confidence_score=round(rng.uniform(0.72, 0.97), 2),
        ),
        defects=defects,
        compliance=ComplianceCheck(
            is_compliant=is_compliant,
            safety_hazards_detected=hazards,
            immediate_action_required=(condition == "CRITICAL"),
        ),
        overall_condition=condition,
        overall_summary=(
            f"[MOCK ANALYSIS — not a real assessment] {asset_type} assessed as {condition}, "
            f"with {len(defects)} defect(s) noted"
            + (f"; the leading concern is {defects[0].defect_type.lower()}." if defects else ".")
            + " This is a simulated result because VISION_MOCK_MODE is enabled or no vision "
            "API key is configured — set OPENAI_API_KEY (or ANTHROPIC_API_KEY) and "
            "VISION_MOCK_MODE=false to get real AI-analyzed pain points instead of this "
            "placeholder text."
        ),
    )


# ---------------------------------------------------------------------------
# OpenAI (GPT-4o) provider
# ---------------------------------------------------------------------------
async def _call_openai(image_path: Path) -> dict:
    from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError

    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.vision_timeout_seconds)
    b64, media_type = _encode_image_b64(image_path)

    try:
        response = await client.chat.completions.create(
            model=settings.openai_vision_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze this industrial asset photo and return the "
                            "structured inspection report.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{b64}"},
                        },
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "InspectionReport",
                    "schema": _make_openai_strict_schema(InspectionReportSchema.model_json_schema()),
                    "strict": True,
                },
            },
            timeout=settings.vision_timeout_seconds,
        )
    except (APITimeoutError, RateLimitError) as exc:
        raise VisionAPIError(f"OpenAI transient error: {exc}") from exc
    except APIError as exc:
        # 5xx are transient/retryable; 4xx (bad request, auth) are not.
        status = getattr(exc, "status_code", None)
        if status and 500 <= status < 600:
            raise VisionAPIError(f"OpenAI server error: {exc}") from exc
        raise

    content = response.choices[0].message.content
    return json.loads(content)


# ---------------------------------------------------------------------------
# Anthropic (Claude 3.5 Sonnet) provider
# ---------------------------------------------------------------------------
async def _call_anthropic(image_path: Path) -> dict:
    import anthropic
    from anthropic import APIError, APIStatusError, APITimeoutError

    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key, timeout=settings.vision_timeout_seconds
    )
    b64, media_type = _encode_image_b64(image_path)

    tool_schema = InspectionReportSchema.model_json_schema()

    try:
        response = await client.messages.create(
            model=settings.anthropic_vision_model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[
                {
                    "name": "submit_inspection_report",
                    "description": "Submit the structured industrial asset inspection report.",
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": "submit_inspection_report"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Analyze this industrial asset photo and return the "
                            "structured inspection report via the tool call.",
                        },
                    ],
                }
            ],
        )
    except APITimeoutError as exc:
        raise VisionAPIError(f"Anthropic timeout: {exc}") from exc
    except APIStatusError as exc:
        if 500 <= exc.status_code < 600 or exc.status_code == 429:
            raise VisionAPIError(f"Anthropic transient error: {exc}") from exc
        raise
    except APIError as exc:
        raise VisionAPIError(f"Anthropic error: {exc}") from exc

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_inspection_report":
            return block.input

    raise VisionValidationError("Anthropic response did not include the expected tool call.")


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
@retry(
    reraise=True,
    stop=stop_after_attempt(max(1, settings.vision_max_retries)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(VisionAPIError),
)
async def _call_provider_with_retry(image_path: Path) -> dict:
    if settings.vision_provider == "anthropic":
        return await _call_anthropic(image_path)
    return await _call_openai(image_path)


async def run_inspection(image_path: Path) -> InspectionReportSchema:
    """Run the full vision analysis for a stored image and return a
    validated `InspectionReportSchema`.

    Raises VisionAPIError (after retries exhausted) or VisionValidationError.
    """
    if settings.vision_mock_mode or not settings.vision_api_key_configured:
        logger.info("Vision engine running in MOCK mode for %s", image_path.name)
        # Simulate realistic latency so the async pipeline / UI polling is
        # exercised the same way it would be against a real API.
        await asyncio.sleep(1.5)
        return _mock_inspection_result(image_path)

    try:
        raw = await _call_provider_with_retry(image_path)
    except VisionAPIError as exc:
        logger.error("Vision provider failed after retries: %s", exc)
        raise
    except asyncio.TimeoutError as exc:
        raise VisionAPIError(f"Vision API call timed out: {exc}") from exc

    try:
        return InspectionReportSchema.model_validate(raw)
    except ValidationError as exc:
        logger.error("Vision response failed schema validation: %s", exc)
        raise VisionValidationError(str(exc)) from exc
