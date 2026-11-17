"""AI Prompt 模板管理模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .user import utcnow


class PromptTemplate(db.Model):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scene: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="deepseek")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1.0")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "scene": self.scene,
            "model": self.model,
            "version": self.version,
            "system_prompt": self.system_prompt or "",
            "status": self.status,
            "status_label": "生效中" if self.status == "active" else "草稿",
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }
