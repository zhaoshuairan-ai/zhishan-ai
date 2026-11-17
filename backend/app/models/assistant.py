"""食安科普与辟谣助手（RAG 知识库）的数据模型。

设计要点：
- AssistantEntry 是对外可引用的「权威问答条目」，一条 = 一个可核实结论 + 来源清单；
- ChatSession / ChatMessage 只保存用户与助手的对话，便于跨设备查看历史；
- 回答里的 sources 是 JSON，直接存下当时引用的来源快照，避免条目后续修改导致历史记录失真。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow

ASSISTANT_CATEGORIES = {
    "myth": "食物相克与常见谣言",
    "storage": "储存、保鲜与剩菜",
    "additive": "食品添加剂",
    "label": "食品标签与营销话术",
    "nutrition": "营养与膳食",
    "processing": "加工、烹饪与包装",
    "special": "特殊人群",
    "safety": "食品安全常识",
}

SOURCE_KINDS = {
    "standard": "国家标准 / 法规",
    "guideline": "膳食指南 / 营养共识",
    "official": "监管部门 / 官方机构",
    "rumor_platform": "辟谣平台",
    "textbook": "教材 / 专业书籍",
}

VERIFICATION_LABELS = {
    "verified": "已核对来源与要点",
    "pending": "待核验（请以官方原文为准）",
}


class AssistantEntry(db.Model):
    __tablename__ = "assistant_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 逗号分隔的口语化问法
    keywords: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 一句话结论
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 原因解释
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 依据
    caveat: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 注意事项
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def to_public(self, *, brief: bool = False) -> dict:
        data = {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "category": self.category,
            "category_label": ASSISTANT_CATEGORIES.get(self.category, self.category),
            "summary": self.summary,
            "verification_status": self.verification_status,
            "verification_label": VERIFICATION_LABELS.get(self.verification_status, self.verification_status),
            "sources": self.sources or [],
        }
        if brief:
            return data
        data.update(
            {
                "aliases": [a for a in (self.aliases or "").split(",") if a],
                "keywords": [k for k in (self.keywords or "").split() if k],
                "detail": self.detail,
                "evidence": self.evidence,
                "caveat": self.caveat,
                "version": self.version,
                "is_featured": bool(self.is_featured),
            }
        )
        return data


class ChatSession(db.Model):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="新的对话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )

    def to_public(self, *, with_messages: bool = False, message_count: int | None = None) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }
        if message_count is not None:
            data["message_count"] = message_count
        if with_messages:
            data["messages"] = [message.to_public() for message in self.messages]
        return data


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="retrieval")
    matched_slug: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "mode": self.mode,
            "matched_slug": self.matched_slug,
            "sources": self.sources or [],
            "payload": self.payload or {},
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
