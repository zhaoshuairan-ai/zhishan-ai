"""分析流水线：字段 → 配料/营养解析 → 知识匹配 → AI/规则解读 → 规则核查 → 入库。"""
from __future__ import annotations

import logging

from flask import current_app
from sqlalchemy import select

from ..extensions import db
from ..models import (
    AnalysisRecord,
    HealthProfile,
    IngredientAnalysis,
    KnowledgeEntry,
    LabelCheck,
    NutritionFact,
    OcrResult,
    ReportMeta,
    utcnow,
)
from ..utils.errors import APIError, ValidationError
from . import ai_service, checker, health_service, knowledge_service, nutrition_parser
from .field_parser import build_corrected_text, parse_fields
from .ingredient_parser import parse_ingredients

logger = logging.getLogger(__name__)

GLOBAL_DISCLAIMER = (
    "本平台仅对食品包装上可见的文字做识别、理解与逻辑一致性核查，"
    "不进行任何实验室检测，不能判断食品是否安全、是否受污染或是否符合官方合规要求。"
)


def save_ocr(record: AnalysisRecord, output, parsed: dict) -> OcrResult:
    """保存 OCR 原始结果（同一记录重复识别时覆盖）。"""
    ocr = record.ocr
    if ocr is None:
        ocr = OcrResult(record_id=record.id)
        db.session.add(ocr)
        record.ocr = ocr
    ocr.provider = output.provider
    ocr.provider_label = output.provider_label
    ocr.engine_version = output.engine_version
    ocr.is_demo = bool(output.is_demo)
    ocr.raw_text = output.raw_text
    if not ocr.corrected_text:
        ocr.corrected_text = build_corrected_text(parsed["fields"])
    ocr.fields = parsed["fields"]
    ocr.field_confidence = parsed["confidence"]
    ocr.field_flags = parsed["flags"]
    ocr.low_confidence_fields = parsed["low_confidence"]
    ocr.missing_fields = parsed["missing"]
    ocr.raw_payload = {
        **(output.raw_payload or {}),
        "lines": [{"text": line.text, "confidence": round(line.confidence, 3)} for line in output.lines],
        "warning": output.warning,
    }
    ocr.duration_ms = output.duration_ms
    found = len([v for v in parsed["fields"].values() if str(v).strip()])
    ocr.status = "success" if found >= 4 else ("partial" if found >= 1 else "failed")
    if output.is_demo:
        record.is_demo = True
    record.ocr_provider = output.provider
    if not record.food_name:
        record.food_name = normalize_food_name((parsed["fields"].get("food_name") or "").strip())
    record.status = "ocr_done"
    db.session.commit()
    return ocr


def apply_correction(record: AnalysisRecord, fields: dict, *, note: str | None = None) -> OcrResult:
    """用户校正识别结果；同时保留原始 OCR 文本。"""
    ocr = record.ocr
    if ocr is None:
        raise APIError("该记录还没有识别结果，请先执行文字识别", code=40400, status=404)
    current = dict(ocr.fields or {})
    changed = []
    for key, value in fields.items():
        if key not in current and key not in {
            "food_name",
            "ingredients_text",
            "nutrition_text",
            "net_content",
            "production_date",
            "shelf_life",
            "expiry_date",
            "storage",
            "producer",
            "standard_no",
            "allergen",
        }:
            continue
        text = "" if value is None else str(value).strip()
        if text != str(current.get(key, "")).strip():
            changed.append(key)
        current[key] = text
    if not changed:
        return ocr

    # 校正后的字段需要重新计算置信度与标记
    confidence = dict(ocr.field_confidence or {})
    flags = dict(ocr.field_flags or {})
    for key in changed:
        value = current.get(key) or ""
        confidence[key] = 1.0 if value else 0.0
        flags[key] = {"status": "ok" if value else "missing", "note": "用户人工校正" if value else "用户清空"}
    ocr.fields = current
    ocr.field_confidence = confidence
    ocr.field_flags = flags
    ocr.missing_fields = [k for k, v in current.items() if not str(v).strip()]
    ocr.low_confidence_fields = [k for k, v in confidence.items() if 0 < float(v) < 0.8]
    ocr.corrected_text = build_corrected_text(current)
    ocr.corrected_at = utcnow()
    if note is not None:
        record.note = note
    record.food_name = (current.get("food_name") or "").strip()[:120] or record.food_name
    record.status = "corrected" if record.status != "analyzed" else record.status
    db.session.commit()
    logger.info("记录 %s 校正字段：%s", record.id, ",".join(changed))
    return ocr


