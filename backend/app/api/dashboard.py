"""首页仪表盘统计数据（全部来自数据库，不含任何虚构数字）。"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, current_app, g
from sqlalchemy import func

from ..extensions import db
from ..models import AnalysisRecord, IngredientAnalysis, LabelCheck, KnowledgeEntry
from ..services import ai_service, knowledge_service
from ..services import ocr as ocr_service
from ..utils.response import ok
from ..utils.security import login_required

bp = Blueprint("dashboard", __name__)

CHECK_LABELS = {
    "none_found": "未发现明显问题",
    "needs_review": "需要进一步核实",
    "suspected": "发现疑似问题",
}


@bp.get("/dashboard")
@login_required
def dashboard():
    user_id = g.current_user.id
    base = AnalysisRecord.query.filter(AnalysisRecord.user_id == user_id)
    records = base.order_by(AnalysisRecord.created_at.desc()).limit(300).all()
    total = base.count()
    analyzed = base.filter(AnalysisRecord.status == "analyzed").count()
    demo_count = base.filter(AnalysisRecord.is_demo.is_(True)).count()
    demo_analyzed = base.filter(AnalysisRecord.is_demo.is_(True), AnalysisRecord.status == "analyzed").count()
    real_analyzed = base.filter(AnalysisRecord.is_demo.is_(False), AnalysisRecord.status == "analyzed").count()

    ingredient_total = 0
    ingredient_real = 0
    citations_total = 0
    top_ingredients: Counter[str] = Counter()
    for record in records:
        if record.ingredient:
            items = [i for i in (record.ingredient.ingredients or []) if isinstance(i, dict)]
            ingredient_total += len(items)
            if not record.is_demo:
                ingredient_real += len(items)
            citations_total += len(record.ingredient.citations or [])
            for item in items:
                name = str(item.get("name") or "").strip()
                if name and len(name) <= 12:
                    top_ingredients[name] += 1

    check_counts = dict(
        db.session.query(LabelCheck.overall, func.count(LabelCheck.id))
        .join(AnalysisRecord, AnalysisRecord.id == LabelCheck.record_id)
        .filter(AnalysisRecord.user_id == user_id)
        .group_by(LabelCheck.overall)
        .all()
    )
    status_counts = dict(
        db.session.query(AnalysisRecord.status, func.count(AnalysisRecord.id))
        .filter(AnalysisRecord.user_id == user_id)
        .group_by(AnalysisRecord.status)
        .all()
    )

    # 近 14 天趋势（按日期补零，明确来自真实记录）
    # 数据库存的是 UTC 时间，展示按服务器本地时区折算，避免跨日错位
    today = date.today()
    days = [today - timedelta(days=offset) for offset in range(13, -1, -1)]
    trend_counter: Counter[str] = Counter()
    for record in records:
        if record.created_at:
            local_date = record.created_at.replace(tzinfo=timezone.utc).astimezone().date()
            trend_counter[local_date.isoformat()] += 1
    trend = [{"date": day.isoformat(), "label": day.strftime("%m-%d"), "count": trend_counter.get(day.isoformat(), 0)} for day in days]

    recent = [record.to_summary() for record in records[:5]]

    featured = (
        KnowledgeEntry.query.filter(KnowledgeEntry.is_featured.is_(True))
        .order_by(KnowledgeEntry.sort_order.asc())
        .limit(4)
        .all()
    )

    rule_counts = Counter()
    for record in records:
        if record.check and record.check.counts:
            for level in ("suspected", "review", "info", "pass"):
                rule_counts[level] += int(record.check.counts.get(level, 0))

    payload = {
        "totals": {
            "records": total,
            "analyzed": analyzed,
            "demo_records": demo_count,
            "demo_analyzed": demo_analyzed,
            "real_records": total - demo_count,
            "real_analyzed": real_analyzed,
            "ingredients_explained": ingredient_total,
            "ingredients_real": ingredient_real,
            "knowledge_citations": citations_total,
            "suspected": check_counts.get("suspected", 0),
            "needs_review": check_counts.get("needs_review", 0),
            "none_found": check_counts.get("none_found", 0),
        },
        "status_distribution": [
            {"key": key, "name": record_label(key), "value": status_counts.get(key, 0)} for key in status_counts
        ],
        "check_distribution": [
            {"key": key, "name": CHECK_LABELS[key], "value": check_counts.get(key, 0)}
            for key in CHECK_LABELS
            if check_counts.get(key, 0) > 0
        ],
        "level_counts": dict(rule_counts),
        "trend": trend,
        "top_ingredients": [{"name": name, "value": count} for name, count in top_ingredients.most_common(8)],
        "recent_records": recent,
        "featured_knowledge": [entry.to_public(brief=True) for entry in featured],
        "knowledge_stats": knowledge_service.stats(),
        "service_status": {
            "ocr_provider": ocr_service.resolve_provider_key(),
            "ocr_label": ocr_service.active_provider_label(),
            "ai_mode": ai_service.resolve_mode(),
            "ai_configured": ai_service.ai_configured(),
            "ai_model": current_app.config.get("AI_MODEL") if ai_service.ai_configured() else None,
        },
        "onboarding": {
            "is_first_visit": total == 0,
            "steps": [
                {
                    "title": "拍一张食品标签照片",
                    "description": "支持 JPG / PNG / WEBP，手机可直接调用相机；尽量让文字占满画面并避免反光。",
                },
                {
                    "title": "核对识别出的文字",
                    "description": "识别结果可逐字修改，低置信度字段会被标出；配料表也可手动输入。",
                },
                {
                    "title": "查看配料与营养解读",
                    "description": "系统拆分配料并解释用途，同时用图表展示营养数据与 NRV 占比。",
                },
                {
                    "title": "核对核查结论与来源",
                    "description": "标签完整性、日期与数值逻辑会给出审慎结论，每条结论都注明依据与待确认事项。",
                },
                {
                    "title": "生成并分享报告",
                    "description": "报告可在电脑或手机上打开、打印或另存为 PDF，也可用同一账号跨设备查看。",
                },
            ],
        },
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
    }
    return ok(payload)


def record_label(status: str) -> str:
    from ..models.record import STATUS_LABELS

    return STATUS_LABELS.get(status, status)
