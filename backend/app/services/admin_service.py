"""管理员服务：统计、用户、记录、知识库、规则、监控与审计。

安全约定：
- 本模块只被 /api/admin/* 调用，路由层统一加了 admin_required；
- 审计日志记录操作人快照（用户名），即使账号被删除也能追溯；
- 用户密码只允许「重置」流程，任何接口都不返回 password_hash；
- 监控接口只返回状态与数量，不返回 Key、密码等配置。
"""
from __future__ import annotations

import secrets
import string
from pathlib import Path
from datetime import datetime, timedelta, timezone

from flask import current_app, g, request
from sqlalchemy import and_, func, or_

from ..extensions import db
from ..models import (
    AnalysisRecord,
    AssistantEntry,
    AuditLog,
    CheckRule,
    Feedback,
    KnowledgeEntry,
    RecordNote,
    RuleRevision,
    ServiceEvent,
    User,
)
from ..models.knowledge import CATEGORIES
from ..rules.label_rules import RULES, RULESET
from ..utils.errors import ConflictError, NotFoundError, ValidationError
from ..utils.security import hash_password, verify_password
from . import dish_nutrition_service

PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# ---------------------------------------------------------------- 基础工具
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _client_ip() -> str:
    from flask import has_request_context

    if not has_request_context():
        return "cli"
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.remote_addr or "")[:64]


def actor() -> User | None:
    return getattr(g, "current_user", None)


def log_audit(
    action: str,
    *,
    target_type: str = "",
    target_id: str | int = "",
    detail: dict | None = None,
    result: str = "success",
) -> AuditLog:
    user = actor()
    entry = AuditLog(
        actor_id=getattr(user, "id", None),
        actor_username=getattr(user, "username", "") or "",
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        detail=detail or {},
        result=result,
        ip=_client_ip(),
        created_at=_now(),
    )
    db.session.add(entry)
    return entry


def record_event(kind: str, message: str, *, detail: dict | None = None, level: str = "error") -> None:
    """写入服务事件；失败不能让主流程报错。"""
    try:
        db.session.add(
            ServiceEvent(
                kind=kind[:20],
                level=level[:10],
                message=message[:300],
                detail=detail or {},
                created_at=_now(),
            )
        )
        db.session.commit()
    except Exception:  # pragma: no cover - 监控失败不影响业务
        db.session.rollback()


def _paginate(query, page: int, per_page: int) -> dict:
    page = max(1, int(page or 1))
    per_page = min(MAX_PAGE_SIZE, max(1, int(per_page or PAGE_SIZE)))
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 1,
    }


# ---------------------------------------------------------------- 管理员认证
ADMIN_MIN_PASSWORD = 10


def validate_admin_password(password: str) -> str:
    password = str(password or "")
    if len(password) < ADMIN_MIN_PASSWORD:
        raise ValidationError(f"密码至少 {ADMIN_MIN_PASSWORD} 位")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValidationError("密码需要同时包含字母和数字")
    if password.lower() in {"admin123456", "password123", "1234567890"}:
        raise ValidationError("该密码过于常见，请更换")
    return password


def create_admin(
    username: str,
    password: str,
    *,
    display_name: str = "",
    email: str | None = None,
    promote: bool = False,
    allow_weak: bool = False,
) -> tuple[User, bool]:
    """创建（或提升）管理员账号。返回 (用户, 是否新建)。"""
    username = (username or "").strip()
    if not username or len(username) > 20:
        raise ValidationError("用户名需为 1-20 个字符")
    if allow_weak:
        # 仅限本地演示：调用方必须显式传入该参数
        if len(str(password or "")) < 8:
            raise ValidationError("即使使用 --allow-weak，密码也至少 8 位")
    else:
        validate_admin_password(password)
    existing = User.query.filter(func.lower(User.username) == username.lower()).first()
    created = False
    if existing:
        if not promote:
            raise ConflictError("该用户名已存在；如需提升为管理员请使用 --promote")
        user = existing
        user.role = "admin"
        user.is_active = True
    else:
        user = User(
            username=username,
            display_name=display_name or "管理员",
            email=email or None,
            password_hash=hash_password(password),
            is_demo=False,
            role="admin",
            is_active=True,
        )
        db.session.add(user)
        created = True
    user.password_hash = hash_password(password)
    db.session.flush()
    log_audit(
        "admin.bootstrap",
        target_type="user",
        target_id=user.id,
        detail={"username": username, "created": created, "via": "cli"},
    )
    db.session.commit()
    return user, created


def authenticate_admin(username: str, password: str) -> User:
    user = User.query.filter(func.lower(User.username) == (username or "").strip().lower()).first()
    if user is None or not verify_password(user.password_hash, password or ""):
        raise ValidationError("用户名或密码不正确")
    if user.role != "admin":
        raise ValidationError("该账号没有管理员权限")
    if not user.is_active:
        raise ValidationError("该管理员账号已被停用")
    user.last_login_at = _now()
    db.session.commit()
    return user


def reset_user_password(user_id: int) -> str:
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    alphabet = string.ascii_letters + string.digits
    temp_password = "".join(secrets.choice(alphabet) for _ in range(6)) + "".join(
        secrets.choice("23456789") for _ in range(4)
    )
    user.password_hash = hash_password(temp_password)
    # 重置后强制该用户所有会话失效
    from ..models import AuthSession

    AuthSession.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    log_audit(
        "user.reset_password",
        target_type="user",
        target_id=user.id,
        detail={"username": user.username, "sessions_revoked": True},
    )
    db.session.commit()
    return temp_password


