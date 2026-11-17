"""食安科普与辟谣助手接口（RAG 问答 + 会话历史）。"""
from __future__ import annotations

from flask import Blueprint, g

from ..services import assistant_service
from ..utils.errors import APIError, NotFoundError, ValidationError
from ..utils.response import ErrorCode, ok
from ..utils.security import login_required
from ..utils.validators import clean_text
from .common import int_field, json_body

bp = Blueprint("assistant", __name__)


@bp.get("/assistant/overview")
def assistant_overview():
    """公开的概览：收录条目数、分类、热门问题。"""
    return ok(
        {
            "stats": assistant_service.stats(),
            "featured": assistant_service.featured_questions(),
            "disclaimer": assistant_service.DISCLAIMER,
        }
    )


@bp.post("/assistant/ask")
@login_required
def assistant_ask():
    payload = json_body()
    question = clean_text(payload.get("question"), max_len=200, field="问题", allow_empty=False)
    if len(question) < 2:
        raise ValidationError("问题太短了，请至少输入 2 个字")
    session_id = payload.get("session_id")
    if session_id in (None, "", 0):
        session_id = None
    else:
        try:
            session_id = int(session_id)
        except (TypeError, ValueError):
            raise ValidationError("session_id 必须是整数")
    context = payload.get("context")
    if context is not None and not isinstance(context, dict):
        raise ValidationError("context 必须是对象")
    health_profile = payload.get("health_data") or payload.get("health_profile")
    if health_profile is not None and not isinstance(health_profile, dict):
        raise ValidationError("health_data / health_profile 必须是对象")
    try:
        result = assistant_service.ask(
            question,
            g.current_user.id,
            session_id,
            context=context,
            health_profile=health_profile,
        )
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise APIError(str(exc), code=ErrorCode.RATE_LIMITED, status=429) from exc
    return ok(result)


@bp.get("/assistant/sessions")
@login_required
def assistant_sessions():
    return ok({"items": assistant_service.list_sessions(g.current_user.id)})


@bp.delete("/assistant/sessions")
@login_required
def assistant_sessions_clear():
    deleted = assistant_service.clear_sessions(g.current_user.id)
    return ok({"deleted": deleted})


@bp.get("/assistant/sessions/<int:session_id>")
@login_required
def assistant_session_detail(session_id: int):
    try:
        data = assistant_service.get_session(g.current_user.id, session_id)
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    return ok({"session": data, "disclaimer": assistant_service.DISCLAIMER})


@bp.delete("/assistant/sessions/<int:session_id>")
@login_required
def assistant_session_delete(session_id: int):
    try:
        assistant_service.delete_session(g.current_user.id, session_id)
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    return ok({"deleted_id": session_id})


@bp.get("/assistant/entries/<slug>")
def assistant_entry(slug: str):
    entry = assistant_service.entry_detail(slug)
    if entry is None:
        raise NotFoundError("该条目不存在")
    return ok({"entry": entry})
