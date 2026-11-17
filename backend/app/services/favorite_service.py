"""食谱收藏：列表、收藏、取消收藏、加入今日排期。"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy.orm.attributes import flag_modified

from ..extensions import db
from ..models import PantryItem, RecipePlan, UserFavoriteRecipe
from ..utils.errors import NotFoundError, ValidationError
from . import cooking_service, ingredient_rules

DISCLAIMER = "食谱用于烹饪参考；肉类、蛋类和水产请彻底加热，具体饮食建议请结合自身情况。"


def _base_name(name: str) -> str:
    text = re.sub(r"[（(].*?[）)]", "", str(name or "")).strip()
    text = re.sub(r"\s+\d+(?:\.\d+)?\s*[^\s]*$", "", text).strip()
    text = re.sub(r"\s+\d+$", "", text).strip()
    return text or str(name or "").strip()


def _match_pantry(pantry: list[PantryItem], name: str) -> PantryItem | None:
    target = _base_name(name)
    for item in pantry:
        source = _base_name(item.name)
        if source == target or source in target or target in source:
            return item
    return None


def _split_ingredient(line: str) -> tuple[str, str]:
    text = str(line or "").strip()
    if not text:
        return "", ""
    match = re.match(r"^(.+?)\s+([\d一二三四五六七八九十百半].*)$", text)
    if match:
        return match.group(1).strip(" ：:"), match.group(2).strip()
    return text, ""


def _ingredients(data: dict) -> list[dict]:
    raw = data.get("main_ingredients")
    if not isinstance(raw, list) or not raw:
        raw = data.get("ingredients") if isinstance(data.get("ingredients"), list) else []
    result: list[dict] = []
    for value in raw:
        if isinstance(value, dict):
            name = str(value.get("name") or "").strip()
            amount = str(value.get("amount") or "").strip()
            role = str(value.get("role") or "").strip()
            if not name:
                continue
            if not role:
                role = ingredient_rules.classify_role(name)
            if role == "auxiliary":
                continue
            result.append({"name": name, "amount": amount})
        else:
            name, amount = _split_ingredient(str(value))
            if name and ingredient_rules.classify_role(name) != "auxiliary":
                result.append({"name": name, "amount": amount})
    # 没有主料字段时，从完整 ingredients 中再补一次
    if not result and isinstance(data.get("ingredients"), list):
        for value in data["ingredients"]:
            if isinstance(value, dict):
                name = str(value.get("name") or "").strip()
                amount = str(value.get("amount") or "").strip()
            else:
                name, amount = _split_ingredient(str(value))
            if name and ingredient_rules.classify_role(name) != "auxiliary":
                result.append({"name": name, "amount": amount})
    seen = set()
    unique = []
    for item in result:
        key = (item["name"], item["amount"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _nutrition(data: dict) -> dict:
    """收藏可能来自早期助手回答，nutrition 为 0 时按食材做一次保守估算。"""
    nutrition = data.get("nutrition") if isinstance(data.get("nutrition"), dict) else {}
    energy = float(nutrition.get("energy_kcal") or 0)
    if energy > 0:
        return nutrition
    lines: list[str] = []
    for item in data.get("ingredients") or data.get("main_ingredients") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            amount = str(item.get("amount") or "").strip()
            if name:
                lines.append(f"{name} {amount}".strip())
        elif str(item).strip():
            lines.append(str(item).strip())
    if not lines:
        return nutrition
    estimated = cooking_service._estimate_nutrition(lines)
    return {**nutrition, **estimated}


def enrich(favorite: UserFavoriteRecipe, pantry: list[PantryItem] | None = None) -> dict:
    data = favorite.recipe_data or {}
    pantry = pantry if pantry is not None else PantryItem.query.filter_by(user_id=favorite.user_id).all()
    mains = _ingredients(data)
    missing = []
    for item in mains:
        matched = _match_pantry(pantry, item["name"])
        item["from_pantry"] = matched is not None
        if matched is None:
            missing.append({"name": item["name"], "amount": item["amount"]})
    payload = favorite.to_public()
    payload["main_ingredients"] = mains
    payload["missing"] = missing
    nutrition = _nutrition(data)
    payload["energy_kcal"] = nutrition.get("energy_kcal") or 0
    payload["nutrition"] = nutrition
    return payload


def favorite_missing(user_id: int, favorite_id: int, family_user_ids: list[int] | None = None) -> dict:
    """按单条收藏计算缺料，供“去采购”定向购物清单使用。"""
    favorite = UserFavoriteRecipe.query.filter_by(id=favorite_id, user_id=user_id).first()
    if favorite is None:
        raise NotFoundError("收藏不存在")
    scope_ids = family_user_ids or [user_id]
    pantry = PantryItem.query.filter(PantryItem.user_id.in_(scope_ids)).all()
    payload = enrich(favorite, pantry)
    payload["recipe_id"] = favorite.id
    payload["recipe_name"] = favorite.recipe_name
    payload["missing"] = payload.get("missing") or []
    return payload


def list_favorites(user_id: int, family_user_ids: list[int] | None = None) -> list[dict]:
    favorites = (
        UserFavoriteRecipe.query.filter_by(user_id=user_id)
        .order_by(UserFavoriteRecipe.created_at.desc(), UserFavoriteRecipe.id.desc())
        .all()
    )
    scope_ids = family_user_ids or [user_id]
    pantry = PantryItem.query.filter(PantryItem.user_id.in_(scope_ids)).all()
    return [enrich(item, pantry) for item in favorites]


def add_favorite(user_id: int, recipe_name: str, recipe_data: dict) -> tuple[dict, bool]:
    name = str(recipe_name or "").strip()[:120]
    if not name:
        raise ValidationError("菜名不能为空")
    if not isinstance(recipe_data, dict) or not recipe_data:
        raise ValidationError("食谱数据不能为空")
    existing = UserFavoriteRecipe.query.filter_by(user_id=user_id, recipe_name=name).first()
    created = existing is None
    if existing is None:
        existing = UserFavoriteRecipe(user_id=user_id, recipe_name=name, recipe_data=recipe_data)
        db.session.add(existing)
    else:
        existing.recipe_data = recipe_data
    db.session.commit()
    return enrich(existing), created


def remove_favorite(user_id: int, favorite_id: int) -> dict:
    favorite = UserFavoriteRecipe.query.filter_by(id=favorite_id, user_id=user_id).first()
    if favorite is None:
        raise NotFoundError("收藏不存在")
    db.session.delete(favorite)
    db.session.commit()
    return {"deleted_id": favorite_id}


def _favorite_meal(favorite: UserFavoriteRecipe, family_user_ids: list[int] | None = None) -> dict:
    data = favorite.recipe_data or {}
    scope_ids = family_user_ids or [favorite.user_id]
    pantry = PantryItem.query.filter(PantryItem.user_id.in_(scope_ids)).all()
    ingredients = []
    missing = []
    for item in _ingredients(data):
        matched = _match_pantry(pantry, item["name"])
        ingredient = {
            "name": item["name"],
            "amount": item["amount"],
            "from_pantry": matched is not None,
            "expiring": bool(matched and matched.status()[0] == "expiring"),
            "role": ingredient_rules.classify_role(item["name"]),
        }
        ingredients.append(ingredient)
        if matched is None:
            missing.append({"name": item["name"], "amount": item["amount"], "reason": "库存没有该食材"})
    steps = [str(step)[:500] for step in (data.get("steps") or [])][:20]
    if not steps and isinstance(data.get("versions"), dict):
        steps = [str(step)[:500] for step in (data["versions"].get("novice", {}) or {}).get("steps", [])][:20]
    nutrition = _nutrition(data)
    return {
        "meal_type": "收藏菜谱",
        "name": favorite.recipe_name,
        "ingredients": ingredients,
        "main_ingredients": [item for item in ingredients if item["role"] != "auxiliary"],
        "auxiliary_ingredients": [item for item in ingredients if item["role"] == "auxiliary"],
        "steps": steps,
        "tips": str(data.get("tips") or "")[:400],
        "nutrition": {
            "energy_kcal": nutrition.get("energy_kcal") or 0,
            "protein_g": nutrition.get("protein_g") or 0,
            "fat_g": nutrition.get("fat_g") or 0,
            "carbs_g": nutrition.get("carbs_g") or 0,
            "sodium_mg": nutrition.get("sodium_mg") or 0,
            "sugar_g": nutrition.get("sugar_g") or 0,
        },
        "suitability": {},
        "missing": missing,
        "versions": data.get("versions") if isinstance(data.get("versions"), dict) else None,
        "from_favorite": True,
        "favorite_id": favorite.id,
    }


def _totals(meals: list[dict]) -> dict:
    result = {"energy_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "sodium_mg": 0.0, "sugar_g": 0.0}
    for meal in meals:
        nutrition = meal.get("nutrition") or {}
        for key in result:
            result[key] += float(nutrition.get(key) or 0)
    return {key: round(value, 1) for key, value in result.items()}


def schedule_favorite(
    user_id: int,
    favorite_id: int,
    family_user_ids: list[int] | None = None,
) -> dict:
    favorite = UserFavoriteRecipe.query.filter_by(id=favorite_id, user_id=user_id).first()
    if favorite is None:
        raise NotFoundError("收藏不存在")
    meal = _favorite_meal(favorite, family_user_ids)
    latest = RecipePlan.query.filter_by(user_id=user_id).order_by(RecipePlan.id.desc()).first()
    today = date.today()
    if latest is not None and latest.created_at and latest.created_at.date() == today:
        plan = dict(latest.result or {})
        meals = list(plan.get("meals") or [])
        existing = next((item for item in meals if item.get("name") == meal["name"]), None)
        if existing is None:
            meals.append(meal)
        else:
            existing.update(meal)
        plan["meals"] = meals
        plan["nutrition_totals"] = _totals(meals)
        plan["shopping_list"] = list(plan.get("shopping_list") or [])
        seen = set(plan["shopping_list"])
        for item in meal["missing"]:
            label = f"{item['name']} {item['amount']}".strip()
            if label not in seen:
                seen.add(label)
                plan["shopping_list"].append(label)
        plan["plan_id"] = latest.id
        plan["agent_trace"] = list(plan.get("agent_trace") or [])
        latest.result = plan
        flag_modified(latest, "result")
        db.session.commit()
    else:
        plan = {
            "mode": "favorite_recipe",
            "mode_label": "收藏菜谱排期",
            "model": None,
            "summary": f"今日收藏菜谱 · {favorite.recipe_name}",
            "meals": [meal],
            "shopping_list": [
                f"{item['name']} {item['amount']}".strip() for item in meal["missing"]
            ],
            "agent_trace": ["已根据收藏菜谱生成今日排期。"],
            "warnings": [DISCLAIMER],
            "rule_vetoes": [],
            "nutrition_totals": _totals([meal]),
            "servings": 2,
            "pantry_count": PantryItem.query.filter_by(user_id=user_id).count(),
            "profile": {},
            "focus_item": None,
            "request": {"source": "favorite", "favorite_id": favorite.id},
            "actual_meals": 1,
            "requested_meals": 1,
        }
        record = RecipePlan(user_id=user_id, mode="favorite_recipe", request=plan["request"], result=plan)
        db.session.add(record)
        db.session.commit()
        plan["plan_id"] = record.id
    return {"favorite": enrich(favorite), "plan": plan, "meal": meal, "message": f"「{favorite.recipe_name}」已加入今日排期"}
