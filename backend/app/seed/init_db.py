"""数据库初始化与轻量级表结构升级。

MVP 使用 SQLite + SQLAlchemy。为了在「已经存在旧数据库」的情况下也能安全启动，
这里提供了一个极简的列级升级器：只做「新增缺失列」这一类安全操作，
不做删除/改名。正式的版本化迁移建议接入 Alembic（见 docs/DEPLOYMENT.md）。
"""
from __future__ import annotations

import logging

from flask import current_app
from sqlalchemy import inspect, text

from ..extensions import db
from ..models import User, utcnow
from ..services import knowledge_service
from ..utils.security import hash_password
from .knowledge_seed import KNOWLEDGE_ENTRIES
from .dashboard_records import seed_dashboard_records

logger = logging.getLogger(__name__)

# (表名, 列名, 列定义) —— 只允许追加，用于老版本数据库平滑升级
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("knowledge_entries", "keywords", "VARCHAR(300) NOT NULL DEFAULT ''"),
    ("ocr_results", "corrected_at", "DATETIME"),
    ("ingredient_analyses", "diff", "JSON"),
    ("ingredient_analyses", "nutrition_notes", "JSON DEFAULT '[]'"),
    ("ingredient_analyses", "tags", "JSON DEFAULT '[]'"),
    ("ingredient_analyses", "personalization", "JSON"),
    ("nutrition_facts", "basis_note", "VARCHAR(300) NOT NULL DEFAULT ''"),
    ("analysis_records", "is_demo", "BOOLEAN NOT NULL DEFAULT 0"),
    ("analysis_records", "ocr_provider", "VARCHAR(32)"),
    ("users", "role", "VARCHAR(20) NOT NULL DEFAULT 'user'"),
    ("users", "family_id", "INTEGER"),
    ("knowledge_entries", "status", "VARCHAR(20) NOT NULL DEFAULT 'published'"),
    ("knowledge_entries", "scope", "VARCHAR(200) NOT NULL DEFAULT '预包装食品标签'"),
    ("knowledge_entries", "published_at", "DATETIME"),
    ("knowledge_entries", "created_by", "VARCHAR(40) NOT NULL DEFAULT ''"),
    ("knowledge_entries", "updated_by", "VARCHAR(40) NOT NULL DEFAULT ''"),
    ("feedbacks", "reply_content", "TEXT NOT NULL DEFAULT ''"),
    ("knowledge_entries", "calories_per_100g", "FLOAT NOT NULL DEFAULT 0"),
    ("knowledge_entries", "carbs_per_100g", "FLOAT NOT NULL DEFAULT 0"),
    ("knowledge_entries", "protein_per_100g", "FLOAT NOT NULL DEFAULT 0"),
    ("knowledge_entries", "fat_per_100g", "FLOAT NOT NULL DEFAULT 0"),
    ("knowledge_entries", "typical_portion_g", "INTEGER NOT NULL DEFAULT 200"),
    ("prompt_templates", "system_prompt", "TEXT NOT NULL DEFAULT ''"),
]

# 新增列的历史行需要补默认值（SQLite 的 ALTER TABLE 不会回填已有行）
BACKFILL_DEFAULTS: list[tuple[str, str, str]] = [
    ("ingredient_analyses", "nutrition_notes", "'[]'"),
    ("users", "role", "'user'"),
    ("knowledge_entries", "status", "'published'"),
    ("knowledge_entries", "scope", "'预包装食品标签'"),
    ("knowledge_entries", "created_by", "''"),
    ("knowledge_entries", "updated_by", "''"),
]


def ensure_feedback_schema() -> list[str]:
    """启动时补齐 feedback.reply_content，并把旧 reply 回填到新字段。

    这是针对已存在 SQLite 数据库的轻量迁移；新建数据库由 create_all 直接建列。
    """
    inspector = inspect(db.engine)
    if "feedbacks" not in set(inspector.get_table_names()):
        return []

    existing = {col["name"] for col in inspector.get_columns("feedbacks")}
    applied: list[str] = []

    if "reply_content" not in existing:
        try:
            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        'ALTER TABLE "feedbacks" '
                        'ADD COLUMN "reply_content" TEXT NOT NULL DEFAULT '''
                    )
                )
            applied.append("feedbacks.reply_content")
            logger.info("已补充字段 feedbacks.reply_content")
        except Exception as exc:  # pragma: no cover
            logger.warning("补充 feedbacks.reply_content 失败：%s", exc)

    try:
        with db.engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE feedbacks "
                    "SET reply_content = reply "
                    "WHERE (reply_content IS NULL OR reply_content = '') "
                    "AND reply IS NOT NULL AND reply != ''"
                )
            )
        if result.rowcount:
            applied.append(f"feedbacks.reply_content（{result.rowcount} 行回填）")
    except Exception as exc:  # pragma: no cover
        logger.warning("回填 feedbacks.reply_content 失败：%s", exc)

    return applied


