"""管理员后台 API（/api/admin/*）。

权限模型：
- 所有 /api/admin/* 路由（除登录）统一使用 @admin_required；
- 管理员与普通用户共用 users 表与 auth_sessions 表，靠 role 区分；
- 登录失败按「用户名 + IP」限流，失败事件写入审计日志。
"""
from __future__ import annotations

import io
import re
import threading
import time

from flask import Blueprint, g, request, send_file
from sqlalchemy import func

from ..extensions import db
from ..models import AnalysisRecord, AuditLog, Feedback, KnowledgeEntry, PromptTemplate, User
from ..models.user import utcnow
from ..models.admin import AUDIT_ACTIONS, AUDIT_RESULTS, FEEDBACK_STATUS
from ..models.knowledge import CATEGORIES as KNOWLEDGE_CATEGORIES
from ..models.knowledge import SOURCE_TYPES, VERIFICATION
from ..services import admin_service, dish_knowledge_service, dish_nutrition_service, knowledge_compose_service, storage
from ..services.captcha_service import captcha_enabled, verify_captcha
from ..utils.errors import (
    APIError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from ..utils.response import ok
from ..utils.security import admin_required, issue_session, login_required, revoke_session
from .common import json_body

bp = Blueprint("admin", __name__)

# 管理端登录限流（单进程内存实现；多实例部署建议换 Redis）
_FAILED: dict[str, list[float]] = {}
_FAILED_LOCK = threading.Lock()
MAX_FAILURES = 5
FAILURE_WINDOW = 300


def _ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "-"


def _throttle_key(username: str) -> str:
    return f"admin|{(username or '').lower()}|{_ip()}"


def _check_throttle(key: str) -> None:
    now = time.time()
    with _FAILED_LOCK:
        attempts = [moment for moment in _FAILED.get(key, []) if now - moment < FAILURE_WINDOW]
        _FAILED[key] = attempts
        if len(attempts) >= MAX_FAILURES:
            raise APIError(
                "登录失败次数过多，请 5 分钟后再试",
                code=42900,
                status=429,
                details={"window_seconds": FAILURE_WINDOW, "max_failures": MAX_FAILURES},
            )


def _record_failure(key: str) -> None:
    with _FAILED_LOCK:
        _FAILED.setdefault(key, []).append(time.time())


def _clear_failure(key: str) -> None:
    with _FAILED_LOCK:
        _FAILED.pop(key, None)


def _page_args(default: int = 20) -> tuple[int, int]:
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", default))
    except (TypeError, ValueError):
        raise ValidationError("page / per_page 必须是整数")
    return max(1, page), min(100, max(1, per_page))


def _audit_login_failure(username: str, reason: str) -> None:
    try:
        db.session.add(
            AuditLog(
                actor_id=None,
                actor_username=(username or "")[:40],
                action="admin.login",
                target_type="admin_session",
                target_id="",
                detail={"reason": reason},
                result="failure",
                ip=_ip()[:64],
            )
        )
        db.session.commit()
    except Exception:  # pragma: no cover
        db.session.rollback()


# ---------------------------------------------------------------- 认证
@bp.post("/admin/auth/login")
def admin_login():
    payload = json_body()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    key = _throttle_key(username)
    _check_throttle(key)
    if captcha_enabled() and not verify_captcha(
        str(payload.get("captcha_id") or ""), str(payload.get("captcha_code") or "")
    ):
        _record_failure(key)
        raise ValidationError("验证码不正确或已过期，请刷新后重试", details={"field": "captcha"})
    try:
        user = admin_service.authenticate_admin(username, password)
    except ValidationError as exc:
        _record_failure(key)
        _audit_login_failure(username, exc.message)
        raise
    _clear_failure(key)
    # 清理过期会话
    from datetime import datetime, timezone

    from ..models import AuthSession

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    AuthSession.query.filter(AuthSession.user_id == user.id, AuthSession.expires_at < now).delete(
        synchronize_session=False
    )
    token, session = issue_session(user)
    # 登录路由没有经过 admin_required，这里补上操作人，便于审计追溯
    g.current_user = user
    admin_service.log_audit(
        "admin.login",
        target_type="admin_session",
        target_id=session.id,
        detail={"role": user.role},
    )
    db.session.commit()
    return ok(
        {
            "token": token,
            "expires_at": session.expires_at.isoformat() + "Z",
            "user": user.to_public(),
        },
        "管理员登录成功",
    )


@bp.post("/admin/auth/logout")
@admin_required
def admin_logout():
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if token:
        revoke_session(token)
    admin_service.log_audit("admin.logout", target_type="admin_session")
    db.session.commit()
    return ok({"logged_out": True}, "已退出管理员账号")


@bp.get("/admin/auth/me")
@admin_required
def admin_me():
    user: User = g.current_user
    return ok({"user": user.to_public(), "permissions": ["admin"]})


# ---------------------------------------------------------------- 元数据
@bp.get("/admin/meta")
@admin_required
def admin_meta():
    return ok(
        {
            "knowledge_categories": [{"value": key, "label": label} for key, label in KNOWLEDGE_CATEGORIES.items()],
            "source_types": [{"value": key, "label": label} for key, label in SOURCE_TYPES.items()],
            "verification": [{"value": key, "label": label} for key, label in VERIFICATION.items()],
            "knowledge_status": [
                {"value": "published", "label": "已发布"},
                {"value": "draft", "label": "待审核"},
                {"value": "offline", "label": "已下架"},
            ],
            "record_status": [
                {"value": "uploaded", "label": "已上传"},
                {"value": "ocr_done", "label": "已识别"},
                {"value": "corrected", "label": "已校正"},
                {"value": "analyzed", "label": "分析完成"},
                {"value": "failed", "label": "处理失败"},
            ],
            "audit_actions": [{"value": key, "label": label} for key, label in AUDIT_ACTIONS.items()],
            "audit_results": [{"value": key, "label": label} for key, label in AUDIT_RESULTS.items()],
            "feedback_status": [{"value": key, "label": label} for key, label in FEEDBACK_STATUS.items()],
        }
    )


# ---------------------------------------------------------------- 仪表盘
@bp.get("/admin/dashboard")
@admin_required
def admin_dashboard():
    return ok(admin_service.dashboard_stats())


# ---------------------------------------------------------------- 用户
@bp.get("/admin/users")
@admin_required
def admin_users():
    page, per_page = _page_args()
    data = admin_service.list_users(
        q=request.args.get("q", ""),
        status=request.args.get("status", ""),
        role=request.args.get("role", ""),
        page=page,
        per_page=per_page,
    )
    return ok(data)


@bp.patch("/admin/users/<int:user_id>")
@admin_required
def admin_update_user(user_id: int):
    payload = json_body()
    if "is_active" not in payload and "role" not in payload:
        raise ValidationError("缺少参数 is_active 或 role")
    user = None
    if "is_active" in payload:
        user = admin_service.set_user_active(user_id, bool(payload.get("is_active")))
    if "role" in payload:
        user = admin_service.set_user_role(user_id, str(payload.get("role")))
    return ok({"user": user.to_public()}, "用户信息已更新")


@bp.patch("/admin/users/<int:user_id>/status")
@admin_required
def admin_update_user_status(user_id: int):
    payload = json_body()
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"active", "disabled"}:
        raise ValidationError("status 只能是 active 或 disabled")

    user = admin_service.set_user_active(
        user_id,
        status == "active",
    )
    return ok({"user": user.to_public()}, "用户状态已更新")


