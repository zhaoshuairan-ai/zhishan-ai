"""标签辅助核查引擎。

输入：OCR 校正后的字段 + 结构化配料 + 营养成分
输出：逐条核查结论（含结果、原因、依据、待确认事项），以及审慎的整体结论。

三条底线：
1. 图片未拍到 ≠ 包装上缺失；
2. 只做「逻辑一致性」与「字段完整性」检查，不做安全性或合规判定；
3. 依据以标准名称级别引用，不编造条款编号与原文。
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from ..rules.label_rules import RULES_BY_ID, RULESET, THRESHOLDS
from ..utils.validators import parse_cn_date

LEVEL_LABELS = {
    "pass": "未发现问题",
    "info": "提示信息",
    "review": "需要进一步核实",
    "suspected": "发现疑似问题",
    "skip": "本次不适用",
}

OVERALL_LABELS = {
    "none_found": "未发现明显问题",
    "needs_review": "需要进一步核实",
    "suspected": "发现疑似问题",
}

FIELD_REQUIRED = [
    ("food_name", "食品名称", "review"),
    ("ingredients_text", "配料表", "review"),
    ("nutrition_text", "营养成分表", "review"),
    ("net_content", "净含量", "review"),
    ("production_date", "生产日期", "review"),
    ("shelf_life", "保质期", "review"),
    ("storage", "贮存条件", "review"),
    ("producer", "生产者信息", "review"),
    ("standard_no", "产品标准号", "info"),
    ("allergen", "致敏物质提示", "info"),
]


def _db_rule_meta() -> dict:
    """后台维护的规则元数据（停用/改标题/改依据后立即生效）。"""
    try:
        from flask import g

        if "admin_rule_meta" in g:
            return g.admin_rule_meta
        from .admin_service import enabled_rule_meta

        meta = enabled_rule_meta()
        g.admin_rule_meta = meta
        return meta
    except Exception:  # 未建表 / 脱离应用上下文时退回静态规则
        return {}


def _rule_meta(rule_id: str) -> dict:
    rule = RULES_BY_ID.get(rule_id, {})
    override = _db_rule_meta().get(rule_id) or {}
    source = rule.get("source", {})
    if override.get("source", {}).get("name"):
        source = override["source"]
    return {
        "rule_id": rule_id,
        "title": override.get("title") or rule.get("title", rule_id),
        "category": rule.get("category", "其他"),
        "basis": override.get("basis") or rule.get("basis", ""),
        "source": source,
        "todo": rule.get("todo", ""),
        "rule_version": override.get("version") or RULESET["version"],
        "rule_updated_at": override.get("updated_at") or RULESET["updated_at"],
    }


def _item(rule_id: str, level: str, result: str, reason: str, **extra) -> dict:
    data = _rule_meta(rule_id)
    data.update(
        {
            "level": level,
            "level_label": LEVEL_LABELS.get(level, level),
            "result": result,
            "reason": reason,
        }
    )
    data.update(extra)
    return data


def add_months(start: date, months: int) -> date:
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def parse_shelf_life(text: str) -> tuple[int | None, str | None]:
    """返回 (天数, 原始单位)；按 30 天/月、365 天/年近似，仅用于提示。"""
    if not text:
        return None, None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(个月|月|天|日|年|周)", str(text))
    if not match:
        return None, None
    value = float(match.group(1))
    unit = match.group(2)
    if unit in {"个月", "月"}:
        return int(round(value * 30)), unit
    if unit in {"年"}:
        return int(round(value * 365)), unit
    if unit in {"周"}:
        return int(round(value * 7)), unit
    return int(round(value)), unit


def compute_expiry(production: str, shelf_life: str) -> tuple[date | None, str | None]:
    start = parse_cn_date(production or "")
    if not start:
        return None, None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(个月|月|天|日|年|周)", shelf_life or "")
    if not match:
        return None, None
    value = float(match.group(1))
    unit = match.group(2)
    if unit in {"个月", "月"}:
        return add_months(start, int(round(value))), "按月推算"
    if unit == "年":
        return add_months(start, int(round(value * 12))), "按年折算为月推算"
    if unit == "周":
        return start + timedelta(days=int(round(value * 7))), "按周推算"
    return start + timedelta(days=int(round(value))), "按日推算"


def _num(item: dict | None) -> float | None:
    if not item or item.get("value") is None:
        return None
    return float(item["value"])


def _fmt(value: float | None, unit: str = "") -> str:
    if value is None:
        return "未识别"
    if value == int(value):
        return f"{int(value)}{unit}"
    return f"{value:g}{unit}"


def _g_value(item: dict | None) -> float | None:
    """取以克为单位的数值；mg 自动换算。"""
    if not item or item.get("value") is None:
        return None
    value = float(item["value"])
    if item.get("unit") == "mg":
        return value / 1000
    if item.get("unit") == "g":
        return value
    return None


def _energy_kj(item: dict | None) -> float | None:
    if not item or item.get("value") is None:
        return None
    value = float(item["value"])
    if item.get("unit") == "kcal":
        return value * 4.184
    if item.get("unit") == "kJ":
        return value
    return None


def run_checks(
    *,
    fields: dict,
    confidence: dict,
    flags: dict,
    ingredients: dict,
    nutrition: dict,
    analysis_mode: str | None,
    is_demo: bool,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    items: list[dict] = []
    fields = fields or {}
    confidence = confidence or {}
    nutrition_items = {item["key"]: item for item in (nutrition or {}).get("items", [])}
    basis = (nutrition or {}).get("basis", "per_100g")

    # ---------- 1. 字段完整性 ----------
    detected = 0
    for key, label, missing_level in FIELD_REQUIRED:
        value = (fields.get(key) or "").strip()
        if value:
            detected += 1
            rule_id = {
                "food_name": "FIELD_FOOD_NAME",
                "ingredients_text": "FIELD_INGREDIENTS",
                "nutrition_text": "FIELD_NUTRITION",
                "producer": "FIELD_PRODUCER",
                "net_content": "FIELD_NET_CONTENT",
                "production_date": "FIELD_DATE",
                "shelf_life": "FIELD_DATE",
                "storage": "FIELD_STORAGE",
                "allergen": "FIELD_ALLERGEN",
                "standard_no": "FIELD_STANDARD_NO",
            }[key]
            items.append(
                _item(
                    rule_id,
                    "pass",
                    f"已识别到{label}",
                    f"图片来源区域内读取到「{value[:40]}」",
                    found=value,
                )
            )
        else:
            rule_id = {
                "food_name": "FIELD_FOOD_NAME",
                "ingredients_text": "FIELD_INGREDIENTS",
                "nutrition_text": "FIELD_NUTRITION",
                "producer": "FIELD_PRODUCER",
                "net_content": "FIELD_NET_CONTENT",
                "production_date": "FIELD_DATE",
                "shelf_life": "FIELD_DATE",
                "storage": "FIELD_STORAGE",
                "allergen": "FIELD_ALLERGEN",
                "standard_no": "FIELD_STANDARD_NO",
            }[key]
            items.append(
                _item(
                    rule_id,
                    missing_level,
                    f"图片中未识别到{label}",
                    "可能是该信息不在本次拍摄区域内，或字迹模糊/反光导致未识别；"
                    "这不代表包装上实际缺少该信息，请结合实物确认。",
                    needs_manual=True,
                )
            )
    # 计量基准未识别时，默认按每 100g 理解，同时在核查列表里明确列出这一条
    basis_note = str((nutrition or {}).get("basis_note") or "")
    if basis_note.startswith("未在"):
        items.append(
            _item(
                "NUTRI_BASIS",
                "review",
                "未识别到明确的每100g或每份计量基准，需人工确认。",
                "系统已默认按每 100g 展示营养明细；若包装实际按每份标示，请在校正页补充表头。",
                title="计量基准",
                needs_manual=True,
            )
        )

    # 合并重复的 FIELD_DATE 条目名称（生产日期/保质期分开更清楚）
    coverage_ratio = round(detected / len(FIELD_REQUIRED), 3)

    # ---------- 2. 识别质量 ----------
    low_fields = [key for key, conf in confidence.items() if 0 < float(conf) < 0.8]
    if low_fields:
        labels = {
            "food_name": "食品名称",
            "ingredients_text": "配料表",
            "nutrition_text": "营养成分表",
            "net_content": "净含量",
            "production_date": "生产日期",
            "shelf_life": "保质期",
            "expiry_date": "到期日期",
            "storage": "贮存条件",
            "producer": "生产者",
            "standard_no": "产品标准号",
            "allergen": "致敏物质提示",
        }
        items.append(
            _item(
                "OCR_CONFIDENCE",
                "review",
                f"{len(low_fields)} 个字段置信度偏低",
                "低置信度字段：" + "、".join(labels.get(k, k) for k in low_fields[:8]) + "。请逐字核对校正结果。",
                needs_manual=True,
                found=low_fields,
            )
        )
    else:
        items.append(_item("OCR_CONFIDENCE", "pass", "识别置信度正常", "未发现明显低置信度字段。"))

    if coverage_ratio < 0.5:
        items.append(
            _item(
                "OCR_COVERAGE",
                "review",
                f"仅识别到 {detected}/{len(FIELD_REQUIRED)} 个关键字段",
                "单张照片通常只覆盖包装的一个面，字段不全是正常现象。建议补拍其他面后重新识别。",
                needs_manual=True,
                found={"detected": detected, "total": len(FIELD_REQUIRED), "ratio": coverage_ratio},
            )
        )
    else:
        items.append(
            _item(
                "OCR_COVERAGE",
                "pass",
                f"关键字段覆盖 {detected}/{len(FIELD_REQUIRED)}",
                "本次识别覆盖了大多数关键字段。",
                found={"detected": detected, "total": len(FIELD_REQUIRED), "ratio": coverage_ratio},
            )
        )

    # ---------- 3. 日期逻辑 ----------
    production = (fields.get("production_date") or "").strip()
    shelf_life = (fields.get("shelf_life") or "").strip()
    expiry_field = (fields.get("expiry_date") or "").strip()
    production_date = parse_cn_date(production) if production else None

    if production:
        if production_date is None:
            items.append(
                _item(
                    "DATE_FORMAT",
                    "review",
                    "生产日期格式无法解析",
                    f"识别到的日期为「{production}」，无法解析为年-月-日。可能是喷码模糊或格式特殊。",
                    needs_manual=True,
                    found=production,
                )
            )
        else:
            items.append(
                _item("DATE_FORMAT", "pass", "生产日期格式可解析", f"解析结果：{production_date.isoformat()}", found=production)
            )
            if production_date > today:
                items.append(
                    _item(
                        "DATE_FUTURE",
                        "suspected",
                        "生产日期晚于当前日期",
                        f"识别到的生产日期为 {production_date.isoformat()}，晚于今天 {today.isoformat()}。"
                        "若实物确实如此，属于需要核实的异常；也可能是识别或系统日期问题。",
                        needs_manual=True,
                        found=production,
                    )
                )
            else:
                items.append(_item("DATE_FUTURE", "pass", "生产日期不晚于今天", f"生产日期 {production_date.isoformat()}"))

    expiry_source = None
    expiry_date = parse_cn_date(expiry_field) if expiry_field else None
    if expiry_date:
        expiry_source = "包装上标示的到期日期"
    elif production_date and shelf_life:
        expiry_date, method = compute_expiry(production, shelf_life)
        if expiry_date:
            expiry_source = f"生产日期 + 保质期推算（{method}）"

    if expiry_date:
        days_left = (expiry_date - today).days
        if days_left < 0:
            items.append(
                _item(
                    "DATE_EXPIRY",
                    "suspected",
                    f"按标示推算已过期 {abs(days_left)} 天",
                    f"推算到期日期为 {expiry_date.isoformat()}，早于今天 {today.isoformat()}（依据：{expiry_source}）。"
                    "若照片为近期拍摄，建议核对实物并联系商家；若为旧照片则属正常。",
                    needs_manual=True,
                    found={"expiry_date": expiry_date.isoformat(), "days_left": days_left},
                )
            )
        elif days_left <= THRESHOLDS["expiry_warning_days"]:
            items.append(
                _item(
                    "DATE_EXPIRY",
                    "review",
                    f"距到期仅剩 {days_left} 天",
                    f"推算到期日期为 {expiry_date.isoformat()}（依据：{expiry_source}），请尽快食用并注意贮存条件。",
                    found={"expiry_date": expiry_date.isoformat(), "days_left": days_left},
                )
            )
        else:
            items.append(
                _item(
                    "DATE_EXPIRY",
                    "pass",
                    f"距到期还有 {days_left} 天",
                    f"推算到期日期为 {expiry_date.isoformat()}（依据：{expiry_source}）。",
                    found={"expiry_date": expiry_date.isoformat(), "days_left": days_left},
                )
            )
    elif production_date and not shelf_life:
        items.append(
            _item(
                "DATE_EXPIRY",
                "review",
                "缺少保质期，无法推算到期日期",
                "已识别到生产日期，但没有可解析的保质期（如「12个月」）。",
                needs_manual=True,
            )
        )
    elif not production:
        items.append(_item("DATE_EXPIRY", "skip", "无生产日期，跳过保质期推算", "未识别到生产日期，本次不做日期推算。"))

    storage = (fields.get("storage") or "").strip()
    if storage:
        if re.search(r"冷藏|冷冻|0\s*[-~至]\s*4|2\s*[-~至]\s*8|冷链|低温", storage):
            items.append(
                _item(
                    "DATE_STORAGE_MATCH",
                    "info",
                    "产品标注需要低温贮存",
                    f"识别到贮存条件「{storage}」，请确认购买与存放环节始终保持该温度；冷链中断会影响实际保质期。",
                    found=storage,
                )
            )
        else:
            items.append(
                _item("DATE_STORAGE_MATCH", "pass", "贮存条件未见特殊温度要求", f"识别到贮存条件「{storage}」。", found=storage)
            )
    else:
        items.append(_item("DATE_STORAGE_MATCH", "skip", "未识别到贮存条件，无法比对", "请确认包装上是否标注贮存条件。"))

    # ---------- 4. 单位与数值 ----------
    if nutrition_items:
        inferred = [item for item in nutrition_items.values() if item.get("unit_inferred")]
        if inferred:
            items.append(
                _item(
                    "NUTRI_UNIT",
                    "review",
                    f"{len(inferred)} 个营养素缺少可识别单位",
                    "已按常见习惯暂定单位：" + "、".join(f"{i['name']}({i['unit']})" for i in inferred[:6]) + "。请人工确认。",
                    needs_manual=True,
                    found=[i["name"] for i in inferred],
                )
            )
        else:
            items.append(_item("NUTRI_UNIT", "pass", "营养成分单位可识别", "主要营养素均带有单位。"))

        weird = []
        for key, item in nutrition_items.items():
            value = _num(item)
            if value is None:
                continue
            if value < 0:
                weird.append(f"{item['name']}为负值")
            if item.get("unit") == "g" and value > 100 and key != "energy":
                weird.append(f"{item['name']}超过 100g/100g")
        if weird:
            items.append(
                _item(
                    "NUTRI_RANGE",
                    "suspected",
                    "营养成分数值超出合理范围",
                    "；".join(weird) + "。这类情况多为 OCR 误读，请对照实物更正。",
                    needs_manual=True,
                    found=weird,
                )
            )
        else:
            items.append(_item("NUTRI_RANGE", "pass", "营养成分数值在合理范围内", "未发现负值或明显不合理的量级。"))

        protein = _g_value(nutrition_items.get("protein"))
        fat = _g_value(nutrition_items.get("fat"))
        carb = _g_value(nutrition_items.get("carbohydrate"))
        if basis == "per_100g" and None not in (protein, fat, carb):
            total = (protein or 0) + (fat or 0) + (carb or 0)
            if total > THRESHOLDS["nutrient_sum_tolerance_g"]:
                items.append(
                    _item(
                        "NUTRI_SUM",
                        "suspected",
                        f"三大营养素合计 {total:.1f}g/100g，超过 100g",
                        "按每 100g 计算，蛋白质+脂肪+碳水化合物之和不应显著超过 100g。常见原因是把「每份」当成「每100g」，或单位/mL 基准不一致。",
                        needs_manual=True,
                        found={"total_g": round(total, 1)},
                    )
                )
            else:
                items.append(
                    _item(
                        "NUTRI_SUM",
                        "pass",
                        f"三大营养素合计 {total:.1f}g/100g",
                        "三者之和未超过 100g/100g，量级合理。",
                        found={"total_g": round(total, 1)},
                    )
                )
        else:
            items.append(
                _item(
                    "NUTRI_SUM",
                    "skip",
                    "三大营养素数据不完整或基准不是每 100g",
                    "缺少蛋白质/脂肪/碳水化合物之一，或计量基准不是每 100g，本次不做合计检查。",
                )
            )

        energy_declared = _energy_kj(nutrition_items.get("energy"))
        if energy_declared and None not in (protein, fat, carb):
            factors = THRESHOLDS["energy_factors_kj_per_g"]
            estimated = protein * factors["protein"] + fat * factors["fat"] + carb * factors["carbohydrate"]
            if estimated > 0:
                deviation = (energy_declared - estimated) / estimated
                tolerance = THRESHOLDS["energy_deviation_tolerance"]
                detail = (
                    f"标示能量 {energy_declared:.0f}kJ，按蛋白质×{factors['protein']}、脂肪×{factors['fat']}、"
                    f"碳水化合物×{factors['carbohydrate']} 估算为 {estimated:.0f}kJ，偏差 {deviation * 100:+.1f}%。"
                )
                if abs(deviation) > tolerance:
                    items.append(
                        _item(
                            "NUTRI_ENERGY",
                            "review",
                            "能量与三大营养素折算偏差较大",
                            detail + "可能原因：单位为每份、能量单位是 kcal、或某项数值识别有误。膳食纤维、糖醇等也会造成偏差。",
                            needs_manual=True,
                            found={"declared_kj": round(energy_declared, 1), "estimated_kj": round(estimated, 1)},
                        )
                    )
                else:
                    items.append(
                        _item(
                            "NUTRI_ENERGY",
                            "pass",
                            "能量与三大营养素折算基本一致",
                            detail,
                            found={"declared_kj": round(energy_declared, 1), "estimated_kj": round(estimated, 1)},
                        )
                    )
        else:
            items.append(_item("NUTRI_ENERGY", "skip", "数据不足，未做能量折算", "缺少能量或三大营养素数值。"))

        nrv_mismatch = []
        for key, item in nutrition_items.items():
            declared = item.get("nrv_percent")
            estimated = item.get("nrv_percent_estimated")
            if declared is None or estimated is None or estimated == 0:
                continue
            if abs(declared - estimated) / max(estimated, 1) > 0.2:
                nrv_mismatch.append(f"{item['name']}（标示 {declared}%，估算 {estimated}%）")
        if nrv_mismatch:
            items.append(
                _item(
                    "NUTRI_NRV",
                    "info",
                    "部分 NRV% 与平台估算不一致",
                    "；".join(nrv_mismatch) + "。平台使用内置 NRV 参考值估算，且可能受计量基准影响；请以包装标示与标准附录为准。",
                    found=nrv_mismatch,
                )
            )
        else:
            items.append(_item("NUTRI_NRV", "pass", "NRV% 未见明显异常", "标示的 NRV% 与平台估算基本吻合或数据不足。"))

        sodium = _num(nutrition_items.get("sodium"))
        if sodium is not None and basis == "per_100g":
            threshold = THRESHOLDS["sodium_high_mg_per_100g"]
            if sodium >= threshold:
                items.append(
                    _item(
                        "NUTRI_HIGH_SODIUM",
                        "info",
                        f"钠含量较高（{_fmt(sodium, 'mg')}/100g）",
                        f"超过平台提示阈值 {threshold:.0f}mg/100g。这是饮食提示，不代表食品不合格或不安全。"
                        f"换算成食盐约为 {sodium / 393:.1f}g/100g。",
                        found={"sodium_mg": sodium, "salt_g": round(sodium / 393, 2)},
                    )
                )
            else:
                items.append(
                    _item(
                        "NUTRI_HIGH_SODIUM",
                        "pass",
                        f"钠含量未超过提示阈值（{_fmt(sodium, 'mg')}/100g）",
                        f"平台提示阈值为 {threshold:.0f}mg/100g，仅用于饮食关注度提示。",
                        found={"sodium_mg": sodium},
                    )
                )
        else:
            items.append(_item("NUTRI_HIGH_SODIUM", "skip", "未识别到钠含量或基准不明", "无法做钠含量提示。"))
    else:
        for rule_id in ("NUTRI_UNIT", "NUTRI_RANGE", "NUTRI_SUM", "NUTRI_ENERGY", "NUTRI_NRV", "NUTRI_HIGH_SODIUM"):
            items.append(_item(rule_id, "skip", "未识别到营养成分数据", "请先补拍或填写营养成分表。"))

    # ---------- 5. 配料表 ----------
    ingredient_items = [i for i in (ingredients or {}).get("items", []) if not i.get("is_category")]
    if ingredient_items:
        if len(ingredient_items) >= 2:
            items.append(
                _item(
                    "INGREDIENT_PARSE",
                    "pass",
                    f"配料表已拆分为 {len(ingredient_items)} 项",
                    "按顿号、逗号等分隔符完成拆分，复合配料括号内的内容保留在原文中。",
                    found=len(ingredient_items),
                )
            )
        else:
            items.append(
                _item(
                    "INGREDIENT_PARSE",
                    "review",
                    "配料表仅解析出 1 项",
                    "可能缺少分隔符或识别有误，请在校正页确认配料表原文。",
                    needs_manual=True,
                )
            )

        percent_items = [i for i in ingredient_items if i.get("percent") is not None]
        if len(percent_items) >= 2:
            violations = []
            for prev, curr in zip(percent_items, percent_items[1:]):
                if curr["percent"] > prev["percent"] + 0.01:
                    violations.append(f"{curr['name']}({curr['percent']}%) 排在 {prev['name']}({prev['percent']}%) 之后")
            if violations:
                items.append(
                    _item(
                        "INGREDIENT_ORDER",
                        "review",
                        "带百分比的配料未按递减顺序排列",
                        "；".join(violations) + "。若 OCR 打乱了行序，或配料属于可豁免排序的情形，则不构成问题。",
                        needs_manual=True,
                        found=violations,
                    )
                )
            else:
                items.append(
                    _item("INGREDIENT_ORDER", "pass", "带百分比的配料按递减顺序排列", "标示顺序与含量顺序一致。")
                )
        else:
            items.append(
                _item(
                    "INGREDIENT_ORDER",
                    "skip",
                    "配料表未标注百分比，无法核对顺序",
                    "未标注含量的情况下，系统无法判断是否按加入量递减排列，只能提示这些配料是按标示顺序排列的。",
                )
            )

        additive_names = [
            i["name"]
            for i in ingredient_items
            if i.get("hint_category") not in {None, "", "普通配料"} or i.get("parent")
        ]
        if additive_names:
            items.append(
                _item(
                    "INGREDIENT_ADDITIVE",
                    "info",
                    f"识别到 {len(additive_names)} 种可能属于添加剂类别的成分",
                    "涉及：" + "、".join(additive_names[:10]) + "。系统仅解释用途，不判定安全性；"
                    "食品添加剂在标准允许的品种、范围与用量内使用是允许的。",
                    found=additive_names,
                )
            )
        else:
            items.append(
                _item("INGREDIENT_ADDITIVE", "pass", "未识别到明显的添加剂特征名称", "配料表以普通配料为主。")
            )
    else:
        for rule_id in ("INGREDIENT_PARSE", "INGREDIENT_ORDER", "INGREDIENT_ADDITIVE"):
            items.append(_item(rule_id, "skip", "未识别到配料表", "请先补拍配料表区域或手动输入后重新分析。"))

    # ---------- 6. 透明度 ----------
    mode_label = {"ai": "大模型分析", "rule": "基础规则模式"}.get(analysis_mode or "", "未分析")
    if is_demo:
        items.append(
            _item(
                "MODE_DISCLOSURE",
                "review",
                "本次记录包含演示数据",
                "OCR 或分析使用了内置演示样例，结果不代表对真实包装的识别，请勿作为事实引用。",
                needs_manual=True,
                found={"analysis_mode": analysis_mode, "is_demo": True},
            )
        )
    else:
        items.append(
            _item(
                "MODE_DISCLOSURE",
                "pass",
                f"分析模式：{mode_label}",
                "报告与分析结果中均已标注本次使用的模式与模型，便于区分真实分析与规则/演示结果。",
                found={"analysis_mode": analysis_mode, "is_demo": False},
            )
        )

    # 后台停用的规则不进入结果；规则的标题/依据/版本以后台维护的元数据为准
    db_meta = _db_rule_meta()
    if db_meta:
        items = [item for item in items if db_meta.get(item["rule_id"], {}).get("enabled", True)]

    counts = {level: 0 for level in LEVEL_LABELS}
    for item in items:
        counts[item["level"]] = counts.get(item["level"], 0) + 1

    if counts["suspected"] > 0:
        overall = "suspected"
    elif counts["review"] > 0:
        overall = "needs_review"
    else:
        overall = "none_found"

    coverage = {
        "detected": detected,
        "total": len(FIELD_REQUIRED),
        "ratio": coverage_ratio,
        "nutrition_items": len([i for i in nutrition_items.values() if i.get("value") is not None]),
        "ingredient_count": len(ingredient_items),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    return {
        "overall": overall,
        "overall_label": OVERALL_LABELS[overall],
        "items": items,
        "counts": counts,
        "coverage": coverage,
        "ruleset_version": RULESET["version"],
    }


__all__ = ["run_checks", "compute_expiry", "parse_shelf_life", "add_months", "OVERALL_LABELS", "LEVEL_LABELS"]
