"""设置与系统状态接口（只暴露状态，不暴露任何密钥）。"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Blueprint, current_app

from ..models import User
from ..rules.label_rules import ruleset_public
from ..services import ai_service, storage
from ..services import ocr as ocr_service
from ..utils.response import ok

bp = Blueprint("settings", __name__)


def _mask(value: str | None) -> str:
    """只显示是否已配置，绝不回传密钥内容。"""
    if not value:
        return "未配置"
    return f"已配置（{len(value)} 位，已隐藏）"


@bp.get("/settings/status")
def settings_status():
    config = current_app.config
    # 展示真正会被请求的完整地址，方便排查 404 / 地址填错
    try:
        from ..services.ocr.vision_llm import candidate_urls

        _vision_endpoint = (candidate_urls(config.get("OCR_VISION_BASE_URL")) or ["（未配置）"])[0]
    except Exception:  # pragma: no cover - 配置非法时不影响状态接口
        _vision_endpoint = "（地址格式不正确）"
    database_uri = str(config.get("SQLALCHEMY_DATABASE_URI") or "")
    if database_uri.startswith("sqlite:///"):
        db_path = database_uri.replace("sqlite:///", "")
        database_display = f"SQLite 文件：{Path(db_path).name}"
    else:
        database_display = "外部数据库（连接串已隐藏）"

    demo_user = User.query.filter_by(username=config.get("DEMO_USERNAME")).first()
    upload_dir = Path(config["UPLOAD_DIR"])
    return ok(
        {
            "app": {
                "name": config["APP_NAME"],
                "subtitle": config["APP_SUBTITLE"],
                "version": config["APP_VERSION"],
                "env": config["ENV"],
                "public_site_url": config.get("PUBLIC_SITE_URL") or None,
            },
            "ocr": {
                "configured_provider": config.get("OCR_PROVIDER"),
                "active_provider": ocr_service.resolve_provider_key(),
                "active_label": ocr_service.active_provider_label(),
                "providers": ocr_service.provider_status(),
                "vision_base_url": config.get("OCR_VISION_BASE_URL"),
                "vision_endpoint": _vision_endpoint,
                "vision_model": config.get("OCR_VISION_MODEL"),
                "vision_key": _mask(config.get("OCR_VISION_API_KEY")),
            },
            "ai": {
                "mode": ai_service.resolve_mode(),
                "configured": ai_service.ai_configured(),
                "provider": config.get("AI_PROVIDER"),
                "base_url": config.get("AI_BASE_URL"),
                "model": config.get("AI_MODEL"),
                "api_key": _mask(config.get("AI_API_KEY")),
                "prompt_version": ai_service.PROMPT_VERSION,
            },
            "assistant": {
                "mode": config.get("ASSISTANT_MODE"),
                "fallback_enabled": config.get("ASSISTANT_AI_FALLBACK"),
                "general_answer_enabled": config.get("ASSISTANT_GENERAL_ANSWER"),
                "llm_base_url": config.get("ASSISTANT_LLM_BASE_URL") or config.get("AI_BASE_URL"),
                "llm_model": config.get("ASSISTANT_LLM_MODEL") or config.get("AI_MODEL"),
                "llm_key": _mask(config.get("ASSISTANT_LLM_API_KEY") or config.get("AI_API_KEY")),
                "dedicated_llm": bool(config.get("ASSISTANT_LLM_API_KEY")),
            },
            "storage": {
                "database": database_display,
                "upload_dir": str(upload_dir),
                "upload_dir_exists": upload_dir.exists(),
                **storage.storage_stats(),
                "max_upload_mb": config.get("MAX_CONTENT_LENGTH_MB"),
                "allowed_formats": ["JPG", "JPEG", "PNG", "WEBP"],
                "image_max_edge": config.get("IMAGE_MAX_EDGE"),
            },
            "security": {
                "password_hashing": "scrypt（werkzeug.security，含随机 salt）",
                "session_days": config.get("SESSION_DAYS"),
                "cors_origins": config.get("CORS_ORIGINS"),
                "demo_mode": config.get("DEMO_MODE"),
                "api_key_in_logs": False,
            },
            "demo_account": {
                "exists": demo_user is not None,
                "username": config.get("DEMO_USERNAME") if demo_user else None,
                "password_hint": "见 README（演示账号密码仅在本地 .env 中配置）" if demo_user else None,
            },
            "ruleset": {
                "version": config.get("RULESET_VERSION"),
                "updated_at": ruleset_public()["updated_at"],
                "rule_count": ruleset_public()["rule_count"],
            },
            "limits": {"page_size": config.get("PAGE_SIZE"), "max_page_size": config.get("MAX_PAGE_SIZE")},
            "runtime": {
                "python": os.sys.version.split()[0],
                "flask": _flask_version(),
            },
        }
    )


@bp.get("/rules")
def rules():
    data = ruleset_public()
    return ok(data)


def _flask_version() -> str:
    try:
        from importlib.metadata import version

        return version("flask")
    except Exception:  # pragma: no cover
        return "unknown"
