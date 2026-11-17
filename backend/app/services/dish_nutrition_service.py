"""菜品营养数据自动估算：保存/发布菜品时由后端无感调用大模型。"""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from ..models import KnowledgeEntry
from . import ai_service

logger = logging.getLogger(__name__)

NUTRITION_FIELDS = (
    "calories_per_100g",
    "carbs_per_100g",
    "protein_per_100g",
    "fat_per_100g",
)

DEFAULT_PORTION_G = 200

VEGETABLE_HINTS = (
    "黄瓜", "西兰花", "青菜", "生菜", "菠菜", "白菜", "萝卜", "番茄",
    "茄子", "菌", "菇", "笋", "豆角", "芹菜", "冬瓜", "丝瓜", "苦瓜",
    "南瓜", "木耳", "海带", "藕", "菜", "瓜",
)
MEAT_HINTS = (
    "鸡", "猪", "牛", "羊", "鸭", "鱼", "虾", "蟹", "肉", "排骨",
    "狮子头", "培根", "香肠",
)
HIGH_FAT_HINTS = (
    "红烧", "炖肉", "油炸", "佛跳墙", "扣肉", "肘子", "猪蹄",
    "排骨", "牛腩", "五花", "鸭", "鹅", "奶油", "芝士", "黄油",
)
STAPLE_HINTS = ("饭", "面", "粉", "饼", "馒头", "粥", "土豆", "红薯")


