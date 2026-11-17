"""健康画像提示：勾选症状后生成一句可执行的饮食提醒。"""
from __future__ import annotations

from flask import current_app

CONDITION_LABELS = {
    "hypertension": "高血压",
    "diabetes": "糖尿病",
    "gout": "痛风",
    "pregnancy": "孕期",
    "kidney": "肾病",
}
GOAL_LABELS = {
    "fat_loss": "减脂",
    "low_sodium": "控盐",
    "low_sugar": "控糖",
    "high_protein": "高蛋白",
    "balanced": "均衡饮食",
}


def _fallback(payload: dict) -> str:
    conditions = payload.get("conditions") or []
    goals = payload.get("goals") or []
    allergies = [str(item).strip() for item in payload.get("allergies") or [] if str(item).strip()]
    notes = str(payload.get("notes") or "").strip()
    points = []
    if "hypertension" in conditions:
        points.append("严格限制钠摄入（少盐、少酱油、少加工肉）")
    if "diabetes" in conditions:
        points.append("控制主食总量，优先低升糖主食，甜品和高糖饮料尽量避开")
    if "gout" in conditions:
        points.append("减少高嘌呤海鲜、内脏和浓汤")
    if "pregnancy" in conditions:
        points.append("避开酒精、生食和高汞鱼，食材彻底加热")
    if "kidney" in conditions:
        points.append("蛋白质和钾的摄入量请按医生建议执行")
    if "fat_loss" in goals:
        points.append("优先高纤维蔬菜和优质蛋白，控制烹调油")
    if "low_sodium" in goals:
        points.append("食谱默认少盐、少酱料")
    if "high_protein" in goals:
        points.append("每餐安排一份优质蛋白")
    if "balanced" in goals:
        points.append("主食、蔬菜和蛋白质按比例搭配")
    if allergies:
        points.append(f"每餐自动避开：{'、'.join(allergies[:6])}")
    if notes:
        points.append(f"已记录补充说明：{notes[:40]}")
    if not points:
        return ""
    return "AI 助理已同步您的健康画像：未来食谱规划将" + "；".join(points) + "。"


def _prompt(payload: dict) -> str:
    conditions = payload.get("conditions") or []
    goals = payload.get("goals") or []
    allergies = [str(item).strip() for item in payload.get("allergies") or [] if str(item).strip()]
    notes = str(payload.get("notes") or "").strip()
    condition_text = "、".join(CONDITION_LABELS.get(item, item) for item in conditions) or "无"
    goal_text = "、".join(GOAL_LABELS.get(item, item) for item in goals) or "无"
    allergy_text = "、".join(allergies[:10]) or "无"
    return (
        "你是家庭营养助理。请根据以下健康画像，用一句中文提醒用户未来食谱规划会如何调整。"
        "只输出一句 45–90 字的建议，不要诊断疾病，不要编造医学结论，不要使用 Markdown。"
        "如果涉及肾病、孕期或严重疾病，提醒用户以医生意见为准。\n"
        f"健康状况：{condition_text}\n饮食目标：{goal_text}\n过敏/忌口：{allergy_text}\n补充说明：{notes or '无'}\n"
        "句式参考：AI 助理已同步您的健康画像：未来食谱规划将……"
    )


def generate(payload: dict) -> dict:
    conditions = payload.get("conditions") or []
    goals = payload.get("goals") or []
    allergies = payload.get("allergies") or []
    notes = str(payload.get("notes") or "").strip()
    if not conditions and not goals and not allergies and not notes:
        return {"tip": "", "source": "empty"}
    fallback = _fallback(payload)
    try:
        from .assistant_service import _chat

        raw = _chat(
            [
                {"role": "system", "content": _prompt(payload)},
                {"role": "user", "content": "请生成健康画像同步提示。"},
            ]
        )
        tip = (raw or "").strip().strip("。") + "。"
        if 10 <= len(tip) <= 220:
            return {"tip": tip, "source": "ai"}
    except Exception:
        pass
    return {"tip": fallback, "source": "rule"}


__all__ = ["generate"]