@bp.patch("/admin/users/<int:user_id>/role")
@admin_required
def admin_update_user_role(user_id: int):
    payload = json_body()
    role = str(payload.get("role") or "").strip().lower()
    if role not in {"admin", "user"}:
        raise ValidationError("role 只能是 admin 或 user")

    user = admin_service.set_user_role(user_id, role)
    return ok({"user": user.to_public()}, "用户角色已更新")


@bp.delete("/admin/users/<int:user_id>")
@admin_required
def admin_delete_user(user_id: int):
    return ok(admin_service.delete_user(user_id), "用户账号已删除")


@bp.post("/admin/users/<int:user_id>/reset-password")
@admin_required
def admin_reset_password(user_id: int):
    temp_password = admin_service.reset_user_password(user_id)
    return ok(
        {"user_id": user_id, "temporary_password": temp_password},
        "已生成临时密码，请通过安全渠道转交用户并提醒立即修改",
    )


# ---------------------------------------------------------------- 分析记录
@bp.get("/admin/records")
@admin_required
def admin_records():
    page, per_page = _page_args()
    data = admin_service.list_records(
        q=request.args.get("q", ""),
        status=request.args.get("status", ""),
        page=page,
        per_page=per_page,
    )
    return ok(data)


@bp.get("/admin/records/<int:record_id>")
@admin_required
def admin_record_detail(record_id: int):
    return ok(admin_service.record_detail(record_id))