def analyze(record: AnalysisRecord, *, retry: bool = False) -> dict:
    """执行完整分析并落库。返回分析摘要。"""
    ocr = record.ocr
    if ocr is None:
        raise APIError("该记录还没有识别结果，请先完成 OCR 识别", code=40400, status=404)
    fields = dict(ocr.fields or {})
    if not (fields.get("ingredients_text") or "").strip() and not (fields.get("nutrition_text") or "").strip():
        raise ValidationError(
            "配料表与营养成分表均为空，无法分析。请在校正页填写配料表，或重新上传更清晰的照片。",
            details={"missing": ["ingredients_text", "nutrition_text"]},
        )

    ingredient_parsed = parse_ingredients(fields.get("ingredients_text") or "")
    nutrition_parsed = nutrition_parser.parse_nutrition(fields.get("nutrition_text") or "")

    names = [item["name"] for item in ingredient_parsed["items"] if not item.get("is_category")]
    profile_row = HealthProfile.query.filter_by(user_id=record.user_id).first()
    health_profile = profile_row.to_public() if profile_row else {}
    knowledge_map = knowledge_service.match_names(names)
    knowledge_hits: list[dict] = []
    for name, hits in knowledge_map.items():
        for hit in hits:
            knowledge_hits.append({**hit, "ingredient": name})

    mode = ai_service.resolve_mode()
    errors: list[str] = []
    ai_result: dict | None = None
    if mode == "ai":
        try:
            ai_result = ai_service.run_ai_analysis(
                food_name=record.food_name or fields.get("food_name") or "",
                ingredients_text=fields.get("ingredients_text") or "",
                ingredient_items=ingredient_parsed["items"],
                nutrition=nutrition_parsed,
                knowledge_hits=knowledge_hits,
                health_profile=health_profile,
            )
        except ai_service.AIServiceError as exc:
            logger.warning("AI 分析失败，降级为规则模式：%s", exc.message)
            errors.append(exc.message)
            mode = "rule"
    if ai_result is None:
        reason = "；".join(errors) if errors else None
        rule_note = None
        if not ai_service.ai_configured():
            rule_note = "未配置大模型 API Key（AI_API_KEY），当前使用基础规则模式"
        elif current_app.config.get("AI_PROVIDER") == "rule":
            rule_note = "AI_PROVIDER=rule，已按配置使用基础规则模式"
        ai_result = ai_service.run_rule_analysis(
            food_name=record.food_name or fields.get("food_name") or "",
            ingredient_items=ingredient_parsed["items"],
            nutrition=nutrition_parsed,
            knowledge_hits=knowledge_hits,
            reason=reason or rule_note,
            health_profile=health_profile,
        )
        if errors:
            ai_result["unconfirmed"].append(f"大模型调用失败，已自动降级为基础规则模式：{errors[0]}")

    # 把知识库命中信息挂到每个配料解释上（便于溯源）
    hits_by_name: dict[str, list[dict]] = {}
    for hit in knowledge_hits:
        hits_by_name.setdefault(hit["ingredient"], []).append(hit)
    for explain in ai_result["ingredients"]:
        hits = hits_by_name.get(explain["name"], [])
        local_entry = db.session.get(KnowledgeEntry, hits[0]["id"]) if hits else None
        if local_entry is not None:
            # 本地库优先：直接复用知识库摘要；待核验的 AI 词条也复用，避免重复消耗 Token
            explain["simple_desc"] = (local_entry.summary or explain.get("simple_desc") or "")[:120]
            explain["explanation"] = (local_entry.content or local_entry.summary or explain.get("explanation") or "")[:500]
            explain["evidence"] = "knowledge_base"
            explain["is_ai_generated"] = bool(local_entry.is_ai_generated)
        elif ai_result.get("mode") == "ai":
            explain["is_ai_generated"] = True
            # 没命中本地库：后台异步沉淀为“待核验”，不阻塞本次分析返回
            knowledge_service.enqueue_ai_entry(
                explain["name"],
                explain.get("simple_desc") or explain.get("purpose") or explain.get("explanation") or "",
                explain.get("explanation") or "",
            )
        else:
            explain["is_ai_generated"] = False
        explain["knowledge_refs"] = [
            {
                "id": h["id"],
                "title": h["title"],
                "source_name": h["source_name"],
                "source_url": h["source_url"],
                "verification_status": h["verification_status"],
                "match_score": h.get("match_score"),
            }
            for h in hits
        ]

    if is_water_only(ingredient_parsed):
        ai_result = apply_water_notice(ai_result)

    check_result = checker.run_checks(
        fields=fields,
        confidence=ocr.field_confidence or {},
        flags=ocr.field_flags or {},
        ingredients=ingredient_parsed,
        nutrition=nutrition_parsed,
        analysis_mode=ai_result["mode"],
        is_demo=bool(ocr.is_demo),
    )

    # ---------- 落库 ----------
    ingredient_row = record.ingredient or IngredientAnalysis(record_id=record.id)
    ingredient_row.mode = ai_result["mode"]
    ingredient_row.model = ai_result.get("model")
    ingredient_row.prompt_version = ai_result.get("prompt_version") or ""
    ingredient_row.summary = ai_result["summary"]
    ingredient_row.tags = ai_result.get("tags", [])
    ingredient_row.personalization = ai_result.get("personalization")
    ingredient_row.ingredients = ai_result["ingredients"]
    ingredient_row.nutrition_notes = ai_result.get("nutrition_notes", [])
    ingredient_row.unknown_items = ai_result.get("unknown_items", [])
    ingredient_row.unconfirmed = ai_result.get("unconfirmed", [])
    ingredient_row.citations = ai_result.get("citations", [])
    ingredient_row.disclaimer = ai_result.get("disclaimer") or ai_service.DISCLAIMER
    ingredient_row.error = ai_result.get("error")
    ingredient_row.raw_response = ai_result.get("raw_response")
    ingredient_row.duration_ms = ai_result.get("duration_ms") or 0
    ingredient_row.diff = {
        "ingredient_count": ingredient_parsed["count"],
        "unknown_count": len(ai_result.get("unknown_items", [])),
        "uncertain_count": len(ai_result.get("unconfirmed", [])),
    }
    if record.ingredient is None:
        db.session.add(ingredient_row)
        record.ingredient = ingredient_row

    nutrition_row = record.nutrition or NutritionFact(record_id=record.id)
    nutrition_row.basis = nutrition_parsed["basis"]
    nutrition_row.basis_note = str(nutrition_parsed.get("basis_note") or "")
    nutrition_row.source = "ocr" if (fields.get("nutrition_text") or "").strip() else "manual"
    nutrition_row.items = nutrition_parsed["items"]
    nutrition_row.warnings = nutrition_parsed["warnings"]
    if record.nutrition is None:
        db.session.add(nutrition_row)
        record.nutrition = nutrition_row

    check_row = record.check or LabelCheck(record_id=record.id)
    check_row.ruleset_version = check_result["ruleset_version"]
    check_row.overall = check_result["overall"]
    check_row.items = check_result["items"]
    check_row.counts = check_result["counts"]
    check_row.coverage = check_result["coverage"]
    if record.check is None:
        db.session.add(check_row)
        record.check = check_row

    # 无标题记录用食品名称补齐
    if not record.food_name and fields.get("food_name"):
        record.food_name = normalize_food_name(fields["food_name"])
    record.status = "analyzed"
    record.analysis_mode = ai_result["mode"]
    record.overall_check = check_result["overall"]
    record.summary = check_result["overall_label"] + "｜" + _summary_line(check_result)
    record.analyzed_at = utcnow()
    record.is_demo = bool(record.is_demo or ocr.is_demo)

    # 记录变化后旧的报告失效，下次访问会重新生成
    stale_report = record.report
    if stale_report is not None:
        db.session.delete(stale_report)
        record.report = None

    db.session.commit()
    return {
        "record_id": record.id,
        "status": record.status,
        "analysis_mode": record.analysis_mode,
        "overall": record.overall_check,
        "counts": check_result["counts"],
        "ingredient_count": ingredient_parsed["count"],
        "errors": errors,
    }


