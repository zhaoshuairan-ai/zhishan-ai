"""家庭食材管家 API：库存、提醒、健康画像与食谱 Agent。"""
from __future__ import annotations

import json
import threading
import time

from flask import Blueprint, Response, current_app, g, request, stream_with_context

from ..extensions import db
from ..services import (
    family_service,
    health_tip_service,
    notify_service,
    ocr,
    pantry_import_service,
    pantry_service,
    recipe_agent_service,
    shelf_life_service,
    shopping_service,
    storage,
)
from ..utils.errors import ValidationError
from ..utils.response import ok
from ..utils.security import login_required
from .common import json_body

bp = Blueprint("pantry", __name__)

# 同一用户只保留一条 SSE 长连接：新连接会通知旧连接退出，
# 避免反复刷新页面把 waitress 工作线程占满（页面/上传请求被拖死）。
_stream_stops: dict[int, threading.Event] = {}
_stream_lock = threading.Lock()


@bp.post("/pantry/consume")
@login_required
def consume_recipe():
    payload = json_body()
    ingredients = payload.get("ingredients")
    if not isinstance(ingredients, list):
        raise ValidationError("ingredients 必须是数组")
    return ok(
        pantry_service.consume_ingredients(
            g.current_user.id,
            str(payload.get("recipe_name") or "这道菜"),
            [item for item in ingredients if isinstance(item, dict)],
        ),
        "已扣减库存",
    )


@bp.get("/pantry")
@login_required
def list_pantry():
    return ok(
        pantry_service.list_items(
            g.current_user.id,
            status=request.args.get("status", ""),
            query=request.args.get("query", ""),
            family_user_ids=family_service.family_member_ids(g.current_user),
        )
    )


@bp.post("/pantry")
@login_required
def create_pantry_item():
    item = pantry_service.create_item(g.current_user.id, json_body())
    return ok({"item": item.to_public()}, "食材已加入库存", 201)


@bp.put("/pantry/<int:item_id>")
@login_required
def update_pantry_item(item_id: int):
    item = pantry_service.update_item(g.current_user.id, item_id, json_body())
    return ok({"item": item.to_public()}, "食材已更新")


@bp.delete("/pantry/<int:item_id>")
@login_required
def delete_pantry_item(item_id: int):
    return ok(
        pantry_service.delete_item(
            g.current_user.id,
            item_id,
            family_user_ids=family_service.family_member_ids(g.current_user),
        ),
        "食材已删除",
    )


@bp.post("/pantry/shopping/checkout")
@login_required
def shopping_checkout():
    payload = json_body()
    return ok(
        shopping_service.checkout(
            g.current_user.id,
            payload.get("items") or [],
            include_staples=bool(payload.get("include_staples")),
        )
    )


@bp.get("/pantry/reminders")
@login_required
def pantry_reminders():
    return ok(pantry_service.reminder_summary(g.current_user.id))


@bp.get("/health-profile")
@login_required
def get_health_profile():
    return ok(pantry_service.get_profile(g.current_user.id))


@bp.put("/health-profile")
@login_required
def update_health_profile():
    profile = pantry_service.save_profile(g.current_user.id, json_body())
    return ok({"profile": profile.to_public()}, "健康画像已保存")


@bp.post("/health-profile/tip")
@login_required
def health_profile_tip():
    return ok(health_tip_service.generate(json_body()))


@bp.post("/recipes/plan")
@login_required
def plan_recipes():
    payload = json_body(required=False)
    try:
        meals = int(payload.get("meals") or 3)
        max_minutes = int(payload.get("max_minutes") or 30)
        servings = int(payload.get("servings") or 2)
        budget = int(payload.get("budget") or 0)
    except (TypeError, ValueError):
        raise ValidationError("meals / max_minutes / servings / budget 必须是整数")
    preference = str(payload.get("preference") or payload.get("user_request") or "").strip()[:500]
    weather = payload.get("weather") if isinstance(payload.get("weather"), dict) else {}
    plan = recipe_agent_service.plan_recipes(
        g.current_user.id,
        meals=meals,
        max_minutes=max_minutes,
        servings=servings,
        budget=budget,
        weather=weather,
        preference=preference,
    )
    return ok(plan, "食谱方案已生成", 201)


