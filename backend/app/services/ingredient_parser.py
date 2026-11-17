"""配料表结构化解析：把一段配料文字拆成有序的配料项列表。"""
from __future__ import annotations

import re

# 添加剂名称中常见的特征片段（仅用于「可能的类别提示」，最终以知识库与标准原文为准）
ADDITIVE_HINTS = [
    ("防腐剂", ("山梨酸", "苯甲酸", "脱氢乙酸", "丙酸", "亚硝酸", "硝酸", "乳酸链球菌素", "纳他霉素", "双乙酸")),
    ("甜味剂", ("糖精", "阿斯巴甜", "安赛蜜", "三氯蔗糖", "甜菊糖", "木糖醇", "麦芽糖醇", "山梨糖醇", "赤藓糖醇", "甜蜜素")),
    ("着色剂", ("色素", "焦糖色", "胭脂红", "苋菜红", "柠檬黄", "日落黄", "亮蓝", "诱惑红", "β-胡萝卜素", "胡萝卜素")),
    ("增稠/稳定剂", ("胶", "淀粉磷酸酯", "卡拉胶", "黄原胶", "瓜尔胶", "果胶", "海藻酸钠", "羧甲基纤维素", "单硬脂酸甘油酯")),
    ("抗氧化剂", ("抗坏血酸", "维生素C", "维生素E", "茶多酚", "特丁基对苯二酚", "TBHQ", "BHA", "BHT", "没食子酸")),
    ("酸度调节剂", ("柠檬酸", "苹果酸", "乳酸", "磷酸", "碳酸氢钠", "碳酸钠", "碳酸钙", "氢氧化钠")),
    ("膨松剂", ("碳酸氢钠", "碳酸氢铵", "泡打粉", "明矾", "硫酸铝钾", "硫酸铝铵")),
    ("增味剂", ("谷氨酸钠", "味精", "呈味核苷酸", "5'-呈味核苷酸")),
    ("水分保持剂", ("磷酸", "三聚磷酸钠", "六偏磷酸钠", "焦磷酸")),
    ("抗结剂", ("二氧化硅", "硅酸钙", "微晶纤维素")),
    ("香精香料", ("香精", "香料", "食用香精", "乙基麦芽酚")),
    ("漂白剂", ("二氧化硫", "亚硫酸", "焦亚硫酸")),
    ("护色剂", ("亚硝酸钠", "亚硝酸钾", "硝酸钠")),
]

CATEGORY_HEADERS = ("食品添加剂", "复配食品添加剂", "营养强化剂", "食用香精香料", "食品用香精")

_SPLIT_CHARS = set("、,，;；/|\n")
_PERCENT_RE = re.compile(r"[(（]?\s*(?:≥|>|约)?\s*(\d+(?:\.\d+)?)\s*[%％]\s*[)）]?")
_LEADING_NOISE = re.compile(r"^[\s\d.、)\]:：•·\-—*※]+")
_TRAILING_NOISE = re.compile(r"[\s。.;；,，、]+$")
_PAREN_RE = re.compile(r"[(（]([^()（）]*)[)）]")


def _smart_split(text: str) -> list[str]:
    """按顶层分隔符切分，括号内的分隔符不拆分。

    真实 OCR 常出现括号不配对（例如多了一个「（」），如果把括号深度无限累加，
    后面的整段配料都会被吞进同一个 token。这里把深度上限设为 1：
    复合配料内部的子配料仍保持在同一项内，但括号闭合后能恢复正常切分。
    """
    tokens: list[str] = []
    buffer: list[str] = []
    depth = 0
    for ch in text:
        if ch in "(（":
            depth = min(depth + 1, 1)
        elif ch in ")）":
            depth = max(0, depth - 1)
        if ch in _SPLIT_CHARS and depth == 0:
            token = "".join(buffer).strip()
            if token:
                tokens.append(token)
            buffer = []
            continue
        buffer.append(ch)
    token = "".join(buffer).strip()
    if token:
        tokens.append(token)
    return tokens