@bp.post("/admin/records/<int:record_id>/notes")
@admin_required
def admin_record_note(record_id: int):
    payload = json_body()
    note = admin_service.add_record_note(record_id, str(payload.get("content") or ""))
    return ok({"note": note.to_public()}, "复核备注已保存", 201)


@bp.get("/admin/records/<int:record_id>/image")
@admin_required
def admin_record_image(record_id: int):
    record = db.session.get(AnalysisRecord, record_id)
    if record is None:
        raise NotFoundError("分析记录不存在")
    if record.image is None:
        raise NotFoundError("该记录没有图片")

    data, mime = storage.read_image(record.image.stored_name, display=False)
    response = send_file(
        io.BytesIO(data),
        mimetype=mime,
        as_attachment=False,
        download_name=record.image.original_name or "record.jpg",
        max_age=300,
    )
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@bp.put("/admin/records/<int:record_id>/review")
@admin_required
def admin_review_record(record_id: int):
    result = admin_service.review_record(record_id, json_body())
    return ok(result, "审核结果已保存")


@bp.delete("/admin/records/<int:record_id>")
@admin_required
def admin_delete_record(record_id: int):
    payload = json_body(required=False)
    result = admin_service.delete_record(record_id, confirm=bool(payload.get("confirm")))
    return ok(result, "记录已删除")


# ---------------------------------------------------------------- 用户反馈
@bp.get("/admin/feedback")
@admin_required
def admin_feedback():
    page, per_page = _page_args()
    return ok(admin_service.list_feedback(status=request.args.get("status", ""), page=page, per_page=per_page))


@bp.route("/admin/feedback/<int:feedback_id>", methods=["PATCH", "PUT"])
@admin_required
def admin_update_feedback(feedback_id: int):
    payload = json_body()
    item = admin_service.resolve_feedback(
        feedback_id,
        status=str(payload.get("status") or "resolved"),
        reply=str(payload.get("reply_content") or payload.get("reply") or ""),
    )
    return ok({"feedback": item.to_public()}, "反馈已处理")


@bp.get("/feedback/mine")
@login_required
def my_feedback():
    """当前用户查看自己的反馈及管理员回复。

    C 端不再传 user_id，直接由当前登录令牌确定用户；
    返回的每条反馈同时包含 reply 与 reply_content。
    """
    user: User = g.current_user
    requested_user_id = request.args.get("user_id", type=int)
    if requested_user_id is not None and requested_user_id != user.id:
        raise ForbiddenError("只能查看自己的反馈")

    items = (
        Feedback.query.filter_by(user_id=user.id)
        .order_by(Feedback.id.desc())
        .all()
    )
    return ok(
        {
            "items": [item.to_public() for item in items],
            "unread": sum(
                1
                for item in items
                if item.status == "resolved"
                and bool((item.reply_content or item.reply or "").strip())
            ),
        }
    )


def _save_feedback_reply(feedback_id_override: int | None = None):
    """标记反馈已处理并写入管理员回复，供多个兼容路由复用。"""
    payload = json_body()
    raw_id = feedback_id_override
    if raw_id is None:
        raw_id = payload.get("feedback_id", payload.get("id"))

    try:
        feedback_id = int(raw_id)
    except (TypeError, ValueError):
        raise ValidationError("feedback_id 必须是整数")

    reply_content = str(
        payload.get("reply_content") or payload.get("reply") or ""
    ).strip()
    if not reply_content:
        raise ValidationError("回复内容不能为空")

    item = admin_service.resolve_feedback(
        feedback_id,
        status="resolved",
        reply=reply_content,
    )
    return ok({"feedback": item.to_public()}, "回复已保存并通知用户")


