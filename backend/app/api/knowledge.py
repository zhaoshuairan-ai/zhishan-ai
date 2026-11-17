"""食品安全知识库接口。"""
from __future__ import annotations

from flask import Blueprint, current_app, request

from ..extensions import db
from ..models.knowledge import CATEGORIES, VERIFICATION
from ..services import dish_nutrition_service, knowledge_service
from ..utils.errors import NotFoundError, ValidationError
from ..utils.response import ok
from ..utils.security import login_required
from .common import pagination

bp = Blueprint("knowledge", __name__)


@bp.get("/knowledge")
def list_knowledge():
    page, per_page = pagination(default_per_page=12, max_per_page=50)
    category = (request.args.get("category") or "all").strip()
    if category != "all" and category not in CATEGORIES:
        raise ValidationError(f"分类不存在，可选：{'、'.join(CATEGORIES)}")
    query = request.args.get("query") or request.args.get("q") or ""
    featured = request.args.get("featured") in {"1", "true", "yes"}
    data = knowledge_service.search(query=query, category=category, page=page, per_page=per_page, featured_only=featured)
    data["categories"] = knowledge_service.category_options()
    current_app.logger.info(
        "[knowledge-public] category=%s query=%r total=%s pages=%s verified_only=1",
        category,
        query,
        data.get("total", 0),
        data.get("pages", 0),
    )
    data["verification_labels"] = VERIFICATION
    return ok(data)


@bp.get("/knowledge/<int:entry_id>")
def knowledge_detail(entry_id: int):
    entry = knowledge_service.get_by_id(entry_id)
    if entry is None:
        raise NotFoundError("知识条目不存在")
    related = (
        entry.__class__.query.filter(entry.__class__.category == entry.category, entry.__class__.id != entry.id)
        .order_by(entry.__class__.sort_order.asc())
        .limit(4)
        .all()
    )
    return ok(
        {
            "entry": entry.to_public(),
            "related": [item.to_public(brief=True) for item in related],
        }
    )


@bp.post("/knowledge/<int:entry_id>/nutrition")
@login_required
def fill_dish_nutrition(entry_id: int):
    """为知识库中的菜品按需补齐营养数据。

    DeepSeek 调用只在后端完成，前端不接触 API Key。
    """
    entry = knowledge_service.get_by_id(entry_id)

    if entry is None:
        raise NotFoundError("知识条目不存在")

    if entry.category != "dish":
        raise ValidationError("只有菜品条目可以补全营养数据")

    result = dish_nutrition_service.auto_fill_dish_nutrition(entry)
    dish_nutrition_service.ensure_dish_summary(entry)
    db.session.commit()

    return ok(
        {
            "entry": entry.to_public(),
            "nutrition_ai": result,
        },
        result.get("message") or "营养数据已更新",
    )


@bp.post("/knowledge/estimate")
def estimate_knowledge_nutrition():
    """根据菜名和描述实时测算，并回写数据库。

    请求体支持：
    {
      "entry_id": 128,
      "title": "水煮肉",
      "description": "猪里脊、豆芽、辣椒..."
    }
    """
    payload = request.get_json(silent=True) or {}
    entry_id = payload.get("entry_id")
    title = str(payload.get("title") or "").strip()
    description = str(
        payload.get("description")
        or payload.get("content")
        or payload.get("summary")
        or ""
    ).strip()

    entry = None
    if entry_id not in (None, "", 0):
        try:
            entry = knowledge_service.get_by_id(int(entry_id))
        except (TypeError, ValueError):
            raise ValidationError("entry_id 必须是整数")

        if entry is not None and entry.category != "dish":
            raise ValidationError("只有菜品条目可以补全营养数据")

    if entry is None and not title:
        raise ValidationError("请提供菜品标题或 entry_id")

    if entry is not None:
        print(
            f"[nutrition-api] entry_id={entry.id} title={entry.title} "
            f"description={description[:200]}",
            flush=True,
        )
        result = dish_nutrition_service.auto_fill_dish_nutrition(entry)
        dish_nutrition_service.ensure_dish_summary(entry)
        db.session.commit()
        return ok(
            {
                "entry": entry.to_public(),
                "nutrition_ai": result,
                "nutrition": {
                    "calories_per_100g": entry.calories_per_100g,
                    "carbs_per_100g": entry.carbs_per_100g,
                    "protein_per_100g": entry.protein_per_100g,
                    "fat_per_100g": entry.fat_per_100g,
                    "typical_portion_g": entry.typical_portion_g,
                },
            },
            result.get("message") or "营养数据已更新",
        )

    print(
        f"[nutrition-api] transient title={title} description={description[:200]}",
        flush=True,
    )
    result = dish_nutrition_service.estimate_dish_nutrition(
        title=title,
        summary=description,
    )
    return ok(
        {
            "entry": None,
            "nutrition_ai": result,
            "nutrition": {
                "calories_per_100g": result.get("calories_per_100g", 0),
                "carbs_per_100g": result.get("carbs_per_100g", 0),
                "protein_per_100g": result.get("protein_per_100g", 0),
                "fat_per_100g": result.get("fat_per_100g", 0),
                "typical_portion_g": result.get("typical_portion_g", 200),
            },
        },
        result.get("message") or "营养测算完成",
    )
