"""OCR 识别结果：同时保留原始识别文本与用户校正文本。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow

# 参与结构化的字段（顺序即页面展示顺序）
OCR_FIELDS = [
    ("food_name", "食品名称"),
    ("ingredients_text", "配料表"),
    ("nutrition_text", "营养成分表"),
    ("net_content", "净含量"),
    ("production_date", "生产日期"),
    ("shelf_life", "保质期"),
    ("expiry_date", "到期日期"),
    ("storage", "贮存条件"),
    ("producer", "生产者"),
    ("standard_no", "产品标准号"),
    ("allergen", "致敏物质提示"),
]


class OcrResult(db.Model):
    __tablename__ = "ocr_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    is_demo: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")  # success | partial | failed
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    corrected_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    field_confidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    field_flags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    low_confidence_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    record = relationship("AnalysisRecord", back_populates="ocr")

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "provider_label": self.provider_label,
            "engine_version": self.engine_version,
            "is_demo": bool(self.is_demo),
            "status": self.status,
            "raw_text": self.raw_text,
            "corrected_text": self.corrected_text,
            "fields": self.fields or {},
            "field_confidence": self.field_confidence or {},
            "field_flags": self.field_flags or {},
            "low_confidence_fields": self.low_confidence_fields or [],
            "missing_fields": self.missing_fields or [],
            "duration_ms": self.duration_ms,
            "field_labels": dict(OCR_FIELDS),
            "meta": {
                "preprocess": (self.raw_payload or {}).get("preprocess"),
                "passes": (self.raw_payload or {}).get("passes"),
                "line_count": (self.raw_payload or {}).get("line_count"),
                "warning": (self.raw_payload or {}).get("warning"),
            },
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "corrected_at": self.corrected_at.isoformat() + "Z" if self.corrected_at else None,
        }