@bp.post("/recipes/from-assistant")
@login_required
def recipe_from_assistant():
    payload = json_body()
    try:
        message_id = int(payload.get("message_id") or 0)
    except (TypeError, ValueError):
        raise ValidationError("message_id 格式不正确")
    if not message_id:
        raise ValidationError("缺少助手消息 ID")
    version = str(payload.get("version") or "novice")
    plan = recipe_agent_service.save_assistant_recipe(g.current_user.id, message_id, version)
    return ok(plan, "已加入食谱规划", 201)


@bp.post("/recipes/complete")
@login_required
def complete_recipe():
    payload = json_body()
    try:
        plan_id = int(payload.get("plan_id") or 0)
        meal_index = int(payload.get("meal_index") or 0)
    except (TypeError, ValueError):
        raise ValidationError("plan_id / meal_index 格式不正确")
    if not plan_id:
        raise ValidationError("缺少食谱方案 ID")
    result = recipe_agent_service.complete_meal(g.current_user.id, plan_id, meal_index)
    return ok(result, result.get("message") or "已完成并扣减库存")


@bp.post("/recipes/remove-meal")
@login_required
def remove_recipe_meal():
    payload = json_body()
    try:
        plan_id = int(payload.get("plan_id") or 0)
        meal_index = int(payload.get("meal_index") or 0)
    except (TypeError, ValueError):
        raise ValidationError("plan_id / meal_index 格式不正确")
    if not plan_id:
        raise ValidationError("缺少食谱方案 ID")
    result = recipe_agent_service.remove_meal(g.current_user.id, plan_id, meal_index)
    return ok(result, result.get("message") or "已从方案中移除")


@bp.get("/recipes/history")
@login_required
def recipe_history():
    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    return ok({"items": recipe_agent_service.history(g.current_user.id, limit=limit)})


@bp.post("/pantry/batch-delete")
@login_required
def batch_delete_pantry():
    payload = json_body()
    result = pantry_service.delete_items(
        g.current_user.id,
        payload.get("ids") or [],
        family_user_ids=family_service.family_member_ids(g.current_user),
    )
    return ok(result, f"已删除 {result['deleted']} 项食材")


@bp.post("/pantry/batch")
@login_required
def batch_create_pantry():
    payload = json_body()
    return ok(pantry_import_service.batch_create(g.current_user.id, payload.get("items") or []), "食材已批量导入", 201)


@bp.post("/pantry/import/text")
@login_required
def import_text():
    payload = json_body()
    text = str(payload.get("text") or "")
    source = "voice" if str(payload.get("source") or "voice") == "voice" else "text"
    return ok(pantry_import_service.parse_text(text, source=source), "解析完成，请确认后导入")


@bp.post("/pantry/import/receipt")
@login_required
def import_receipt():
    file = request.files.get("file")
    if file is None:
        raise ValidationError("请上传小票或商品图片")
    raw = file.read()
    max_mb = int(current_app.config.get("MAX_CONTENT_LENGTH_MB") or 10)
    meta = storage.save_image(
        raw,
        original_name=file.filename or "receipt.jpg",
        max_mb=max_mb,
        max_edge=int(current_app.config.get("IMAGE_MAX_EDGE") or 2200),
    )
    root = storage.upload_root()
    path = root / meta["stored_name"]
    try:
        output = ocr.recognize(path)
        if not output.raw_text.strip():
            raise ValidationError("图片中没有识别到文字，请换一张更清晰的小票照片")
        parsed = pantry_import_service.parse_receipt_text(output.raw_text)
    finally:
        for name in (meta["stored_name"], storage.display_name(meta["stored_name"])):
            try:
                (root / name).unlink(missing_ok=True)
            except OSError:
                pass
    parsed["ocr"] = {
        "provider": output.provider,
        "provider_label": output.provider_label,
        "is_demo": output.is_demo,
        "line_count": len(output.lines),
        "raw_text": output.raw_text[:3000],
        "warning": output.warning,
    }
    return ok(parsed, "小票识别完成，请确认后导入")