# ---------------------------------------------------------------- 仪表盘
def dashboard_stats() -> dict:
    now = _now()
    week_ago = now - timedelta(days=7)
    users_total = User.query.count()
    users_active = User.query.filter_by(is_active=True).count()
    users_disabled = User.query.filter_by(is_active=False).count()
    users_admin = User.query.filter_by(role="admin").count()
    users_new = User.query.filter(User.created_at >= week_ago).count()

    records_total = AnalysisRecord.query.count()
    analyzed = AnalysisRecord.query.filter_by(status="analyzed").count()
    failed = AnalysisRecord.query.filter_by(status="failed").count()
    real_records = AnalysisRecord.query.filter_by(data_source="real").count()
    success_rate = round(analyzed / records_total * 100, 1) if records_total else 0.0

    knowledge_total = KnowledgeEntry.query.count()
    knowledge_published = KnowledgeEntry.query.filter_by(status="published").count()
    knowledge_draft = KnowledgeEntry.query.filter(KnowledgeEntry.status != "published").count()
    assistant_total = AssistantEntry.query.count()
    rules_total = CheckRule.query.count()
    rules_enabled = CheckRule.query.filter_by(enabled=True).count()
    feedback_open = Feedback.query.filter_by(status="open").count()

    # 近 14 天按天统计（真实数据；没有记录的日期补 0）
    start = (now - timedelta(days=13)).date()
    rows = (
        db.session.query(func.date(AnalysisRecord.created_at), func.count(AnalysisRecord.id))
        .filter(AnalysisRecord.created_at >= datetime.combine(start, datetime.min.time()))
        .group_by(func.date(AnalysisRecord.created_at))
        .all()
    )
    counts = {str(day): int(count) for day, count in rows}
    trend = []
    for offset in range(14):
        day = start + timedelta(days=offset)
        trend.append({"date": day.isoformat(), "count": counts.get(day.isoformat(), 0)})

    status_rows = (
        db.session.query(AnalysisRecord.status, func.count(AnalysisRecord.id))
        .group_by(AnalysisRecord.status)
        .all()
    )
    recent_audit = (
        AuditLog.query.order_by(AuditLog.id.desc()).limit(6).all()
    )
    return {
        "totals": {
            "users": users_total,
            "users_active": users_active,
            "users_disabled": users_disabled,
            "users_admin": users_admin,
            "users_new_7d": users_new,
            "records": records_total,
            "analyzed": analyzed,
            "failed": failed,
            "success_rate": success_rate,
            "real_records": real_records,
            "knowledge": knowledge_total,
            "knowledge_published": knowledge_published,
            "knowledge_draft": knowledge_draft,
            "assistant_entries": assistant_total,
            "rules": rules_total,
            "rules_enabled": rules_enabled,
            "feedback_open": feedback_open,
        },
        "trend": trend,
        "status_distribution": [{"status": status, "count": int(count)} for status, count in status_rows],
        "recent_audit": [item.to_public() for item in recent_audit],
        "generated_at": _iso(now),
    }


# ---------------------------------------------------------------- 用户管理
def list_users(*, q: str = "", status: str = "", role: str = "", page: int = 1, per_page: int = PAGE_SIZE) -> dict:
    query = User.query
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.username.ilike(like), User.display_name.ilike(like)))
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "disabled":
        query = query.filter_by(is_active=False)
    if role in {"admin", "user"}:
        query = query.filter_by(role=role)
    query = query.order_by(User.id.asc())
    result = _paginate(query, page, per_page)
    items = []
    for user in result["items"]:
        item = user.to_public()
        item.update(
            {
                "is_active": bool(user.is_active),
                "role": user.role,
                "last_login_at": _iso(user.last_login_at),
                "record_count": AnalysisRecord.query.filter_by(user_id=user.id).count(),
            }
        )
        items.append(item)
    result["items"] = items
    result["stats"] = {
        "total": User.query.count(),
        "active": User.query.filter_by(is_active=True).count(),
        "disabled": User.query.filter_by(is_active=False).count(),
        "admin": User.query.filter_by(role="admin").count(),
    }
    return result


def set_user_active(user_id: int, active: bool) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    current = actor()
    if current and current.id == user.id and not active:
        raise ValidationError("不能停用当前登录的管理员账号")
    if user.role == "admin" and not active:
        remaining = User.query.filter(User.role == "admin", User.is_active.is_(True), User.id != user.id).count()
        if remaining == 0:
            raise ValidationError("至少需要保留一个可用的管理员账号")
    user.is_active = bool(active)
    log_audit(
        "user.update",
        target_type="user",
        target_id=user.id,
        detail={"username": user.username, "is_active": user.is_active},
    )
    db.session.commit()
    return user


def set_user_role(user_id: int, role: str) -> User:
    """把普通用户提升为管理员，或把管理员降级为普通用户。"""
    if role not in {"user", "admin"}:
        raise ValidationError("角色只能是 user 或 admin")
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    current = actor()
    if current and current.id == user.id and role != "admin":
        raise ValidationError("不能取消当前登录管理员的管理权限")
    if user.role == "admin" and role == "user":
        remaining = User.query.filter(User.role == "admin", User.is_active.is_(True), User.id != user.id).count()
        if remaining == 0:
            raise ValidationError("至少需要保留一个可用的管理员账号")
    user.role = role
    log_audit(
        "user.role",
        target_type="user",
        target_id=user.id,
        detail={"username": user.username, "role": role},
    )
    db.session.commit()
    return user


