"""家庭共享 API。"""
from __future__ import annotations

from flask import Blueprint, g

from ..services import family_service
from ..utils.response import ok
from ..utils.security import login_required

bp = Blueprint("family", __name__)


@bp.get("/family")
@login_required
def get_family():
    return ok(family_service.family_payload(g.current_user))


@bp.post("/family/join")
@login_required
def join_family():
    from .common import json_body

    payload = json_body()
    return ok(
        family_service.join_family(g.current_user, str(payload.get("invite_code") or "")),
        "已加入家庭，库存已共享",
    )


@bp.post("/family/create")
@login_required
def create_family():
    return ok(
        family_service.create_family(g.current_user),
        "家庭创建成功",
        201,
    )


@bp.post("/family/leave")
@login_required
def leave_family():
    result = family_service.leave_family(g.current_user)
    message = "家庭已解散" if result.get("action") == "dissolved" else "已退出当前家庭"
    return ok(result, message)


@bp.delete("/family/members/<int:member_id>")
@login_required
def remove_member(member_id: int):
    return ok(family_service.remove_member(g.current_user, member_id), "已移除家庭成员")


@bp.put("/family/name")
@login_required
def update_family_name():
    from .common import json_body

    payload = json_body()
    return ok(
        family_service.rename_family(
            g.current_user,
            str(payload.get("name") or ""),
        ),
        "家庭名称已更新",
    )


@bp.put("/family/members/<int:member_id>")
@login_required
def update_family_member(member_id: int):
    from .common import json_body

    payload = json_body()
    return ok(
        family_service.update_member_name(
            g.current_user,
            member_id,
            str(payload.get("display_name") or ""),
        ),
        "成员备注已更新",
    )


@bp.get("/family/alert")
@login_required
def family_alert():
    return ok({"alert": family_service.family_health_alert(g.current_user)})
