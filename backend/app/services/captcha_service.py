"""登录验证码（算术题 + SVG 图片，服务端一次性校验）。

设计：
- 题目与答案只在服务端保存，前端只拿到图片与 captcha_id；
- 5 分钟内有效、一次性使用，校验失败或过期即作废；
- 不依赖第三方服务与字体文件，SVG 自带干扰线，离线可用；
- 测试环境可通过 CAPTCHA_ECHO 暴露题目文本，生产默认关闭。
"""
from __future__ import annotations

import base64
import hmac
import random
import secrets
import threading
import time

from flask import current_app

CAPTCHA_TTL = 300
_STORE: dict[str, dict] = {}
_LOCK = threading.Lock()
_MAX_ENTRIES = 5000


def _config_bool(key: str, default: bool) -> bool:
    value = current_app.config.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def captcha_enabled() -> bool:
    return _config_bool("LOGIN_CAPTCHA", True)


def echo_enabled() -> bool:
    return _config_bool("CAPTCHA_ECHO", False)


def _cleanup(now: float) -> None:
    expired = [key for key, item in _STORE.items() if item["expires_at"] <= now]
    for key in expired:
        _STORE.pop(key, None)
    if len(_STORE) > _MAX_ENTRIES:
        # 极端情况下丢弃最早的一半，避免内存无限增长
        for key in list(_STORE)[: len(_STORE) - _MAX_ENTRIES // 2]:
            _STORE.pop(key, None)


def _svg(question: str) -> str:
    """生成带干扰线/噪点的算术验证码 SVG（不依赖外部字体）。"""
    width, height = 132, 44
    lines = []
    for _ in range(4):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        color = random.choice(["#b7cfc9", "#c9dbd6", "#a9c6bf"])
        lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.2" opacity="0.65"/>'
        )
    dots = []
    for _ in range(18):
        dots.append(
            f'<circle cx="{random.randint(0, width)}" cy="{random.randint(0, height)}" r="{random.choice([1, 1.4, 2])}" '
            f'fill="#c2d6d1" opacity="0.7"/>'
        )
    text = question.replace("&", "&amp;").replace("<", "&lt;")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" rx="8" fill="#f2f8f6"/>'
        + "".join(lines)
        + "".join(dots)
        + f'<text x="{width / 2}" y="29" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="19" font-weight="700" fill="#0d3f38" letter-spacing="1.5">{text}</text>'
        "</svg>"
    )


def issue_captcha() -> dict:
    now = time.time()
    with _LOCK:
        _cleanup(now)
        a = random.randint(2, 9)
        b = random.randint(1, 9)
        if random.random() < 0.5:
            if a < b:
                a, b = b, a
            question = f"{a} - {b} = ?"
            answer = str(a - b)
        else:
            question = f"{a} + {b} = ?"
            answer = str(a + b)
        captcha_id = secrets.token_urlsafe(18)
        _STORE[captcha_id] = {"answer": answer, "expires_at": now + CAPTCHA_TTL}
    image = base64.b64encode(_svg(question).encode("utf-8")).decode("ascii")
    payload = {
        "captcha_id": captcha_id,
        "image": f"data:image/svg+xml;base64,{image}",
        "question": question,  # 用于无障碍提示与自动化测试；答案不返回
        "expires_in": CAPTCHA_TTL,
    }
    if echo_enabled():  # 仅测试环境开启
        payload["answer"] = answer
    return payload


def verify_captcha(captcha_id: str, code: str) -> bool:
    """一次性校验：无论成功失败都会消耗该 captcha_id。"""
    if not captcha_id or not code:
        return False
    now = time.time()
    with _LOCK:
        item = _STORE.pop(str(captcha_id), None)
    if not item or item["expires_at"] <= now:
        return False
    return hmac.compare_digest(item["answer"], str(code).strip())


__all__ = ["issue_captcha", "verify_captcha", "captcha_enabled", "CAPTCHA_TTL"]