@bp.get("/pantry/lookup/shelf-life")
@login_required
def lookup_shelf_life():
    name = str(request.args.get("name") or "").strip()
    if not name:
        raise ValidationError("请提供食材名称")
    return ok(shelf_life_service.lookup_shelf_life(name, use_web=request.args.get("web", "1") != "0"))


@bp.post("/pantry/decode-barcode")
@login_required
def decode_barcode():
    file = request.files.get("file")
    if file is None:
        raise ValidationError("请上传条码照片")
    raw = file.read()
    max_mb = int(current_app.config.get("MAX_CONTENT_LENGTH_MB") or 10)
    meta = storage.save_image(
        raw,
        original_name=file.filename or "barcode.jpg",
        max_mb=max_mb,
        max_edge=int(current_app.config.get("IMAGE_MAX_EDGE") or 2200),
    )
    root = storage.upload_root()
    path = root / meta["stored_name"]
    try:
        result = shelf_life_service.decode_barcode_image(path)
    finally:
        for name in (meta["stored_name"], storage.display_name(meta["stored_name"])):
            try:
                (root / name).unlink(missing_ok=True)
            except OSError:
                pass
    if not result.get("found"):
        raise ValidationError(result.get("message") or "没有识别到条码")
    return ok(result)


@bp.get("/pantry/lookup/barcode")
@login_required
def lookup_barcode():
    return ok(shelf_life_service.lookup_barcode(str(request.args.get("barcode") or "")))


@bp.post("/pantry/notify-test")
@login_required
def notify_test():
    result = notify_service.send_digest(g.current_user.id, username=g.current_user.username)
    return ok(result, "已生成并尝试发送今日摘要")


@bp.post("/recipes/rescue")
@login_required
def rescue_recipe():
    payload = json_body(required=False)
    try:
        item_id = int(payload.get("item_id") or 0)
        meals = max(2, min(3, int(payload.get("meals") or 2)))
    except (TypeError, ValueError):
        raise ValidationError("item_id / meals 格式不正确")
    if not item_id:
        raise ValidationError("请指定要拯救的临期食材")
    plan = recipe_agent_service.plan_recipes(
        g.current_user.id, meals=meals, max_minutes=30, focus_item_id=item_id
    )
    return ok(plan, "临期拯救食谱已生成", 201)


@bp.get("/pantry/stream")
@login_required
def pantry_stream():
    """SSE 实时提醒。

    浏览器用 fetch + Authorization 读取；不是 WebSocket（当前 WSGI 栈不支持）。
    服务端每 2 秒发送心跳、每 20 秒推送一次提醒；同一用户的新连接会主动结束旧连接，
    防止反复刷新页面时长连接占满工作线程。
    """
    user_id = g.current_user.id
    once = request.args.get("once") == "1"

    def generate():
        stop = threading.Event()
        if not once:
            with _stream_lock:
                previous = _stream_stops.get(user_id)
                if previous is not None:
                    previous.set()
                _stream_stops[user_id] = stop
        try:
            while not stop.is_set():
                db.session.expire_all()
                data = pantry_service.reminder_summary(user_id)
                yield "event: reminder\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"
                if once:
                    break
                # 心跳间隔 2 秒，发现旧连接关闭/被替换后尽快退出
                for _ in range(10):
                    if stop.is_set():
                        return
                    time.sleep(1)
                    yield ": keep-alive\n\n"
        finally:
            with _stream_lock:
                if _stream_stops.get(user_id) is stop:
                    _stream_stops.pop(user_id, None)

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
