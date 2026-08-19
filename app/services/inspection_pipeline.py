"""
Shared inspection-processing pipeline.

This is the single place that turns a PENDING Inspection row into a
COMPLETED (or FAILED) one by calling the vision engine and persisting
results. It is invoked either:
  - directly, from a FastAPI `BackgroundTask` (default, no Redis needed), or
  - from the Celery worker task (`USE_CELERY=true`), via its own event loop.

Keeping this logic provider-agnostic and transport-agnostic means the API
route doesn't care which execution path is active.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.asset import Asset
from app.models.defect import Defect
from app.models.inspection import EmailStatus, Inspection, InspectionStatus
from app.services.email_service import send_inspection_report_email
from app.services.vision_engine import (
    VisionAPIError,
    VisionValidationError,
    run_inspection,
)

logger = logging.getLogger("fieldcheck.pipeline")


async def process_inspection(inspection_id: str) -> None:
    """Load the inspection, run vision analysis, and persist the outcome.
    Never raises — all failures are captured onto the Inspection row so the
    client polling `GET /inspections/{id}` always gets a terminal state.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Inspection).where(Inspection.id == inspection_id))
        inspection = result.scalar_one_or_none()
        if inspection is None:
            logger.error("process_inspection: inspection %s not found", inspection_id)
            return

        inspection.status = InspectionStatus.PROCESSING
        await session.commit()

        try:
            image_path = Path(inspection.file_path)
            report = await run_inspection(image_path)

            # --- Persist asset metadata --------------------------------
            asset = Asset(
                inspection_id=inspection.id,
                asset_type=report.asset_metadata.asset_type,
                manufacturer=report.asset_metadata.manufacturer,
                model_number=report.asset_metadata.model_number,
                serial_or_tag_number=report.asset_metadata.serial_or_tag_number,
                confidence_score=report.asset_metadata.confidence_score,
            )
            session.add(asset)

            # --- Persist defects -----------------------------------------
            for d in report.defects:
                session.add(
                    Defect(
                        inspection_id=inspection.id,
                        defect_type=d.defect_type,
                        severity=d.severity.value,
                        location_description=d.location_description,
                        impact_explanation=d.impact_explanation,
                        recommendation=d.recommendation,
                    )
                )

            # --- Update inspection summary fields --------------------------
            inspection.overall_condition = report.overall_condition.value
            inspection.overall_summary = report.overall_summary
            inspection.is_compliant = report.compliance.is_compliant
            inspection.safety_hazards_detected = report.compliance.safety_hazards_detected
            inspection.immediate_action_required = report.compliance.immediate_action_required
            inspection.raw_vision_payload = report.model_dump(mode="json")
            inspection.status = InspectionStatus.COMPLETED
            inspection.error_message = None

            from datetime import datetime, timezone

            inspection.completed_at = datetime.now(timezone.utc)

            from app.config import settings

            inspection.vision_provider_used = (
                "mock" if settings.vision_mock_mode or not settings.vision_api_key_configured
                else settings.vision_provider
            )

            await session.commit()
            logger.info("Inspection %s completed successfully.", inspection_id)

            # --- Email the report, if requested ---------------------------
            # Never allowed to affect the inspection's own COMPLETED status —
            # a failed/misconfigured email send is recorded on its own
            # email_status/email_error_message fields only.
            if inspection.inspector_email:
                inspection.email_status = EmailStatus.PENDING
                await session.commit()

                # Relationships were populated on these in-session objects but
                # not necessarily reflected onto inspection.asset/defects, and
                # `overall_condition` was assigned as a plain string above
                # (`.value`) rather than an OverallCondition enum member —
                # the report template calls `.value` on it, which would raise
                # `AttributeError: 'str' object has no attribute 'value'`.
                # Refreshing from the DB re-loads it (and asset/defects'
                # severity enums) through SQLAlchemy's type layer, which
                # coerces them back into proper enum instances.
                await session.refresh(
                    inspection, attribute_names=["overall_condition", "asset", "defects"]
                )

                try:
                    email_result = await send_inspection_report_email(inspection)
                    inspection.email_status = (
                        EmailStatus.SENT if email_result.sent else EmailStatus.FAILED
                    )
                    inspection.email_error_message = None if email_result.sent else email_result.detail
                    if email_result.sent:
                        from datetime import datetime as _dt
                        from datetime import timezone as _tz

                        inspection.email_sent_at = _dt.now(_tz.utc)
                    await session.commit()
                    logger.info(
                        "Inspection %s report email: %s", inspection_id, email_result.detail
                    )
                except Exception as email_exc:  # noqa: BLE001 - never fail the inspection
                    await session.rollback()
                    inspection.email_status = EmailStatus.FAILED
                    inspection.email_error_message = f"Unexpected email error: {email_exc}"[:2000]
                    await session.commit()
                    logger.exception(
                        "Inspection %s: unexpected error sending report email.", inspection_id
                    )

        except (VisionAPIError, VisionValidationError) as exc:
            await session.rollback()
            inspection.status = InspectionStatus.FAILED
            inspection.error_message = str(exc)[:2000]
            inspection.retry_count += 1
            await session.commit()
            logger.error("Inspection %s failed: %s", inspection_id, exc)

        except Exception as exc:  # noqa: BLE001 - final safety net
            await session.rollback()
            inspection.status = InspectionStatus.FAILED
            inspection.error_message = f"Unexpected error: {exc}"[:2000]
            await session.commit()
            logger.exception("Inspection %s failed unexpectedly.", inspection_id)