def delete_user(user_id: int) -> dict:
    """删除用户账号及其关联数据；不允许删除自己或最后一个管理员。"""
    from ..models import ChatMessage, ChatSession, HealthProfile, PantryItem, RecipePlan

    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    current = actor()
    if current and current.id == user.id:
        raise ValidationError("不能删除当前登录的管理员账号")
    if user.role == "admin":
        remaining = User.query.filter(User.role == "admin", User.is_active.is_(True), User.id != user.id).count()
        if remaining == 0:
            raise ValidationError("至少需要保留一个可用的管理员账号")

    username = user.username
    record_count = AnalysisRecord.query.filter_by(user_id=user.id).count()

    # 尽力删除磁盘上的图片文件，避免留下孤儿文件
    upload_dir = Path(current_app.config["UPLOAD_DIR"])
    removed_files = 0
    for record in AnalysisRecord.query.filter_by(user_id=user.id).all():
        if record.image and record.image.stored_name:
            target = (upload_dir / record.image.stored_name).resolve()
            try:
                if upload_dir.resolve() in target.parents and target.is_file():
                    target.unlink()
                    removed_files += 1
            except OSError:
                pass

    # 反馈与账号一起清理，避免留下指向已删除用户的孤儿数据
    Feedback.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    PantryItem.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    HealthProfile.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    RecipePlan.query.filter_by(user_id=user.id).delete(synchronize_session=False)

    session_ids = [row[0] for row in db.session.query(ChatSession.id).filter_by(user_id=user.id).all()]
    if session_ids:
        ChatMessage.query.filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
        ChatSession.query.filter(ChatSession.id.in_(session_ids)).delete(synchronize_session=False)

    db.session.delete(user)
    log_audit(
        "user.delete",
        target_type="user",
        target_id=user_id,
        detail={"username": username, "role": user.role, "records": record_count, "files": removed_files},
    )
    db.session.commit()
    return {"deleted": True, "id": user_id, "records": record_count, "files": removed_files}


# ---------------------------------------------------------------- 记录管理
def list_records(*, q: str = "", status: str = "", user_id: int | None = None, page: int = 1, per_page: int = PAGE_SIZE) -> dict:
    query = AnalysisRecord.query
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(AnalysisRecord.food_name.ilike(like), AnalysisRecord.brand.ilike(like)))
    if status:
        query = query.filter_by(status=status)
    if user_id:
        query = query.filter_by(user_id=user_id)
    query = query.order_by(AnalysisRecord.id.asc())
    result = _paginate(query, page, per_page)
    items = []
    for record in result["items"]:
        item = record.to_summary()
        item["username"] = record.user.username if record.user else ""
        item["note_count"] = RecordNote.query.filter_by(record_id=record.id).count()
        items.append(item)
    result["items"] = items
    result["status_options"] = [
        {"value": "uploaded", "label": "已上传"},
        {"value": "ocr_done", "label": "已识别"},
        {"value": "corrected", "label": "已校正"},
        {"value": "analyzed", "label": "分析完成"},
        {"value": "pending_review", "label": "待复核"},
        {"value": "reviewed", "label": "已人工修正"},
        {"value": "failed", "label": "处理失败"},
    ]
    return result


def record_detail(record_id: int) -> dict:
    record = db.session.get(AnalysisRecord, record_id)
    if record is None:
        raise NotFoundError("分析记录不存在")
    from .analysis_service import build_detail

    detail = build_detail(record)
    detail["owner"] = {
        "id": record.user.id,
        "username": record.user.username,
        "display_name": record.user.display_name,
        "is_demo": bool(record.user.is_demo),
    } if record.user else None
    detail["notes"] = [note.to_public() for note in RecordNote.query.filter_by(record_id=record.id).order_by(RecordNote.id.desc()).all()]
    detail["feedback"] = [
        item.to_public() for item in Feedback.query.filter_by(record_id=record.id).order_by(Feedback.id.desc()).all()
    ]
    return detail


def add_record_note(record_id: int, content: str, note: str = "") -> RecordNote:
    record = db.session.get(AnalysisRecord, record_id)
    if record is None:
        raise NotFoundError("分析记录不存在")
    content = (content or "").strip()
    if len(content) < 2:
        raise ValidationError("备注至少 2 个字符")
    if len(content) > 1000:
        raise ValidationError("备注不能超过 1000 个字符")
    user = actor()
    entry = RecordNote(
        record_id=record.id,
        admin_id=getattr(user, "id", None),
        admin_username=getattr(user, "username", "") or "",
        content=content,
        created_at=_now(),
    )
    db.session.add(entry)
    log_audit(
        "record.note",
        target_type="record",
        target_id=record.id,
        detail={"food_name": record.food_name, "note": note[:120]},
    )
    db.session.commit()
    return entry


