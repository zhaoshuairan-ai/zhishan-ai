"""图片上传接口。"""
from __future__ import annotations

import logging

from flask import Blueprint, request

from ..services import upload_service
from ..utils.response import ok
from ..utils.security import login_required

logger = logging.getLogger(__name__)
bp = Blueprint("uploads", __name__)


@bp.post("/upload")
@login_required
def upload():
    record, image, limits = upload_service.save_uploaded_record(request.files.get("file"))
    payload = {
        "record": record.to_summary(),
        "image": image.to_public(),
        "limits": limits,
    }
    return ok(payload, "图片上传成功，可以开始文字识别", 201)