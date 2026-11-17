"""家庭食材管家服务：库存 CRUD、临期提醒、健康画像。"""
from __future__ import annotations

from datetime import date, datetime

from ..extensions import db
from ..models import HealthProfile, PantryItem, User
from ..models.pantry import HEALTH_CONDITIONS, HEALTH_GOALS, PANTRY_CATEGORIES
from ..utils.errors import NotFoundError, ValidationError
from ..utils.validators import clean_text
from . import ingredient_rules

MAX_ITEMS = 200
MAX_ALLERGIES = 20
REMIND_DAYS = 3


def _parse_date(value, field: str) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{field}格式应为 YYYY-MM-DD")


def _validate_item(payload: dict, *, current: PantryItem | None = None) -> dict:
    name = clean_text(payload.get("name"), max_len=40, field="食材名称", allow_empty=False).strip()
    if not name:
        raise ValidationError("食材名称不能为空")
    category = str(payload.get("category") or (current.category if current else "other"))
    if category not in PANTRY_CATEGORIES:
        raise ValidationError("食材分类不合法")
    raw_quantity = payload.get("quantity")
    if raw_quantity in (None, ""):
        raw_quantity = current.quantity if current else 1
    try:
        quantity = float(raw_quantity)
    except (TypeError, ValueError):
        raise ValidationError("数量必须是数字")
    if quantity <= 0 or quantity > 10000:
        raise ValidationError("数量需要在 0–10000 之间")
    unit = clean_text(payload.get("unit"), max_len=10, field="单位") or "份"
    purchased_at = _parse_date(
        payload.get("purchased_at") if "purchased_at" in payload else (current.purchased_at if current else None),
        "购买日期",
    )
    expires_at = _parse_date(
        payload.get("expires_at") if "expires_at" in payload else (current.expires_at if current else None),
        "保质期",
    )
    if purchased_at and expires_at and expires_at < purchased_at:
        raise ValidationError("保质期不能早于购买日期")
    note = clean_text(payload.get("note"), max_len=200, field="备注") or ""
    return {
        "name": name,
        "category": category,
        "quantity": round(quantity, 2),
        "unit": unit,
        "purchased_at": purchased_at,
        "expires_at": expires_at,
        "note": note,
    }


def list_items(user_id: int, *, status: str = "", query: str = "", family_user_ids: list[int] | None = None) -> dict:
    scope_ids = family_user_ids or [user_id]
    items = (
        PantryItem.query.filter(PantryItem.user_id.in_(scope_ids))
        .order_by(PantryItem.expires_at.is_(None), PantryItem.expires_at.asc(), PantryItem.id.desc())
        .all()
    )
    query = (query or "").strip()
    if query:
        items = [item for item in items if query in item.name or query in item.note]
    if status in {"expired", "expiring", "fresh", "no_expiry"}:
        items = [item for item in items if item.status()[0] == status]
    owner_names = {
        row.id: (row.display_name or row.username)
        for row in User.query.filter(User.id.in_(scope_ids)).all()
    }
    public_items = []
    for item in items:
        public = item.to_public()
        public["owner_id"] = item.user_id
        public["owner_name"] = owner_names.get(item.user_id) or "家人"
        public["is_shared"] = item.user_id != user_id
        public_items.append(public)
    return {
        "items": public_items,
        "total": len(items),
        "categories": [{"value": key, "label": label} for key, label in PANTRY_CATEGORIES.items()],
        "reminder": reminder_summary(user_id),
    }


def create_item(user_id: int, payload: dict) -> PantryItem:
    if PantryItem.query.filter_by(user_id=user_id).count() >= MAX_ITEMS:
        raise ValidationError(f"最多保存 {MAX_ITEMS} 项食材，请先清理库存")
    data = _validate_item(payload)
    item = PantryItem(user_id=user_id, **data)
    db.session.add(item)
    db.session.commit()
    return item


def update_item(user_id: int, item_id: int, payload: dict) -> PantryItem:
    item = PantryItem.query.filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise NotFoundError("食材不存在")
    for key, value in _validate_item(payload, current=item).items():
        setattr(item, key, value)
    db.session.commit()
    return item