def ensure_dish_nutrition_schema() -> list[str]:
    """为旧数据库补充菜品营养字段（幂等）。"""
    inspector = inspect(db.engine)
    if "knowledge_entries" not in set(inspector.get_table_names()):
        return []

    existing = {col["name"] for col in inspector.get_columns("knowledge_entries")}
    columns = {
        "calories_per_100g": "FLOAT NOT NULL DEFAULT 0",
        "carbs_per_100g": "FLOAT NOT NULL DEFAULT 0",
        "protein_per_100g": "FLOAT NOT NULL DEFAULT 0",
        "fat_per_100g": "FLOAT NOT NULL DEFAULT 0",
        "typical_portion_g": "INTEGER NOT NULL DEFAULT 200",
    }
    applied: list[str] = []

    for name, ddl in columns.items():
        if name in existing:
            continue
        try:
            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        f'ALTER TABLE "knowledge_entries" '
                        f'ADD COLUMN "{name}" {ddl}'
                    )
                )
            applied.append(f"knowledge_entries.{name}")
            logger.info("已补充字段 knowledge_entries.%s", name)
        except Exception as exc:  # pragma: no cover
            logger.warning("补充 knowledge_entries.%s 失败：%s", name, exc)

    return applied


def _backfill_defaults(targets: list[tuple[str, str, str]] | None = None) -> list[str]:
    """把新增列里历史行的 NULL 补成合理默认值（幂等）。"""
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    applied: list[str] = []
    for table, column, literal in targets if targets is not None else BACKFILL_DEFAULTS:
        if table not in tables:
            continue
        columns = {col["name"] for col in inspector.get_columns(table)}
        if column not in columns:
            continue
        try:
            with db.engine.begin() as conn:
                result = conn.execute(
                    text(f'UPDATE "{table}" SET "{column}" = {literal} WHERE "{column}" IS NULL')
                )
            if result.rowcount:
                applied.append(f"{table}.{column}（{result.rowcount} 行）")
        except Exception as exc:  # pragma: no cover
            logger.warning("回填默认值失败 %s.%s：%s", table, column, exc.__class__.__name__)
    return applied


def _ensure_columns() -> list[str]:
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    applied: list[str] = []
    for table, column, ddl in COLUMN_MIGRATIONS:
        if table not in tables:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column in existing:
            continue
        try:
            with db.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
            applied.append(f"{table}.{column}")
            logger.info("已补充字段 %s.%s", table, column)
        except Exception as exc:  # pragma: no cover
            logger.warning("补充字段失败 %s.%s：%s", table, column, exc.__class__.__name__)
    return applied


def ensure_demo_user() -> dict:
    config = current_app.config
    if not config.get("SEED_DEMO_ACCOUNT"):
        return {"created": False, "reason": "SEED_DEMO_ACCOUNT=0"}
    username = config.get("DEMO_USERNAME", "demo")
    password = config.get("DEMO_PASSWORD", "demo123456")
    user = User.query.filter_by(username=username).first()
    if user:
        return {"created": False, "reason": "already_exists", "username": username}
    user = User(
        username=username,
        display_name="演示账号",
        password_hash=hash_password(password),
        is_demo=True,
        created_at=utcnow(),
    )
    db.session.add(user)
    db.session.commit()
    logger.info("已创建演示账号 %s", username)
    return {"created": True, "username": username}


def init_database(*, verbose: bool = False, with_demo_data: bool = True) -> dict:
    db.create_all()
    migrated = _ensure_columns()
    migrated += ensure_feedback_schema()
    migrated += ensure_dish_nutrition_schema()
    backfilled = _backfill_defaults()
    knowledge = knowledge_service.upsert_seed(KNOWLEDGE_ENTRIES)
    from ..services import admin_service as _admin_service

    rules = _admin_service.seed_rules()
    from ..services import assistant_service

    assistant_stats = assistant_service.upsert_entries()
    demo_user = ensure_demo_user()
    demo_records = {"created": 0}
    if with_demo_data and demo_user.get("username"):
        from .demo_data import seed_demo

        demo_records = seed_demo()
        dashboard_records = seed_dashboard_records()
        if dashboard_records.get("total"):
            demo_records = dashboard_records
    message = (
        f"数据库初始化完成：知识库 {knowledge['total']} 条"
        f"（新增 {knowledge['created']}，更新 {knowledge['updated']}）；"
        f"科普问答 {assistant_stats['total']} 条；"
        f"核查规则 {rules['total']} 条；"
        f"演示账号：{demo_user.get('username') if demo_user.get('username') else '未创建'}；"
        f"演示记录：{demo_records.get('created', 0)} 条"
    )
    if migrated:
        message += f"；补充字段：{', '.join(migrated)}"
    if backfilled:
        message += f"；回填默认值：{', '.join(backfilled)}"
    if verbose:
        logger.info(message)
    return {
        "message": message,
        "knowledge": knowledge,
        "assistant": assistant_stats,
        "rules": rules,
        "demo_user": demo_user,
        "demo_records": demo_records,
        "migrated_columns": migrated,
        "backfilled_columns": backfilled,
    }
