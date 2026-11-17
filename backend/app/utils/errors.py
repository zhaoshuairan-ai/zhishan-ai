"""统一异常类型与错误处理器注册。"""
from __future__ import annotations

import logging

from flask import Flask, request
from werkzeug.exceptions import HTTPException

from .response import ErrorCode, fail

logger = logging.getLogger(__name__)


class APIError(Exception):
    """业务异常：由接口层直接抛出，统一转换为 JSON 错误响应。"""

    def __init__(
        self,
        message: str,
        code: int = ErrorCode.VALIDATION,
        status: int = 400,
        details=None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details = details


class NotFoundError(APIError):
    def __init__(self, message: str = "资源不存在", details=None) -> None:
        super().__init__(message, ErrorCode.NOT_FOUND, 404, details)


class UnauthorizedError(APIError):
    def __init__(self, message: str = "请先登录", details=None) -> None:
        super().__init__(message, ErrorCode.UNAUTHORIZED, 401, details)


class ForbiddenError(APIError):
    def __init__(self, message: str = "没有访问该资源的权限", details=None) -> None:
        super().__init__(message, ErrorCode.FORBIDDEN, 403, details)


class ValidationError(APIError):
    def __init__(self, message: str = "请求参数不合法", details=None) -> None:
        super().__init__(message, ErrorCode.VALIDATION, 400, details)


class ConflictError(APIError):
    def __init__(self, message: str = "资源冲突", details=None) -> None:
        super().__init__(message, ErrorCode.CONFLICT, 409, details)


class ServiceError(APIError):
    """上游服务（OCR / LLM）失败。"""

    def __init__(
        self,
        message: str = "外部服务暂时不可用",
        code: int = ErrorCode.UPSTREAM_ERROR,
        status: int = 502,
        details=None,
    ) -> None:
        super().__init__(message, code, status, details)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def _handle_api_error(err: APIError):  # pragma: no cover - 由测试覆盖
        if err.status >= 500:
            logger.warning("APIError %s: %s", err.status, err.message)
        return fail(err.message, err.code, err.status, err.details)

    @app.errorhandler(HTTPException)
    def _handle_http_error(err: HTTPException):
        mapping = {
            400: ErrorCode.VALIDATION,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            405: ErrorCode.VALIDATION,
            413: ErrorCode.PAYLOAD_TOO_LARGE,
            415: ErrorCode.UNSUPPORTED_MEDIA,
            429: ErrorCode.RATE_LIMITED,
        }
        message = err.description or "请求失败"
        if err.code == 404:
            message = "接口或资源不存在"
        elif err.code == 405:
            message = "请求方法不被允许"
        elif err.code == 413:
            message = "请求体超过服务端允许的大小"
        return fail(message, mapping.get(err.code or 400, ErrorCode.INTERNAL), err.code or 400)

    @app.errorhandler(Exception)
    def _handle_unexpected(err: Exception):  # pragma: no cover
        logger.exception("未捕获异常: %s", err.__class__.__name__)
        try:
            from ..services.admin_service import record_event

            record_event(
                "api",
                f"{err.__class__.__name__}: {str(err)[:200]}",
                detail={"path": request.path, "method": request.method},
            )
        except Exception:
            pass
        return fail("服务器内部错误，请稍后重试", ErrorCode.INTERNAL, 500)