def review_record(record_id: int, payload: dict) -> dict:
    """管理员人工审核并修正记录，状态变为已人工修正。"""
    record = db.session.get(AnalysisRecord, record_id)
    if record is None:
        raise NotFoundError("分析记录不存在")

    food_name = str(payload.get("food_name") or "").strip()
    if not food_name:
        raise ValidationError("食品名称不能为空")
    if len(food_name) > 120:
        raise ValidationError("食品名称不能超过 120 个字符")

    brand = str(payload.get("brand") or "").strip()[:120]
    summary = str(payload.get("summary") or "").strip()[:2000]
    overall = str(payload.get("overall_check") or "needs_review").strip()
    allowed_overall = {"none_found", "needs_review", "suspected"}
    if overall not in allowed_overall:
        raise ValidationError("核查结论不合法")

    record.food_name = food_name
    record.brand = brand or None
    record.summary = summary or None
    record.overall_check = overall
    record.status = "reviewed"

    ocr_text = str(payload.get("ocr_text") or "").strip()
    if record.ocr is not None:
        if ocr_text:
            record.ocr.corrected_text = ocr_text[:20000]
            fields = dict(record.ocr.fields or {})
            fields["food_name"] = food_name
            record.ocr.fields = fields
        if brand:
            record.ocr.fields = {**(record.ocr.fields or {}), "brand": brand}

    ingredient_summary = str(payload.get("ingredient_summary") or "").strip()
    if record.ingredient is not None and ingredient_summary:
        record.ingredient.summary = ingredient_summary[:2000]

    if record.check is not None:
        record.check.overall = overall

    log_audit(
        "record.review",
        target_type="record",
        target_id=record.id,
        detail={
            "food_name": food_name,
            "brand": brand,
            "overall_check": overall,
            "status": "reviewed",
        },
    )
    db.session.commit()
    return record_detail(record.id)


def delete_record(record_id: int, *, confirm: bool) -> dict:
    if not confirm:
        raise ValidationError("删除记录需要二次确认（confirm=true）")
    record = db.session.get(AnalysisRecord, record_id)
    if record is None:
        raise NotFoundError("分析记录不存在")
    food_name = record.food_name
    owner = record.user.username if record.user else ""
    db.session.delete(record)
    log_audit(
        "record.delete",
        target_type="record",
        target_id=record_id,
        detail={"food_name": food_name, "owner": owner},
    )
    db.session.commit()
    return {"deleted": True, "id": record_id}


def list_feedback(*, status: str = "", page: int = 1, per_page: int = PAGE_SIZE) -> dict:
    query = Feedback.query
    if status in {"open", "resolved"}:
        query = query.filter_by(status=status)
    query = query.order_by(Feedback.id.desc())
    result = _paginate(query, page, per_page)
    result["items"] = [
        {
            **item.to_public(),
            "username": (db.session.get(User, item.user_id).username if db.session.get(User, item.user_id) else ""),
        }
        for item in result["items"]
    ]
    result["stats"] = {
        "open": Feedback.query.filter_by(status="open").count(),
        "resolved": Feedback.query.filter_by(status="resolved").count(),
    }
    return result


def resolve_feedback(feedback_id: int, *, status: str, reply: str = "") -> Feedback:
    item = db.session.get(Feedback, feedback_id)
    if item is None:
        raise NotFoundError("反馈不存在")
    if status not in {"open", "resolved"}:
        raise ValidationError("状态只能是 open 或 resolved")
    reply = (reply or "").strip()
    if status == "resolved" and not reply:
        raise ValidationError("处理反馈时必须填写回复内容")
    item.status = status
    # 双写：reply 兼容旧前端，reply_content 为新接口/C 端标准字段
    item.reply = reply[:2000]
    item.reply_content = reply[:2000]
    item.handled_by = getattr(actor(), "username", "") or ""
    log_audit(
        "feedback.resolve",
        target_type="feedback",
        target_id=item.id,
        detail={"status": status, "has_reply": bool(item.reply_content or item.reply)},
    )
    db.session.commit()
    return item


# ---------------------------------------------------------------- 知识库管理
def list_knowledge_admin(
    *,
    q: str = "",
    category: str = "",
    status: str = "",
    source: str = "",
    verification: str = "",
    page: int = 1,
    per_page: int = PAGE_SIZE,
) -> dict:
    query = KnowledgeEntry.query
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(KnowledgeEntry.title.ilike(like), KnowledgeEntry.slug.ilike(like), KnowledgeEntry.keywords.ilike(like))
        )
    if category in CATEGORIES:
        query = query.filter_by(category=category)
    if status == "published":
        # 已发布对后台的含义是：发布态 + 已核验，C 端同样使用这个口径
        query = query.filter(
            KnowledgeEntry.status == "published",
            KnowledgeEntry.verification_status == "verified",
        )
    elif status in {"pending", "draft"}:
        # 待审核 = 草稿 + 已发布但尚未核验（兼容旧版 draft 参数）
        query = query.filter(
            or_(
                KnowledgeEntry.status == "draft",
                and_(
                    KnowledgeEntry.status == "published",
                    KnowledgeEntry.verification_status != "verified",
                ),
            )
        )
    elif status == "offline":
        query = query.filter(KnowledgeEntry.status == "offline")
    if source == "ai":
        query = query.filter(KnowledgeEntry.source_name.like("AI生成%"))
    elif source == "local":
        query = query.filter(~KnowledgeEntry.source_name.like("AI生成%"))
    if verification in {"pending", "verified"}:
        query = query.filter_by(verification_status=verification)
    query = query.order_by(KnowledgeEntry.id.asc())
    result = _paginate(query, page, per_page)
    result["items"] = [item.to_public() for item in result["items"]]
    result["categories"] = [{"value": key, "label": label} for key, label in CATEGORIES.items()]
    total = KnowledgeEntry.query.count()
    offline = KnowledgeEntry.query.filter_by(status="offline").count()
    published = KnowledgeEntry.query.filter(
        KnowledgeEntry.status == "published",
        KnowledgeEntry.verification_status == "verified",
    ).count()
    pending = total - published - offline
    result["stats"] = {
        "total": total,
        "published": published,
        "pending": pending,
        # 旧字段保留为 pending 的别名，避免旧前端读取到错误的 0
        "draft": pending,
        "offline": offline,
        "verified": KnowledgeEntry.query.filter_by(verification_status="verified").count(),
        "ai": KnowledgeEntry.query.filter(KnowledgeEntry.source_name.like("AI生成%")).count(),
        "local": KnowledgeEntry.query.filter(~KnowledgeEntry.source_name.like("AI生成%")).count(),
    }
    current_app.logger.info(
        "[knowledge-admin] status=%s verification=%s total=%s filtered=%s stats=%s",
        status or "all",
        verification or "all",
        result["stats"]["total"],
        result["total"],
        result["stats"],
    )
    return result