def delete_item(
    user_id: int,
    item_id: int,
    *,
    family_user_ids: list[int] | None = None,
) -> dict:
    scope_ids = family_user_ids or [user_id]
    item = PantryItem.query.filter(
        PantryItem.id == item_id,
        PantryItem.user_id.in_(scope_ids),
    ).first()
    if item is None:
        raise NotFoundError("食材不存在")
    db.session.delete(item)
    db.session.commit()
    return {"deleted": True, "id": item_id}


def delete_items(
    user_id: int,
    item_ids: list[int],
    *,
    family_user_ids: list[int] | None = None,
) -> dict:
    if not isinstance(item_ids, list) or not item_ids:
        raise ValidationError("请至少选择一项要删除的食材")
    ids = []
    for value in item_ids:
        try:
            item_id = int(value)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and item_id not in ids:
            ids.append(item_id)
    if not ids:
        raise ValidationError("食材 ID 不合法")
    if len(ids) > 200:
        raise ValidationError("一次最多删除 200 项")
    scope_ids = family_user_ids or [user_id]
    rows = PantryItem.query.filter(PantryItem.user_id.in_(scope_ids), PantryItem.id.in_(ids)).all()
    found = {row.id for row in rows}
    for row in rows:
        db.session.delete(row)
    db.session.commit()
    return {
        "deleted": len(rows),
        "requested": len(ids),
        "missing": [item_id for item_id in ids if item_id not in found],
    }


def _quick_rescue(item: dict) -> dict:
    name = item["name"]
    category = item.get("category")
    if category == "vegetable":
        recipe, steps = f"清炒{name}", ["洗净切好，少油快炒。", "出锅前少量盐调味，尽快食用。"]
    elif category in {"meat", "seafood"}:
        recipe, steps = f"{name}快煮", ["切薄片或小块，沸水煮熟。", "搭配现有蔬菜，少盐调味，确保熟透。"]
    elif category == "staple":
        recipe, steps = f"{name}粥/饭", ["按份量煮熟，搭配现有蔬菜或蛋白质。", "优先安排在本餐消耗。"]
    elif category == "egg_dairy":
        recipe, steps = f"{name}早餐组合", ["搭配主食或水果食用。", "牛奶开封后尽快喝完，鸡蛋充分加热。"]
    else:
        recipe, steps = f"{name}优先消耗", ["检查状态后尽快安排食用。", "不确认是否变质时请丢弃，不要冒险。"]
    return {
        "item_id": item["id"],
        "item_name": name,
        "recipe_name": recipe,
        "steps": steps,
        "source": "rule",
        "note": "这是按食材类别自动生成的快速消耗建议；点击「拯救食谱」可获得完整方案。",
    }


def reminder_summary(user_id: int, *, days: int = REMIND_DAYS) -> dict:
    items = PantryItem.query.filter_by(user_id=user_id).all()
    expiring: list[dict] = []
    expired: list[dict] = []
    for item in items:
        if ingredient_rules.is_staple(item.name, item.category):
            # 调味料默认常备，不生成过期提醒
            continue
        status, text = item.status()
        public = item.to_public()
        if status == "expired":
            expired.append(public)
        elif status == "expiring":
            expiring.append(public)
    expiring.sort(key=lambda item: item["days_left"] if item["days_left"] is not None else 99)
    urgent = [item for item in expiring if item.get("days_left") is not None and item["days_left"] <= 1]
    for item in urgent:
        item["rescue_available"] = True
        item["rescue"] = _quick_rescue(item)
    expired.sort(key=lambda item: item["days_left"] if item["days_left"] is not None else 0)
    return {
        "expiring": expiring,
        "expired": expired,
        "urgent": urgent,
        "urgent_count": len(urgent),
        "counts": {"expiring": len(expiring), "expired": len(expired), "total": len(items)},
        "window_days": days,
        "message": _reminder_message(expiring, expired),
    }


def _reminder_message(expiring: list[dict], expired: list[dict]) -> str:
    if expired:
        names = "、".join(item["name"] for item in expired[:3])
        return f"有 {len(expired)} 项食材已过期（{names}），请及时清理。"
    if expiring:
        names = "、".join(f"{item['name']}（{item['status_text']}）" for item in expiring[:3])
        return f"{len(expiring)} 项食材临近保质期：{names}。"
    return "库存中没有临近过期的食材。"