def _clean_name(token: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    for inner in _PAREN_RE.findall(token):
        percent = _PERCENT_RE.search(inner)
        if percent:
            notes.append(f"含量 {percent.group(1)}%")
        elif inner.strip():
            notes.append(inner.strip())
    name = _PAREN_RE.sub("", token)
    name = _LEADING_NOISE.sub("", name)
    name = _TRAILING_NOISE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    # OCR 常出现括号不配对（例如复合配料只拍到左括号），此时保留括号前的主体名称
    if name.count("(") > name.count(")"):
        index = name.find("(")
        if index > 0:
            notes.append("复合配料括号未闭合，已保留主体名称")
            name = name[:index].strip()
        else:
            name = name.replace("(", "").strip()
    return name, notes


def _percent_of(token: str) -> float | None:
    match = _PERCENT_RE.search(token)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def classify_hint(name: str) -> tuple[str, float, str]:
    """基于名称片段的粗略分类（仅提示，不作为安全性结论）。"""
    for category, keywords in ADDITIVE_HINTS:
        for keyword in keywords:
            if keyword and keyword.lower() in name.lower():
                return category, 0.65, f"名称中包含「{keyword}」，可能属于{category}相关物质"
    if name in CATEGORY_HEADERS:
        return "添加剂类目", 0.9, "该文本是添加剂类目标题"
    return "普通配料", 0.4, "未匹配到添加剂特征片段"


def _join_soft_wraps(text: str) -> str:
    """把 OCR 的行内折行拼回去。

    中文标签的配料分隔符是「、，,;；/」，换行绝大多数只是行宽折行
    （例如「聚甘油脂\\n肪酸酯」应还原为「聚甘油脂肪酸酯」）。
    因此这里直接去掉换行，由分隔符决定切分。
    """
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    return "".join(line for line in lines if line)


def parse_ingredients(text: str) -> dict:
    """返回结构化配料列表。

    items: [{index, name, raw, parent, percent, notes, hint_category, hint_confidence, hint_reason}]
    """
    cleaned = (text or "").replace("\r", "\n").strip()
    cleaned = re.sub(r"^配\s*料(?:\s*表)?\s*[:：]?", "", cleaned)
    cleaned = _join_soft_wraps(cleaned)
    tokens = _smart_split(cleaned)

    items: list[dict] = []
    warnings: list[dict] = []
    current_header: str | None = None
    for token in tokens:
        raw = token.strip()
        if not raw:
            continue
        name, notes = _clean_name(raw)
        if not name:
            continue
        percent = _percent_of(raw)
        hint_category, hint_conf, hint_reason = classify_hint(name)

        # 「食品添加剂（A、B）」这类类目标题：展开括号内子项
        inner = _PAREN_RE.search(raw)
        if name in CATEGORY_HEADERS and inner and _smart_split(inner.group(1)):
            current_header = name
            items.append(
                {
                    "index": len(items) + 1,
                    "name": name,
                    "raw": raw,
                    "parent": None,
                    "percent": percent,
                    "notes": notes,
                    "is_category": True,
                    "hint_category": "添加剂类目",
                    "hint_confidence": 0.9,
                    "hint_reason": "该文本是添加剂类目标题，括号内为具体品种",
                }
            )
            for child in _smart_split(inner.group(1)):
                child_name, child_notes = _clean_name(child)
                if not child_name:
                    continue
                c_cat, c_conf, c_reason = classify_hint(child_name)
                items.append(
                    {
                        "index": len(items) + 1,
                        "name": child_name,
                        "raw": child.strip(),
                        "parent": name,
                        "percent": _percent_of(child),
                        "notes": child_notes,
                        "is_category": False,
                        "hint_category": c_cat,
                        "hint_confidence": c_conf,
                        "hint_reason": c_reason,
                    }
                )
            # 类目标题只作用于其括号内的子项，后续配料不属于该标题
            current_header = None
            continue

        if name in CATEGORY_HEADERS:
            current_header = name
        items.append(
            {
                "index": len(items) + 1,
                "name": name,
                "raw": raw,
                "parent": current_header if name not in CATEGORY_HEADERS else None,
                "percent": percent,
                "notes": notes,
                "is_category": False,
                "hint_category": hint_category,
                "hint_confidence": hint_conf,
                "hint_reason": hint_reason,
            }
        )

    if len(items) <= 1 and len(cleaned) > 6:
        warnings.append(
            {
                "level": "review",
                "message": "配料表未能拆分出多个配料项，可能缺少分隔符或识别有误。",
                "detail": "请在校正页检查是否使用了「、」或逗号分隔配料。",
            }
        )
    if any(len(item["name"]) > 40 for item in items):
        warnings.append(
            {
                "level": "review",
                "message": "存在超长配料项，可能未正确分隔。",
                "detail": "请人工确认配料表中的分隔符是否完整。",
            }
        )

    return {
        "items": items,
        "count": len(items),
        "warnings": warnings,
        "has_percent": any(item["percent"] is not None for item in items),
        "raw_text": cleaned,
    }


def names_only(parsed: dict) -> list[str]:
    return [item["name"] for item in parsed.get("items", []) if not item.get("is_category")]


__all__ = ["parse_ingredients", "classify_hint", "names_only", "ADDITIVE_HINTS", "CATEGORY_HEADERS"]