NUTRITION_CATEGORIES = {"dish", "ingredient"}


def _auto_fill_nutrition_if_needed(entry: KnowledgeEntry) -> dict:
    """只对菜品/常见配料做营养测算，其他分类直接跳过。"""
    category = (getattr(entry, "category", "") or "").strip()

    if category not in NUTRITION_CATEGORIES:
        result = {
            "status": "skipped",
            "message": "该分类不需要营养测算",
            "filled_fields": [],
        }
        entry._nutrition_ai = result
        current_app.logger.info(
            "[knowledge-nutrition] skip category=%s title=%s",
            category,
            getattr(entry, "title", ""),
        )
        return result

    result = dish_nutrition_service.auto_fill_dish_nutrition(entry)
    dish_nutrition_service.ensure_dish_summary(entry)

    current_app.logger.info(
        "[knowledge-nutrition] category=%s title=%s status=%s filled=%s",
        category,
        getattr(entry, "title", ""),
        getattr(result, "get", lambda *_: "?")("status"),
        getattr(result, "get", lambda *_: [])("filled_fields"),
    )
    return result


def _knowledge_payload(payload: dict, *, current: KnowledgeEntry | None = None) -> dict:
    from ..utils.validators import clean_text

    title = clean_text(payload.get("title"), max_len=160, field="标题", allow_empty=False).strip()
    summary = clean_text(payload.get("summary"), max_len=2000, field="摘要") or ""
    content = clean_text(payload.get("content"), max_len=8000, field="正文") or ""
    category = str(payload.get("category") or "").strip()
    if category not in CATEGORIES:
        raise ValidationError("分类不合法")
    # 菜品是运营手工维护的基础资料，允许不填来源；其它知识条目仍必须有来源
    if category == "dish":
        source_name = (
            clean_text(
                payload.get("source_name"),
                max_len=200,
                field="来源名称",
                allow_empty=True,
            ).strip()
            or "平台菜品资料整理"
        )
    else:
        source_name = clean_text(
            payload.get("source_name"),
            max_len=200,
            field="来源名称",
            allow_empty=False,
        ).strip()
    verification = str(payload.get("verification_status") or "pending").strip()
    if verification not in {"verified", "pending"}:
        raise ValidationError("核验状态不合法")
    status = str(payload.get("status") or (current.status if current else "draft")).strip()
    if status not in {"published", "draft", "offline"}:
        raise ValidationError("发布状态不合法")
    scope = clean_text(payload.get("scope"), max_len=200, field="适用范围") or ""
    version = clean_text(payload.get("version"), max_len=20, field="版本") or "1.0"
    source_url = clean_text(payload.get("source_url"), max_len=300, field="来源链接")
    if source_url and not source_url.startswith(("http://", "https://")):
        raise ValidationError("来源链接必须以 http(s):// 开头")

    def nutrition_number(
        key: str,
        alias: str,
        fallback: float,
        maximum: float,
    ) -> float:
        raw = payload.get(key, payload.get(alias))
        if raw in (None, ""):
            return float(getattr(current, key, fallback) or fallback) if current else fallback
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise ValidationError(f"{key} 必须是数字")
        if number < 0 or number > maximum:
            raise ValidationError(f"{key} 超出合理范围")
        return round(number, 1)

    return {
        "title": title,
        "summary": summary,
        "content": content,
        "category": category,
        "source_name": source_name,
        "source_url": source_url or None,
        "source_type": str(payload.get("source_type") or (current.source_type if current else "editorial")),
        "verification_status": verification,
        "status": status,
        "scope": scope,
        "version": version,
        "usage_note": clean_text(payload.get("usage_note"), max_len=1000, field="使用提示") or "",
        "aliases": clean_text(payload.get("aliases"), max_len=300, field="别名") or "",
        "keywords": clean_text(payload.get("keywords"), max_len=300, field="关键词") or "",
        "is_featured": bool(payload.get("is_featured")),
        "calories_per_100g": nutrition_number(
            "calories_per_100g", "calories", 0, 2000
        ),
        "carbs_per_100g": nutrition_number(
            "carbs_per_100g", "carbs", 0, 100
        ),
        "protein_per_100g": nutrition_number(
            "protein_per_100g", "protein", 0, 100
        ),
        "fat_per_100g": nutrition_number(
            "fat_per_100g", "fat", 0, 100
        ),
        "typical_portion_g": int(
            nutrition_number(
                "typical_portion_g", "portion_g", 200, 5000
            )
        ),
    }


