"""分析触发接口与识饭菜 SSE 流式输出。"""
from __future__ import annotations

import base64
import binascii
import io
import json
import re
import time

from flask import Blueprint, Response, request
from werkzeug.datastructures import FileStorage

from ..models import AnalysisRecord
from ..services import analysis_service, dish_service, storage, upload_service
from ..services import ocr as ocr_service
from ..services.field_parser import FIELD_ORDER, merge_provider_fields, parse_fields
from ..utils.errors import NotFoundError, ValidationError
from ..utils.response import ok
from ..utils.security import login_required, owned_or_404
from .common import int_field, json_body

bp = Blueprint("analyze", __name__)


def _normalize_upload_mode(raw_mode: object) -> str:
    value = str(raw_mode or "").strip().lower()
    if value in {"packaging", "package"}:
        return "packaging"
    if value == "dish":
        return "dish"
    raise ValidationError(
        "mode 只能是 packaging 或 dish",
        details={"mode": value, "allowed": ["packaging", "dish"]},
    )


def _file_storage_from_base64(data_url: object) -> FileStorage:
    """把 JSON 中的 data URL / Base64 字符串还原为 FileStorage。

    支持：
    - data:image/jpeg;base64,xxxxx
    - data:image/png;base64,xxxxx
    - 直接传 Base64（无 data URL 前缀）
    """
    text = str(data_url or "").strip()
    if not text:
        raise ValidationError("image_base64 不能为空")

    mime = "image/jpeg"
    encoded = text
    if text.startswith("data:"):
        header, separator, payload = text.partition(",")
        if not separator or ";base64" not in header.lower():
            raise ValidationError("image_base64 必须是合法的 Base64 data URL")
        mime = header[5:].split(";", 1)[0].strip().lower() or "image/jpeg"
        encoded = payload

    if not mime.startswith("image/"):
        raise ValidationError("image_base64 的 MIME 类型必须是 image/*")

    compact = re.sub(r"\s+", "", encoded)
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError("image_base64 不是合法的 Base64 数据") from exc
    if not raw:
        raise ValidationError("image_base64 解码后图片为空")

    ext = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get(mime, "jpg")
    return FileStorage(
        stream=io.BytesIO(raw),
        filename=f"base64-upload.{ext}",
        content_type=mime,
    )


@bp.post("/analyze")
@login_required
def analyze():
    """分析入口。

    支持三种调用方式：
    - Base64 JSON：`{image_base64, mode=packaging|dish}`，上传、建记录并完成
      包装 OCR 或识饭菜分析（前端图片上传的默认方式）。
    - multipart：`file` + `mode`，保留旧客户端兼容。
    - JSON：`{record_id, type}`，用于校正文字后的正式分析（原有流程）。
    """
    if request.mimetype == "multipart/form-data":
        return analyze_uploaded()

    payload = json_body()
    if "image_base64" in payload:
        return analyze_base64(payload)

    record_id = int_field(payload, "record_id", field="记录 ID")
    analysis_type = str(payload.get("type") or "package").strip().lower()
    if analysis_type not in {"package", "dish"}:
        raise ValidationError(
            "type 只能是 package 或 dish",
            details={"type": analysis_type, "allowed": ["package", "dish"]},
        )
    record = owned_or_404(AnalysisRecord, record_id)
    if analysis_type == "dish":
        result = dish_service.analyze_record(record)
        message = "菜品分析完成"
    else:
        result = analysis_service.analyze(record)
        message = "分析完成" if not result.get("errors") else "分析完成（大模型调用失败，已使用基础规则模式）"
    return ok(
        {
            "result": result,
            "record": record.to_summary(),
            "detail": analysis_service.build_detail(record),
        },
        message,
    )


def analyze_base64(payload: dict) -> Response:
    """Base64 JSON 上传入口。"""
    mode = _normalize_upload_mode(payload.get("mode"))
    return _analyze_upload(_file_storage_from_base64(payload.get("image_base64")), mode)


def analyze_uploaded():
    """multipart 上传入口（旧客户端兼容）。"""
    mode = _normalize_upload_mode(request.form.get("mode"))
    return _analyze_upload(request.files.get("file"), mode)


def _analyze_upload(upload_file, mode: str) -> Response:
    """保存图片、创建记录，并完成包装 OCR 或识饭菜分析。

    packaging 模式返回与 `/ocr` 相同的字段，前端进入“核对校正”步骤；
    dish 模式直接完成识饭菜分析，并返回 SSE 流地址。
    """
    record, image, limits = upload_service.save_uploaded_record(upload_file)

    if mode == "dish":
        result = dish_service.analyze_record(record)
        return ok(
            {
                "mode": mode,
                "record": record.to_summary(),
                "image": image.to_public(),
                "limits": limits,
                "result": result,
                "detail": analysis_service.build_detail(record),
                "stream_url": f"/analyze/dish/{record.id}/stream",
            },
            "菜品分析完成",
            201,
        )

    target = storage.ocr_target(record.image.stored_name)
    output = ocr_service.recognize(target)
    parsed = parse_fields([(line.text, line.confidence) for line in output.lines])
    merge_provider_fields(parsed, (output.raw_payload or {}).get("fields"))
    ocr = analysis_service.save_ocr(record, output, parsed)

    return ok(
        {
            "mode": mode,
            "record": record.to_summary(),
            "image": image.to_public(),
            "limits": limits,
            "ocr": ocr.to_public(),
            "fields": parsed["fields"],
            "field_order": FIELD_ORDER,
            "demo_warning": output.warning if output.is_demo else None,
            "ocr_warning": None if output.is_demo else output.warning,
            "provider": {
                "key": output.provider,
                "label": output.provider_label,
                "version": output.engine_version,
                "is_demo": output.is_demo,
                "duration_ms": output.duration_ms,
            },
        },
        "图片已上传并完成文字识别，请核对结果",
        201,
    )


@bp.get("/analyze/dish/<int:record_id>/stream")
@login_required
def stream_dish(record_id: int):
    """把已落库的识饭菜结果按 SSE 逐字返回，前端用打字机效果展示。"""
    record = owned_or_404(AnalysisRecord, record_id)
    raw = record.ingredient.raw_response if record.ingredient else None
    dish = (raw or {}).get("dish") if isinstance(raw, dict) else None
    if not dish:
        raise NotFoundError("这条记录还没有识饭菜结果，请先完成分析")

    text = dish_service.format_stream_text(dish)

    def generate():
        for char in text:
            yield f"data: {json.dumps({'text': char}, ensure_ascii=False)}\n\n"
            time.sleep(0.018)
        yield "event: done\ndata: {\"done\": true}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