WATER_ONLY_NOTICE = "这是纯净水，0卡0脂，无需评估"
MARKETING_NAME_MARKERS = ("#", "您", "新鲜养自己", "养自己", "元气", "唤醒", "轻负担", "宠粉", "种草", "打卡")
FOOD_NAME_HINTS = (
    "饼干", "面包", "饮料", "水", "牛奶", "酸奶", "茶", "咖啡", "薯片", "糖果", "巧克力",
    "方便面", "酱油", "醋", "零食", "食品", "坚果", "果冻", "罐头", "肉", "鱼", "肠", "酱",
    "粉", "油", "糖", "盐", "乳", "汁", "酒", "豆",
)


def normalize_food_name(name: str) -> str:
    """去掉营销口号；无法判断真实品类时使用统一占位名。"""
    text = (name or "").strip()
    if not text:
        return ""
    if text.startswith("#") or any(marker in text for marker in MARKETING_NAME_MARKERS):
        if not any(hint in text for hint in FOOD_NAME_HINTS):
            return "[待完善] 某品牌食品"
    if len(text) > 24 and not any(hint in text for hint in FOOD_NAME_HINTS):
        return "[待完善] 某品牌食品"
    return text[:120]


def is_water_only(ingredient_parsed: dict) -> bool:
    names = [str(item.get("name") or "").strip() for item in ingredient_parsed.get("items") or []]
    names = [name for name in names if name and not name.startswith("类别")]
    return bool(names) and all(name in {"水", "饮用水", "纯净水", "矿泉水"} for name in names)


