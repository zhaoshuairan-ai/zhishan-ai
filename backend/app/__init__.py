"""Flask 应用工厂。

分层：api（路由/参数校验）→ services（业务逻辑）→ models（持久化）。
"""
from __future__ import annotations

import logging
import mimetypes
import time
import uuid
from http import HTTPStatus
from pathlib import Path

from flask import Flask, g, request
from werkzeug.exceptions import NotFound

from .config import PROJECT_ROOT, Config
from .extensions import cors, db
from .utils.errors import register_error_handlers
from .utils.response import ErrorCode, fail


def _configure_logging(app: Flask) -> None:
    level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def _before():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        g.started_at = time.perf_counter()

    @app.after_request
    def _after(response):
        started = getattr(g, "started_at", None)
        if started is not None:
            response.headers["X-Response-Time"] = f"{(time.perf_counter() - started) * 1000:.1f}ms"
        response.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def _register_cli(app: Flask) -> None:
    import click

    @app.cli.command("init-db")
    def init_db_command():
        """创建/升级数据库表结构并写入知识库种子数据。"""
        from .seed.init_db import init_database

        result = init_database(verbose=True)
        click.echo(result["message"])

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """写入演示账号与演示分析记录（明确标记为演示数据）。"""
        from .seed.demo_data import seed_demo

        result = seed_demo()
        click.echo(result["message"])


def _register_frontend(app: Flask) -> None:
    """生产环境单服务部署：由 Flask 直接托管前端构建产物。

    开发环境通常由 Vite 提供页面，此处默认关闭（SERVE_FRONTEND=0）。
    """
    dist = Path(app.config.get("FRONTEND_DIST") or (PROJECT_ROOT / "frontend" / "dist")).resolve()
    enabled = bool(app.config.get("SERVE_FRONTEND")) and dist.exists()
    if not enabled:
        if app.config.get("SERVE_FRONTEND") and not dist.exists():
            app.logger.warning(
                "SERVE_FRONTEND=1 但未找到前端构建产物（%s），请先在 frontend 目录执行构建（npm run build）。",
                dist,
            )
        return

    mimetypes.add_type("application/manifest+json", ".webmanifest")
    mimetypes.add_type("text/javascript", ".js")

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path: str):
        if path.startswith("api/") or path == "api":
            return fail("接口不存在", ErrorCode.NOT_FOUND, HTTPStatus.NOT_FOUND)
        candidate = (dist / path).resolve()
        if path and dist in candidate.parents and candidate.is_file():
            # 使用 POSIX 风格相对路径，避免 Windows 反斜杠被 werkzeug 当作单个文件名
            return app.send_static_file(candidate.relative_to(dist).as_posix())
        # SPA 路由回退
        index = dist / "index.html"
        if not index.exists():  # pragma: no cover
            raise NotFound("前端尚未构建")
        response = app.send_static_file("index.html")
        response.headers["Cache-Control"] = "no-cache"
        return response

    app.static_folder = str(dist)
    app.logger.info("已启用前端静态托管：%s", dist)


def create_app(config_object=None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_object or Config)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    _configure_logging(app)
    app.logger.info("启动 %s v%s（环境：%s）", app.config["APP_NAME"], app.config["APP_VERSION"], app.config["ENV"])

    # 目录准备（数据库目录、上传目录）
    Path(app.config["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    # 扩展
    db.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"] or "*"}},
        supports_credentials=False,
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    _register_hooks(app)
    register_error_handlers(app)

    from .api import register_blueprints

    register_blueprints(app)
    _register_cli(app)
    _register_frontend(app)

    with app.app_context():
        # 确保模型被导入，db.create_all() 才能建出全部表
        from . import models  # noqa: F401

        # 旧数据库平滑补齐反馈回复字段（幂等）
        try:
            from .seed.init_db import (
                ensure_dish_nutrition_schema,
                ensure_feedback_schema,
            )

            ensure_feedback_schema()
            ensure_dish_nutrition_schema()
        except Exception:
            app.logger.exception("反馈回复字段迁移失败，请执行 flask init-db")

    return app
