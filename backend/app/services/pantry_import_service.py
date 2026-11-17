"""多模态食材录入：小票 OCR / 自然语言 / 条码后的名称解析。

所有结果先返回「预览」，由用户确认后再批量入库；不会因为模型识别而直接写库。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

import requests
from flask import current_app
from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from ..extensions import db
from ..models import PantryItem
from ..utils.errors import ValidationError
from . import shelf_life_service
from .pantry_service import _validate_item

UNIT_WORDS = "kg|公斤|千克|斤|克|g|个|颗|根|盒|袋|瓶|把|块|只|条|包|升|ml|毫升|份"
QTY_RE = re.compile(rf"(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{UNIT_WORDS})", re.I)
PRICE_RE = re.compile(r"[¥￥]?\s*\d+(?:\.\d{1,2})?\s*元?")
LONG_NUMBER_RE = re.compile(r"\b\d{8,}\b")
NOISE_WORDS = (
    "合计",
    "小计",
    "总计",
    "应付",
    "实付",
    "找零",
    "优惠",
    "会员",
    "收银",
    "门店",
    "电话",
    "地址",
    "发票",
    "日期",
    "时间",
    "欢迎",
    "谢谢",
    "支付",
    "微信",
    "支付宝",
    "二维码",
    "订单",
    "数量",
    "单价",
    "金额",
)
VOICE_NOISE = (
    "今天",
    "买了",
    "买",
    "购入",
    "采购",
    "还有",
    "放入",
    "放进",
    "放",
    "冷藏",
    "冷冻",
    "常温",
    "冰箱",
    "保存",
    "一共",
    "一些",
    "帮我",
    "记一下",
)


class ParsedItemModel(BaseModel):
    name: str
    quantity: float = 1
    unit: str = "份"
    category: str | None = None
    shelf_life_days: int | None = None


class ParsedItemsModel(BaseModel):
    items: list[ParsedItemModel] = Field(default_factory=list)


def _config() -> dict:
    config = current_app.config
    return {
        "base": str(config.get("AI_BASE_URL") or "").rstrip("/"),
        "key": str(config.get("AI_API_KEY") or ""),
        "model": config.get("AI_MODEL") or "deepseek-chat",
        "timeout": int(config.get("AI_TIMEOUT") or 60),
        "mode": str(config.get("PANTRY_IMPORT_MODE") or "auto").lower(),
    }


def _allow_ai() -> bool:
    cfg = _config()
    return cfg["mode"] != "rule" and bool(cfg["key"] and cfg["base"])


def _call_llm(messages: list[dict]) -> str:
    cfg = _config()
    url = cfg["base"] if cfg["base"].endswith("/chat/completions") else cfg["base"] + "/chat/completions"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
        json={"model": cfg["model"], "temperature": 0.1, "messages": messages},
        timeout=cfg["timeout"],
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    payload = resp.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content or "").strip()


def _strip_fence(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return match.group(1).strip() if match else text.strip()


def _ai_parse(text: str, *, source: str) -> list[dict] | None:
    if not _allow_ai():
        return None
    system = (
        "你是家庭食材录入助手。从用户文本/小票 OCR 文本中提取实际购买的食材，"
        "忽略门店名、电话、合计、支付方式、优惠等噪声；数量无法确定时用 1。"
        "只输出 JSON：{\"items\":[{\"name\":\"西红柿\",\"quantity\":3,\"unit\":\"个\",\"category\":\"vegetable\",\"shelf_life_days\":null}]}。"
        "category 只能是 vegetable/fruit/meat/seafood/egg_dairy/staple/bean/condiment/other。"
        f"来源：{source}。不要编造文本中不存在的食材。"
    )
    try:
        raw = _call_llm([{"role": "system", "content": system}, {"role": "user", "content": text[:6000]}])
        data = json.loads(_strip_fence(raw))
        parsed = ParsedItemsModel.model_validate(data)
        if not parsed.items:
            return None
        # 防幻觉：名称必须在原文中出现（允许去掉数量后的名称）
        result = []
        for item in parsed.items:
            name = item.name.strip()
            if not name or name not in text:
                continue
            result.append(item.model_dump())
        return result or None
    except (requests.RequestException, RuntimeError, json.JSONDecodeError, PydanticValidationError, KeyError, TypeError):
        return None


def _clean_name(raw: str) -> str:
    name = raw
    for word in VOICE_NOISE:
        name = name.replace(word, "")
    name = re.sub(r"^[\s\d、,，.。:：;；\-—]+", "", name)
    name = re.sub(r"[\s\d、,，.。:：;；\-—]+$", "", name)
    name = PRICE_RE.sub("", name)
    name = LONG_NUMBER_RE.sub("", name)
    name = re.sub(r"\s+", "", name)
    return name.strip("：:，,。.；;、")


def _rule_parse(text: str, *, source: str) -> list[dict]:
    if source == "receipt":
        segments = [line.strip() for line in text.splitlines() if line.strip()]
    else:
        cleaned = text
        for word in ("今天", "买了", "买", "购入", "采购"):
            cleaned = cleaned.replace(word, "")
        segments = [part.strip() for part in re.split(r"[、,，;；\n]|以及|还有|和", cleaned) if part.strip()]

    items: list[dict] = []
    seen: set[str] = set()
    for segment in segments:
        if any(noise in segment for noise in NOISE_WORDS):
            continue
        qty = 1.0
        unit = "份"
        match = QTY_RE.search(segment)
        if match:
            try:
                qty = float(match.group("qty"))
            except ValueError:
                qty = 1.0
            unit = match.group("unit")
            if unit.lower() == "g":
                unit = "克"
            if unit.lower() == "ml":
                unit = "毫升"
            segment = segment[: match.start()] + segment[match.end() :]
        # 去掉价格、条码、规格（如 500g 已作为数量处理）
        name = _clean_name(segment)
        if not name or len(name) > 20 or len(name) < 1:
            continue
        if name.isdigit() or name in seen:
            continue
        # 纯英文/符号行通常是小票噪声
        if not re.search(r"[\u4e00-\u9fa5A-Za-z]", name):
            continue
        seen.add(name)
        items.append(
            {
                "name": name,
                "quantity": round(qty, 2),
                "unit": unit,
                "category": shelf_life_service.guess_category(name),
                "shelf_life_days": None,
            }
        )
        if len(items) >= 30:
            break
    return items


def _enrich(items: list[dict], *, use_web: bool = True) -> list[dict]:
    today = date.today()
    result: list[dict] = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        category = str(item.get("category") or shelf_life_service.guess_category(name))
        shelf = shelf_life_service.lookup_shelf_life(name, use_web=use_web)
        days = item.get("shelf_life_days") or shelf.get("days")
        try:
            days = int(days) if days is not None else None
        except (TypeError, ValueError):
            days = None
        expires = today + timedelta(days=days) if days else None
        result.append(
            {
                "name": name,
                "quantity": float(item.get("quantity") or 1),
                "unit": str(item.get("unit") or "份")[:10],
                "category": category,
                "purchased_at": today.isoformat(),
                "expires_at": expires.isoformat() if expires else "",
                "shelf_life_days": days,
                "shelf_life_confidence": shelf.get("confidence_percent") or 0,
                "shelf_life_confidence_label": shelf.get("confidence_label") or "未估算",
                "shelf_life_alternatives": shelf.get("alternatives") or [],
                "shelf_life_basis": shelf.get("basis") or "",
                "storage": shelf.get("storage") or "常温",
                "shelf_life_source": shelf.get("source") or "builtin",
                "shelf_life_note": shelf.get("note") or "",
                "shelf_life_warning": shelf.get("warning"),
                "note": (
                    f"AI 估算保质期 {days} 天（置信度 {shelf.get('confidence_percent') or 0}%）；请按包装核对；"
                    if days
                    else "智能录入未估算保质期，请自行选择到期日；"
                )
                + (shelf.get("note") or ""),
            }
        )
    return result


def parse_text(text: str, *, source: str = "voice") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValidationError("没有可解析的文本")
    if len(text) > 6000:
        raise ValidationError("文本过长，请缩短到 6000 字以内")
    ai_items = _ai_parse(text, source=source)
    mode = "ai"
    if not ai_items:
        ai_items = _rule_parse(text, source=source)
        mode = "rule"
    items = _enrich(ai_items)
    if not items:
        raise ValidationError("没有识别到食材，请换一种说法或手动录入")
    warnings = []
    if mode == "rule":
        warnings.append("本次使用规则解析（未调用大模型或模型返回不可用），请核对名称与数量。")
    missing = [
        item["name"]
        for item in items
        if item.get("shelf_life_warning") and not item.get("shelf_life_days")
    ]
    if missing:
        shown = "、".join(missing[:6])
        more = f" 等 {len(missing)} 项" if len(missing) > 6 else ""
        warnings.append(
            f"以下食材未收录常规保质期，未做估算，请手动选择到期日：{shown}{more}。"
        )
    return {
        "mode": mode,
        "source": source,
        "items": items,
        "warnings": warnings[:6],
        "count": len(items),
    }


def parse_receipt_text(text: str) -> dict:
    return parse_text(text, source="receipt")


def batch_create(user_id: int, items: list[dict]) -> dict:
    if not isinstance(items, list) or not items:
        raise ValidationError("没有可导入的食材")
    if len(items) > 30:
        raise ValidationError("一次最多导入 30 项食材")
    from ..models import PantryItem as _PantryItem

    existing = _PantryItem.query.filter_by(user_id=user_id).count()
    if existing + len(items) > 200:
        raise ValidationError("导入后库存将超过 200 项，请先清理")
    # 先全部校验，再一次性提交，避免中途失败留下半批数据
    validated = [_validate_item(payload) for payload in items if isinstance(payload, dict)]
    if len(validated) != len(items):
        raise ValidationError("食材数据格式不正确")
    created = [PantryItem(user_id=user_id, **data) for data in validated]
    db.session.add_all(created)
    db.session.commit()
    return {"items": [item.to_public() for item in created], "count": len(created)}

__all__ = ["parse_text", "parse_receipt_text", "batch_create"]