@bp.route("/admin/feedback/reply", methods=["POST", "PUT"])
@admin_required
def admin_reply_feedback():
    """管理员标准回复接口：/api/admin/feedback/reply。"""
    return _save_feedback_reply()


@bp.route("/admin/feedback/handle", methods=["POST", "PUT"])
@admin_required
def admin_handle_feedback():
    """兼容「标记已处理」语义：/api/admin/feedback/handle。"""
    return _save_feedback_reply()


@bp.route("/admin/feedback/<int:feedback_id>/reply", methods=["POST", "PUT"])
@admin_required
def admin_reply_feedback_by_id(feedback_id: int):
    """REST 风格别名：/api/admin/feedback/<id>/reply。"""
    return _save_feedback_reply(feedback_id_override=feedback_id)


# 旧版本前端曾调用公开前缀，保留兼容，不再作为新代码入口
@bp.post("/feedback/reply")
@admin_required
def reply_feedback():
    return _save_feedback_reply()


@bp.post("/feedback")
@login_required
def submit_feedback():
    """普通用户提交反馈（登录后）。"""
    payload = json_body()
    content = str(payload.get("content") or "").strip()
    if len(content) < 5:
        raise ValidationError("反馈内容至少 5 个字符")
    if len(content) > 2000:
        raise ValidationError("反馈内容不能超过 2000 个字符")
    user: User = g.current_user
    record_id_raw = payload.get("record_id")
    record_id: int | None = None
    if record_id_raw not in (None, ""):
        try:
            record_id = int(record_id_raw)
        except (TypeError, ValueError):
            raise ValidationError("关联记录编号必须是整数")
        if record_id <= 0:
            raise ValidationError("关联记录编号不合法")

    item = Feedback(
        user_id=user.id,
        record_id=record_id,
        content=content,
        contact=str(payload.get("contact") or "")[:120],
    )
    db.session.add(item)
    db.session.commit()
    return ok({"feedback": item.to_public()}, "反馈已提交，管理员会尽快处理", 201)


# ---------------------------------------------------------------- 知识库
@bp.get("/admin/knowledge")
@admin_required
def admin_knowledge_list():
    page, per_page = _page_args()
    return ok(
        admin_service.list_knowledge_admin(
            q=request.args.get("q", ""),
            category=request.args.get("category", ""),
            status=request.args.get("status", ""),
            source=request.args.get("source", ""),
            verification=request.args.get("verification", ""),
            page=page,
            per_page=per_page,
        )
    )


@bp.post("/admin/knowledge/estimate-nutrition")
@admin_required
def admin_knowledge_estimate_nutrition():
    payload = json_body()
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValidationError("请先填写菜品标题")

    result = dish_nutrition_service.estimate_dish_nutrition(
        title=title,
        summary=str(payload.get("summary") or ""),
        content=str(payload.get("content") or ""),
    )
    return ok(result, "AI 营养测算完成")


@bp.post("/admin/knowledge/ai-compose")
@admin_required
def admin_knowledge_ai_compose():
    payload = json_body()
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValidationError("请先填写标题")

    try:
        result = knowledge_compose_service.compose_knowledge(title)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    except Exception as exc:
        raise APIError(
            "AI 内容生成失败，请稍后重试",
            code=50300,
            status=503,
            details={"reason": exc.__class__.__name__},
        ) from exc

    return ok(result, "AI 一键建库内容已生成")


