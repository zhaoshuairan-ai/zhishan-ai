"""OCR 文字识别接口。"""
from __future__ import annotations

from flask import Blueprint, g

from ..models import AnalysisRecord
from ..services import analysis_service, storage
from ..services import ocr as ocr_service
from ..services.field_parser import FIELD_ORDER, merge_provider_fields, parse_fields
from ..utils.errors import ValidationError
from ..utils.response import ok
from ..utils.security import login_required, owned_or_404
from .common import int_field, json_body

bp = Blueprint("ocr", __name__)


@bp.post("/ocr")
@login_required
def run_ocr():
    payload = json_body()
    record_id = int_field(payload, "record_id", field="记录 ID")
    record = owned_or_404(AnalysisRecord, record_id)
    if record.image is None:
        raise ValidationError("该记录还没有上传图片，请先上传食品标签照片")

    target = storage.ocr_target(record.image.stored_name)
    output = ocr_service.recognize(target)
    parsed = parse_fields([(line.text, line.confidence) for line in output.lines])
    # 视觉模型会直接返回结构化字段，优先采用（仍保留置信度与标记）
    merge_provider_fields(parsed, (output.raw_payload or {}).get("fields"))
    ocr = analysis_service.save_ocr(record, output, parsed)

    return ok(
        {
            "record": record.to_summary(),
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
        "文字识别完成，请核对识别结果",
    )
