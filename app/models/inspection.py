"""Inspection ORM model — the central record of an uploaded asset photo
and its AI analysis lifecycle."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid4_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InspectionStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EmailStatus(str, enum.Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class OverallCondition(str, enum.Enum):
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    POOR = "POOR"
    CRITICAL = "CRITICAL"


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)

    # --- Uploaded file bookkeeping ---------------------------------------
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- Inspector / provenance --------------------------------------------
    inspector_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inspector_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    site_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Report email delivery ---------------------------------------------
    # Set to PENDING when inspector_email is provided at upload time; flipped
    # to SENT/FAILED by the pipeline after analysis completes. Email failures
    # never affect the inspection's own status/results.
    email_status: Mapped[EmailStatus] = mapped_column(
        Enum(EmailStatus, native_enum=False, length=20),
        nullable=False,
        default=EmailStatus.NOT_REQUESTED,
    )
    email_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Lifecycle state -------------------------------------------------
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, native_enum=False, length=20),
        nullable=False,
        default=InspectionStatus.PENDING,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    vision_provider_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)

    # --- AI analysis results (denormalized summary; details in relations) --
    overall_condition: Mapped[OverallCondition | None] = mapped_column(
        Enum(OverallCondition, native_enum=False, length=20), nullable=True
    )
    overall_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_compliant: Mapped[bool | None] = mapped_column(nullable=True)
    safety_hazards_detected: Mapped[list | None] = mapped_column(JSON, nullable=True)
    immediate_action_required: Mapped[bool | None] = mapped_column(nullable=True)

    # Full raw structured-output payload from the vision model, kept for
    # audit/debug purposes even though it's also normalized into relations.
    raw_vision_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- Timestamps --------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Relationships -------------------------------------------------
    asset: Mapped["Asset | None"] = relationship(
        "Asset", back_populates="inspection", uselist=False, cascade="all, delete-orphan"
    )
    defects: Mapped[list["Defect"]] = relationship(
        "Defect", back_populates="inspection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Inspection id={self.id} status={self.status}>"