def _as_number(value, *, minimum: float, maximum: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number or number < minimum or number > maximum:
        return None
    return round(number, 1)


def _missing_fields(entry: KnowledgeEntry) -> list[str]:
    missing = []
    for field in NUTRITION_FIELDS:
        value = getattr(entry, field, 0) or 0
        if float(value) <= 0:
            missing.append(field)
    if not getattr(entry, "typical_portion_g", 0):
        missing.append("typical_portion_g")
    return missing


def _build_prompt(entry: KnowledgeEntry) -> str:
    description = (entry.summary or "").strip()
    content = (entry.content or "").strip()
    context = description or content or "无额外描述"

    return f"""你是一名严谨的中国注册营养师。请严格按《中国食物成分表》的常见基准数据估算菜品，禁止凭空编造。

菜品名称：{entry.title}
菜品描述：{context}

必须按以下顺序推理：

第一步：拆解食材和调料
先列出这道菜的核心食材、调味料及其可食重量（g）。例如：
拍黄瓜 = 黄瓜 250g + 香油 5g + 生抽 5g + 白糖 2g + 蒜 3g。
如果是炒菜，要单独列出食用油；如果是肉类，要列出肉的实际重量。

第二步：对标食物成分表
每 100g 可食部参考值（允许按常见品种小幅调整，但不能偏离常识）：
- 黄瓜：16 kcal，碳水 2.9g，蛋白质 0.8g，脂肪 0.2g
- 西兰花：36 kcal，碳水 4.3g，蛋白质 4.1g，脂肪 0.6g
- 番茄：15 kcal，碳水 3.3g，蛋白质 0.9g，脂肪 0.2g
- 土豆：81 kcal，碳水 17.8g，蛋白质 2.6g，脂肪 0.2g
- 鸡胸肉：133 kcal，碳水 2.5g，蛋白质 19.4g，脂肪 5.0g
- 猪五花肉：568 kcal，碳水 2.4g，蛋白质 9.3g，脂肪 59.0g
- 米饭：116 kcal，碳水 25.9g，蛋白质 2.6g，脂肪 0.3g
- 香油：898 kcal，碳水 0.2g，蛋白质 0g，脂肪 99.7g
- 生抽：63 kcal，碳水 5.6g，蛋白质 5.6g，脂肪 0.1g
- 白糖：400 kcal，碳水 99.9g，蛋白质 0g，脂肪 0g
- 猪蹄：260 kcal，碳水 0g，蛋白质 22.6g，脂肪 18.8g
- 带皮鸡腿肉：181 kcal，碳水 0g，蛋白质 16.0g，脂肪 13.0g
- 火腿：330 kcal，碳水 0g，蛋白质 16.0g，脂肪 28.0g
- 猪骨高汤（带油）：50 kcal，碳水 0g，蛋白质 3.0g，脂肪 4.0g
- 花生油/食用油：900 kcal，碳水 0g，蛋白质 0g，脂肪 99.9g

第三步：加权计算
按“每种食材重量 / 100 × 该食材每100g营养值”求整份总量，再除以成品总重量，换算成每 100g。
不要先猜一个每 100g 数字，再倒推营养素。

第四步：合理性自检
- 拍黄瓜、清炒西兰花等蔬菜类，通常低于 50 kcal/100g；叶菜、瓜类多在 15-40 kcal。
- 蔬菜菜品的碳水占能量比例不应畸高；如果碳水异常高，优先检查是否把糖或主食算多了。
- 肉类菜品热量通常高于 80 kcal/100g，蛋白质应明显高于蔬菜。
- 红烧、炖肉、油炸、佛跳墙、扣肉、肘子、猪蹄、排骨、牛腩、鸭鹅、奶油/芝士类菜品，属于高脂高蛋白菜品，脂肪不得低于 15g/100g，热量通常不得低于 150 kcal/100g；如果算出来低于这些边界，必须重新检查是否漏掉猪蹄、肥肉、带皮肉、浓汤、油或糖。
- 佛跳墙必须拆解猪蹄/老母鸡/火腿/高汤/鲍鱼/花胶等核心高热量食材，不能只按清汤蔬菜估算。
- 热量必须约等于 4×碳水 + 4×蛋白质 + 9×脂肪（允许 ±20% 误差）。
- 任何一项不符合常识时，返回修正后的结果，而不是保留错误结果。

第五步：返回严格 JSON，不要输出 Markdown、解释或代码块：
{{
  "ingredients": [
    {{
      "name": "黄瓜",
      "grams": 250,
      "calories_per_100g": 16,
      "carbs_per_100g": 2.9,
      "protein_per_100g": 0.8,
      "fat_per_100g": 0.2
    }}
  ],
  "calories_per_100g": 0,
  "carbs_per_100g": 0,
  "protein_per_100g": 0,
  "fat_per_100g": 0,
  "typical_portion_g": 200
}}"""


def _estimate(entry: KnowledgeEntry) -> dict:
    raw = ai_service._call_llm(
        [
            {
                "role": "system",
                "content": (
                    "你是严谨的中国注册营养师。必须先拆解食材，"
                    "再按中国食物成分表加权计算，只输出 JSON 对象。"
                ),
            },
            {"role": "user", "content": _build_prompt(entry)},
        ]
    )

    print(
        f"[nutrition-ai] entry={getattr(entry, 'title', '')} "
        f"raw={raw[:2000]}",
        flush=True,
    )
    logger.info(
        "nutrition AI raw response for %s: %s",
        getattr(entry, "title", ""),
        raw,
    )

    data = json.loads(ai_service._strip_code_fence(raw))
    if not isinstance(data, dict):
        raise ValueError("AI 未返回 JSON 对象")
    return data


def _normalize_from_ingredients(data: dict) -> dict:
    """当模型的总营养字段为 0 时，用食材明细加权回算。"""
    ingredients = data.get("ingredients")
    if not isinstance(ingredients, list) or not ingredients:
        return data

    total_weight = 0.0
    totals = {
        "calories_per_100g": 0.0,
        "carbs_per_100g": 0.0,
        "protein_per_100g": 0.0,
        "fat_per_100g": 0.0,
    }

    for item in ingredients:
        if not isinstance(item, dict):
            continue
        grams = _as_number(item.get("grams"), minimum=1, maximum=5000)
        if grams is None:
            continue
        total_weight += grams
        for field in totals:
            per100 = _as_number(
                item.get(field),
                minimum=0,
                maximum=1000 if field == "calories_per_100g" else 100,
            )
            if per100 is not None:
                totals[field] += per100 * grams / 100

    if total_weight <= 0:
        return data

    derived = {
        field: round(value / total_weight * 100, 1)
        for field, value in totals.items()
    }

    normalized = dict(data)
    for field, value in derived.items():
        current = _as_number(
            normalized.get(field),
            minimum=0,
            maximum=1000 if field == "calories_per_100g" else 100,
        )
        if current is None or current <= 0:
            normalized[field] = value

    return normalized


def _apply_common_sense_bounds(
    data: dict,
    entry: KnowledgeEntry,
) -> dict:
    """给红烧、炖肉、油炸、佛跳墙等菜品加脂肪下限，防止明显失真。"""
    title = entry.title or ""
    if not any(word in title for word in HIGH_FAT_HINTS):
        return data

    fat = _as_number(data.get("fat_per_100g"), minimum=0, maximum=100)
    carbs = _as_number(data.get("carbs_per_100g"), minimum=0, maximum=100)
    protein = _as_number(data.get("protein_per_100g"), minimum=0, maximum=100)
    calories = _as_number(data.get("calories_per_100g"), minimum=1, maximum=1000)

    if fat is None or fat < 15:
        fat = 15.0

    minimum_calories = 4 * (carbs or 0) + 4 * (protein or 0) + 9 * fat
    if calories is None or calories < 150:
        calories = round(max(150.0, minimum_calories), 1)
    else:
        calories = round(max(calories, minimum_calories), 1)

    normalized = dict(data)
    normalized["fat_per_100g"] = fat
    normalized["calories_per_100g"] = min(calories, 1000.0)
    return normalized


def _validate_result(data: dict, entry: KnowledgeEntry) -> str | None:
    calories = _as_number(data.get("calories_per_100g"), minimum=1, maximum=1000)
    carbs = _as_number(data.get("carbs_per_100g"), minimum=0, maximum=100)
    protein = _as_number(data.get("protein_per_100g"), minimum=0, maximum=100)
    fat = _as_number(data.get("fat_per_100g"), minimum=0, maximum=100)

    if None in (calories, carbs, protein, fat):
        return "营养字段缺失或超出合理范围"

    calculated = carbs * 4 + protein * 4 + fat * 9
    tolerance = max(18, calories * 0.25)
    if abs(calculated - calories) > tolerance:
        return "热量与三大营养素折算不一致"

    ingredients = data.get("ingredients")
    if not isinstance(ingredients, list) or not ingredients:
        return "AI 未提供食材拆解"

    title = entry.title or ""
    if any(word in title for word in VEGETABLE_HINTS):
        if calories > 70:
            return "蔬菜类热量明显偏高"
        if carbs > 25:
            return "蔬菜类碳水明显偏高"

    if any(word in title for word in MEAT_HINTS):
        if calories < 60:
            return "肉类菜品热量明显偏低"
        if protein < 4:
            return "肉类菜品蛋白质明显偏低"

    if any(word in title for word in HIGH_FAT_HINTS):
        if fat < 15:
            return "高脂菜品脂肪估算明显偏低"
        if calories < 150:
            return "高脂菜品热量估算明显偏低"

    if any(word in title for word in STAPLE_HINTS) and carbs < 8:
        return "主食类碳水明显偏低"

    return None


def auto_fill_dish_nutrition(entry: KnowledgeEntry) -> dict:
    """补齐菜品缺失的营养字段，失败时保留默认 0，不阻断保存。"""
    status = {
        "status": "skipped",
        "message": "",
        "filled_fields": [],
    }

    # 只有菜品和常见配料需要营养测算；添加剂/术语/科普一律跳过
    if entry.category not in {"dish", "ingredient"}:
        status.update(
            status="skipped",
            message="该分类不需要营养测算",
        )
        entry._nutrition_ai = status
        logger.info(
            "[nutrition] skip category=%s title=%s",
            entry.category,
            getattr(entry, "title", ""),
        )
        return status

    missing = _missing_fields(entry)
    if not missing:
        entry._nutrition_ai = status
        return status

    def apply_defaults() -> None:
        for field in NUTRITION_FIELDS:
            if float(getattr(entry, field, 0) or 0) <= 0:
                setattr(entry, field, 0.0)
        if not getattr(entry, "typical_portion_g", 0):
            entry.typical_portion_g = DEFAULT_PORTION_G

    if not ai_service.ai_configured():
        apply_defaults()
        status.update(
            status="failed",
            message="未配置大模型 API Key，营养数据暂用默认值，请手动补充",
        )
        entry._nutrition_ai = status
        return status

    try:
        data = _estimate(entry)
        data = _normalize_from_ingredients(data)
        data = _apply_common_sense_bounds(data, entry)
    except Exception as exc:
        logger.warning("菜品营养自动估算失败：%s", exc)
        apply_defaults()
        status.update(
            status="failed",
            message="AI 测算失败，请手动补充营养数据",
        )
        entry._nutrition_ai = status
        return status

    validation_error = _validate_result(data, entry)
    if validation_error:
        logger.warning("菜品营养结果未通过校验：%s（%s）", validation_error, entry.title)
        apply_defaults()
        status.update(
            status="failed",
            message=f"{validation_error}，请手动补充营养数据",
            validation_error=validation_error,
        )
        entry._nutrition_ai = status
        return status

    filled: list[str] = []

    for field in NUTRITION_FIELDS:
        if field not in missing:
            continue
        value = _as_number(
            data.get(field),
            minimum=1 if field == "calories_per_100g" else 0.01,
            maximum=1000 if field == "calories_per_100g" else 100,
        )
        if value is None:
            continue
        setattr(entry, field, value)
        filled.append(field)

    if "typical_portion_g" in missing:
        portion = _as_number(
            data.get("typical_portion_g"),
            minimum=20,
            maximum=2000,
        )
        if portion is not None:
            entry.typical_portion_g = int(round(portion))
            filled.append("typical_portion_g")
        else:
            entry.typical_portion_g = DEFAULT_PORTION_G

    apply_defaults()

    if filled:
        status.update(
            status="success",
            message="AI 已自动补全菜品营养数据",
            filled_fields=filled,
            ingredients=data.get("ingredients") or [],
        )
    else:
        status.update(
            status="failed",
            message="AI 测算失败，请手动补充营养数据",
        )

    entry._nutrition_ai = status
    return status


def estimate_dish_nutrition(title: str, summary: str = "", content: str = "") -> dict:
    """根据标题/描述测算营养数据，但不写入数据库（用于后台一键测算）。"""
    entry = SimpleNamespace(
        category="dish",
        title=title,
        summary=summary,
        content=content,
        calories_per_100g=0.0,
        carbs_per_100g=0.0,
        protein_per_100g=0.0,
        fat_per_100g=0.0,
        typical_portion_g=0,
    )

    result = auto_fill_dish_nutrition(entry)

    return {
        **result,
        "calories_per_100g": round(float(getattr(entry, "calories_per_100g", 0) or 0), 1),
        "carbs_per_100g": round(float(getattr(entry, "carbs_per_100g", 0) or 0), 1),
        "protein_per_100g": round(float(getattr(entry, "protein_per_100g", 0) or 0), 1),
        "fat_per_100g": round(float(getattr(entry, "fat_per_100g", 0) or 0), 1),
        "typical_portion_g": int(getattr(entry, "typical_portion_g", 0) or 200),
    }


def summarize_knowledge_content(title: str, content: str) -> str:
    """把知识正文压缩成 50 字以内的通俗结论，用于摘要。"""
    text = (content or "").strip()
    if len(text) < 10:
        raise ValueError("内容正文太短，无法生成摘要")

    raw = ai_service._call_llm(
        [
            {
                "role": "system",
                "content": (
                    "你是严谨的中文食品营养编辑。"
                    "只输出一句适合放在卡片上的摘要，不要 Markdown，不要引号。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"标题：{title or '未命名知识'}\n"
                    f"正文：{text[:6000]}\n\n"
                    "请用通俗、具体、可执行的大白话总结核心结论，"
                    "必须控制在 50 个汉字以内；不要重复标题，不要空泛套话。"
                ),
            },
        ]
    )

    summary = ai_service._strip_code_fence(raw).strip().strip('"“”\'')
    summary = " ".join(summary.split())
    if len(summary) > 50:
        summary = summary[:50].rstrip("，。；;,. ")
    if not summary:
        raise ValueError("AI 未返回有效摘要")
    print(f"[summary-ai] title={title} raw={raw[:500]} summary={summary}", flush=True)
    return summary


def summary_needs_improvement(summary: str | None, title: str) -> bool:
    text = (summary or "").strip()
    name = (title or "").strip()
    if not text:
        return True
    if text == name:
        return True
    if len(text) < 12:
        return True
    return False


def ensure_dish_summary(entry) -> str | None:
    """摘要为空、过短或只是重复菜名时，生成一条健康建议。"""
    title = getattr(entry, "title", "") or ""
    if not summary_needs_improvement(getattr(entry, "summary", ""), title):
        return getattr(entry, "summary", "")

    context = (
        getattr(entry, "content", "")
        or getattr(entry, "summary", "")
        or "无额外描述"
    ).strip()

    nutrition = (
        f"热量 {getattr(entry, 'calories_per_100g', 0) or 0} kcal/100g，"
        f"蛋白质 {getattr(entry, 'protein_per_100g', 0) or 0}g，"
        f"脂肪 {getattr(entry, 'fat_per_100g', 0) or 0}g，"
        f"碳水 {getattr(entry, 'carbs_per_100g', 0) or 0}g"
    )

    try:
        raw = ai_service._call_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的中国注册营养师。"
                        "只输出一句面向普通消费者的健康食用建议，"
                        "不要 Markdown，不要引号。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"菜品：{title}\n"
                        f"描述：{context[:3000]}\n"
                        f"每100g营养估算：{nutrition}\n\n"
                        "写一句 30-80 字的健康建议，必须提到具体食用方式、"
                        "适合或需要控制的人群（如高血压、减脂、胃炎），"
                        "不能只重复菜名，不能空泛。"
                    ),
                },
            ]
        )

        print(
            f"[summary-fallback] entry={title} raw={raw[:800]}",
            flush=True,
        )

        summary = ai_service._strip_code_fence(raw).strip().strip('"“”\'')
        summary = " ".join(summary.split())
        if len(summary) > 100:
            summary = summary[:100].rstrip("，。；;,. ")

        if len(summary) >= 12 and summary != title:
            entry.summary = summary
            return summary
    except Exception as exc:
        logger.warning("菜品摘要兜底生成失败：%s", exc)

    return getattr(entry, "summary", "") or None
