"""中国家庭厨房常用计量：小勺、汤勺、小碗、电饭煲量杯、个/把/掌心。

展示格式统一为「生活化单位（约克数/毫升）」，例如：
- 食盐 1小勺（约3g）
- 食用油 1小勺（约5ml）
- 大米 一杯（电饭煲量杯，约133g）
严禁输出茶匙、汤匙、盎司等西式单位。
"""
from __future__ import annotations

import re

MASS_UNITS = {"g": 1.0, "克": 1.0, "kg": 1000.0, "千克": 1000.0}
VOLUME_UNITS = {"ml": 1.0, "毫升": 1.0, "l": 1000.0, "升": 1000.0}
HOUSEHOLD_UNITS = ("小勺", "汤勺", "小碗", "杯", "个", "只", "把", "块", "盒", "片", "掌心", "小撮", "份")


def _num(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _sanitize(text: str) -> str:
    return (
        text.replace("茶匙", "小勺")
        .replace("汤匙", "汤勺")
        .replace("盎司", "小勺")
        .replace("oz", "小勺")
        .replace("tsp", "小勺")
        .replace("tbsp", "汤勺")
    )


def _amount_parts(amount: str) -> tuple[float, str] | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|克|千克|ml|毫升|升|l)?", amount or "", re.I)
    if not match:
        return None
    return float(match.group(1)), (match.group(2) or "").lower()


def _grams(value: float, unit: str) -> float | None:
    if unit in MASS_UNITS:
        return value * MASS_UNITS[unit]
    if unit in VOLUME_UNITS:
        return value * VOLUME_UNITS[unit]
    return None


def _cup_text(cups: float) -> str:
    if cups < 0.38:
        return "小半杯"
    if cups < 0.62:
        return "半杯"
    if cups < 0.88:
        return "大半杯"
    if cups < 1.12:
        return "一杯"
    if cups < 1.38:
        return "一杯多"
    if cups < 1.65:
        return "一杯半"
    return f"{_num(cups)}杯"


def _household(name: str, grams: float) -> str | None:
    n = name or ""
    if any(word in n for word in ("大米", "米", "杂粮", "糙米")):
        return f"{_cup_text(grams / 133.0)}（电饭煲量杯，约{_num(grams)}g）"
    if "面粉" in n:
        return f"{_cup_text(grams / 120.0)}（量杯，约{_num(grams)}g）"
    if "燕麦" in n:
        return f"{_num(round(grams / 10.0))}汤勺（约{_num(grams)}g）"
    if "油" in n:
        if grams < 15:
            return f"{_num(round(grams / 5.0))}小勺（约{_num(grams)}ml）"
        return f"{_num(round(grams / 15.0))}汤勺（约{_num(grams)}ml）"
    if "盐" in n:
        if grams < 1.5:
            return f"一小撮（约{_num(grams)}g）"
        if grams < 2.5:
            return f"半小勺（约{_num(grams)}g）"
        if grams < 4.5:
            return f"1小勺（约{_num(grams)}g）"
        return f"{_num(round(grams / 3.0))}小勺（约{_num(grams)}g）"
    if "糖" in n:
        return f"{_num(round(grams / 4.0))}小勺（约{_num(grams)}g）"
    if any(word in n for word in ("生抽", "酱油", "蚝油", "醋", "料酒")):
        return f"{_num(round(grams / 5.0))}小勺（约{_num(grams)}ml）"
    if "鸡蛋" in n or "鸭蛋" in n:
        return f"{_num(grams / 50.0)}个（约{_num(grams)}g）"
    if any(word in n for word in ("牛奶", "酸奶", "豆浆")):
        return f"{_num(grams / 250.0)}盒（约{_num(grams)}ml）"
    if any(word in n for word in ("鸡胸", "鸡腿", "鸡肉", "猪肉", "牛肉", "羊肉", "鱼", "虾")):
        return f"{_num(grams / 100.0)}个掌心大小（约{_num(grams)}g）"
    if any(word in n for word in ("番茄", "西红柿")):
        return f"{_num(grams / 150.0)}个中等大小（约{_num(grams)}g）"
    if any(word in n for word in ("土豆", "红薯", "黄瓜", "茄子")):
        return f"{_num(grams / 150.0)}个（约{_num(grams)}g）"
    if "豆腐" in n:
        return f"{_num(grams / 300.0)}块（约{_num(grams)}g）"
    if any(word in n for word in ("菜", "菠菜", "生菜", "西兰花", "菌", "菇")):
        return f"{_num(grams / 100.0)}小把（约{_num(grams)}g）"
    return None


def describe_amount(amount: str, name: str = "") -> str:
    """把克/毫升优先改写成中国家庭单位；已有家庭单位则保留。"""
    text = _sanitize((amount or "").strip())
    if not text:
        return text
    if text.startswith(("约", "一", "半", "小半", "大半")) and any(unit in text for unit in HOUSEHOLD_UNITS):
        return text
    if re.match(r"^\d+(?:\.\d+)?\s*(小勺|汤勺|小碗|杯|个|只|把|块|盒|片|份)", text):
        return text
    parts = _amount_parts(text)
    if not parts:
        return text
    value, unit = parts
    if not unit:
        return text
    grams = _grams(value, unit)
    if grams is None:
        return text
    return _household(name, grams) or text


def enrich_ingredients(ingredients: list[dict]) -> list[dict]:
    for item in ingredients or []:
        if isinstance(item, dict):
            item["amount"] = describe_amount(str(item.get("amount") or ""), str(item.get("name") or ""))
    return ingredients


def enrich_ingredient_line(line: str) -> str:
    text = _sanitize((line or "").strip())
    if not text:
        return text
    # 已经带家庭单位的行（如“番茄 2个（约400g）”）只补计数克数，不再改括号内容
    if any(unit in text for unit in HOUSEHOLD_UNITS):
        count = re.match(r"^(.+?)[\s：:]*([\d.]+)\s*(个|只|盒)", text)
        if count and "（" not in text:
            name = count.group(1).strip()
            amount = float(count.group(2))
            if "鸡蛋" in name or "鸭蛋" in name:
                return f"{text}（约{_num(amount * 50)}g）"
            if any(word in name for word in ("牛奶", "酸奶", "豆浆")) and "盒" in count.group(3):
                return f"{text}（约{_num(amount * 250)}ml）"
        return text
    match = re.match(r"^(.+?)[\s：:]*([\d.]+\s*(?:kg|g|克|千克|ml|毫升|升|l))", text, re.I)
    if not match:
        return text
    name = match.group(1).strip()
    amount = match.group(2).strip()
    return text.replace(amount, describe_amount(amount, name), 1)


__all__ = ["describe_amount", "enrich_ingredients", "enrich_ingredient_line"]
