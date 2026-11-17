"""分析记录接口：列表 / 详情 / 校正 / 删除 / 图片读取 / 重新分析。"""
from __future__ import annotations

import io
import logging

from flask import Blueprint, current_app, g, request, send_file
from sqlalchemy import func, select

from ..extensions import db
from ..models import AnalysisRecord, NutritionFact, OCR_FIELDS
from ..services import analysis_service, storage
from ..utils.errors import ValidationError
from ..utils.response import ok
from ..utils.security import login_required, owned_or_404
from ..utils.validators import clean_multiline, clean_text
from .common import int_field, json_body, pagination

logger = logging.getLogger(__name__)
bp = Blueprint("records", __name__)

STATUS_VALUES = {"all", "uploaded", "ocr_done", "corrected", "analyzed", "failed"}
FIELD_KEYS = {key for key, _ in OCR_FIELDS}


@bp.get("/records")
@login_required
def list_records():
    page, per_page = pagination(default_per_page=int(current_app.config.get("PAGE_SIZE", 8)))
    status = (request.args.get("status") or "all").strip().lower()
    if status not in STATUS_VALUES:
        raise ValidationError(f"status 取值不合法（可选：{'、'.join(sorted(STATUS_VALUES))}）")
    query = clean_text(request.args.get("query"), max_len=40, field="搜索关键词")
    result = analysis_service.list_records_for_user(
        g.current_user.id, query=query, status=status, page=page, per_page=per_page
    )

    user_id = g.current_user.id
    stats = {
        "total": db.session.execute(
            select(func.count(AnalysisRecord.id)).where(AnalysisRecord.user_id == user_id)
        ).scalar_one(),
        "analyzed": db.session.execute(
            select(func.count(AnalysisRecord.id)).where(
                AnalysisRecord.user_id == user_id, AnalysisRecord.status == "analyzed"
            )
        ).scalar_one(),
        "suspected": db.session.execute(
            select(func.count(AnalysisRecord.id)).where(
                AnalysisRecord.user_id == user_id, AnalysisRecord.overall_check == "suspected"
            )
        ).scalar_one(),
        "demo": db.session.execute(
            select(func.count(AnalysisRecord.id)).where(
                AnalysisRecord.user_id == user_id, AnalysisRecord.is_demo.is_(True)
            )
        ).scalar_one(),
    }
    result["stats"] = stats
    result["filters"] = {"query": query, "status": status}
    return ok(result)


