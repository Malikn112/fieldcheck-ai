"""Defect ORM model — one row per visual defect detected on an asset
(one-to-many with an Inspection)."""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid4_str() -> str:
    return str(uuid.uuid4())


class DefectSeverity(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Defect(Base):
    __tablename__ = "defects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    inspection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )

    defect_type: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[DefectSeverity] = mapped_column(
        Enum(DefectSeverity, native_enum=False, length=20), nullable=False
    )
    location_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Why this defect matters — root cause + operational/safety consequence
    # if left unaddressed. Kept separate from `recommendation` (the action
    # to take) so the report can clearly answer both "what should we do"
    # and "why does it matter" for a non-technical reader.
    impact_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    inspection: Mapped["Inspection"] = relationship("Inspection", back_populates="defects")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Defect id={self.id} type={self.defect_type} severity={self.severity}>"
