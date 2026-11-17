"""家庭共享服务：邀请码、成员列表、家庭库存范围与家庭健康提醒。"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from ..extensions import db
from ..models import Family, HealthProfile, PantryItem, User
from ..utils.errors import NotFoundError, ValidationError
from ..utils.validators import clean_text

INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SPICY_WORDS = ("辣条", "麻辣", "辛辣", "辣椒", "辣味", "火锅", "烧烤", "花椒", "芥末")


def generate_invite_code() -> str:
    for _ in range(20):
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(6))
        if Family.query.filter_by(invite_code=code).first() is None:
            return code
    raise ValidationError("邀请码生成失败，请稍后重试")


def ensure_family(user: User) -> Family:
    if user.family_id:
        family = db.session.get(Family, user.family_id)
        if family is not None:
            return family
    family = Family(
        invite_code=generate_invite_code(),
        name=f"{user.display_name or user.username}的家庭",
        created_by=user.id,
    )
    db.session.add(family)
    db.session.flush()
    user.family_id = family.id
    db.session.commit()
    return family


def family_member_ids(user: User) -> list[int]:
    if not user.family_id:
        return [user.id]
    return [row.id for row in User.query.filter_by(family_id=user.family_id, is_active=True).all()]


def family_payload(user: User) -> dict | None:
    # 新用户默认没有家庭；只有主动创建/加入后才建立家庭关系
    if not user.family_id:
        return None
    family = db.session.get(Family, user.family_id)
    if family is None:
        return None
    members = User.query.filter_by(family_id=family.id, is_active=True).order_by(User.id.asc()).all()
    return {
        "family": family.to_public(),
        "members": [
            {
                "id": member.id,
                "username": member.username,
                "display_name": member.display_name or member.username,
                "initial": (member.display_name or member.username or "家")[:1].upper(),
                "avatar_url": None,
                "is_self": member.id == user.id,
                "is_owner": member.id == family.created_by,
                "role": "户主" if member.id == family.created_by else "成员",
            }
            for member in members
        ],
        "member_count": len(members),
        "is_owner": family.created_by == user.id,
    }


def join_family(user: User, invite_code: str) -> dict:
    code = clean_text(invite_code, max_len=12, field="邀请码").strip().upper()
    if not code:
        raise ValidationError("请输入家庭邀请码")

    # 有家庭身份时不再允许重复加入/切换，避免误覆盖原家庭关系
    if user.family_id:
        current = db.session.get(Family, user.family_id)
        if current is not None:
            raise ValidationError("您已经是当前家庭的成员，无需重复加入")

    family = Family.query.filter_by(invite_code=code).first()
    if family is None:
        raise NotFoundError("邀请码错误或已过期")

    user.family_id = family.id
    db.session.commit()
    return family_payload(user)


def create_family(user: User) -> dict:
    if user.family_id:
        raise ValidationError("您已经加入其他家庭，请先退出当前家庭")
    ensure_family(user)
    return family_payload(user)


def leave_family(user: User) -> dict:
    if not user.family_id:
        raise ValidationError("您还没有加入家庭")

    family = db.session.get(Family, user.family_id)
    if family is None:
        user.family_id = None
        db.session.commit()
        return {"left": True, "action": "left", "family_id": None}

    family_id = family.id
    is_owner = family.created_by == user.id

    if is_owner:
        # 户主解散：解除所有成员绑定，并删除家庭本身
        for member in User.query.filter_by(family_id=family_id).all():
            member.family_id = None
        db.session.delete(family)
        db.session.commit()
        return {"left": True, "action": "dissolved", "family_id": family_id}

    user.family_id = None
    db.session.commit()
    return {"left": True, "action": "left", "family_id": family_id}


def family_health_alert(user: User) -> dict | None:
    """家庭成员新增辛辣食品时，给胃炎/胃病用户生成首页提示。"""
    if not user.family_id:
        return None
    profile = HealthProfile.query.filter_by(user_id=user.id).first()
    conditions = set(profile.conditions or []) if profile else set()
    if "gastritis" not in conditions:
        return None

    member_ids = family_member_ids(user)
    if len(member_ids) <= 1:
        return None

    since = datetime.now(timezone.utc) - timedelta(days=30)
    filters = [
        PantryItem.user_id.in_(member_ids),
        PantryItem.user_id != user.id,
        PantryItem.created_at >= since,
    ]
    filters.append(or_(*[PantryItem.name.ilike(f"%{word}%") for word in SPICY_WORDS]))
    item = PantryItem.query.filter(*filters).order_by(PantryItem.created_at.desc()).first()
    if item is None:
        return None
    owner = db.session.get(User, item.user_id)
    return {
        "message": "检测到家人购买辛辣食品，提醒您注意肠胃健康",
        "item_name": item.name,
        "owner_name": (owner.display_name or owner.username) if owner else "家人",
        "item_id": item.id,
        "created_at": item.created_at.isoformat() + "Z" if item.created_at else None,
        "source": "AI家庭健康提醒",
    }


def rename_family(user: User, name: str) -> dict:
    family = ensure_family(user)
    if family.created_by != user.id:
        raise ValidationError("只有户主可以修改家庭名称")
    clean_name = clean_text(name, max_len=30, field="家庭名称", allow_empty=False).strip()
    if not clean_name:
        raise ValidationError("家庭名称不能为空")
    family.name = clean_name
    db.session.commit()
    return family_payload(user)


def update_member_name(user: User, member_id: int, display_name: str) -> dict:
    if not user.family_id:
        raise ValidationError("尚未加入家庭")
    family = db.session.get(Family, user.family_id)
    if family is None:
        raise ValidationError("家庭不存在")
    member = User.query.filter_by(
        id=member_id,
        family_id=family.id,
        is_active=True,
    ).first()
    if member is None:
        raise NotFoundError("家庭成员不存在")
    if member.id != user.id and family.created_by != user.id:
        raise ValidationError("只能修改自己的成员备注")
    clean_name = clean_text(
        display_name,
        max_len=20,
        field="成员备注",
        allow_empty=False,
    ).strip()
    if not clean_name:
        raise ValidationError("成员备注不能为空")
    member.display_name = clean_name
    db.session.commit()
    return family_payload(user)


def remove_member(user: User, member_id: int) -> dict:
    """仅户主可移除其他家庭成员；户主不能移除自己。"""
    if not user.family_id:
        raise ValidationError("尚未加入家庭")
    family = db.session.get(Family, user.family_id)
    if family is None:
        raise ValidationError("家庭不存在")
    if family.created_by != user.id:
        raise ValidationError("只有户主可以移除家庭成员")
    if member_id == user.id:
        raise ValidationError("户主不能移除自己")
    member = User.query.filter_by(id=member_id, family_id=family.id).first()
    if member is None:
        raise NotFoundError("家庭成员不存在")
    member.family_id = None
    db.session.commit()
    return {"removed_id": member_id, "family": family_payload(user)}
