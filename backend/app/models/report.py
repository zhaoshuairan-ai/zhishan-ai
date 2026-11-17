"""报告元数据。报告正文由真实记录数据实时渲染，不缓存易失内容。"""
from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow


def generate_report_no(record_id: int) -> str:
    stamp = datetime.now().strftime("%Y%m%d")
    return f"FS-{stamp}-{record_id:04d}-{secrets.token_hex(2).upper()}"


class ReportMeta(db.Model):
    __tablename__ = "report_meta"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    report_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    generated_count: Mapped[int] = mapped_column(nullable=False, default=1)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    record = relationship("AnalysisRecord", back_populates="report")

    def to_public(self) -> dict:
        return {
            "report_no": self.report_no,
            "version": self.version,
            "generated_at": self.generated_at.isoformat() + "Z" if self.generated_at else None,
            "generated_count": self.generated_count,
        }
