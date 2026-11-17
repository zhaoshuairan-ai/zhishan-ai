"""一键购物清单结算：把“购物清单”里的食材加入库存（模拟采购）。

清单来自食谱的 shopping_list/missing，格式可能是：
- 鸡蛋 1个（早餐蛋白质来源）
- 食用油 15ml
- 燕麦片 1小包
- 生姜 少量

这里做尽力解析：名称 + 数量 + 单位；无法识别的按 1 份处理，并在返回中说明。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import PantryItem
from ..utils.errors import ValidationError
from . import ingredient_rules, pantry_service, shelf_life_service, storage_advice_service

UNIT_ALIASES = {
    "克": "g",
    "千克": "kg",
    "公斤": "kg",
    "毫升": "ml",
    "升": "l",
    "小包": "包",
    "小袋": "袋",
    "小瓶": "瓶",
}
UNITS = "kg|g|克|千克|公斤|ml|毫升|升|l|个|只|颗|根|把|块|盒|袋|瓶|包|小包|小袋|小瓶|份|片|杯|小勺|汤勺"


def _clean(label: str) -> str:
    # 去掉括号里的推荐理由，避免“鸡胸肉 100g（午餐）”干扰解析
    return re.sub(r"[（(].*?[）)]", "", label or "").strip()


def parse_label(label: str) -> dict:
    text = _clean(label)
    if not text:
        raise ValidationError("购物清单里有空项")
    match = re.match(rf"^(.+?)[\s:：]+(\d+(?:\.\d+)?)\s*({UNITS})?\s*$", text, re.I)
    if match:
        name = match.group(1).strip(" ·-")
        quantity = float(match.group(2))
        unit = (match.group(3) or "份").lower()
        unit = UNIT_ALIASES.get(unit, unit)
    else:
        # 没有数量（“生姜 少量”“主食”）：按 1 份录入
        name = re.sub(r"\s*(少量|少许|适量)$", "", text).strip(" ·-")
        quantity = 1.0
        unit = "份"
    if not name or len(name) > 40:
        raise ValidationError("购物清单里有无法识别的食材名称")
    if quantity <= 0 or quantity > 10000:
        quantity = 1.0
    return {
        "name": name,
        "quantity": round(quantity, 2),
        "unit": unit,
        "category": shelf_life_service.guess_category(name),
    }


def checkout(user_id: int, labels: list[str], include_staples: bool = False) -> dict:
    if not isinstance(labels, list) or not labels:
        raise ValidationError("请至少选择一项需要补购的食材")
    if len(labels) > 30:
        raise ValidationError("一次最多采购 30 项")
    existing = PantryItem.query.filter_by(user_id=user_id).all()
    if len(existing) + len(labels) > 200:
        raise ValidationError("库存将超过 200 项，请先清理")

    parsed: dict[tuple[str, str], dict] = {}
    staples: list[str] = []
    for label in labels:
        item = parse_label(str(label))
        if ingredient_rules.is_non_purchase(item["name"]):
            continue
        if ingredient_rules.is_staple(item["name"], item.get("category")):
            staples.append(item["name"])
            if not include_staples:
                continue
            item["is_staple"] = True
        else:
            item["is_staple"] = False
        key = (item["name"], item["unit"])
        if key in parsed:
            parsed[key]["quantity"] = round(parsed[key]["quantity"] + item["quantity"], 2)
        else:
            parsed[key] = item

    if not parsed:
        if staples and not include_staples:
            raise ValidationError("调料请加入购物车走常规发货")
        raise ValidationError("请至少选择一项需要采购的商品")
    today = date.today()
    now = datetime.now()
    arrival = now + timedelta(minutes=30)
    day_label = "今日" if arrival.date() == today else "明日"
    arrival_text = f"{day_label}{arrival.strftime('%H:%M')}"
    storage_map = storage_advice_service.generate(
        [{"name": item["name"], "category": item["category"]} for item in parsed.values()]
    )
    purchased = []
    fresh_count = sum(1 for item in parsed.values() if not item.get("is_staple"))
    staple_count = sum(1 for item in parsed.values() if item.get("is_staple"))
    regular_delivery = "常规发货（次日达），预计明日送达"
    by_name_unit = {(item.name, item.unit): item for item in existing}
    for item in parsed.values():
        shelf = shelf_life_service.lookup_shelf_life(item["name"], use_web=False)
        days = shelf.get("days") or 7
        expires = today + timedelta(days=days)
        delivery_text = "常规发货（已送达）" if item.get("is_staple") else "同城急送（已送达）"
        advice = storage_map.get(item["name"]) or storage_advice_service.fallback_advice(item["name"], item["category"])
        note = f"{delivery_text}；AI科学存储建议：{advice}"
        current = by_name_unit.get((item["name"], item["unit"]))
        if current is not None:
            current.quantity = round(float(current.quantity) + item["quantity"], 2)
            if current.note and "模拟一键采购" not in current.note:
                current.note = f"{current.note}；{delivery_text}；AI科学存储建议：{advice}"
            else:
                current.note = note
            purchased.append(
                {
                    "name": item["name"],
                    "quantity": item["quantity"],
                    "unit": item["unit"],
                    "remaining": current.quantity,
                    "merged": True,
                    "delivery": delivery_text,
                    "is_staple": bool(item.get("is_staple")),
                }
            )
        else:
            row = PantryItem(
                user_id=user_id,
                name=item["name"],
                category=item["category"],
                quantity=item["quantity"],
                unit=item["unit"],
                purchased_at=today,
                expires_at=expires,
                note=note,
            )
            db.session.add(row)
            purchased.append(
                {
                    "name": item["name"],
                    "quantity": item["quantity"],
                    "unit": item["unit"],
                    "expires_at": expires.isoformat(),
                    "merged": False,
                    "delivery": delivery_text,
                    "is_staple": bool(item.get("is_staple")),
                }
            )
    db.session.commit()
    if fresh_count and staple_count:
        message = f"已入库：生鲜同城急送（已送达），调料常规发货（已送达）；共 {len(purchased)} 项已加入食材管家"
        delivery = "生鲜：同城急送（已送达）；调料：常规发货（已送达）"
    elif fresh_count:
        message = f"已入库：同城急送（已送达）；{fresh_count} 项生鲜已加入食材管家"
        delivery = "同城急送（已送达）"
    else:
        message = f"已入库：常规发货（已送达）；{staple_count} 项调料已加入食材管家"
        delivery = "常规发货（已送达）"
    return {
        "purchased": purchased,
        "count": len(purchased),
        "fresh_count": fresh_count,
        "staple_count": staple_count,
        "message": message,
        "delivery": delivery,
        "estimated_arrival": "已送达",
        "staples": sorted(set(staples)),
    }


__all__ = ["checkout", "parse_label"]