def _slugify(value: str) -> str:
    base = "".join(ch if ch.isalnum() else "-" for ch in (value or "").strip().lower())
    base = "-".join(filter(None, base.split("-")))[:60]
    return base or f"entry-{secrets.token_hex(4)}"


def _assert_publishable(data: dict) -> None:
    """未经核验的「编辑整理」内容（通常来自 AI 草稿）不得直接作为权威内容发布。"""
    if (
        data.get("status") == "published"
        and data.get("verification_status") == "pending"
        and data.get("source_type") == "editorial"
    ):
        raise ValidationError("未经核验的编辑整理内容不能直接发布：请先核验来源，或保存为草稿/下架状态")


def create_knowledge(payload: dict) -> KnowledgeEntry:
    data = _knowledge_payload(payload)
    _assert_publishable(data)
    slug = _slugify(str(payload.get("slug") or data["title"]))
    if KnowledgeEntry.query.filter_by(slug=slug).first():
        slug = f"{slug}-{secrets.token_hex(2)}"
    user = actor()
    entry = KnowledgeEntry(
        slug=slug,
        **data,
        published_at=_now() if data["status"] == "published" else None,
        created_by=getattr(user, "username", "") or "",
        updated_by=getattr(user, "username", "") or "",
    )
    db.session.add(entry)
    db.session.flush()

    # 菜品缺少营养字段时，在入库前自动调用大模型
    _auto_fill_nutrition_if_needed(entry)

    log_audit(
        "knowledge.create",
        target_type="knowledge",
        target_id=entry.id,
        detail={"slug": entry.slug, "title": entry.title, "status": entry.status},
    )
    db.session.commit()
    return entry


def update_knowledge(entry_id: int, payload: dict) -> KnowledgeEntry:
    entry = db.session.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise NotFoundError("知识条目不存在")
    data = _knowledge_payload(payload, current=entry)
    _assert_publishable(data)
    before_status = entry.status
    for key, value in data.items():
        setattr(entry, key, value)
    entry.updated_by = getattr(actor(), "username", "") or ""

    db.session.flush()
    _auto_fill_nutrition_if_needed(entry)

    if data["status"] == "published" and before_status != "published":
        entry.published_at = _now()
    log_audit(
        "knowledge.update",
        target_type="knowledge",
        target_id=entry.id,
        detail={"slug": entry.slug, "title": entry.title, "status": entry.status, "version": entry.version},
    )
    db.session.commit()
    return entry


def publish_knowledge(entry_id: int, status: str) -> KnowledgeEntry:
    entry = db.session.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise NotFoundError("知识条目不存在")
    if status not in {"published", "draft", "offline"}:
        raise ValidationError("发布状态不合法")
    if status == "published" and entry.verification_status == "pending" and entry.source_type == "editorial":
        raise ValidationError("未经核验的编辑整理内容不能发布：请先核验来源")
    entry.status = status
    entry.updated_by = getattr(actor(), "username", "") or ""

    db.session.flush()
    _auto_fill_nutrition_if_needed(entry)

    if status == "published" and not entry.published_at:
        entry.published_at = _now()
    log_audit(
        "knowledge.publish",
        target_type="knowledge",
        target_id=entry.id,
        detail={"slug": entry.slug, "status": status},
    )
    db.session.commit()
    return entry


def verify_knowledge(entry_id: int) -> KnowledgeEntry:
    """管理员一键审核通过 AI 生成词条，正式转为已核验知识。"""
    entry = db.session.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise NotFoundError("知识条目不存在")
    entry.verification_status = "verified"
    entry.status = "published"
    entry.updated_by = getattr(actor(), "username", "") or ""

    db.session.flush()
    _auto_fill_nutrition_if_needed(entry)

    if not entry.published_at:
        entry.published_at = _now()
    log_audit(
        "knowledge.verify",
        target_type="knowledge",
        target_id=entry.id,
        detail={"slug": entry.slug, "title": entry.title},
    )
    db.session.commit()
    return entry


def delete_knowledge(entry_id: int) -> dict:
    entry = db.session.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise NotFoundError("知识条目不存在")
    log_audit(
        "knowledge.delete",
        target_type="knowledge",
        target_id=entry.id,
        detail={"slug": entry.slug, "title": entry.title},
    )
    db.session.delete(entry)
    db.session.commit()
    return {"deleted": True, "id": entry_id}


# ---------------------------------------------------------------- 核查规则
def seed_rules() -> dict:
    """把静态规则登记到数据库（幂等），供后台维护。"""
    created = 0
    for index, rule in enumerate(RULES):
        rule_id = rule["id"]
        if CheckRule.query.filter_by(rule_id=rule_id).first():
            continue
        source = rule.get("source") or {}
        effective = RULESET.get("updated_at")
        try:
            effective_date = datetime.strptime(effective, "%Y-%m-%d").date() if effective else None
        except ValueError:
            effective_date = None
        db.session.add(
            CheckRule(
                rule_id=rule_id,
                title=rule.get("title", rule_id),
                category=rule.get("category", "其他"),
                level_default="review",
                description=rule.get("description", ""),
                basis=rule.get("basis", ""),
                source_name=source.get("name", ""),
                source_url=source.get("url"),
                scope="预包装食品标签（图片可见区域）",
                version=RULESET.get("version", "1.0"),
                effective_date=effective_date,
                enabled=True,
                sort_order=100 + index,
                created_by="system",
                updated_by="system",
            )
        )
        created += 1
    db.session.commit()
    return {"created": created, "total": CheckRule.query.count()}


