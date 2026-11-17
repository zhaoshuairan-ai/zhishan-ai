"""菜品知识自动补全：用已有菜品资料作为风格参考，调用大模型补全条目。"""
from __future__ import annotations

import json

from ..extensions import db
from ..models import KnowledgeEntry
from . import ai_service, dish_library
from ..utils.errors import ValidationError


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    for sep in ("，", ",", "、", ";", "；", "\n"):
        if sep in text:
            return [item.strip() for item in text.split(sep) if item.strip()]
    return text.split()


def _existing_context(limit: int = 10) -> list[dict]:
    dishes = []
    for dish in dish_library.load_all():
        dishes.append(
            {
                "name": dish.get("dish_name", ""),
                "category": dish.get("category", ""),
                "calories": dish.get("calories_per_100g"),
                "tip": dish.get("health_tip", ""),
            }
        )
        if len(dishes) >= limit:
            break
    return dishes


def enrich_dish(entry: KnowledgeEntry) -> KnowledgeEntry:
    """补全菜品的摘要、正文、别名、关键词和使用提示。

    只补空字段或过短的摘要/正文，避免覆盖运营已经写好的完整内容。
    """
    if entry.category != "dish":
        raise ValidationError("只有菜品分类支持自动补全")

    if not ai_service.ai_configured():
        raise ValidationError("未配置 AI_API_KEY，暂时无法自动补全菜品信息")

    context = _existing_context()
    context_text = "\n".join(
        f"- {item['name']}（{item['category']}，约 {item['calories']} kcal/100g）：{item['tip']}"
        for item in context
    )

    prompt = f"""你是菜品营养知识库的编辑。请参考已有菜品的字段风格，补全新菜品信息。

已有菜品示例：
{context_text}

新增菜品：
- 名称：{entry.title}
- 用户补充：{entry.summary or "无"}
- 现有正文：{entry.content or "无"}

要求：
1. 只基于常见做法给出概述性营养说明，不虚构检测数据或权威标准。
2. summary 不超过 40 个汉字，概括菜品主要食材、口味和营养特点。
3. content 约 80-200 个汉字，说明主要食材、大致热量/营养特点、适合人群和食用提醒。
4. aliases 返回 1-4 个常见别名；keywords 返回 3-8 个检索关键词；usage_note 不超过 80 个汉字。
5. 严格返回以下 JSON，不要输出 Markdown：
{{
  "summary": "……",
  "content": "……",
  "aliases": ["……"],
  "keywords": ["……"],
  "usage_note": "……"
}}"""

    raw = ai_service._call_llm(
        [
            {
                "role": "system",
                "content": "你是严谨的中文菜品营养资料编辑，只输出 JSON。",
            },
            {"role": "user", "content": prompt},
        ]
    )

    try:
        data = json.loads(ai_service._strip_code_fence(raw))
    except (TypeError, ValueError) as exc:
        raise ai_service.AIServiceError("AI 返回的菜品信息不是合法 JSON") from exc

    if not isinstance(data, dict):
        raise ai_service.AIServiceError("AI 未返回有效的菜品信息")

    summary = str(data.get("summary") or "").strip()
    content = str(data.get("content") or "").strip()
    aliases = _as_list(data.get("aliases"))
    keywords = _as_list(data.get("keywords"))
    usage_note = str(data.get("usage_note") or "").strip()

    # 过短的摘要/正文视为“未填写”，用 AI 结果补全
    if (not entry.summary.strip() or len(entry.summary.strip()) < 12) and summary:
        entry.summary = summary[:200]
    if (not entry.content.strip() or len(entry.content.strip()) < 30) and content:
        entry.content = content[:4000]
    if aliases and not entry.aliases.strip():
        entry.aliases = ", ".join(aliases)[:300]
    if keywords and not entry.keywords.strip():
        entry.keywords = " ".join(keywords)[:300]
    if usage_note and not entry.usage_note.strip():
        entry.usage_note = usage_note[:1000]

    db.session.commit()
    return entry