def apply_water_notice(result: dict) -> dict:
    result["summary"] = WATER_ONLY_NOTICE
    result["tags"] = [
        {"name": "能量", "value": "0 kcal", "status": "good", "label": "0卡"},
        {"name": "脂肪", "value": "0 g", "status": "good", "label": "0脂"},
        {"name": "添加", "value": "0", "status": "good", "label": "无添加"},
    ]
    result["nutrition_notes"] = []
    result["unknown_items"] = []
    result["unconfirmed"] = []
    result["water_only"] = True
    return result


def _summary_line(check_result: dict) -> str:
    counts = check_result["counts"]
    parts = []
    if counts.get("suspected"):
        parts.append(f"疑似问题 {counts['suspected']} 项")
    if counts.get("review"):
        parts.append(f"待核实 {counts['review']} 项")
    if counts.get("info"):
        parts.append(f"提示 {counts['info']} 项")
    if counts.get("pass"):
        parts.append(f"通过 {counts['pass']} 项")
    return "、".join(parts) if parts else "无核查结果"


def build_detail(record: AnalysisRecord) -> dict:
    """结果页 / 报告页共用的完整数据。"""
    detail = {
        "record": record.to_summary(),
        "ocr": record.ocr.to_public() if record.ocr else None,
        "ingredient": (record.ingredient.to_public() if record.ingredient else None),
        "nutrition": (record.nutrition.to_public() if record.nutrition else None),
        "check": (record.check.to_public() if record.check else None),
        "report": record.report.to_public() if record.report else None,
        "health": health_service.assess(record) if record.nutrition else None,
        "meta": {
            "disclaimer": GLOBAL_DISCLAIMER,
            "ruleset_version": current_app.config.get("RULESET_VERSION"),
            "is_demo": bool(record.is_demo),
            "generated_at": utcnow().isoformat() + "Z",
        },
    }
    if record.ocr and record.ocr.is_demo:
        detail["meta"]["demo_notice"] = (
            "本次 OCR 使用了内置演示样例文字，不是对上传图片的真实识别。"
        )
    if record.ingredient and record.ingredient.mode == "rule":
        detail["meta"]["mode_notice"] = "本次配料解读由本地规则引擎生成，未调用大模型。"
    return detail


def ensure_report(record: AnalysisRecord) -> ReportMeta:
    from ..models.report import generate_report_no
    import hashlib
    import json

    report = record.report
    payload_hash = hashlib.sha256(
        json.dumps(
            {
                "record": record.to_summary(),
                "ocr": record.ocr.corrected_text if record.ocr else "",
                "ingredient": record.ingredient.ingredients if record.ingredient else [],
                "check": record.check.items if record.check else [],
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    if report is None:
        report = ReportMeta(record_id=record.id, report_no=generate_report_no(record.id), snapshot_hash=payload_hash)
        db.session.add(report)
        db.session.commit()
        record.report = report
    return report


def list_records_for_user(user_id: int, *, query: str = "", status: str = "all", page: int = 1, per_page: int = 8):
    from sqlalchemy import func

    conditions = [AnalysisRecord.user_id == user_id]
    if status and status != "all":
        conditions.append(AnalysisRecord.status == status)
    if query:
        conditions.append(AnalysisRecord.food_name.like(f"%{query}%"))
    total = db.session.execute(select(func.count(AnalysisRecord.id)).where(*conditions)).scalar_one()
    page = max(1, page)
    per_page = max(1, min(per_page, 50))
    stmt = (
        select(AnalysisRecord)
        .where(*conditions)
        .order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = db.session.execute(stmt).scalars().all()
    return {
        "items": [record.to_summary() for record in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }
