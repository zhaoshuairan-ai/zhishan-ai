"""验证码接口（公开，无需登录）。"""
from __future__ import annotations

from flask import Blueprint

from ..services.captcha_service import captcha_enabled, issue_captcha
from ..utils.response import ok

bp = Blueprint("captcha", __name__)


@bp.get("/captcha")
def captcha():
    data = issue_captcha()
    data["enabled"] = captcha_enabled()
    # 验证码图片必须每次刷新，禁止任何层缓存
    response, status = ok(data, "验证码已生成")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response, status
