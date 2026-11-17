"""AI / 规则模式的配料分析结果。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow

MODE_LABELS = {
    "ai": "大模型分析",
    "rule": "基础规则模式（未配置大模型）",
    "demo": "演示模式（固定样例数据）",
}


class IngredientAnalysis(db.Model):
    __tablename__ = "ingredient_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    mode: Mapped[str] = mapped_column(String(12), nullable=False, default="rule")
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    personalization: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ingredients: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    nutrition_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unknown_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unconfirmed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    record = relationship("AnalysisRecord", back_populates="ingredient")

    def to_public(self) -> dict:
        return {
            "mode": self.mode,
            "mode_label": MODE_LABELS.get(self.mode, self.mode),
            "model": self.model,
            "prompt_version": self.prompt_version,
            "summary": self.summary,
            "tags": self.tags or [],
            "personalization": self.personalization,
            "ingredients": self.ingredients or [],
            "nutrition_notes": self.nutrition_notes or [],
            "unknown_items": self.unknown_items or [],
            "unconfirmed": self.unconfirmed or [],
            "citations": self.citations or [],
            "diff": self.diff,
            "disclaimer": self.disclaimer,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
