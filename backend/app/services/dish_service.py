"""识饭菜：视觉模型识别菜品与重量 → 菜品营养库检索 → 按份量精准换算。"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from pathlib import Path

import requests
from flask import current_app

from ..extensions import db
from ..models import (
    HealthProfile,
    IngredientAnalysis,
    LabelCheck,
    NutritionFact,
    OcrResult,
    utcnow,
)
from ..utils.errors import APIError, ValidationError
from . import dish_library, storage
from .ocr.vision_llm import candidate_urls

logger = logging.getLogger(__name__)

# 沿用需求指定的识饭菜 System Prompt；用户消息进一步限定只返回菜名与重量。
DISH_SYSTEM_PROMPT = (
    "你是营养师，请识别图片中的菜品，估算其重量、热量及三大营养素，并给出饮食建议。返回JSON格式。"
)

DISH_USER_PROMPT = """请识别这张菜品照片，只返回以下 JSON：
{
  "dish": "西红柿炒鸡蛋",
  "estimated_weight": 200,
  "confidence": "high|medium|low"
}
要求：
1. dish 写图片中最主要、最常见的中国菜名；
2. estimated_weight 是可食用部分的估算克数，必须是数字；
3. 不需要估算热量和营养素，后端会按菜品营养库精准换算；
4. 只输出 JSON，不要输出解释文字。"""


class DishServiceError(APIError):
    def __init__(self, message: str, *, status: int = 503) -> None:
        super().__init__(message, code=50300, status=status)


def _strip_code_fence(text: str) -> str:
    raw = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if match:
        raw = match.group(1).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return raw[start : end + 1]
    return raw


def _number(value, default: float = 0) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, round(float(value), 1))
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    if not match:
        return default
    return max(0.0, round(float(match.group(0)), 1))


def _fmt(value: float) -> str:
    return f"{round(float(value), 1):g}"


def _dish_messages(health_profile: dict | None) -> list[dict]:
    profile_text = json.dumps(health_profile or {}, ensure_ascii=False)
    return [
        {"role": "system", "content": DISH_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": DISH_USER_PROMPT + f"\n【用户健康画像】{profile_text}",
                }
            ],
        },
    ]


def _vision_configured() -> bool:
    config = current_app.config
    return bool(
        str(config.get("OCR_VISION_API_KEY") or "").strip()
        and str(config.get("OCR_VISION_BASE_URL") or "").strip()
    )


def analyze_image(image_path: Path, health_profile: dict | None = None) -> dict:
    """调用视觉模型识别菜品与估算重量；未配置视觉模型时给出明确提示。"""
    if not _vision_configured():
        raise DishServiceError("识饭菜需要配置视觉模型（OCR_VISION_API_KEY / OCR_VISION_BASE_URL）")

    config = current_app.config
    suffix = image_path.suffix.lower()
    mime = ".png" if suffix == ".png" else (".webp" if suffix == ".webp" else ".jpg")
    mime = {"png": "image/png", "webp": "image/webp"}.get(mime[1:], "image/jpeg")
    try:
        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise DishServiceError("读取菜品图片失败", status=500) from exc

    messages = _dish_messages(health_profile)
    messages[1]["content"].append(
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    )
    payload = {
        "model": config.get("OCR_VISION_MODEL"),
        "temperature": 0,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {config.get('OCR_VISION_API_KEY')}",
        "Content-Type": "application/json",
    }
    timeout = config.get("OCR_TIMEOUT", 45)
    urls = candidate_urls(config.get("OCR_VISION_BASE_URL", ""))
    if not urls:
        raise DishServiceError("未配置视觉模型接口地址（OCR_VISION_BASE_URL）")

    response = None
    last_error = ""
    for url in urls:
        for extra in ({"response_format": {"type": "json_object"}}, {}):
            try:
                response = requests.post(
                    url, headers=headers, json={**payload, **extra}, timeout=timeout
                )
            except requests.Timeout as exc:
                raise DishServiceError("视觉模型识别菜品超时，请稍后重试", status=504) from exc
            except requests.RequestException as exc:
                raise DishServiceError(f"视觉模型网络请求失败：{exc.__class__.__name__}") from exc
            if response.status_code == 200:
                break
            last_error = response.text[:240]
            if (
                extra
                and response.status_code == 400
                and ("response_format" in last_error or "json_object" in last_error)
            ):
                continue
            break
        if response is not None and response.status_code == 200:
            break
        if response is not None and response.status_code in (404, 405):
            continue
        break

    if response is None or response.status_code != 200:
        detail = f"：{last_error}" if last_error else ""
        raise DishServiceError(f"视觉模型识别菜品失败{detail}")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise DishServiceError("视觉模型返回内容无法解析") from exc
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    try:
        data = json.loads(_strip_code_fence(content))
    except (json.JSONDecodeError, TypeError) as exc:
        raise DishServiceError("视觉模型没有返回可解析的菜品 JSON") from exc

    dish_name = str(data.get("dish") or data.get("dish_name") or "").strip()
    if not dish_name:
        raise DishServiceError("没有识别到菜品，请换一张俯拍、光线充足的照片")

    return {
        "dish_name": dish_name[:80],
        "estimated_weight_g": _number(
            data.get("estimated_weight")
            or data.get("estimated_weight_g")
            or data.get("weight_g")
        ),
        "confidence": str(data.get("confidence") or "medium").lower(),
    }


def format_stream_text(dish: dict) -> str:
    """生成用户最终看到的流式三行营养结果。"""
    totals = dish["totals"]
    return (
        f"识别到：{dish['dish_name']}（约{_fmt(totals['weight_g'])}克）。\n"
        "依据《中国食物成分表》：\n"
        f"🔥 总热量：{_fmt(totals['calories'])} 大卡\n"
        f"🍞 碳水：{_fmt(totals['carbs_g'])}g | "
        f"🥩 蛋白质：{_fmt(totals['protein_g'])}g | "
        f"🧈 脂肪：{_fmt(totals['fat_g'])}g\n"
        f"💡 健康建议：{dish['health_tip']}"
    )


def analyze_record(record) -> dict:
    """识饭菜：视觉识别 → 营养库匹配 → 份量换算 → 写入现有记录结构。"""
    image = record.image
    if image is None:
        raise ValidationError("这条记录没有图片，请重新上传菜品照片")

    profile_row = HealthProfile.query.filter_by(user_id=record.user_id).first()
    profile = profile_row.to_public() if profile_row else {}
    started = time.perf_counter()
    recognition = analyze_image(storage.ocr_target(image.stored_name), profile)
    duration_ms = int((time.perf_counter() - started) * 1000)

    dish = dish_library.find_dish(recognition["dish_name"])
    if dish is None:
        raise DishServiceError(
            f"菜品营养库暂未收录「{recognition['dish_name']}」，请换一张更清晰的菜品照片，"
            "或到「知识库 → 常见菜品」中查看已收录菜品。",
            status=422,
        )

    weight = recognition["estimated_weight_g"] or dish["typical_portion_g"]
    weight = max(20.0, min(2000.0, float(weight)))
    totals = dish_library.calculate(dish, weight)
    health_tip = dish["health_tip"]
    risk_notes = []
    if dish["calories_per_100g"] >= 220:
        risk_notes.append("这道菜热量密度偏高，建议控制份量并搭配清淡蔬菜。")
    if dish["fat_per_100g"] >= 15:
        risk_notes.append("脂肪含量较高，减脂期建议少蘸汤汁或只吃七成。")
    if dish["carbs_per_100g"] >= 25:
        risk_notes.append("碳水含量较高，吃了它要相应减少米饭、面条等主食。")

    dish_info = {
        **dish,
        "estimated_weight_g": totals["weight_g"],
        "totals": {
            "weight_g": totals["weight_g"],
            "calories": totals["calories"],
            "protein_g": totals["protein_g"],
            "fat_g": totals["fat_g"],
            "carbs_g": totals["carbs_g"],
        },
        "matched": True,
        "recognition_name": recognition["dish_name"],
        "confidence": recognition["confidence"],
        "source": dish_library.DISH_SOURCE,
    }

    names = [dish["dish_name"]]
    nutrition_text = (
        f"能量 {_fmt(totals['calories'])}kcal，蛋白质 {_fmt(totals['protein_g'])}g，"
        f"脂肪 {_fmt(totals['fat_g'])}g，碳水化合物 {_fmt(totals['carbs_g'])}g"
    )
    ocr = record.ocr or OcrResult(record_id=record.id)
    ocr.provider = "dish_vision"
    ocr.provider_label = "AI 菜品视觉识别 + 营养库检索"
    ocr.engine_version = str(current_app.config.get("OCR_VISION_MODEL") or "vision")
    ocr.is_demo = False
    ocr.status = "success"
    ocr.raw_text = json.dumps(
        {"recognition": recognition, "dish": dish_info}, ensure_ascii=False
    )
    ocr.corrected_text = format_stream_text(dish_info)
    ocr.fields = {
        "food_name": dish["dish_name"],
        "ingredients_text": "、".join(names),
        "nutrition_text": nutrition_text,
    }
    ocr.field_confidence = {key: recognition["confidence"] for key in ocr.fields}
    ocr.field_flags = {}
    ocr.low_confidence_fields = [] if recognition["confidence"] == "high" else ["food_name"]
    ocr.missing_fields = []
    ocr.raw_payload = {"mode": "dish", "dish": dish_info, "recognition": recognition}
    ocr.duration_ms = duration_ms
    if record.ocr is None:
        db.session.add(ocr)
        record.ocr = ocr

    ingredient_rows = [
        {
            "name": dish["dish_name"],
            "category": dish["category"],
            "role": "菜品主体",
            "purpose": "提供能量与主要营养素",
            "simple_desc": f"约 {_fmt(totals['weight_g'])}g，按菜品照片与营养库估算。",
            "explanation": "重量来自视觉估算，营养数据来自菜品营养库，实际以称重为准。",
            "confidence": recognition["confidence"],
            "evidence": "dish_library",
            "is_ai_generated": False,
            "caution": health_tip,
            "knowledge_refs": [],
        }
    ]

    tags = [
        {
            "name": "热量",
            "value": f"{_fmt(totals['calories'])}kcal",
            "status": "high" if totals["calories"] >= 700 else "medium",
            "label": "本份估算",
        },
        {
            "name": "蛋白质",
            "value": f"{_fmt(totals['protein_g'])}g",
            "status": "good" if totals["protein_g"] >= 15 else "medium",
            "label": "本份估算",
        },
        {
            "name": "碳水",
            "value": f"{_fmt(totals['carbs_g'])}g",
            "status": "high" if totals["carbs_g"] >= 60 else "medium",
            "label": "本份估算",
        },
    ]
    ingredient_row = record.ingredient or IngredientAnalysis(record_id=record.id)
    ingredient_row.mode = "ai"
    ingredient_row.model = "dish-library-rag"
    ingredient_row.prompt_version = "dish-rag-v1"
    ingredient_row.summary = health_tip
    ingredient_row.tags = tags
    ingredient_row.personalization = {
        "level": "warning" if risk_notes else "info",
        "title": "结合您的健康画像",
        "message": health_tip,
        "reasons": risk_notes,
    }
    ingredient_row.ingredients = ingredient_rows
    ingredient_row.nutrition_notes = [
        f"识别菜名：{recognition['dish_name']}；匹配菜品：{dish['dish_name']}。",
        f"每 100g 热量 {_fmt(dish['calories_per_100g'])} 大卡，本份 {_fmt(totals['weight_g'])}g。",
        "数据参考《中国食物成分表》与常见食堂做法估算，实际以称重为准。",
    ]
    ingredient_row.unknown_items = []
    ingredient_row.unconfirmed = ["菜品重量为视觉估算值"]
    ingredient_row.citations = []
    ingredient_row.disclaimer = "识饭菜结果由视觉模型估算重量并检索菜品营养库生成，不构成医学诊断。"
    ingredient_row.raw_response = {"dish": dish_info, "recognition": recognition}
    ingredient_row.duration_ms = duration_ms
    ingredient_row.diff = {
        "ingredient_count": 1,
        "unknown_count": 0,
        "uncertain_count": len(risk_notes),
    }
    if record.ingredient is None:
        db.session.add(ingredient_row)
        record.ingredient = ingredient_row

    nutrition_row = record.nutrition or NutritionFact(record_id=record.id)
    nutrition_row.basis = "per_serving"
    nutrition_row.basis_note = f"约 {_fmt(totals['weight_g'])}g/份（视觉估算）"
    nutrition_row.source = "dish_library"
    nutrition_row.items = [
        {
            "key": "energy",
            "name": "能量",
            "value": totals["calories"],
            "unit": "kcal",
            "nrv_percent": None,
        },
        {
            "key": "protein",
            "name": "蛋白质",
            "value": totals["protein_g"],
            "unit": "g",
            "nrv_percent": None,
        },
        {
            "key": "fat",
            "name": "脂肪",
            "value": totals["fat_g"],
            "unit": "g",
            "nrv_percent": None,
        },
        {
            "key": "carbohydrate",
            "name": "碳水化合物",
            "value": totals["carbs_g"],
            "unit": "g",
            "nrv_percent": None,
        },
    ]
    nutrition_row.warnings = risk_notes
    if record.nutrition is None:
        db.session.add(nutrition_row)
        record.nutrition = nutrition_row

    check_items = [
        {
            "rule_id": "dish-library",
            "level": "pass",
            "title": "已匹配菜品营养库",
            "message": f"匹配到「{dish['dish_name']}」，按每 100g 数据与估算克数换算。",
            "basis": dish_library.DISH_SOURCE,
            "category": "识饭菜",
        },
        {
            "rule_id": "dish-estimation",
            "level": "review",
            "title": "份量为视觉估算值",
            "message": "照片无法精确称重，实际热量会因油量、份量与做法变化。",
            "basis": "视觉估算",
            "category": "识饭菜",
        },
    ]
    check_items.extend(
        {
            "rule_id": f"dish-risk-{index + 1}",
            "level": "review",
            "title": "饮食风险提示",
            "message": note,
            "basis": "AI 营养师建议",
            "category": "识饭菜",
        }
        for index, note in enumerate(risk_notes)
    )
    check_row = record.check or LabelCheck(record_id=record.id)
    check_row.ruleset_version = "dish-rag-v1"
    check_row.overall = "needs_review"
    check_row.items = check_items
    check_row.counts = {
        "pass": 1,
        "review": len(check_items) - 1,
        "suspected": 0,
    }
    check_row.coverage = {"checked": 1, "total": 1}
    if record.check is None:
        db.session.add(check_row)
        record.check = check_row

    record.food_name = dish["dish_name"][:120]
    record.ocr_provider = "dish_vision"
    record.status = "analyzed"
    record.analysis_mode = "ai"
    record.overall_check = "needs_review"
    record.summary = f"需要进一步核实｜{health_tip}"[:280]
    record.analyzed_at = utcnow()
    record.is_demo = False

    if record.report is not None:
        db.session.delete(record.report)
        record.report = None

    db.session.commit()
    return {
        "record_id": record.id,
        "status": record.status,
        "analysis_mode": record.analysis_mode,
        "overall": record.overall_check,
        "counts": check_row.counts,
        "ingredient_count": len(ingredient_rows),
        "errors": [],
        "dish": dish_info,
        "stream_text": format_stream_text(dish_info),
    }