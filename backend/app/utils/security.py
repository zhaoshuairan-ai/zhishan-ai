"""密码哈希、会话令牌与鉴权辅助。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Callable

from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models.user import AuthSession, User
from .errors import ForbiddenError, NotFoundError, UnauthorizedError

# werkzeug 默认使用 scrypt（或 pbkdf2），每次调用自带随机 salt，不存储明文
PASSWORD_METHOD = "scrypt"


def hash_password(raw: str) -> str:
    return generate_password_hash(raw, method=PASSWORD_METHOD)


def verify_password(password_hash: str, raw: str) -> bool:
    try:
        return check_password_hash(password_hash, raw)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    # 数据库只保存令牌的 SHA-256，泄库也无法直接登录
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(user: User) -> tuple[str, AuthSession]:
    token = secrets.token_urlsafe(32)
    days = int(current_app.config["SESSION_DAYS"])
    session = AuthSession(
        token_hash=_token_hash(token),
        user_id=user.id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=days),
    )
    db.session.add(session)
    db.session.commit()
    return token, session


def revoke_session(token: str) -> bool:
    session = AuthSession.query.filter_by(token_hash=_token_hash(token)).first()
    if not session:
        return False
    db.session.delete(session)
    db.session.commit()
    return True


def _extract_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            return token
    # 兼容图片 <img> 等无法自定义头的场景（仅用于只读预览）
    return request.args.get("token")


def current_user() -> User | None:
    if "current_user" in g:
        return g.current_user
    token = _extract_token()
    user = None
    if token:
        session = AuthSession.query.filter_by(token_hash=_token_hash(token)).first()
        now = datetime.now(timezone.utc)
        if session and session.expires_at.replace(tzinfo=timezone.utc) > now:
            user = db.session.get(User, session.user_id)
            if user and user.is_active:
                g.auth_session = session
                g.current_user = user
                return user
    g.current_user = None
    return None


def login_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            raise UnauthorizedError("请先登录后再使用该功能")
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn: Callable) -> Callable:
    """管理员权限校验：未登录 401，非管理员 403，被停用 403。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            raise UnauthorizedError("请先以管理员身份登录")
        if not getattr(user, "is_admin", False):
            raise ForbiddenError("需要管理员权限")
        if not user.is_active:
            raise ForbiddenError("该账号已被停用")
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def current_admin() -> User | None:
    user = current_user()
    return user if user is not None and getattr(user, "is_admin", False) else None


def owned_or_404(model, obj_id: int, *, allow_demo: bool = False):
    """按 ID 取出资源，并校验归属；不存在与无权限统一返回 404，避免探测他人数据。"""
    obj = db.session.get(model, obj_id)
    if obj is None:
        raise NotFoundError("资源不存在或无权访问", details={"id": obj_id})
    user = current_user()
    owner_id = getattr(obj, "user_id", None)
    if owner_id is None or user is None or owner_id != user.id:
        raise NotFoundError("资源不存在或无权访问", details={"id": obj_id})
    return obj


def safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


__all__ = [
    "hash_password",
    "verify_password",
    "issue_session",
    "revoke_session",
    "current_user",
    "login_required",
    "admin_required",
    "current_admin",
    "owned_or_404",
    "ForbiddenError",
]
