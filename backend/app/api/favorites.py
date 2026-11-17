"""食谱收藏接口。"""
from __future__ import annotations

from flask import Blueprint, g

from ..services import family_service, favorite_service
from ..utils.errors import ValidationError
from ..utils.response import ok
from ..utils.security import login_required
from .common import json_body

bp = Blueprint("favorites", __name__)


@bp.get("/favorites")
@login_required
def list_favorites():
    items = favorite_service.list_favorites(
        g.current_user.id,
        family_service.family_member_ids(g.current_user),
    )
    return ok({"items": items, "total": len(items)})


@bp.post("/favorites")
@login_required
def add_favorite():
    payload = json_body()
    recipe_name = str(payload.get("recipe_name") or "").strip()
    recipe_data = payload.get("recipe_data")
    if not isinstance(recipe_data, dict):
        raise ValidationError("recipe_data 必须是对象")
    favorite, created = favorite_service.add_favorite(g.current_user.id, recipe_name, recipe_data)
    return ok({"favorite": favorite, "created": created}, "已加入收藏" if created else "收藏已更新")


@bp.get("/favorites/<int:favorite_id>/missing")
@login_required
def favorite_missing(favorite_id: int):
    return ok(
        favorite_service.favorite_missing(
            g.current_user.id,
            favorite_id,
            family_service.family_member_ids(g.current_user),
        )
    )


@bp.delete("/favorites/<int:favorite_id>")
@login_required
def remove_favorite(favorite_id: int):
    return ok(favorite_service.remove_favorite(g.current_user.id, favorite_id), "已取消收藏")


@bp.post("/favorites/<int:favorite_id>/schedule")
@login_required
def schedule_favorite(favorite_id: int):
    return ok(
        favorite_service.schedule_favorite(
            g.current_user.id,
            favorite_id,
            family_service.family_member_ids(g.current_user),
        ),
        "已加入今日排期",
    )
