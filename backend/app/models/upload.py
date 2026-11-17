"""上传图片元数据（文件本身保存在受控目录 uploads/ 中）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow


class UploadedImage(db.Model):
    __tablename__ = "uploaded_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stored_name: Mapped[str] = mapped_column(String(80), nullable=False)  # 服务端生成，不含路径
    original_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    ext: Mapped[str] = mapped_column(String(8), nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    record = relationship("AnalysisRecord", back_populates="image")

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "original_name": self.original_name,
            "ext": self.ext,
            "mime": self.mime,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "url": f"/api/records/{self.record_id}/image",
        }