def list_rules(*, q: str = "", category: str = "", enabled: str = "", page: int = 1, per_page: int = PAGE_SIZE) -> dict:
    query = CheckRule.query
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(CheckRule.rule_id.ilike(like), CheckRule.title.ilike(like)))
    if category:
        query = query.filter_by(category=category)
    if enabled in {"true", "false"}:
        query = query.filter_by(enabled=(enabled == "true"))
    query = query.order_by(CheckRule.sort_order.asc(), CheckRule.id.asc())
    result = _paginate(query, page, per_page)
    result["items"] = [item.to_public() for item in result["items"]]
    categories = [row[0] for row in db.session.query(CheckRule.category).distinct().all()]
    result["categories"] = sorted([item for item in categories if item])
    result["stats"] = {
        "total": CheckRule.query.count(),
        "enabled": CheckRule.query.filter_by(enabled=True).count(),
        "disabled": CheckRule.query.filter_by(enabled=False).count(),
    }
    return result


def _rule_payload(payload: dict, *, current: CheckRule | None = None) -> dict:
    from ..utils.validators import clean_text

    title = clean_text(payload.get("title"), max_len=120, field="规则标题", allow_empty=False).strip()
    basis = clean_text(payload.get("basis"), max_len=2000, field="依据") or ""
    source_name = clean_text(payload.get("source_name"), max_len=200, field="来源名称") or ""
    scope = clean_text(payload.get("scope"), max_len=200, field="适用范围") or "预包装食品标签（图片可见区域）"
    version = clean_text(payload.get("version"), max_len=20, field="版本") or "1.0"
    effective = str(payload.get("effective_date") or "").strip()
    effective_date = None
    if effective:
        try:
            effective_date = datetime.strptime(effective, "%Y-%m-%d").date()
        except ValueError:
            raise ValidationError("生效日期格式应为 YYYY-MM-DD")
    return {
        "title": title,
        "category": clean_text(payload.get("category"), max_len=40, field="分类") or (current.category if current else "其他"),
        "level_default": str(payload.get("level_default") or (current.level_default if current else "review")),
        "description": clean_text(payload.get("description"), max_len=2000, field="说明") or "",
        "basis": basis,
        "source_name": source_name or (current.source_name if current else ""),
        "source_url": clean_text(payload.get("source_url"), max_len=300, field="来源链接") or None,
        "scope": scope,
        "version": version,
        "effective_date": effective_date,
    }


def create_rule(payload: dict) -> CheckRule:
    data = _rule_payload(payload)
    rule_id = str(payload.get("rule_id") or "").strip().upper()
    if not rule_id or not rule_id.replace("_", "").isalnum():
        raise ValidationError("规则编号只能包含字母、数字与下划线")
    if CheckRule.query.filter_by(rule_id=rule_id).first():
        raise ConflictError("规则编号已存在")
    user = getattr(actor(), "username", "") or ""
    rule = CheckRule(
        rule_id=rule_id,
        **data,
        enabled=bool(payload.get("enabled", True)),
        sort_order=int(payload.get("sort_order") or 900),
        created_by=user,
        updated_by=user,
    )
    db.session.add(rule)
    db.session.flush()
    db.session.add(
        RuleRevision(
            rule_id=rule.rule_id,
            action="create",
            version=rule.version,
            before=None,
            after=rule.snapshot(),
            changed_by=user,
            note="后台创建规则",
            changed_at=_now(),
        )
    )
    log_audit("rule.create", target_type="rule", target_id=rule.rule_id, detail={"title": rule.title})
    db.session.commit()
    return rule


def update_rule(rule_id: str, payload: dict) -> CheckRule:
    rule = CheckRule.query.filter_by(rule_id=rule_id).first()
    if rule is None:
        raise NotFoundError("规则不存在")
    before = rule.snapshot()
    data = _rule_payload(payload, current=rule)
    for key, value in data.items():
        setattr(rule, key, value)
    rule.updated_by = getattr(actor(), "username", "") or ""
    db.session.add(
        RuleRevision(
            rule_id=rule.rule_id,
            action="update",
            version=rule.version,
            before=before,
            after=rule.snapshot(),
            changed_by=rule.updated_by,
            note=str(payload.get("change_note") or "")[:300],
            changed_at=_now(),
        )
    )
    log_audit("rule.update", target_type="rule", target_id=rule.rule_id, detail={"version": rule.version})
    db.session.commit()
    return rule


def toggle_rule(rule_id: str, enabled: bool) -> CheckRule:
    rule = CheckRule.query.filter_by(rule_id=rule_id).first()
    if rule is None:
        raise NotFoundError("规则不存在")
    before = rule.snapshot()
    rule.enabled = bool(enabled)
    rule.updated_by = getattr(actor(), "username", "") or ""
    db.session.add(
        RuleRevision(
            rule_id=rule.rule_id,
            action="toggle",
            version=rule.version,
            before=before,
            after=rule.snapshot(),
            changed_by=rule.updated_by,
            note="启用" if enabled else "停用",
            changed_at=_now(),
        )
    )
    log_audit("rule.toggle", target_type="rule", target_id=rule.rule_id, detail={"enabled": bool(enabled)})
    db.session.commit()
    return rule


