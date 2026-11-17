"""营养成分表解析。

原则：
- 只解析文本中真实出现的数值，绝不补全或估算缺失项；
- 保留原始数值与单位，同时给出可选的统一换算（仅用于图表与一致性检查）；
- 单位缺失、基准不明、数值异常都会被显式标记为待确认。
"""
from __future__ import annotations

import re

from ..rules.label_rules import THRESHOLDS

# 名称 -> (key, 默认单位, 单位族)
NUTRIENT_DEFS: list[tuple[str, str, str, str]] = [
    ("能量", "energy", "kJ", "energy"),
    ("蛋白质", "protein", "g", "mass"),
    ("脂肪", "fat", "g", "mass"),
    ("碳水化合物", "carbohydrate", "g", "mass"),
    ("钠", "sodium", "mg", "sodium"),
    ("糖", "sugar", "g", "mass"),
    ("膳食纤维", "dietary_fiber", "g", "mass"),
    ("饱和脂肪", "saturated_fat", "g", "mass"),
    ("反式脂肪酸", "trans_fat", "g", "mass"),
    ("胆固醇", "cholesterol", "mg", "mass_mg"),
    ("钙", "calcium", "mg", "mass_mg"),
    ("铁", "iron", "mg", "mass_mg"),
    ("锌", "zinc", "mg", "mass_mg"),
]

CORE_KEYS = ["energy", "protein", "fat", "carbohydrate", "sodium"]
CORE_NAMES = {
    "energy": "能量",
    "protein": "蛋白质",
    "fat": "脂肪",
    "carbohydrate": "碳水化合物",
    "sodium": "钠",
}

NAME_LOOKUP: dict[str, tuple[str, str, str]] = {}
for _name, _key, _unit, _family in NUTRIENT_DEFS:
    NAME_LOOKUP[_name] = (_key, _unit, _family)
# 常见别名
NAME_LOOKUP.update(
    {
        "热量": ("energy", "kJ", "energy"),
        "碳水化合物化合物": ("carbohydrate", "g", "mass"),
        "碳水": ("carbohydrate", "g", "mass"),
        "食盐": ("sodium", "mg", "sodium"),
        "饱和脂肪酸": ("saturated_fat", "g", "mass"),
        "反式脂肪": ("trans_fat", "g", "mass"),
    }
)

_NAME_ALTERNATION = "|".join(sorted((re.escape(n) for n in NAME_LOOKUP), key=len, reverse=True))

_ITEM_RE = re.compile(
    r"(?P<name>" + _NAME_ALTERNATION + r")\s*(?:\((?P<paren>[^)]{0,10})\))?\s*[:：]?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>kcal|kJ|KJ|kj|千焦|干焦|千售|千焦耳|千卡|大卡|mg|g|MG|G|克|毫克|豪克)?\s*"
    r"(?:[\(（]?\s*(?P<nrv>\d+(?:\.\d+)?)\s*[%％])?",
    re.I,
)
_NAME_ONLY_RE = re.compile(
    r"^(?P<name>" + _NAME_ALTERNATION + r")\s*(?:\((?P<unit>[^)]{0,10})\))?$", re.I
)
# 单独成行的数值（可能带单位），用于「项目 / 每份 / 营养素参考值%」这类逐格 OCR 结果
_VALUE_ONLY_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:kcal|kJ|KJ|kj|千焦|干焦|千售|千卡|大卡|mg|g|克|毫克|豪克)?$", re.I
)
_PERCENT_ONLY = re.compile(r"^[\(（]?\s*(\d+(?:\.\d+)?)\s*[%％]\s*[\)）]?$")
_BASIS_RE = re.compile(r"每\s*(100\s*(?:g|克|ml|毫升)|份|100\s*(?:kJ|千焦))", re.I)
_SKIP_LINE = re.compile(r"^(项目|营养素|含量|每\s*100|NRV|序号|检测|每份|每袋|每支|每包)", re.I)

UNIT_NORMALIZE = {
    "kj": "kJ",
    "千焦": "kJ",
    "干焦": "kJ",  # OCR 常见错字：千 → 干
    "千售": "kJ",  # OCR 常见错字：焦 → 售
    "千焦耳": "kJ",
    "kcal": "kcal",
    "千卡": "kcal",
    "大卡": "kcal",
    "g": "g",
    "克": "g",
    "mg": "mg",
    "毫克": "mg",
    "豪克": "mg",  # OCR 常见错字：毫 → 豪
}

