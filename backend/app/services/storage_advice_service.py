"""入库时的 AI 科学存储建议。

优先调用大模型批量生成；模型不可用时按分类给出稳定的规则兜底，
保证一键采购的成功路径不被 AI 网络问题阻塞。
"""
from __future__ import annotations

import json
import re

CATEGORY_LABELS = {
    "seafood": "水产",
    "fish": "水产",
    "meat": "肉类",
    "pork": "肉类",
    "beef": "肉类",
    "chicken": "肉类",
    "bean": "豆制品",
    "tofu": "豆制品",
    "vegetable": "蔬菜",
    "staple": "主食",
    "rice": "主食",
    "egg_dairy": "蛋奶",
    "egg": "蛋奶",
    "fruit": "水果",
    "condiment": "调料",
}

FALLBACK = {
    "seafood": "建议尽快冷藏/冷冻",
    "meat": "建议分装冷藏或冷冻",
    "bean": "建议泡水冷藏或尽快食用",
    "vegetable": "擦干水分后冷藏，尽快食用",
    "staple": "密封防潮防虫，置于阴凉干燥处",
    "egg_dairy": "冷藏保存，注意保质期",
    "fruit": "阴凉通风或冷藏，尽快食用",
    "condiment": "密封置于阴凉干燥处",
    "other": "按包装说明冷藏保存",
}


def _fallback_category(name: str, category: str | None) -> str:
    text = f"{name} {category or ''}"
    if category in FALLBACK:
        return category
    if any(word in text for word in ("鱼", "虾", "蟹", "贝", "海鲜", "水产")):
        return "seafood"
    if any(word in text for word in ("豆腐", "豆干", "豆皮", "腐竹", "豆浆")):
        return "bean"
    if any(word in text for word in ("肉", "排骨", "鸡", "鸭", "牛", "羊")):
        return "meat"
    if any(word in text for word in ("米", "面", "粉", "馒头", "面包", "燕麦", "杂粮")):
        return "staple"
    if any(word in text for word in ("菜", "瓜", "茄", "萝卜", "葱", "姜", "蒜", "椒")):
        return "vegetable"
    if any(word in text for word in ("蛋", "奶", "酸奶", "芝士")):
        return "egg_dairy"
    if any(word in text for word in ("苹果", "香蕉", "橙", "梨", "葡萄", "水果")):
        return "fruit"
    if any(word in text for word in ("盐", "酱", "醋", "油", "料酒", "糖", "淀粉")):
        return "condiment"
    return "other"


def fallback_advice(name: str, category: str | None = None) -> str:
    return FALLBACK[_fallback_category(name, category)]


def _parse_json(raw: str) -> dict:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def generate(items: list[dict]) -> dict[str, str]:
    """items: [{name, category}] -> {name: 存储建议}。"""
    wanted = []
    seen = set()
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        wanted.append({"name": name, "category": CATEGORY_LABELS.get(str(item.get("category") or ""), str(item.get("category") or "其他"))})
    if not wanted:
        return {}

    result = {
        item["name"]: fallback_advice(item["name"], item.get("category"))
        for item in wanted
    }
    try:
        from .assistant_service import _chat

        prompt = (
            "你是家庭食材存储助理。请根据食材分类和名称，为每一项生成一句简短的 AI 科学存储建议。"
            "要求：每条 8–22 个汉字；给出可执行动作（如冷藏、冷冻、密封、防潮、尽快食用）；"
            "不要诊断疾病，不要写“建议”以外的冗长解释。"
            "只返回 JSON 对象，键是食材名，值是建议，例如："
            '{"鲤鱼":"建议尽快冷藏/冷冻","豆腐":"建议泡水冷藏或尽快食用","大米":"密封防潮防虫"}。'
            f"食材列表：{json.dumps(wanted, ensure_ascii=False)}"
        )
        raw = _chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请生成存储建议 JSON。"},
            ]
        )
        parsed = _parse_json(raw)
        for name in result:
            value = str(parsed.get(name) or "").strip()
            value = re.sub(r"^建议[：:]?\s*", "", value)
            if 4 <= len(value) <= 40:
                result[name] = value
    except Exception:
        pass
    return result


__all__ = ["generate", "fallback_advice"]
