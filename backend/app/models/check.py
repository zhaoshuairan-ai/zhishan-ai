"""标签辅助核查结果（审慎三档结论）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow

OVERALL_LABELS = {
    "none_found": "未发现明显问题",
    "needs_review": "需要进一步核实",
    "suspected": "发现疑似问题",
}


class LabelCheck(db.Model):
    __tablename__ = "label_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    ruleset_version: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    overall: Mapped[str] = mapped_column(String(20), nullable=False, default="needs_review")
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    coverage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    record = relationship("AnalysisRecord", back_populates="check")

    @property
    def issue_count(self) -> int:
        return len([i for i in (self.items or []) if i.get("level") in {"suspected", "review"}])

    def to_public(self) -> dict:
        return {
            "ruleset_version": self.ruleset_version,
            "overall": self.overall,
            "overall_label": OVERALL_LABELS.get(self.overall, self.overall),
            "items": self.items or [],
            "counts": self.counts or {},
            "coverage": self.coverage or {},
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }
