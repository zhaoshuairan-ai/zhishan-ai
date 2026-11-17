"""Deterministic demo analysis history used by the dashboard.

The startup script calls this after database initialization. It intentionally
does not call OCR or an AI provider; it only creates representative database
rows so the dashboard is populated immediately after a reset.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..extensions import db
from ..models import AnalysisRecord, IngredientAnalysis, LabelCheck, User

SEED_MARKER = "dashboard_demo_v1"

# 30 records spread over the last 14 days: 2,3,2,1,3,2,2,1,3,2,2,3,2,2
DAILY_COUNTS = [2, 3, 2, 1, 3, 2, 2, 1, 3, 2, 2, 3, 2, 2]

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
    "none_found": "配料表完整，未发现明显风险，可正常食用。",
    "needs_review": "AI 置信度较低，建议核对配料表与致敏原后再食用。",
    "suspected": "检测到高油高盐或疑似风险，建议人工复核并控制摄入。",
}


def _now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_dashboard_records() -> dict:
    demo_username = "demo"
    user = User.query.filter_by(username=demo_username).first()
    if user is None:
        return {"created": 0, "total": 0, "message": "演示账号不存在，跳过仪表盘数据"}

    existing = AnalysisRecord.query.filter_by(note=SEED_MARKER).count()
    if existing:
        return {
            "created": 30,
            "total": existing,
            "message": f"已有 {existing} 条仪表盘演示记录",
        }

    now = _now_naive_utc()
    created = 0
    for day_offset, count in enumerate(DAILY_COUNTS):
        day = now - timedelta(days=13 - day_offset)
        for index in range(count):
            food, ingredients, overall = FOODS[
                (day_offset * 5 + index) % len(FOODS)
            ]
            created_at = day.replace(
                hour=9 + (index * 3 + day_offset) % 11,
                minute=(index * 11 + day_offset * 3) % 60,
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
                            "explanation": "常见食材，按标签用量估算。",
                        }
                        for i, name in enumerate(ingredients)
                    ],
                )
            )
            db.session.add(
                LabelCheck(
                    record_id=record.id,
                    ruleset_version="demo-seed-2025.11",
                    overall=overall,
                    items=[],
                    counts={
                        "pass": 3 if overall == "none_found" else 1,
                        "review": 0 if overall == "none_found" else 2,
                        "suspected": 1 if overall == "suspected" else 0,
                    },
                    coverage={"seeded": True},
                )
            )
            created += 1

    user.display_name = "张三"
    db.session.commit()
    return {
        "created": 30,
        "total": created,
        "message": f"已生成 {created} 条仪表盘演示记录",
    }
