"""Seed realistic dashboard history records.

Usage:
    backend/.venv/Scripts/python.exe backend/scripts/seed_dashboard_records.py

This script is idempotent for records marked with ``note='dashboard_seed_v1'``.
It creates dashboard history only; it does not call OCR or an AI provider.
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    AnalysisRecord,
    IngredientAnalysis,
    LabelCheck,
    User,
)

SEED_MARKER = "dashboard_seed_v1"

FOODS = [
    ("番茄鸡蛋面", ["西红柿", "鸡蛋", "面条"], "none_found"),
    ("清蒸鲈鱼", ["鲈鱼", "姜", "葱"], "none_found"),
    ("红烧肉", ["猪肉", "冰糖", "生抽"], "needs_review"),
    ("牛奶燕麦粥", ["牛奶", "燕麦", "香蕉"], "none_found"),
    ("西兰花炒虾仁", ["西兰花", "虾仁", "蒜"], "none_found"),
    ("香辣鸡腿堡", ["鸡腿", "面包", "生菜"], "suspected"),
    ("凉拌黄瓜", ["黄瓜", "蒜", "香油"], "none_found"),
    ("麻婆豆腐", ["豆腐", "猪肉", "豆瓣酱"], "needs_review"),
    ("酸奶水果杯", ["酸奶", "草莓", "蓝莓"], "none_found"),
    ("炸鸡配可乐", ["鸡胸肉", "面包糠", "可乐"], "suspected"),
    ("青菜豆腐汤", ["青菜", "豆腐", "香菇"], "none_found"),
    ("牛肉炒饭", ["牛肉", "米饭", "胡萝卜"], "needs_review"),
]

SUMMARY = {
    "none_found": "未发现明显问题，注意均衡搭配。",
    "needs_review": "需要进一步核实配料与营养信息。",
    "suspected": "发现疑似风险，建议人工复核后食用。",
}

DAILY_COUNTS = [5, 7, 4, 8, 6, 3, 7, 5, 4, 8, 6, 5, 7, 4]


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_for_user(user: User, *, offset: int = 0) -> int:
    rng = random.Random(20251115 + user.id)
    now = _now_utc_naive()
    created = 0

    for day_offset, count in enumerate(DAILY_COUNTS):
        day = now - timedelta(days=13 - day_offset)
        for index in range(count):
            food, ingredients, overall = FOODS[
                (day_offset * 7 + index + offset) % len(FOODS)
            ]
            extra_ingredients = (
                "鸡蛋", "牛奶", "西红柿", "猪肉", "青菜",
                "米饭", "豆腐", "黄瓜",
            )
            ingredients = [
                *ingredients,
                extra_ingredients[
                    (day_offset * 5 + index + offset) % len(extra_ingredients)
                ],
            ]
            # spread records over the day, keeping "today" populated
            hour = 8 + (index * 2 + day_offset) % 12
            minute = (index * 13 + day_offset * 7) % 60
            created_at = day.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            record = AnalysisRecord(
                user_id=user.id,
                food_name=food,
                brand="",
                status="analyzed",
                data_source="real",
                analysis_mode="dish",
                ocr_provider="dish_vision",
                overall_check=overall,
                summary=SUMMARY[overall],
                note=SEED_MARKER,
                is_demo=False,
                created_at=created_at,
                analyzed_at=created_at,
            )
            db.session.add(record)
            db.session.flush()

            db.session.add(
                IngredientAnalysis(
                    record_id=record.id,
                    mode="dish",
                    model="deepseek",
                    summary=SUMMARY[overall],
                    ingredients=[
                        {
                            "name": name,
                            "role": "main" if i < 2 else "auxiliary",
                            "category": "食材",
                            "explanation": "常见食材，按标签用量估算。",
                        }
                        for i, name in enumerate(ingredients)
                    ],
                )
            )
            db.session.add(
                LabelCheck(
                    record_id=record.id,
                    ruleset_version="seed-2025.11",
                    overall=overall,
                    items=[],
                    counts={
                        "pass": 3 if overall == "none_found" else 1,
                        "review": 0 if overall == "none_found" else 2,
                        "suspected": 0 if overall != "suspected" else 1,
                    },
                    coverage={"seeded": True},
                )
            )
            created += 1

    return created


def main() -> None:
    app = create_app()
    with app.app_context():
        # Remove a previous run of this specific seeding script only.
        old = AnalysisRecord.query.filter_by(note=SEED_MARKER).all()
        for record in old:
            db.session.delete(record)
        db.session.commit()

        users = User.query.filter(User.username.in_(["demo", "zhao"])).all()
        total = 0
        for index, user in enumerate(users):
            total += seed_for_user(user, offset=index * 3)

        # Make demo names look like real product users rather than test fixtures.
        for user in users:
            if user.username == "demo":
                user.display_name = "张三"
            elif user.username == "zhao":
                user.display_name = "李四"

        db.session.commit()
        print(f"seeded {total} dashboard records for {[u.username for u in users]}")


if __name__ == "__main__":
    main()
