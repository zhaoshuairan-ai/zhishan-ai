"""账号与会话接口。

安全要点：
- 密码使用 werkzeug scrypt 哈希存储，数据库不保存明文；
- 登录令牌为随机串，数据库只存 SHA-256，泄露数据库也无法直接登录；
- 登录失败次数在内存中限流，避免暴力破解；
- 接口不返回任何密钥信息。
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone

from flask import Blueprint, g, request
from sqlalchemy import func

from ..extensions import db
from ..models import AnalysisRecord, AuthSession, User
from ..utils.errors import APIError, ConflictError, UnauthorizedError, ValidationError
from ..utils.response import ok
from ..utils.security import hash_password, issue_session, login_required, revoke_session, verify_password
from ..services.captcha_service import captcha_enabled, verify_captcha
from ..utils.validators import clean_text
from .common import json_body

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[A-Za-z]{2,8}$")

# 简易登录限流（单进程内存实现，生产多实例部署建议换成 Redis）
_FAILED: dict[str, list[float]] = {}
_FAILED_LOCK = threading.Lock()
MAX_FAILURES = 6
FAILURE_WINDOW = 300


def _throttle_key(username: str) -> str:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "-").split(",")[0].strip()
    return f"{username.lower()}|{ip}"


def _check_throttle(key: str) -> None:
    now = time.time()
    with _FAILED_LOCK:
        attempts = [t for t in _FAILED.get(key, []) if now - t < FAILURE_WINDOW]
        _FAILED[key] = attempts
        if len(attempts) >= MAX_FAILURES:
            raise APIError(
                "登录失败次数过多，请 5 分钟后再试",
                code=42900,
                status=429,
                details={"window_seconds": FAILURE_WINDOW, "max_failures": MAX_FAILURES},
            )


def _record_failure(key: str) -> None:
    with _FAILED_LOCK:
        _FAILED.setdefault(key, []).append(time.time())


def _clear_failure(key: str) -> None:
    with _FAILED_LOCK:
        _FAILED.pop(key, None)


def _validate_password(password: str) -> str:
    password = clean_text(password, max_len=64, field="密码", allow_empty=False)
    if len(password) < 8:
        raise ValidationError("密码至少 8 位")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError("密码需要同时包含字母和数字")
    return password


@bp.post("/auth/register")
def register():
    payload = json_body()
    username = clean_text(payload.get("username"), max_len=20, field="用户名", allow_empty=False).strip()
    if not USERNAME_RE.match(username):
        raise ValidationError("用户名需为 3-20 位中文、字母、数字或下划线")
    password = _validate_password(str(payload.get("password") or ""))
    display_name = clean_text(payload.get("display_name"), max_len=20, field="昵称") or username
    email = clean_text(payload.get("email"), max_len=120, field="邮箱")
    if email and not EMAIL_RE.match(email):
        raise ValidationError("邮箱格式不正确")

    if User.query.filter(func.lower(User.username) == username.lower()).first():
        raise ConflictError("该用户名已被注册，请更换")

    user = User(
        username=username,
        display_name=display_name,
        email=email or None,
        password_hash=hash_password(password),
        is_demo=False,
    )
    db.session.add(user)
    db.session.commit()

    token, session = issue_session(user)
    return ok(
        {"token": token, "expires_at": session.expires_at.isoformat() + "Z", "user": user.to_public()},
        "注册成功，已自动登录",
        201,
    )


@bp.post("/auth/login")
def login():
    payload = json_body()
    username = clean_text(payload.get("username"), max_len=20, field="用户名", allow_empty=False)
    password = str(payload.get("password") or "")
    key = _throttle_key(username)
    _check_throttle(key)

    if captcha_enabled() and not verify_captcha(
        str(payload.get("captcha_id") or ""), str(payload.get("captcha_code") or "")
    ):
        raise ValidationError("验证码不正确或已过期，请刷新后重试", details={"field": "captcha"})

    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if user is None or not verify_password(user.password_hash, password):
        _record_failure(key)
        raise UnauthorizedError("用户名或密码不正确")
    if not user.is_active:
        raise UnauthorizedError("该账号已被停用", details={"reason": "inactive"})

    _clear_failure(key)
    # 清理该用户已过期的会话
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    AuthSession.query.filter(AuthSession.user_id == user.id, AuthSession.expires_at < now).delete(
        synchronize_session=False
    )
    user.last_login_at = datetime.now(timezone.utc)
    token, session = issue_session(user)
    return ok(
        {
            "token": token,
            "expires_at": session.expires_at.isoformat() + "Z",
            "user": user.to_public(),
            "is_demo_account": bool(user.is_demo),
        },
        "登录成功",
    )


@bp.post("/auth/logout")
@login_required
def logout():
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if token:
        revoke_session(token)
    return ok({"logged_out": True}, "已退出登录")


@bp.post("/auth/change-password")
@login_required
def change_password():
    """用户修改自己的密码：校验旧密码 → 重设 → 注销全部旧会话 → 返回新令牌。"""
    payload = json_body()
    old_password = str(payload.get("old_password") or "")
    new_password = _validate_password(str(payload.get("new_password") or ""))
    user: User = g.current_user
    if not verify_password(user.password_hash, old_password):
        raise ValidationError("原密码不正确")
    if verify_password(user.password_hash, new_password):
        raise ValidationError("新密码不能与原密码相同")
    user.password_hash = hash_password(new_password)
    AuthSession.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.commit()
    token, session = issue_session(user)
    return ok(
        {
            "token": token,
            "expires_at": session.expires_at.isoformat() + "Z",
            "user": user.to_public(),
        },
        "密码已修改，其他设备上的登录已失效",
    )


@bp.put("/auth/profile")
@login_required
def update_profile():
    """Update the current user's display name (nickname)."""
    payload = json_body()
    display_name = clean_text(
        payload.get("display_name"),
        max_len=20,
        field="昵称",
        allow_empty=False,
    )

    user: User = g.current_user
    user.display_name = display_name
    db.session.commit()

    return ok({"user": user.to_public()}, "昵称修改成功")


@bp.get("/auth/me")
@login_required
def me():
    user: User = g.current_user
    record_count = AnalysisRecord.query.filter_by(user_id=user.id).count()
    analyzed = AnalysisRecord.query.filter_by(user_id=user.id, status="analyzed").count()
    return ok(
        {
            "user": user.to_public(),
            "stats": {"record_count": record_count, "analyzed_count": analyzed},
            "demo_hint": (
                "当前使用的是演示账号，记录仅对该账号可见，且包含明确标记的演示数据。"
                if user.is_demo
                else None
            ),
        }
    )