@bp.delete("/records")
@login_required
def clear_records():
    """一键删除当前用户的全部历史记录，并清理图片文件。"""
    records = AnalysisRecord.query.filter_by(user_id=g.current_user.id).all()
    stored_names = [record.image.stored_name for record in records if record.image]
    count = len(records)
    for record in records:
        db.session.delete(record)
    db.session.commit()
    for stored_name in stored_names:
        try:
            storage.delete_image(stored_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("清理历史图片失败：%s", exc.__class__.__name__)
    return ok({"deleted_count": count}, f"已删除 {count} 条历史记录")


@bp.get("/records/<int:record_id>")
@login_required
def record_detail(record_id: int):
    record = owned_or_404(AnalysisRecord, record_id)
    return ok(analysis_service.build_detail(record))


@bp.delete("/records/<int:record_id>")
@login_required
def delete_record(record_id: int):
    record = owned_or_404(AnalysisRecord, record_id)
    stored_name = record.image.stored_name if record.image else None
    db.session.delete(record)
    db.session.commit()
    deleted_files: list[str] = []
    if stored_name:
        try:
            deleted_files = storage.delete_image(stored_name)
        except Exception as exc:  # pragma: no cover - 文件删除失败不影响记录删除
            logger.warning("删除图片文件失败：%s", exc.__class__.__name__)
    return ok({"deleted_id": record_id, "deleted_files": deleted_files}, "记录已删除")


@bp.put("/records/<int:record_id>")
@login_required
def update_record(record_id: int):
    record = owned_or_404(AnalysisRecord, record_id)
    payload = json_body()
    if "food_name" in payload:
        record.food_name = str(payload.get("food_name") or "").strip()[:120]
    nutrition = payload.get("nutrition")
    if isinstance(nutrition, dict):
        defs = {
            "energy": ("能量", "kJ"),
            "protein": ("蛋白质", "g"),
            "fat": ("脂肪", "g"),
            "carbohydrate": ("碳水化合物", "g"),
            "sodium": ("钠", "mg"),
            "sugar": ("糖", "g"),
        }
        provided = {}
        for key, (_, unit) in defs.items():
            if key not in nutrition or nutrition[key] in (None, ""):
                continue
            try:
                value = float(nutrition[key])
            except (TypeError, ValueError):
                raise ValidationError(f"{defs[key][0]}必须是数字")
            if value < 0 or value > 1_000_000:
                raise ValidationError(f"{defs[key][0]}数值不合法")
            provided[key] = round(value, 3)
        if provided:
            fact = record.nutrition
            if fact is None:
                fact = NutritionFact(record_id=record.id, basis="per_100g", source="manual", items=[], warnings=[])
                db.session.add(fact)
                record.nutrition = fact
            items = list(fact.items or [])
            for key, value in provided.items():
                name, unit = defs[key]
                target = next((item for item in items if item.get("key") == key), None)
                if target is None:
                    items.append(
                        {
                            "key": key,
                            "name": name,
                            "raw_name": name,
                            "value": value,
                            "unit": unit,
                            "nrv_percent": None,
                            "status": "manual",
                            "unit_family": "energy" if key == "energy" else ("sodium" if key == "sodium" else "mass"),
                        }
                    )
                else:
                    target["value"] = value
                    target["unit"] = unit
                    target["status"] = "manual"
                    if "nrv_percent" not in target:
                        target["nrv_percent"] = None
            fact.items = items
            fact.source = "manual"
            fact.basis = fact.basis or "per_100g"
    db.session.commit()
    return ok(analysis_service.build_detail(record), "记录已更新")


@bp.put("/records/<int:record_id>/ocr")
@login_required
def correct_ocr(record_id: int):
    record = owned_or_404(AnalysisRecord, record_id)
    payload = json_body()
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise ValidationError("fields 必须是对象，键为字段名、值为校正后的文本")
    unknown = [k for k in fields if k not in FIELD_KEYS]
    if unknown:
        raise ValidationError(f"包含未知字段：{'、'.join(unknown[:5])}", details={"allowed": sorted(FIELD_KEYS)})
    cleaned = {}
    for key, value in fields.items():
        limit = 20000 if key in {"ingredients_text", "nutrition_text"} else 500
        cleaned[key] = clean_multiline(value, max_len=limit, field=key) if isinstance(value, str) else ""
    note = payload.get("note")
    if note is not None:
        note = clean_multiline(note, max_len=500, field="备注")
    ocr = analysis_service.apply_correction(record, cleaned, note=note)
    return ok({"record": record.to_summary(), "ocr": ocr.to_public()}, "识别结果已保存")


@bp.post("/records/<int:record_id>/reanalyze")
@login_required
def reanalyze(record_id: int):
    record = owned_or_404(AnalysisRecord, record_id)
    result = analysis_service.analyze(record)
    return ok(
        {"result": result, "record": record.to_summary(), "detail": analysis_service.build_detail(record)},
        "已重新分析",
    )


@bp.get("/records/<int:record_id>/image")
@login_required
def record_image(record_id: int):
    record = owned_or_404(AnalysisRecord, record_id)
    if record.image is None:
        raise ValidationError("该记录没有关联图片", details={"record_id": record_id})
    want_original = request.args.get("original") == "1"
    data, mime = storage.read_image(record.image.stored_name, display=not want_original)
    response = send_file(
        io.BytesIO(data),
        mimetype=mime,
        as_attachment=False,
        download_name=record.image.original_name or "label.jpg",
        max_age=300,
    )
    response.headers["Cache-Control"] = "private, max-age=300"
    return response
