"""API 层公共工具：统一 JSON 入参读取与分页参数校验。"""
from __future__ import annotations

from typing import Any

from flask import request

from ..utils.errors import ValidationError


def json_body(*, required: bool = True) -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        if required:
            raise ValidationError("请求体必须是 JSON 格式（Content-Type: application/json）")
        return {}
    if not isinstance(payload, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    return payload


def pagination(default_per_page: int = 8, max_per_page: int = 50) -> tuple[int, int]:
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        raise ValidationError("page 必须是正整数")
    try:
        per_page = int(request.args.get("per_page", default_per_page))
    except (TypeError, ValueError):
        raise ValidationError("per_page 必须是正整数")
    if page < 1:
        raise ValidationError("page 必须大于等于 1")
    if per_page < 1:
        raise ValidationError("per_page 必须大于等于 1")
    return page, min(per_page, max_per_page)


def int_field(payload: dict, key: str, *, field: str, minimum: int = 1) -> int:
    value: Any = payload.get(key)
    if value is None:
        raise ValidationError(f"缺少参数 {key}（{field}）")
    try:
        num = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"参数 {key} 必须是整数")
    if num < minimum:
        raise ValidationError(f"参数 {key} 必须大于等于 {minimum}")
    return num
