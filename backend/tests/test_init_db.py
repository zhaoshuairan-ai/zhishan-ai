"""数据库初始化与表结构升级测试。"""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.extensions import db
from app.models import AnalysisRecord, IngredientAnalysis, KnowledgeEntry, User
from app.seed.init_db import COLUMN_MIGRATIONS, _backfill_defaults, _ensure_columns, init_database


def test_init_database_is_idempotent(app):
    """重复执行初始化不应产生重复数据或报错。"""
    with app.app_context():
        before = KnowledgeEntry.query.count()
        first = init_database(with_demo_data=False)
        second = init_database(with_demo_data=False)
        after = KnowledgeEntry.query.count()

        assert after == before, "知识库数量应保持稳定（按 slug 幂等 upsert）"
        assert first["knowledge"]["total"] == after
        assert "message" in first and "数据库初始化完成" in first["message"]
        # TestConfig 关闭了演示账号，因此不会创建 demo 用户
        assert second["demo_user"].get("username") is None


def test_all_expected_tables_exist(app):
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
    expected = {
        "users",
        "auth_sessions",
        "analysis_records",
        "uploaded_images",
        "ocr_results",
        "ingredient_analyses",
        "nutrition_facts",
        "label_checks",
        "knowledge_entries",
        "report_meta",
    }
    assert expected <= tables, expected - tables


def test_ensure_columns_is_noop_when_up_to_date(app):
    """当前结构已包含全部迁移列时，不应再执行任何 ALTER。"""
    with app.app_context():
        inspector = inspect(db.engine)
        for table, column, _ in COLUMN_MIGRATIONS:
            columns = {col["name"] for col in inspector.get_columns(table)}
            assert column in columns, f"{table}.{column} 缺失"
        assert _ensure_columns() == []


def test_migrations_cover_new_column(app):
    """新增的 nutrition_notes 必须登记在迁移清单里，保证旧库能被升级。"""
    assert ("ingredient_analyses", "nutrition_notes", "JSON DEFAULT '[]'") in COLUMN_MIGRATIONS


def test_backfill_null_nutrition_notes(app):
    """ALTER TABLE 新增列不会回填历史行，初始化时必须把 NULL 补成 []。"""
    with app.app_context():
        # 真实场景：旧库通过 ALTER TABLE 新增可空列，历史行为 NULL
        db.session.execute(text("CREATE TABLE _backfill_probe (id INTEGER PRIMARY KEY, value JSON)"))
        db.session.execute(text("INSERT INTO _backfill_probe (value) VALUES (NULL)"))
        db.session.commit()
        try:
            applied = _backfill_defaults([("_backfill_probe", "value", "'[]'")])
            assert applied and "_backfill_probe.value" in applied[0]
            value = db.session.execute(text("SELECT value FROM _backfill_probe")).scalar_one()
            assert value == "[]"
        finally:
            db.session.execute(text("DROP TABLE IF EXISTS _backfill_probe"))
            db.session.commit()


def test_backfill_registered_for_nutrition_notes(app):
    from app.seed.init_db import BACKFILL_DEFAULTS

    assert ("ingredient_analyses", "nutrition_notes", "'[]'") in BACKFILL_DEFAULTS
