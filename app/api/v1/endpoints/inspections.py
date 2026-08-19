"""Inspection endpoints — upload, status poll, and HTML report."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.inspection import Inspection, InspectionStatus
from app.schemas.inspection import InspectionOut, UploadResponse
from app.services.email_service import is_valid_email
from app.services.inspection_pipeline import process_inspection
from app.services.report_service import render_inspection_html
from app.services.storage_service import (
    FileTooLargeError,
    InvalidImageError,
    UnsupportedFileTypeError,
    save_upload,
)

logger = logging.getLogger("fieldcheck.api.inspections")

router = APIRouter(prefix="/inspections", tags=["inspections"])


def _to_inspection_out(inspection: Inspection) -> InspectionOut:
    out = InspectionOut.model_validate(inspection)
    out.image_url = f"{settings.api_v1_prefix}/inspections/{inspection.id}/image"
    return out


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a field photo and kick off async AI inspection",
)
async def upload_inspection(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    inspector_name: str | None = Form(default=None),
    inspector_email: str | None = Form(default=None),
    site_location: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Accepts an image, validates/sanitizes it, creates a PENDING
    Inspection record, and schedules async vision analysis. Returns
    immediately — the client polls `GET /inspections/{id}` for results.

    If `inspector_email` is provided, the completed report is automatically
    emailed to that address once analysis finishes (see
    `app.services.email_service` — mock mode by default)."""
    try:
        stored = await save_upload(file)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    except FileTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    except InvalidImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    inspector_email = inspector_email.strip() if inspector_email else None
    if inspector_email and not is_valid_email(inspector_email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{inspector_email}' does not look like a valid email address.",
        )

    inspection = Inspection(
        original_filename=file.filename or "upload",
        stored_filename=stored.stored_filename,
        file_path=str(stored.file_path),
        mime_type=stored.mime_type,
        file_size_bytes=stored.file_size_bytes,
        sha256_hash=stored.sha256_hash,
        inspector_name=inspector_name,
        inspector_email=inspector_email,
        site_location=site_location,
        notes=notes,
        status=InspectionStatus.PENDING,
    )
    db.add(inspection)
    await db.commit()
    await db.refresh(inspection)

    if settings.use_celery:
        from app.services.celery_app import process_inspection_task

        process_inspection_task.delay(inspection.id)
    else:
        background_tasks.add_task(process_inspection, inspection.id)

    return UploadResponse(inspection_id=inspection.id, status=inspection.status)


@router.get(
    "/{inspection_id}",
    response_model=InspectionOut,
    summary="Poll inspection status and retrieve results once completed",
)
async def get_inspection(inspection_id: str, db: AsyncSession = Depends(get_db)) -> InspectionOut:
    result = await db.execute(
        select(Inspection)
        .where(Inspection.id == inspection_id)
    )
    inspection = result.scalar_one_or_none()
    if inspection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found.")

    # Explicitly load relationships (lazy='raise' safe pattern under async).
    await db.refresh(inspection, attribute_names=["asset", "defects"])

    return _to_inspection_out(inspection)


@router.get(
    "/{inspection_id}/report",
    response_class=HTMLResponse,
    summary="Render a clean HTML inspection report",
)
async def get_inspection_report(inspection_id: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    result = await db.execute(select(Inspection).where(Inspection.id == inspection_id))
    inspection = result.scalar_one_or_none()
    if inspection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found.")

    await db.refresh(inspection, attribute_names=["asset", "defects"])

    if inspection.status != InspectionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report not available yet — inspection status is {inspection.status.value}.",
        )

    html = render_inspection_html(inspection)
    return HTMLResponse(content=html)


@router.get(
    "/{inspection_id}/image",
    summary="Fetch the original uploaded photo for an inspection",
)
async def get_inspection_image(inspection_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Inspection).where(Inspection.id == inspection_id))
    inspection = result.scalar_one_or_none()
    if inspection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found.")

    from pathlib import Path

    path = Path(inspection.file_path)
    # Defense-in-depth: only ever serve files inside the configured upload dir.
    if settings.upload_path.resolve() not in path.resolve().parents or not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found.")

    return FileResponse(path, media_type=inspection.mime_type)


@router.get(
    "",
    response_model=list[InspectionOut],
    summary="List recent inspections",
)
async def list_inspections(
    limit: int = 50, db: AsyncSession = Depends(get_db)
) -> list[InspectionOut]:
    limit = max(1, min(limit, 200))
    result = await db.execute(
        select(Inspection).order_by(Inspection.created_at.desc()).limit(limit)
    )
    inspections = result.scalars().all()
    out = []
    for insp in inspections:
        await db.refresh(insp, attribute_names=["asset", "defects"])
        out.append(_to_inspection_out(insp))
    return out
