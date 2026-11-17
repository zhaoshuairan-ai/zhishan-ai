"""常见菜品营养库接口（公开，供知识库和图2热量字典使用）。"""
from __future__ import annotations

from flask import Blueprint, request

from ..services import dish_library
from ..utils.errors import NotFoundError, ValidationError
from ..utils.response import ok
from .common import pagination

bp = Blueprint("dishes", __name__)


@bp.get("/dishes")
def list_dishes():
    page, per_page = pagination(default_per_page=12, max_per_page=60)
    category = (request.args.get("category") or "all").strip()
    query = request.args.get("query") or request.args.get("q") or ""
    categories = dish_library.category_options()
    if category != "all" and category not in {item["value"] for item in categories}:
        raise ValidationError("菜品分类不存在")
    data = dish_library.search(query=query, category=category, page=page, per_page=per_page)
    return ok(data)


@bp.get("/dishes/<slug>")
def dish_detail(slug: str):
    dish = dish_library.get_by_slug(slug)
    if dish is None:
        raise NotFoundError("菜品不存在")
    return ok({"dish": dish, "related": dish_library.related(slug)})