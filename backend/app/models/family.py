"""家庭共享：同一家庭的食材库存共享。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .user import utcnow


class Family(db.Model):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(primary_key=True)
    invite_code: Mapped[str] = mapped_column(String(12), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False, default="我的家庭")
    created_by: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "invite_code": self.invite_code,
            "name": self.name,
            "owner_id": self.created_by,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
