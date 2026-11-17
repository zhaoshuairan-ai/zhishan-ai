"""健康评估（自建参考模型）：反式脂肪、糖、添加剂与综合健康分。

重要边界：
- 不是国家标准、不是医学诊断、不是合规判定；
- 「反式脂肪是否超标」只能对照 WHO 的供能比参考建议，不能称为法规意义上的超标；
- 添加剂是否合规需要具体品类、用量与适用范围，系统未收录限量数据，因此只提示「待核实」；
- 健康分是本站自定义的透明评分，缺失数据会降低置信度，不能替代营养师或医生意见。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ..models import AnalysisRecord
from . import knowledge_service

MODEL_VERSION = "health-1.0"
SUGAR_DAILY_LIMIT_G = 25.0  # 《中国居民膳食指南（2022）》添加糖建议上限（25–50g，取更严格值）
SODIUM_DAILY_LIMIT_MG = 2000.0  # NRV
WHO_TRANS_ENERGY_RATIO = 1.0  # WHO 建议反式脂肪供能 < 1%
WHO_SAT_ENERGY_RATIO = 10.0  # WHO 建议饱和脂肪供能 < 10%

GRADES = [
    (85, "A", "较优"),
    (70, "B", "良好"),
    (55, "C", "一般"),
    (40, "D", "需留意"),
    (0, "E", "重点关注"),
]

RISK_NOTES = {
    "sodium-nitrite": "亚硝酸盐在高温煎炸或与胺类物质共同存在时，可能生成亚硝胺；本系统无法判断实际生成量。",
    "sulfites": "哮喘人群可能对二氧化硫及亚硫酸盐较敏感。",
    "aspartame": "苯丙酮尿症（PKU）患者应避免阿斯巴甜。",
    "erythritol": "糖醇一次大量摄入可能引起腹胀或腹泻。",
    "phosphates": "肾功能不全人群通常需要限制磷摄入。",
    "carrageenan": "部分肠病人群对卡拉胶的耐受性存在个体差异。",
    "caffeine": "对咖啡因敏感者、孕妇与儿童需注意摄入量。",
}

ADDITIVE_HINT_WORDS = (
    "防腐",
    "甜味",
    "着色",
    "增稠",
    "乳化",
    "抗氧化",
    "酸度",
    "膨松",
    "水分保持",
    "抗结",
    "漂白",
    "护色",
    "增味",
    "香精",
    "色素",
)

DISCLAIMER = (
    "健康分是本站基于包装标签数据自建的参考模型，不是国家标准、医学诊断或合规判定；"
    "数据缺失、标签标示方式与个体差异都会影响结果，请结合配料表、营养成分表与专业意见判断。"
)


def _item_map(record: AnalysisRecord) -> dict[str, dict]:
    nutrition = record.nutrition
    if not nutrition:
        return {}
    return {item.get("key"): item for item in nutrition.items or [] if item.get("key")}


def _value(item: dict | None, *, unit: str | None = None) -> float | None:
    if not item:
        return None
    value = item.get("value")
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    item_unit = str(item.get("unit") or "")
    if unit == "mg" and item_unit == "g":
        number *= 1000
    if unit == "g" and item_unit == "mg":
        number /= 1000
    return number


def _energy_kj(item: dict | None) -> float | None:
    if not item:
        return None
    value = item.get("value_kj")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    number = _value(item)
    if number is None:
        return None
    return number * 4.184 if str(item.get("unit")) == "kcal" else number


def _net_content_g(record: AnalysisRecord) -> float | None:
    text = ""
    if record.ocr and record.ocr.fields:
        text = str(record.ocr.fields.get("net_content") or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|千克|g|克|ml|毫升|L|升)", text, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    if unit in {"kg", "千克", "l", "升"}:
        amount *= 1000
    return round(amount, 1)


def _grade(score: int) -> tuple[str, str]:
    for threshold, grade, label in GRADES:
        if score >= threshold:
            return grade, label
    return "E", "重点关注"


def _sugar_assessment(items: dict[str, dict], net_g: float | None) -> tuple[dict, dict, int]:
    sugar_item = items.get("sugar")
    sugar = _value(sugar_item)
    if sugar is None:
        finding = {
            "key": "sugar",
            "title": "糖与减脂",
            "level": "unknown",
            "level_label": "数据不足",
            "summary": "标签未标注糖，无法量化含糖量对减脂的影响。",
            "detail": "糖不是强制标示项目；可以看配料表中白砂糖、果葡糖浆、蜂蜜、浓缩果汁等是否排在前列，并结合能量判断。",
            "basis": "GB 28050 营养标签与《中国居民膳食指南（2022）》添加糖建议",
            "confidence": "低",
        }
        return finding, {"value_g": None, "daily_ratio": None, "package_sugar_g": None}, 14

    ratio = round(sugar / SUGAR_DAILY_LIMIT_G * 100, 1)
    package_sugar = round(sugar * net_g / 100, 1) if net_g else None
    if sugar <= 5:
        level, level_label, score, tone = "good", "较低", 25, "每 100g 含糖较低"
    elif sugar <= 15:
        level, level_label, score, tone = "watch", "中等", 16, "每 100g 含糖处于中等水平"
    else:
        level, level_label, score, tone = "watch", "偏高", 6, "每 100g 含糖偏高"
    detail = (
        f"每 100g 含糖 {sugar:g}g，约相当于每日添加糖建议上限（25g）的 {ratio}%。"
        "标签上的「糖」包含天然糖，不等于全部是添加糖。"
    )
    if package_sugar is not None:
        detail += f" 按净含量约 {net_g:g}g 计算，吃完整份约摄入 {package_sugar:g}g 糖，约占每日上限的 {round(package_sugar / SUGAR_DAILY_LIMIT_G * 100, 1)}%。"
    detail += " 减脂人群更需要控制总能量与添加糖，建议按份量食用并减少含糖饮料。"
    finding = {
        "key": "sugar",
        "title": "糖与减脂",
        "level": level,
        "level_label": level_label,
        "summary": f"{tone}：约 {ratio}% 的每日添加糖参考上限（按每 100g 计）。",
        "detail": detail,
        "basis": "《中国居民膳食指南（2022）》添加糖建议；标签糖含量不等于添加糖",
        "confidence": "中" if sugar_item.get("status") == "ok" else "低",
    }
    return finding, {"value_g": sugar, "daily_ratio": ratio, "package_sugar_g": package_sugar}, score


def _trans_assessment(items: dict[str, dict], energy_kj: float | None) -> tuple[dict, dict, int]:
    trans_item = items.get("trans_fat")
    trans = _value(trans_item)
    if trans is None:
        return (
            {
                "key": "trans_fat",
                "title": "反式脂肪酸",
                "level": "unknown",
                "level_label": "数据不足",
                "summary": "标签未标注反式脂肪酸，无法评估。",
                "detail": "反式脂肪酸不是强制标示项目；可查看配料表是否含「氢化植物油」「人造奶油」「代可可脂」等，并结合脂肪酸组成判断。",
                "basis": "GB 28050 与 WHO 反式脂肪供能建议",
                "confidence": "低",
            },
            {"value_g": None, "energy_ratio": None},
            8,
        )

    ratio = None
    if energy_kj and energy_kj > 0:
        ratio = round(trans * 37 / energy_kj * 100, 2)  # 1g 脂肪约 37kJ
    if trans == 0:
        level, level_label, score, summary = (
            "good",
            "标示为 0",
            15,
            "标签标示反式脂肪酸为 0g/100g。",
        )
        detail = (
            "按 GB 28050，反式脂肪酸含量低于标示阈值时可标为 0，因此「0」代表很低，不代表绝对不含。"
            "仍建议减少反复煎炸食品与含「氢化植物油」的加工食品。"
        )
    elif ratio is not None and ratio > WHO_TRANS_ENERGY_RATIO:
        level, level_label, score = "watch", "高于参考", 4
        summary = f"反式脂肪酸供能约 {ratio}%，高于 WHO 建议的 <1% 参考水平。"
        detail = (
            f"每 100g 含反式脂肪酸 {trans:g}g，按能量折算约占总能量的 {ratio}%。"
            "这是与 WHO 参考建议的比较，不是法规意义上的「超标」；建议减少食用频率，并留意配料表中的氢化油脂。"
        )
    elif ratio is None:
        level, level_label, score = "unknown", "无法计算", 10
        summary = f"每 100g 含反式脂肪酸 {trans:g}g，但能量未标注，无法计算供能比。"
        detail = (
            f"每 100g 含反式脂肪酸 {trans:g}g。WHO 的参考建议是反式脂肪供能 <1%，"
            "缺少能量数据时无法判断是否接近该水平，建议核对营养成分表或减少高油脂加工食品。"
        )
    else:
        level, level_label, score = "good", "参考范围内", 13
        summary = "反式脂肪酸供能比处于 WHO 参考建议范围内。"
        detail = (
            f"每 100g 含反式脂肪酸 {trans:g}g，约占总能量 {ratio}%。"
            "参考建议为 <1% 总能量（WHO），并非法规限量。"
        )
    finding = {
        "key": "trans_fat",
        "title": "反式脂肪酸",
        "level": level,
        "level_label": level_label,
        "summary": summary,
        "detail": detail,
        "basis": "WHO：反式脂肪供能 <1%；GB 28050「0」标示规则",
        "confidence": "中" if ratio is not None else "低",
    }
    return finding, {"value_g": trans, "energy_ratio": ratio}, score


def _fat_quality(items: dict[str, dict], energy_kj: float | None) -> tuple[dict, int]:
    fat = _value(items.get("fat"))
    saturated = _value(items.get("saturated_fat"))
    ratio = None
    if saturated is not None and energy_kj:
        ratio = round(saturated * 37 / energy_kj * 100, 1)
    if saturated is None:
        return (
            {
                "key": "fat_quality",
                "title": "脂肪质量",
                "level": "unknown",
                "level_label": "数据不足",
                "summary": "未标注饱和脂肪，无法计算脂肪供能结构。",
                "detail": "可结合配料表判断是否含棕榈油、黄油、起酥油等饱和脂肪较高的原料。",
                "basis": "WHO 饱和脂肪供能建议",
                "confidence": "低",
            },
            9,
        )
    if ratio is not None and ratio > WHO_SAT_ENERGY_RATIO:
        level, score = "watch", 6
        summary = f"饱和脂肪供能约 {ratio}%，高于 WHO 建议的 <10% 参考水平。"
    elif ratio is None:
        level, score = "unknown", 9
        summary = "能量未标注，无法计算饱和脂肪供能比。"
    else:
        level, score = "good", 14
        summary = f"饱和脂肪供能约 {ratio}%，处于 WHO 参考建议内。"
    detail = f"每 100g 含脂肪 {fat:g}g（如标示）、饱和脂肪 {saturated:g}g。" if fat is not None else f"每 100g 含饱和脂肪 {saturated:g}g。"
    return (
        {
            "key": "fat_quality",
            "title": "脂肪质量",
            "level": level,
            "level_label": "需留意" if level == "watch" else "参考范围内",
            "summary": summary,
            "detail": detail,
            "basis": "WHO：饱和脂肪供能 <10%",
            "confidence": "中" if ratio is not None else "低",
        },
        score,
    )


def _additives(record: AnalysisRecord) -> tuple[dict, dict, int]:
    ingredient = record.ingredient
    ingredients = (ingredient.ingredients if ingredient else []) or []
    names = [str(item.get("name") or "").strip() for item in ingredients if item.get("name")]

    hits = knowledge_service.match_names(names) if names else {}
    additive_by_slug: dict[str, dict] = {}
    for name, matches in hits.items():
        for hit in matches:
            if hit.get("category") != "additive":
                continue
            slug = hit.get("slug")
            if not slug:
                continue
            additive_by_slug.setdefault(
                slug,
                {
                    "name": hit.get("title") or name,
                    "ingredient_name": name,
                    "role": "食品添加剂（详见知识库）",
                    "knowledge_id": hit.get("id"),
                    "knowledge_title": hit.get("title"),
                    "source_name": hit.get("source_name"),
                    "risk_note": RISK_NOTES.get(slug),
                    "compliance": "待核实",
                },
            )

    # 知识库没覆盖、但配料表类别明确属于添加剂的，也要列出
    for item in ingredients:
        category = str(item.get("category") or "")
        name = str(item.get("name") or "")
        if not name or not any(word in category for word in ADDITIVE_HINT_WORDS):
            continue
        if any(entry["ingredient_name"] == name for entry in additive_by_slug.values()):
            continue
        additive_by_slug[f"unknown:{name}"] = {
            "name": name,
            "ingredient_name": name,
            "role": category,
            "knowledge_id": None,
            "knowledge_title": None,
            "source_name": None,
            "risk_note": None,
            "compliance": "待核实",
        }

    count = len(additive_by_slug)
    if count == 0:
        score = 5
    elif count <= 2:
        score = 4
    elif count <= 4:
        score = 3
    elif count <= 6:
        score = 2
    else:
        score = 1
    names_text = "、".join(entry["name"] for entry in list(additive_by_slug.values())[:8]) or "未识别到常见添加剂"
    finding = {
        "key": "additives",
        "title": "添加剂与合规性",
        "level": "info",
        "level_label": "待核实",
        "summary": f"识别到 {count} 种常见添加剂：{names_text}。",
        "detail": (
            "添加剂本身不等于不安全；是否合规取决于允许的食品类别、用量与适用范围。"
            "本站未收录 GB 2760 的具体限量数据，无法判断本产品是否合规，需以官方标准、抽检或检测结果为准。"
        ),
        "basis": "GB 2760《食品安全国家标准 食品添加剂使用标准》（名称引用，未收录限量）",
        "confidence": "中" if count else "低",
    }
    return finding, {"count": count, "items": list(additive_by_slug.values())}, score


def assess(record: AnalysisRecord) -> dict:
    items = _item_map(record)
    net_g = _net_content_g(record)
    energy_kj = _energy_kj(items.get("energy"))

    sugar_finding, sugar_metrics, sugar_score = _sugar_assessment(items, net_g)
    trans_finding, trans_metrics, trans_score = _trans_assessment(items, energy_kj)
    fat_finding, fat_score = _fat_quality(items, energy_kj)
    additive_finding, additive_metrics, additive_score = _additives(record)

    core_keys = ("energy", "protein", "fat", "carbohydrate", "sodium")
    core_present = [key for key in core_keys if _value(items.get(key)) is not None]
    has_sugar = _value(items.get("sugar")) is not None
    has_trans = _value(items.get("trans_fat")) is not None
    transparency = 2 + round(len(core_present) / len(core_keys) * 5) + (2 if has_sugar else 0) + (1 if record.ingredient and record.ingredient.ingredients else 0)
    transparency = min(10, transparency)

    protein = _value(items.get("protein")) or 0
    fiber = _value(items.get("dietary_fiber")) or 0
    positive = min(
        10,
        (5 if protein >= 12 else 3 if protein >= 6 else 1) + (5 if fiber >= 6 else 3 if fiber >= 3 else 1),
    )
    positive_finding = {
        "key": "positive",
        "title": "蛋白质与膳食纤维",
        "level": "good" if positive >= 10 else "info",
        "level_label": "较丰富" if positive >= 10 else "一般",
        "summary": f"蛋白质 {protein:g}g/100g，膳食纤维 {fiber:g}g/100g。",
        "detail": "蛋白质与膳食纤维有助于饱腹感，但也要结合总能量与整体饮食判断，不能只看单一指标。",
        "basis": "GB 28050 营养素参考值（NRV）",
        "confidence": "中",
    }

    sodium = _value(items.get("sodium"), unit="mg")
    if sodium is None:
        sodium_score = 12
        sodium_finding = {
            "key": "sodium",
            "title": "钠与血压",
            "level": "unknown",
            "level_label": "数据不足",
            "summary": "未标注钠，无法评估钠摄入负担。",
            "detail": "钠是强制标示项目；如果缺失，建议核对营养成分表或包装原图。",
            "basis": "GB 28050 钠的 NRV 为 2000mg",
            "confidence": "低",
        }
    else:
        if sodium <= 120:
            sodium_score, level, label = 20, "good", "较低"
        elif sodium <= 300:
            sodium_score, level, label = 16, "good", "适中"
        elif sodium <= 600:
            sodium_score, level, label = 10, "watch", "偏高"
        elif sodium <= 1000:
            sodium_score, level, label = 6, "watch", "偏高"
        else:
            sodium_score, level, label = 3, "watch", "很高"
        sodium_finding = {
            "key": "sodium",
            "title": "钠与血压",
            "level": level,
            "level_label": label,
            "summary": f"每 100g 含钠 {sodium:g}mg，约占每日 NRV 的 {round(sodium / SODIUM_DAILY_LIMIT_MG * 100, 1)}%。",
            "detail": "钠摄入过多与血压升高相关；减脂人群也应同时关注高盐调味料与加工食品。",
            "basis": "GB 28050：钠 NRV 2000mg；《中国居民膳食指南》建议少盐",
            "confidence": "中" if items.get("sodium", {}).get("status") == "ok" else "低",
        }
    # 营养数据太少时不给数字分，避免把「未标注」误读成「不健康」
    sufficient = len(core_present) >= 3 and energy_kj is not None
    if sufficient:
        raw_score = sugar_score + sodium_score + trans_score + fat_score + positive + additive_score + transparency
        score = max(0, min(100, int(raw_score)))
        grade, grade_label = _grade(score)
    else:
        score = None
        grade, grade_label = "NA", "数据不足"

    dimensions = [
        {
            "key": "sugar",
            "label": "糖",
            "score": sugar_score,
            "max": 25,
            "status": "unknown" if _value(items.get("sugar")) is None else "ok",
        },
        {
            "key": "sodium",
            "label": "钠",
            "score": sodium_score,
            "max": 20,
            "status": "unknown" if sodium is None else "ok",
        },
        {
            "key": "fat",
            "label": "脂肪质量",
            "score": fat_score,
            "max": 15,
            "status": "unknown" if _value(items.get("saturated_fat")) is None else "ok",
        },
        {
            "key": "trans",
            "label": "反式脂肪",
            "score": trans_score,
            "max": 15,
            "status": "unknown" if _value(items.get("trans_fat")) is None else "ok",
        },
        {"key": "positive", "label": "蛋白质/纤维", "score": positive, "max": 10, "status": "ok"},
        {"key": "additives", "label": "添加剂负担", "score": additive_score, "max": 5, "status": "ok"},
        {"key": "transparency", "label": "标签完整性", "score": transparency, "max": 10, "status": "ok"},
    ]


    if score is None:
        headline = "标签营养数据不足，暂不给出健康分；以下只列出能判断的项目，建议核对包装原图。"
    elif grade in {"A", "B"}:
        headline = f"{grade} · {grade_label}：整体指标较均衡，仍建议以完整饮食结构为准。"
    elif grade == "C":
        headline = f"{grade} · {grade_label}：部分指标需要留意，建议控制份量并搭配蔬果与蛋白质。"
    else:
        headline = f"{grade} · {grade_label}：糖、钠或脂肪等指标存在需要关注的项目，建议减少食用频率。"

    findings = [trans_finding, sugar_finding, sodium_finding, fat_finding, additive_finding, positive_finding]
    if score is not None and not has_sugar:
        headline += " 糖未标注，本次健康分的置信度较低。"

    unknown_dimensions = [item["label"] for item in dimensions if item.get("status") == "unknown"]
    score_note = (
        "缺失的营养项按中性分计入总分，不代表该项健康或安全；数据越完整，评分参考价值越高。"
        if unknown_dimensions
        else "标签营养数据较完整，评分主要基于标示值计算。"
    )

    return {
        "model_version": MODEL_VERSION,
        "score": score,
        "grade": grade,
        "grade_label": grade_label,
        "headline": headline,
        "dimensions": dimensions,
        "score_note": score_note,
        "unknown_dimensions": unknown_dimensions,
        "findings": findings,
        "additives": additive_metrics,
        "sugar": sugar_metrics,
        "trans_fat": trans_metrics,
        "sodium": {"value_mg": sodium, "nrv_percent": round(sodium / SODIUM_DAILY_LIMIT_MG * 100, 1) if sodium else None},
        "data_quality": {
            "core_present": len(core_present),
            "core_total": len(core_keys),
            "has_sugar": has_sugar,
            "has_trans_fat": has_trans,
            "ingredient_count": len(record.ingredient.ingredients) if record.ingredient else 0,
            "net_content_g": net_g,
        },
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
    }


__all__ = ["assess", "MODEL_VERSION", "DISCLAIMER"]