def rule_revisions(rule_id: str) -> dict:
    rule = CheckRule.query.filter_by(rule_id=rule_id).first()
    if rule is None:
        raise NotFoundError("规则不存在")
    revisions = RuleRevision.query.filter_by(rule_id=rule_id).order_by(RuleRevision.id.desc()).all()
    return {
        "rule": rule.to_public(),
        "revisions": [item.to_public() for item in revisions],
    }


def enabled_rule_meta() -> dict[str, dict]:
    """供 checker 使用：规则 ID → 元数据；停用的规则不出现在结果里。"""
    rules = CheckRule.query.all()
    return {
        rule.rule_id: {
            "title": rule.title,
            "basis": rule.basis,
            "source": {"name": rule.source_name, "url": rule.source_url},
            "version": rule.version,
            "updated_at": rule.updated_at.strftime("%Y-%m-%d") if rule.updated_at else "",
            "enabled": bool(rule.enabled),
        }
        for rule in rules
    }


# ---------------------------------------------------------------- 监控与审计
def monitor_overview() -> dict:
    config = current_app.config
    now = _now()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    ocr_total = 0
    ocr_failed = 0
    try:
        from ..models import OcrResult

        ocr_total = OcrResult.query.count()
        ocr_failed = OcrResult.query.filter(OcrResult.status == "failed").count()
        avg_ocr = db.session.query(func.avg(OcrResult.duration_ms)).scalar() or 0
    except Exception:  # pragma: no cover
        avg_ocr = 0

    ai_total = 0
    try:
        from ..models import IngredientAnalysis

        ai_total = IngredientAnalysis.query.count()
    except Exception:  # pragma: no cover
        pass

    records_24h = AnalysisRecord.query.filter(AnalysisRecord.created_at >= day_ago).count()
    failed_24h = AnalysisRecord.query.filter(
        AnalysisRecord.created_at >= day_ago, AnalysisRecord.status == "failed"
    ).count()
    records_7d = AnalysisRecord.query.filter(AnalysisRecord.created_at >= week_ago).count()

    events = (
        ServiceEvent.query.order_by(ServiceEvent.id.desc()).limit(20).all()
    )
    errors_24h = ServiceEvent.query.filter(ServiceEvent.created_at >= day_ago).count()

    ocr_provider = config.get("OCR_PROVIDER", "demo")
    ai_provider = config.get("AI_PROVIDER", "rule")
    return {
        "services": {
            "ocr": {
                "provider": ocr_provider,
                "is_demo": ocr_provider == "demo",
                "vision_configured": bool(config.get("OCR_VISION_API_KEY")),
                "status": "ok" if ocr_provider else "unconfigured",
            },
            "ai": {
                "provider": ai_provider,
                "configured": bool(config.get("AI_API_KEY")),
                "model": config.get("AI_MODEL"),
                "mode": "ai" if config.get("AI_API_KEY") else "rule",
            },
            "assistant": {
                "dedicated_llm": bool(config.get("ASSISTANT_LLM_API_KEY")),
                "model": config.get("ASSISTANT_LLM_MODEL") or config.get("AI_MODEL"),
                "general_answer": str(config.get("ASSISTANT_GENERAL_ANSWER")) == "1",
            },
        },
        "requests": {
            "records_total": AnalysisRecord.query.count(),
            "records_24h": records_24h,
            "records_7d": records_7d,
            "failed_total": AnalysisRecord.query.filter_by(status="failed").count(),
            "failed_24h": failed_24h,
            "ocr_total": ocr_total,
            "ocr_failed": ocr_failed,
            "ai_total": ai_total,
            "errors_24h": errors_24h,
        },
        "performance": {
            "avg_ocr_ms": round(float(avg_ocr or 0), 1),
            "max_ocr_ms": int(db.session.query(func.max(OcrResult.duration_ms)).scalar() or 0),
        },
        "recent_errors": [item.to_public() for item in events],
        "generated_at": _iso(now),
        "note": "监控数据来自数据库中的真实记录；外部服务仅展示是否已配置，不返回密钥。",
    }


def list_audit_logs(*, action: str = "", actor_name: str = "", result: str = "", page: int = 1, per_page: int = PAGE_SIZE) -> dict:
    query = AuditLog.query
    if action:
        query = query.filter(AuditLog.action == action)
    if actor_name:
        query = query.filter(AuditLog.actor_username.ilike(f"%{actor_name}%"))
    if result in {"success", "failure", "denied"}:
        query = query.filter_by(result=result)
    query = query.order_by(AuditLog.id.desc())
    result_data = _paginate(query, page, per_page)
    result_data["items"] = [item.to_public() for item in result_data["items"]]
    result_data["actions"] = [{"value": key, "label": label} for key, label in __import__(
        "app.models.admin", fromlist=["AUDIT_ACTIONS"]
    ).AUDIT_ACTIONS.items()]
    return result_data


__all__ = [
    "validate_admin_password",
    "create_admin",
    "authenticate_admin",
    "reset_user_password",
    "dashboard_stats",
    "list_users",
    "set_user_active",
    "set_user_role",
    "delete_user",
    "list_records",
    "record_detail",
    "add_record_note",
    "delete_record",
    "list_feedback",
    "resolve_feedback",
    "list_knowledge_admin",
    "create_knowledge",
    "update_knowledge",
    "publish_knowledge",
    "delete_knowledge",
    "seed_rules",
    "list_rules",
    "create_rule",
    "update_rule",
    "toggle_rule",
    "rule_revisions",
    "enabled_rule_meta",
    "monitor_overview",
    "list_audit_logs",
    "log_audit",
    "record_event",
]
