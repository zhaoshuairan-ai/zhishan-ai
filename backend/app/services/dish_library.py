"""常见菜品营养库：加载 JSON、搜索、别名匹配与份量换算。"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "dish_database.json"

DISH_SOURCE = "菜品营养库（参考《中国食物成分表》与常见食堂做法估算）"


def _norm(text: str) -> str:
    value = (text or "").strip().lower()
    return re.sub(r"[\s()（）\[\]【】,，、;；:：。./\\\-_]+", "", value)


@lru_cache(maxsize=1)
def load_all() -> tuple[dict, ...]:
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    dishes: list[dict] = []
    for index, item in enumerate(raw, start=1):
        dish = dict(item)
        dish["slug"] = f"dish-{index:03d}"
        dish["source"] = DISH_SOURCE
        dishes.append(dish)
    return tuple(dishes)


def public_dish(dish: dict) -> dict:
    return {
        "slug": dish["slug"],
        "dish_name": dish["dish_name"],
        "aliases": list(dish.get("aliases") or []),
        "category": dish.get("category") or "常见菜品",
        "calories_per_100g": float(dish["calories_per_100g"]),
        "protein_per_100g": float(dish["protein_per_100g"]),
        "fat_per_100g": float(dish["fat_per_100g"]),
        "carbs_per_100g": float(dish["carbs_per_100g"]),
        "typical_portion_g": int(dish["typical_portion_g"]),
        "health_tip": dish.get("health_tip") or "",
        "source": DISH_SOURCE,
    }


def category_options() -> list[dict]:
    counts: dict[str, int] = {}
    for dish in load_all():
        category = dish.get("category") or "常见菜品"
        counts[category] = counts.get(category, 0) + 1
    options = [
        {"value": key, "label": key, "count": count}
        for key, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    return [{"value": "all", "label": "全部", "count": len(load_all())}] + options


def search(
    *,
    query: str = "",
    category: str = "all",
    page: int = 1,
    per_page: int = 12,
) -> dict:
    keyword = _norm(query)
    items = list(load_all())
    if category and category != "all":
        items = [dish for dish in items if dish.get("category") == category]
    if keyword:
        matched = []
        for dish in items:
            haystack = _norm(
                " ".join(
                    [dish["dish_name"], *[str(alias) for alias in dish.get("aliases") or []], dish.get("category") or ""]
                )
            )
            if keyword in haystack:
                matched.append(dish)
        items = matched

    total = len(items)
    page = max(1, page)
    per_page = max(1, min(per_page, 60))
    start = (page - 1) * per_page
    sliced = items[start : start + per_page]
    return {
        "items": [public_dish(dish) for dish in sliced],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
        "query": query,
        "category": category,
        "categories": category_options(),
        "source": DISH_SOURCE,
    }


def get_by_slug(slug: str) -> dict | None:
    for dish in load_all():
        if dish["slug"] == slug:
            return public_dish(dish)
    return None


def related(slug: str, limit: int = 4) -> list[dict]:
    current = next((dish for dish in load_all() if dish["slug"] == slug), None)
    if current is None:
        return []
    same = [
        dish
        for dish in load_all()
        if dish["slug"] != slug and dish.get("category") == current.get("category")
    ]
    return [public_dish(dish) for dish in same[:limit]]


def find_dish(name: str) -> dict | None:
    """按菜名/别名精确匹配，再做包含匹配与相似度兜底。"""
    key = _norm(name)
    if not key:
        return None

    dishes = list(load_all())
    for dish in dishes:
        candidates = [dish["dish_name"], *[str(alias) for alias in dish.get("aliases") or []]]
        if any(_norm(candidate) == key for candidate in candidates):
            return public_dish(dish)

    for dish in dishes:
        candidates = [dish["dish_name"], *[str(alias) for alias in dish.get("aliases") or []]]
        if any(len(_norm(candidate)) >= 3 and (_norm(candidate) in key or key in _norm(candidate)) for candidate in candidates):
            return public_dish(dish)

    best: tuple[float, dict] | None = None
    for dish in dishes:
        candidates = [dish["dish_name"], *[str(alias) for alias in dish.get("aliases") or []]]
        for candidate in candidates:
            ratio = SequenceMatcher(None, key, _norm(candidate)).ratio()
            if ratio >= 0.72 and (best is None or ratio > best[0]):
                best = (ratio, dish)
    return public_dish(best[1]) if best else None


def calculate(dish: dict, weight_g: float) -> dict:
    weight = max(1.0, float(weight_g or dish["typical_portion_g"]))
    factor = weight / 100.0
    return {
        "weight_g": round(weight, 1),
        "calories": round(dish["calories_per_100g"] * factor, 1),
        "protein_g": round(dish["protein_per_100g"] * factor, 1),
        "fat_g": round(dish["fat_per_100g"] * factor, 1),
        "carbs_g": round(dish["carbs_per_100g"] * factor, 1),
    }