def get_profile(user_id: int) -> dict:
    profile = HealthProfile.query.filter_by(user_id=user_id).first()
    if profile is None:
        return {
            "conditions": [],
            "condition_labels": [],
            "goals": [],
            "goal_labels": [],
            "allergies": [],
            "notes": "",
            "updated_at": None,
            "options": {
                "conditions": [{"value": key, "label": label} for key, label in HEALTH_CONDITIONS.items()],
                "goals": [{"value": key, "label": label} for key, label in HEALTH_GOALS.items()],
            },
        }
    data = profile.to_public()
    data["options"] = {
        "conditions": [{"value": key, "label": label} for key, label in HEALTH_CONDITIONS.items()],
        "goals": [{"value": key, "label": label} for key, label in HEALTH_GOALS.items()],
    }
    return data


def save_profile(user_id: int, payload: dict) -> HealthProfile:
    conditions = payload.get("conditions") or []
    goals = payload.get("goals") or []
    allergies = payload.get("allergies") or []
    if not isinstance(conditions, list) or not isinstance(goals, list) or not isinstance(allergies, list):
        raise ValidationError("conditions / goals / allergies 必须是数组")
    conditions = [str(item) for item in conditions if str(item) in HEALTH_CONDITIONS]
    goals = [str(item) for item in goals if str(item) in HEALTH_GOALS]
    cleaned_allergies: list[str] = []
    for item in allergies[:MAX_ALLERGIES]:
        text = clean_text(str(item), max_len=20, field="过敏原")
        if text and text not in cleaned_allergies:
            cleaned_allergies.append(text)
    notes = clean_text(payload.get("notes"), max_len=300, field="备注") or ""
    profile = HealthProfile.query.filter_by(user_id=user_id).first()
    if profile is None:
        profile = HealthProfile(user_id=user_id)
        db.session.add(profile)
    profile.conditions = conditions
    profile.goals = goals
    profile.allergies = cleaned_allergies
    profile.notes = notes
    db.session.commit()
    return profile


__all__ = [
    "list_items",
    "create_item",
    "update_item",
    "delete_item",
    "delete_items",
    "reminder_summary",
    "get_profile",
    "save_profile",
]


def consume_ingredients(user_id: int, recipe_name: str, ingredients: list[dict]) -> dict:
    """按一道菜的主料用量扣减库存（用于食谱详情抽屉的“烹饪完成”）。"""
    from . import recipe_agent_service

    pantry = PantryItem.query.filter_by(user_id=user_id).all()
    consumed: list[dict] = []
    missing: list[dict] = []
    skipped: list[dict] = []
    staples: list[dict] = []
    for ingredient in ingredients:
        name = str(ingredient.get("name") or "").strip()
        amount_text = str(ingredient.get("amount") or "")
        if not name:
            continue
        if ingredient_rules.is_staple(name):
            staples.append({"name": name, "amount": amount_text, "reason": "常备调料，视为无限库存"})
            continue
        if ingredient_rules.is_non_purchase(name):
            continue
        item = recipe_agent_service._match_pantry(pantry, name)
        if item is None:
            missing.append({"name": name, "amount": amount_text, "reason": "库存中没有该食材"})
            continue
        amount, amount_unit = recipe_agent_service._parse_amount(amount_text, item.unit)
        if amount is None or amount <= 0:
            skipped.append({"name": item.name, "amount": amount_text, "reason": "用量不明确，未自动扣减"})
            continue
        deduct = recipe_agent_service._convert_amount(amount, amount_unit, item)
        estimated = False
        if deduct is None:
            deduct = 1.0
            estimated = True
        before = float(item.quantity)
        after = max(0.0, before - deduct)
        item.quantity = round(after, 2)
        consumed.append({
            "name": item.name,
            "amount": amount_text,
            "deducted": round(min(deduct, before), 2),
            "unit": item.unit,
            "remaining": round(after, 2),
            "estimated": estimated,
        })
        if after <= 0:
            db.session.delete(item)
    db.session.commit()
    return {
        "recipe_name": recipe_name,
        "consumed": consumed,
        "missing": missing,
        "skipped": skipped,
        "staples": staples,
        "message": f"已扣减 {len(consumed)} 项库存" if consumed else "库存未发生扣减",
    }
