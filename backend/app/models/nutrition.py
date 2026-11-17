"""营养成分（保留原始数值与单位，缺失即缺失）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow


class NutritionFact(db.Model):
    __tablename__ = "nutrition_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    basis: Mapped[str] = mapped_column(String(30), nullable=False, default="per_100g")
    basis_note: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="ocr")  # ocr | manual
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    record = relationship("AnalysisRecord", back_populates="nutrition")

    def to_public(self) -> dict:
        return {
            "basis": self.basis,
            "basis_note": self.basis_note or "",
            "source": self.source,
            "items": self.items or [],
            "warnings": self.warnings or [],
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }
