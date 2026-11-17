"""图片上传领域逻辑：上传接口与 /api/analyze 的 multipart 入口共用。"""
from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from flask import current_app, g

from ..extensions import db
from ..models import AnalysisRecord, UploadedImage
from ..utils.errors import ValidationError
from ..utils.validators import clean_filename
from . import storage

ALLOWED_EXT_HINT = "JPG / JPEG / PNG / WEBP"


def save_uploaded_record(upload_file) -> tuple[AnalysisRecord, UploadedImage, dict]:
    """保存图片并创建一条 uploaded 状态的记录。

    调用方负责认证；本函数只处理文件校验、落盘和数据库事务。
    """
    if upload_file is None or not upload_file.filename:
        raise ValidationError(
            "未收到图片文件，请使用 multipart/form-data 上传，字段名为 file",
            details={"field": "file", "allowed": ["jpg", "jpeg", "png", "webp"]},
        )

    max_mb = int(current_app.config["MAX_CONTENT_LENGTH_MB"])
    max_edge = int(current_app.config["IMAGE_MAX_EDGE"])
    raw = upload_file.read()
    if len(raw) > max_mb * 1024 * 1024:
        raise ValidationError(
            f"图片大小超过限制（最大 {max_mb} MB）",
            details={"max_mb": max_mb},
        )

    original_name = clean_filename(upload_file.filename, fallback="label.jpg")
    meta = storage.save_image(raw, original_name=original_name, max_mb=max_mb, max_edge=max_edge)

    record = AnalysisRecord(
        user_id=g.current_user.id,
        status="uploaded",
        data_source="real",
        food_name="",
        note="",
    )
    db.session.add(record)
    try:
        db.session.flush()
        image = UploadedImage(record_id=record.id, user_id=g.current_user.id, **meta)
        db.session.add(image)
        record.image = image
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        storage.delete_image(meta["stored_name"])
        raise

    return record, image, {"max_mb": max_mb, "allowed": ALLOWED_EXT_HINT}