"""食品安全知识库条目。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .user import utcnow

CATEGORIES = {
    "additive": "食品添加剂",
    "ingredient": "常见配料",
    # 菜品既可由独立菜品营养库提供，也可在后台知识库手动维护
    "dish": "菜品",
    "nutrition": "营养术语",
    "label_rule": "标签与核查规则",
    "safety": "食品安全常识",
}

SOURCE_TYPES = {
    "standard_name": "标准/法规名称（未收录原文）",
    "textbook": "教材与专业书籍",
    "public_health": "公共卫生与科普机构",
    "official_website": "官方网站在线资料",
    "community": "社区资料（需谨慎引用）",
    "editorial": "平台编辑整理（概述性内容）",
}

VERIFICATION = {
    "verified": "已核对来源名称与要点",
    "pending": "待核验（仅作参考，请以官方原文为准）",
}


class KnowledgeEntry(db.Model):
    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    aliases: Mapped[str] = mapped_column(String(300), nullable=False, default="")  # 逗号分隔，便于检索
    keywords: Mapped[str] = mapped_column(String(300), nullable=False, default="")  # 检索用关键词
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    usage_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="editorial")
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="published", index=True)  # published | draft | offline
    scope: Mapped[str] = mapped_column(String(200), nullable=False, default="预包装食品标签")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=100)

    # 菜品营养数据（每 100g），由后台保存时自动估算或用人工数据覆盖
    calories_per_100g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    carbs_per_100g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    protein_per_100g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fat_per_100g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    typical_portion_g: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def is_ai_generated(self) -> bool:
        return (self.created_by or "").upper() == "AI" or (self.source_name or "").startswith("AI生成")

    def to_public(self, *, brief: bool = False) -> dict:
        data = {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "aliases": [a for a in (self.aliases or "").split(",") if a],
            "keywords": [k for k in (self.keywords or "").split() if k],
            "category": self.category,
            "category_label": CATEGORIES.get(self.category, self.category),
            "summary": self.summary,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "source_type_label": SOURCE_TYPES.get(self.source_type, self.source_type),
            "verification_status": self.verification_status,
            "verification_label": VERIFICATION.get(self.verification_status, self.verification_status),
            "version": self.version,
            "status": self.status,
            "scope": self.scope,
            "published_at": self.published_at.isoformat() + "Z" if self.published_at else None,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "is_featured": bool(self.is_featured),
            "is_ai_generated": self.is_ai_generated,
            "source_kind": "ai" if self.is_ai_generated else "local",
            "calories": self.calories_per_100g,
            "carbs": self.carbs_per_100g,
            "protein": self.protein_per_100g,
            "fat": self.fat_per_100g,
            "calories_per_100g": self.calories_per_100g,
            "carbs_per_100g": self.carbs_per_100g,
            "protein_per_100g": self.protein_per_100g,
            "fat_per_100g": self.fat_per_100g,
            "typical_portion_g": self.typical_portion_g,
            "nutrition": {
                "calories_per_100g": self.calories_per_100g,
                "carbs_per_100g": self.carbs_per_100g,
                "protein_per_100g": self.protein_per_100g,
                "fat_per_100g": self.fat_per_100g,
                "typical_portion_g": self.typical_portion_g,
            },
        }
        if not brief:
            data["content"] = self.content
            data["usage_note"] = self.usage_note
        return data
