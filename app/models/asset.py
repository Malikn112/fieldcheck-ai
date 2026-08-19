"""Asset ORM model — OCR-extracted nameplate/metadata for the inspected
industrial equipment (one-to-one with an Inspection)."""
from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid4_str() -> str:
    return str(uuid.uuid4())


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    inspection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    asset_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial_or_tag_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    inspection: Mapped["Inspection"] = relationship("Inspection", back_populates="asset")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Asset id={self.id} type={self.asset_type}>"
