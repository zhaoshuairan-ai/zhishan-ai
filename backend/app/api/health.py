"""健康检查 / 运行状态接口。"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from flask import Blueprint, current_app
from sqlalchemy import text

from ..extensions import db
from ..services import ai_service, ocr as ocr_service
from ..services.storage import storage_stats
from ..utils.response import ok

bp = Blueprint("health", __name__)
_STARTED_AT = time.time()


@bp.get("/health")
def health():
    checks = {}
    healthy = True

    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "engine": db.engine.dialect.name}
    except Exception as exc:  # pragma: no cover
        healthy = False
        checks["database"] = {"status": "error", "message": exc.__class__.__name__}

    try:
        stats = storage_stats()
        checks["storage"] = {"status": "ok", "file_count": stats["file_count"]}
    except Exception as exc:  # pragma: no cover
        healthy = False
        checks["storage"] = {"status": "error", "message": exc.__class__.__name__}

    checks["ocr"] = {
        "status": "ok",
        "provider": ocr_service.resolve_provider_key(),
        "is_demo_possible": True,
    }
    checks["ai"] = {
        "status": "ok" if ai_service.ai_configured() else "unconfigured",
        "mode": ai_service.resolve_mode(),
    }

    payload = {
        "status": "ok" if healthy else "degraded",
        "app": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "env": current_app.config["ENV"],
        "uptime_seconds": int(time.time() - _STARTED_AT),
        "server_time": datetime.now(timezone.utc).isoformat() + "Z",
        "checks": checks,
    }
    return ok(payload, "服务正常" if healthy else "部分依赖异常", 200 if healthy else 503)
