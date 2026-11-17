"""管理员后台相关模型：审计日志、核查规则版本、复核备注、用户反馈、服务事件。

设计原则：
1. 审计日志只追加、不修改，记录操作人与结果；
2. 规则修改保留 before/after 快照，旧版本可追溯；
3. 反馈与复核备注按记录/用户关联，便于追责与隐私控制。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .user import utcnow

AUDIT_ACTIONS = {
    "admin.login": "管理员登录",
    "admin.logout": "管理员退出",
    "admin.bootstrap": "初始化管理员",
    "user.update": "用户状态变更",
    "user.role": "变更用户角色",
    "user.role_change": "变更用户角色",
    "user.delete": "删除用户账号",
    "user.reset_password": "重置用户密码",
    "knowledge.create": "新增知识条目",
    "knowledge.update": "修改知识条目",
    "knowledge.publish": "发布/下架知识条目",
    "knowledge.verify": "核验知识条目",
    "knowledge.delete": "删除知识条目",
    "rule.create": "新增核查规则",
    "rule.update": "修改核查规则",
    "rule.toggle": "启用/停用核查规则",
    "rule.delete": "删除核查规则",
    "record.note": "添加复核备注",
    "record.review": "审核分析记录",
    "record.delete": "删除分析记录",
    "feedback.resolve": "处理用户反馈",
}

AUDIT_RESULTS = {"success": "成功", "failure": "失败", "denied": "被拒绝"}

RULE_ACTIONS = {
    "create": "创建",
    "update": "修改",
    "toggle": "启停",
    "delete": "删除",
}

FEEDBACK_STATUS = {"open": "待处理", "resolved": "已处理"}


AUDIT_TARGET_LABELS = {
    "knowledge": "知识条目",
    "record": "分析记录",
    "user": "用户",
    "rule": "核查规则",
    "feedback": "用户反馈",
    "admin_session": "管理员会话",
}

AUDIT_FIELD_LABELS = {
    "title": "标题",
    "food_name": "食品",
    "name": "名称",
    "brand": "品牌",
    "status": "状态",
    "overall_check": "核查",
    "username": "用户",
    "role": "角色",
    "is_active": "状态",
    "version": "版本",
    "records": "记录数",
    "note": "备注",
    "reason": "原因",
}

AUDIT_VALUE_LABELS = {
    "draft": "待审核",
    "published": "已发布",
    "offline": "已下架",
    "active": "启用",
    "disabled": "停用",
    "admin": "管理员",
    "user": "普通用户",
    "none_found": "正常放行",
    "needs_review": "需人工介入",
    "analyzed": "分析完成",
    "pending_review": "待复核",
    "reviewed": "已人工修正",
    "uploaded": "已上传",
    "ocr_done": "已识别",
    "corrected": "已校正",
    "suspected": "疑似风险",
    "success": "成功",
    "failure": "失败",
    "denied": "拒绝",
    "open": "待处理",
    "resolved": "已处理",
}


def _audit_value(value) -> str:
    if isinstance(value, bool):
        return "启用" if value else "停用"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    text = str(value).strip()
    return AUDIT_VALUE_LABELS.get(text, text)


def format_audit_detail(
    action: str,
    detail: dict | None,
    *,
    target_type: str = "",
    target_id: str = "",
) -> str:
    data = detail or {}

    if action.endswith(".delete"):
        if target_type == "user":
            name = data.get("username") or target_id
            return f"删除对象：用户 {name}".strip()
        name = data.get("title") or data.get("food_name") or data.get("name") or target_id
        label = AUDIT_TARGET_LABELS.get(target_type, "对象")
        return f"删除对象：{label}「{name}」".strip()

    preferred = (
        "title", "food_name", "username", "brand", "status",
        "overall_check", "role", "is_active", "version", "records",
    )
    parts: list[str] = []
    for key in preferred:
        if key not in data:
            continue
        value = _audit_value(data.get(key))
        if not value:
            continue
        label = AUDIT_FIELD_LABELS.get(key, key)
        parts.append(f"{label}：{value}")

    if not parts:
        for key, value in data.items():
            if key in {"slug", "path", "method"}:
                continue
            text = _audit_value(value)
            if text:
                parts.append(f"{AUDIT_FIELD_LABELS.get(key, key)}：{text}")

    return "；".join(parts)


def audit_target_label(target_type: str, target_id: str) -> str:
    label = AUDIT_TARGET_LABELS.get(target_type)
    if not label:
        return target_id or ""
    return f"{label} #{target_id}" if target_id else label


class AuditLog(db.Model):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_username: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_username": self.actor_username,
            "action": self.action,
            "action_label": AUDIT_ACTIONS.get(self.action, self.action),
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_label": audit_target_label(
                self.target_type,
                self.target_id,
            ),
            "detail": self.detail or {},
            "detail_text": format_audit_detail(
                self.action,
                self.detail,
                target_type=self.target_type,
                target_id=self.target_id,
            ),
            "result": self.result,
            "result_label": AUDIT_RESULTS.get(self.result, self.result),
            "ip": self.ip,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class CheckRule(db.Model):
    """可后台维护的核查规则元数据（判定逻辑仍在 checker.py）。"""

    __tablename__ = "check_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="其他")
    level_default: Mapped[str] = mapped_column(String(20), nullable=False, default="review")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    basis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    scope: Mapped[str] = mapped_column(String(200), nullable=False, default="预包装食品标签（图片可见区域）")
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    created_by: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    revisions = relationship(
        "RuleRevision", back_populates="rule", cascade="all, delete-orphan", order_by="RuleRevision.id"
    )

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "level_default": self.level_default,
            "description": self.description,
            "basis": self.basis,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "scope": self.scope,
            "version": self.version,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "enabled": bool(self.enabled),
            "sort_order": self.sort_order,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }

    def snapshot(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "level_default": self.level_default,
            "description": self.description,
            "basis": self.basis,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "scope": self.scope,
            "version": self.version,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "enabled": bool(self.enabled),
        }


class RuleRevision(db.Model):
    __tablename__ = "rule_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(
        String(60), ForeignKey("check_rules.rule_id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="update")
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    note: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    rule = relationship("CheckRule", back_populates="revisions")

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "action": self.action,
            "action_label": RULE_ACTIONS.get(self.action, self.action),
            "version": self.version,
            "before": self.before,
            "after": self.after,
            "changed_by": self.changed_by,
            "note": self.note,
            "changed_at": self.changed_at.isoformat() + "Z" if self.changed_at else None,
        }


class RecordNote(db.Model):
    """管理员对某条分析记录的复核备注（保留历史）。"""

    __tablename__ = "record_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_username: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "record_id": self.record_id,
            "admin_username": self.admin_username,
            "content": self.content,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class Feedback(db.Model):
    """用户提交的问题反馈，管理员处理后标记状态。"""

    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    record_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contact: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    reply: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 兼容旧字段：新代码同时把回复写入 reply_content，C 端接口直接返回该字段
    reply_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    handled_by: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "record_id": self.record_id,
            "content": self.content,
            "contact": self.contact,
            "status": self.status,
            "status_label": FEEDBACK_STATUS.get(self.status, self.status),
            "reply": self.reply,
            "reply_content": self.reply_content or self.reply,
            "handled_by": self.handled_by,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }


class ServiceEvent(db.Model):
    """服务事件（错误/异常）记录，供系统监控页展示最近错误。"""

    __tablename__ = "service_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="api", index=True)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="error")
    message: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "level": self.level,
            "message": self.message,
            "detail": self.detail or {},
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