KNOWN_UNITS = {"kJ", "kcal", "g", "mg"}


def _normalize_unit(unit: str | None, default: str) -> tuple[str, bool]:
    if not unit:
        return default, True
    key = unit.strip()
    norm = UNIT_NORMALIZE.get(key.lower(), UNIT_NORMALIZE.get(key, key))
    if norm not in KNOWN_UNITS:
        # 单位没认出来（例如「千售」之外的乱码）：按默认单位理解并标记为推断
        return default, True
    return norm, False


def _family_of(unit: str) -> str:
    if unit in {"kJ", "kcal"}:
        return "energy"
    if unit == "mg":
        return "mass_mg"
    return "mass"


# 表格边框 / 项目符号常被 OCR 带进行首或行尾（例如「-饱和脂肪酸」「钠|」）
_EDGE_NOISE = re.compile(r"^[\s\-—–·•|:：,，、]+|[\s\-—–·•|:：,，、]+$")


def _strip_edge_noise(line: str) -> str:
    # 竖线基本都是表格边框，直接当作空格，避免「能量|889」这种被卡住
    cleaned = line.replace("|", " ").replace("│", " ")
    return _EDGE_NOISE.sub("", cleaned).strip()


def parse_nutrition(text: str) -> dict:
    """解析营养成分段落，返回 {basis, basis_note, items, missing_core, warnings}。"""
    warnings: list[dict] = []
    items: list[dict] = []
    raw_lines = [
        cleaned for cleaned in (_strip_edge_noise(line) for line in (text or "").split("\n")) if cleaned
    ]

    basis = "per_100g"
    basis_note = "未在营养成分表文字中找到明确的计量基准，已按「每 100g」理解，请人工确认。"
    basis_match = _BASIS_RE.search("\n".join(raw_lines))
    if basis_match:
        matched = basis_match.group(1).lower()
        if "100" in matched:
            basis = "per_100g" if ("g" in matched or "克" in matched) else "per_100ml"
            basis_note = None
        elif "份" in matched:
            basis = "per_serving"
            basis_note = "该表按「每份」标示，每份的重量/体积未识别到，跨产品比较时需注意。"
    elif raw_lines:
        # 保留结构化警告供接口/报告使用；结果页会把它折叠成不打断阅读的小字提示
        warnings.append(
            {
                "level": "review",
                "message": "未能确认营养成分的计量基准（每 100g / 每份）。",
                "detail": "系统已默认按每 100g 理解，请查看营养成分表表头后人工确认。",
            }
        )

    # OCR 常把表格拆成「名称一行、数值一行、NRV% 一行」，先把它们拼回逻辑行
    logical: list[str] = []
    index = 0
    while index < len(raw_lines):
        line = raw_lines[index]
        compact = re.sub(r"\s+", "", line)
        name_match = _NAME_ONLY_RE.match(compact)
        if name_match:
            parts = [line]
            cursor = index + 1
            # 最多向前合并 2 行（数值 + 百分比）
            while cursor < len(raw_lines) and len(parts) < 3:
                candidate = raw_lines[cursor].strip()
                if _VALUE_ONLY_RE.match(candidate) or _PERCENT_ONLY.match(candidate):
                    parts.append(candidate)
                    cursor += 1
                    continue
                break
            logical.append(" ".join(parts))
            index = cursor
            continue
        logical.append(line)
        index += 1

    # 再处理「NRV% 单独成行」的情况：并入上一行
    merged: list[str] = []
    for line in logical:
        if merged and _PERCENT_ONLY.match(line):
            merged[-1] = f"{merged[-1]} {line}"
        elif not _SKIP_LINE.match(re.sub(r"\s+", "", line)):
            merged.append(line)

    seen: dict[str, int] = {}
    for line in merged:
        for match in _ITEM_RE.finditer(line):
            raw_name = match.group("name")
            key, default_unit, default_family = NAME_LOOKUP[raw_name]
            unit, inferred = _normalize_unit(match.group("unit"), default_unit)
            if match.group("paren"):
                paren_unit = _normalize_unit(match.group("paren"), default_unit)
                if paren_unit[0] in UNIT_NORMALIZE.values():
                    unit, inferred = paren_unit
            try:
                value = float(match.group("value"))
            except (TypeError, ValueError):
                continue
            nrv = float(match.group("nrv")) if match.group("nrv") else None
            status = "ok"
            note = ""
            if inferred:
                status = "unit_inferred"
                note = f"未识别到单位，暂按 {unit} 理解"
            if key == "energy" and unit == "kcal":
                note = (note + "；" if note else "") + "能量以 kcal 标示，图表已换算为 kJ 展示"

            item = {
                "key": key,
                "name": CORE_NAMES.get(key, raw_name),
                "raw_name": raw_name,
                "value": value,
                "unit": unit,
                "unit_inferred": inferred,
                "nrv_percent": nrv,
                "nrv_percent_estimated": None,
                "status": status,
                "note": note,
                "raw": line[:120],
                "value_kj": round(value * 4.184, 1) if unit == "kcal" else (value if unit == "kJ" else None),
                "value_g": value / 1000 if unit == "mg" and key != "sodium" else (value if unit == "g" else None),
                "unit_family": _family_of(unit) or default_family,
            }
            if key in seen:
                # 同一营养素出现多次：保留第一次，后续标记为待确认
                items[seen[key]]["note"] = (items[seen[key]]["note"] + "；" if items[seen[key]]["note"] else "") + (
                    f"同一项目出现多次（另见「{line[:40]}」），请人工确认"
                )
                items[seen[key]]["status"] = "duplicate"
                continue
            seen[key] = len(items)
            items.append(item)

    # 缺失的核心营养素：补占位项（value=None），前端显示「未识别」
    for key in CORE_KEYS:
        if key not in seen:
            default_unit = next(u for n, k, u, _ in NUTRIENT_DEFS if k == key)
            items.append(
                {
                    "key": key,
                    "name": CORE_NAMES[key],
                    "raw_name": CORE_NAMES[key],
                    "value": None,
                    "unit": default_unit,
                    "unit_inferred": False,
                    "nrv_percent": None,
                    "nrv_percent_estimated": None,
                    "status": "missing",
                    "note": "未识别到该项目的数值",
                    "raw": "",
                    "value_kj": None,
                    "value_g": None,
                    "unit_family": "energy" if key == "energy" else ("sodium" if key == "sodium" else "mass"),
                }
            )

    # 计算缺失的 NRV%（仅用于理解辅助，明确标注为「估算」）
    nrv_refs = THRESHOLDS["nrv"]
    for item in items:
        if item["value"] is None or item["nrv_percent"] is not None:
            continue
        ref_key = f"{item['key']}_kj" if item["key"] == "energy" else (
            f"{item['key']}_mg" if item["unit"] == "mg" else f"{item['key']}_g"
        )
        ref = nrv_refs.get(ref_key)
        if not ref:
            continue
        value_in_ref_unit = item["value"]
        if ref_key.endswith("_g") and item["unit"] == "mg":
            value_in_ref_unit = item["value"] / 1000
        item["nrv_percent_estimated"] = round(value_in_ref_unit / ref * 100, 1)

    # 数值异常提示
    for item in items:
        if item["value"] is None:
            continue
        if item["value"] < 0:
            warnings.append({"level": "suspected", "message": f"{item['name']} 数值为负数，明显异常。", "detail": item["raw"]})
        if item["unit"] == "g" and item["value"] > 100 and item["key"] != "energy":
            warnings.append(
                {
                    "level": "suspected",
                    "message": f"{item['name']} 标示 {item['value']}g，按每 100g 计已超过 100g，疑似识别错误。",
                    "detail": item["raw"],
                }
            )
        if item["status"] == "unit_inferred":
            warnings.append(
                {
                    "level": "review",
                    "message": f"{item['name']} 的单位未能识别，已暂按 {item['unit']} 理解。",
                    "detail": "请在校正页补充单位后再分析。",
                }
            )

    return {
        "basis": basis,
        "basis_note": basis_note,
        "items": items,
        "missing_core": [k for k in CORE_KEYS if k not in seen],
        "warnings": warnings,
        "raw_text": text or "",
    }


def value_of(parsed: dict, key: str) -> dict | None:
    for item in parsed.get("items", []):
        if item["key"] == key and item["value"] is not None:
            return item
    return None


__all__ = ["parse_nutrition", "NUTRIENT_DEFS", "CORE_KEYS", "CORE_NAMES", "value_of"]
