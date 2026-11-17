"""分析记录（贯穿 上传 → OCR → 校正 → AI 分析 → 核查 → 报告）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow

STATUS_LABELS = {
    "uploaded": "已上传",
    "ocr_done": "已识别",
    "corrected": "已校正",
    "analyzed": "分析完成",
    "pending_review": "待复核",
    "reviewed": "已人工修正",
    "failed": "处理失败",
}


class AnalysisRecord(db.Model):
    __tablename__ = "analysis_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    food_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False, index=True)
    data_source: Mapped[str] = mapped_column(String(12), default="real", nullable=False)  # real | demo
    analysis_mode: Mapped[str | None] = mapped_column(String(12), nullable=True)  # ai | rule | demo
    ocr_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    overall_check: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user = relationship("User", back_populates="records")
    image = relationship(
        "UploadedImage", back_populates="record", uselist=False, cascade="all, delete-orphan"
    )
    ocr = relationship("OcrResult", back_populates="record", uselist=False, cascade="all, delete-orphan")
    ingredient = relationship(
        "IngredientAnalysis", back_populates="record", uselist=False, cascade="all, delete-orphan"
    )
    nutrition = relationship("NutritionFact", back_populates="record", uselist=False, cascade="all, delete-orphan")
    check = relationship("LabelCheck", back_populates="record", uselist=False, cascade="all, delete-orphan")
    report = relationship("ReportMeta", back_populates="record", uselist=False, cascade="all, delete-orphan")

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    def to_summary(self) -> dict:
        image = self.image
        return {
            "id": self.id,
            "food_name": self.food_name or "未命名食品",
            "food_name_raw": self.food_name or "",
            "owner_name": (
                (self.user.display_name or self.user.username)
                if self.user
                else ""
            ),
            "data_complete": bool(
                self.status == "analyzed"
                and self.ocr
                and str((self.ocr.fields or {}).get("ingredients_text") or "").strip()
                and str((self.ocr.fields or {}).get("nutrition_text") or "").strip()
                and self.ingredient
                and self.nutrition
                and self.check
            ),
            "brand": self.brand,
            "status": self.status,
            "status_label": self.status_label,
            "data_source": self.data_source,
            "analysis_mode": self.analysis_mode,
            "is_demo": bool(self.is_demo),
            "ocr_provider": self.ocr_provider,
            "overall_check": self.overall_check,
            "summary": self.summary,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "analyzed_at": self.analyzed_at.isoformat() + "Z" if self.analyzed_at else None,
            "image_url": f"/api/records/{self.id}/image" if image else None,
            "image": (
                {
                    "width": image.width,
                    "height": image.height,
                    "size_bytes": image.size_bytes,
                    "mime": image.mime,
                }
                if image
                else None
            ),
            "ingredient_count": len((self.ingredient.ingredients or [])) if self.ingredient else 0,
            "issue_count": (self.check.issue_count if self.check else 0),
            "has_report": bool(self.report),
        }
