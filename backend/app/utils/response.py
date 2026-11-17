"""统一 JSON 响应格式。

所有接口返回：
{
  "success": true|false,
  "code": 0 | 业务错误码,
  "message": "人类可读信息",
  "data": ...,
  "details": {...} | null,
  "request_id": "..."
}
"""
from __future__ import annotations

from typing import Any

from flask import g, jsonify


def _request_id() -> str:
    return getattr(g, "request_id", "-")


def ok(data: Any = None, message: str = "ok", status: int = 200, **extra: Any):
    payload = {
        "success": True,
        "code": 0,
        "message": message,
        "data": data,
        "details": None,
        "request_id": _request_id(),
    }
    payload.update(extra)
    return jsonify(payload), status


def fail(
    message: str,
    code: int = 40000,
    status: int = 400,
    details: Any = None,
    data: Any = None,
):
    return (
        jsonify(
            {
                "success": False,
                "code": code,
                "message": message,
                "data": data,
                "details": details,
                "request_id": _request_id(),
            }
        ),
        status,
    )


class ErrorCode:
    VALIDATION = 40000
    UNAUTHORIZED = 40100
    FORBIDDEN = 40300
    NOT_FOUND = 40400
    CONFLICT = 40900
    UNPROCESSABLE = 42200
    PAYLOAD_TOO_LARGE = 41300
    UNSUPPORTED_MEDIA = 41500
    RATE_LIMITED = 42900
    INTERNAL = 50000
    SERVICE_UNAVAILABLE = 50300
    UPSTREAM_ERROR = 50200
    TIMEOUT = 50400