@bp.post("/admin/knowledge/summarize")
@admin_required
def admin_knowledge_summarize():
    payload = json_body()
    title = str(payload.get("title") or "").strip()
    content = str(payload.get("content") or "").strip()

    try:
        summary = dish_nutrition_service.summarize_knowledge_content(
            title,
            content,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    return ok({"summary": summary}, "摘要已生成")


@bp.post("/admin/knowledge")
@admin_required
def admin_knowledge_create():
    entry = admin_service.create_knowledge(json_body())
    return ok(
        {
            "entry": entry.to_public(),
            "nutrition_ai": getattr(entry, "_nutrition_ai", None),
        },
        "知识条目已创建",
        201,
    )


@bp.put("/admin/knowledge/<int:entry_id>")
@admin_required
def admin_knowledge_update(entry_id: int):
    entry = admin_service.update_knowledge(entry_id, json_body())
    return ok(
        {
            "entry": entry.to_public(),
            "nutrition_ai": getattr(entry, "_nutrition_ai", None),
        },
        "知识条目已更新",
    )


@bp.post("/admin/knowledge/<int:entry_id>/publish")
@admin_required
def admin_knowledge_publish(entry_id: int):
    payload = json_body()
    entry = admin_service.publish_knowledge(entry_id, str(payload.get("status") or "published"))
    return ok(
        {
            "entry": entry.to_public(),
            "nutrition_ai": getattr(entry, "_nutrition_ai", None),
        },
        "发布状态已更新",
    )


@bp.post("/admin/knowledge/<int:entry_id>/verify")
@admin_required
def admin_knowledge_verify(entry_id: int):
    """审核通过知识条目。

    强制拦截：食品添加剂、营养术语、食安科普、标签规则不需要营养测算，
    在这些分类上必须在进入任何 AI 逻辑之前直接完成发布。
    """
    entry = db.session.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise NotFoundError("知识条目不存在")

    category = (entry.category or "").strip()
    nutrition_categories = {"dish", "ingredient"}

    if category not in nutrition_categories:
        entry.verification_status = "verified"
        entry.status = "published"
        entry.updated_by = getattr(g.current_user, "username", "") or ""
        entry.published_at = entry.published_at or utcnow()
        entry._nutrition_ai = {
            "status": "skipped",
            "message": "该分类不需要营养测算",
            "filled_fields": [],
        }
        admin_service.log_audit(
            "knowledge.verify",
            target_type="knowledge",
            target_id=entry.id,
            detail={
                "slug": entry.slug,
                "title": entry.title,
                "category": category,
                "nutrition_ai": "skipped",
            },
        )
        db.session.commit()
        return ok(
            {
                "entry": entry.to_public(),
                "nutrition_ai": entry._nutrition_ai,
            },
            "审核通过，词条已转为已核验知识",
        )

    entry = admin_service.verify_knowledge(entry_id)
    return ok(
        {
            "entry": entry.to_public(),
            "nutrition_ai": getattr(entry, "_nutrition_ai", None),
        },
        "审核通过，词条已转为已核验知识",
    )


@bp.post("/admin/knowledge/<int:entry_id>/enrich")
@admin_required
def admin_knowledge_enrich(entry_id: int):
    """使用 DeepSeek 参考已有菜品，自动补全菜品知识字段。"""
    entry = db.session.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise NotFoundError("知识条目不存在")

    try:
        entry = dish_knowledge_service.enrich_dish(entry)
    except Exception as exc:
        from ..services.ai_service import AIServiceError

        if isinstance(exc, AIServiceError):
            raise APIError(
                str(exc),
                code=exc.code if isinstance(exc.code, int) else 503,
                status=exc.status or 503,
            ) from exc
        raise

    return ok({"entry": entry.to_public()}, "已根据已有菜品自动补全信息")


@bp.delete("/admin/knowledge/<int:entry_id>")
@admin_required
def admin_knowledge_delete(entry_id: int):
    return ok(admin_service.delete_knowledge(entry_id), "知识条目已删除")


# ---------------------------------------------------------------- 核查规则
@bp.get("/admin/rules")
@admin_required
def admin_rules():
    page, per_page = _page_args()
    return ok(
        admin_service.list_rules(
            q=request.args.get("q", ""),
            category=request.args.get("category", ""),
            enabled=request.args.get("enabled", ""),
            page=page,
            per_page=per_page,
        )
    )


@bp.post("/admin/rules")
@admin_required
def admin_rule_create():
    rule = admin_service.create_rule(json_body())
    return ok({"rule": rule.to_public()}, "规则已创建", 201)


@bp.put("/admin/rules/<rule_id>")
@admin_required
def admin_rule_update(rule_id: str):
    rule = admin_service.update_rule(rule_id, json_body())
    return ok({"rule": rule.to_public()}, "规则已更新")


@bp.post("/admin/rules/<rule_id>/toggle")
@admin_required
def admin_rule_toggle(rule_id: str):
    payload = json_body()
    rule = admin_service.toggle_rule(rule_id, bool(payload.get("enabled")))
    return ok({"rule": rule.to_public()}, "规则状态已更新")


@bp.get("/admin/rules/<rule_id>/revisions")
@admin_required
def admin_rule_revisions(rule_id: str):
    return ok(admin_service.rule_revisions(rule_id))


# ---------------------------------------------------------------- 监控
@bp.get("/admin/monitor")
@admin_required
def admin_monitor():
    return ok(admin_service.monitor_overview())


# ---------------------------------------------------------------- 审计
@bp.get("/admin/audit-logs")
@admin_required
def admin_audit_logs():
    page, per_page = _page_args()
    return ok(
        admin_service.list_audit_logs(
            action=request.args.get("action", ""),
            actor_name=request.args.get("actor", ""),
            result=request.args.get("result", ""),
            page=page,
            per_page=per_page,
        )
    )

PROMPT_SEED = [
    {"name": "营养成分解析", "scene": "包装食品营养表结构化提取", "model": "deepseek", "version": "v2.4", "status": "active"},
    {"name": "食谱生成", "scene": "结合库存、天气与健康画像生成三餐", "model": "deepseek", "version": "v3.1", "status": "active"},
    {"name": "风险拦截", "scene": "过敏原、疾病禁忌与添加剂风险复核", "model": "deepseek", "version": "v2.8", "status": "active"},
    {"name": "健康画像解读", "scene": "生成个性化饮食禁忌与绿灯建议", "model": "deepseek", "version": "v2.2", "status": "active"},
    {"name": "菜品视觉识别", "scene": "识饭菜图片识别菜名与估算重量", "model": "deepseek", "version": "v1.9", "status": "active"},
    {"name": "食安科普问答", "scene": "RAG 检索增强与来源约束", "model": "deepseek", "version": "v1.6", "status": "draft"},
]


def _ensure_prompt_templates() -> None:
    if PromptTemplate.query.count() > 0:
        return
    for item in PROMPT_SEED:
        payload = dict(item)
        payload.setdefault("system_prompt", payload.get("scene", ""))
        db.session.add(PromptTemplate(**payload))
    db.session.commit()


@bp.get("/admin/prompts")
@admin_required
def admin_prompts():
    _ensure_prompt_templates()
    items = PromptTemplate.query.order_by(PromptTemplate.id.asc()).all()
    return ok({"items": [item.to_public() for item in items]})


@bp.post("/admin/prompts/<int:prompt_id>/publish")
@admin_required
def admin_publish_prompt(prompt_id: int):
    _ensure_prompt_templates()
    item = PromptTemplate.query.filter_by(id=prompt_id).first()
    if item is None:
        raise ValidationError("Prompt 模板不存在")
    item.status = "active"
    item.updated_at = utcnow()
    db.session.commit()
    return ok({"prompt": item.to_public()}, "Prompt 已发布")


def _bump_prompt_version(version: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)?)", version or "")
    if not match:
        return "v1.1"
    number = round(float(match.group(1)) + 0.1, 1)
    return f"v{number:.1f}"


@bp.put("/admin/prompts/<int:prompt_id>")
@admin_required
def admin_update_prompt(prompt_id: int):
    _ensure_prompt_templates()
    item = PromptTemplate.query.filter_by(id=prompt_id).first()
    if item is None:
        raise ValidationError("Prompt 模板不存在")

    payload = json_body()
    system_prompt = str(
        payload.get("system_prompt")
        or payload.get("content")
        or ""
    ).strip()
    if not system_prompt:
        raise ValidationError("系统提示词不能为空")

    item.system_prompt = system_prompt[:20000]
    item.version = _bump_prompt_version(item.version)
    item.updated_at = utcnow()
    db.session.commit()
    return ok({"prompt": item.to_public()}, "Prompt 已保存，版本号已更新")


@bp.post("/admin/prompts/<int:prompt_id>/draft")
@admin_required
def admin_draft_prompt(prompt_id: int):
    _ensure_prompt_templates()
    item = PromptTemplate.query.filter_by(id=prompt_id).first()
    if item is None:
        raise ValidationError("Prompt 模板不存在")
    item.status = "draft"
    item.updated_at = utcnow()
    db.session.commit()
    return ok({"prompt": item.to_public()}, "Prompt 已转为草稿")

