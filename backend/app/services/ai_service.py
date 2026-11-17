"""配料解读服务：大模型模式（可配置）+ 基础规则模式（无需 Key）。

安全与诚实性约束：
- 只解释成分的常见用途与营养含义，不判定某件食品「安全/不安全/合格」；
- 不允许模型编造标准条款、文献与来源，返回的引用必须能对应到知识库条目；
- 模型输出全部经过 Pydantic 校验，并对「幻觉配料」「虚构引用」做过滤；
- 未配置模型时明确降级为基础规则模式，结果中带有 mode 标记，前端据此展示横幅。
"""
from __future__ import annotations

import json
import logging
import re
import time

import requests
from flask import current_app
from pydantic import ValidationError

from ..models.ingredient import MODE_LABELS
from ..schemas.ai_output import IngredientAnalysisModel
from . import knowledge_service

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ingredient-v3"

DISCLAIMER = (
    "本解读由程序基于配料表文字生成，属于信息理解辅助，不构成安全性、合规性判定，"
    "也不能替代实验室检测或官方检验结论。"
)

SYSTEM_PROMPT = """你是一名严谨的健康膳食与食品标签解读助手，服务对象是普通消费者、家庭健康管理者与食品专业学生。
你的任务：基于用户给出的配料表、营养成分与知识库参考资料，客观解释每种成分的常见用途与营养含义。

必须遵守的硬性规则：
1. 只做「成分用途解释」与「营养数值解读」，绝不判断这件食品是否安全、是否有毒、是否合格或是否合规。
2. 不得把食品添加剂描述为「有毒」「有害」「致癌」「危险」。可以说「在标准允许的类别与用量范围内使用是允许的」。
3. 不得推断图片或文字中不存在的信息，例如微生物、农药残留、重金属、非法添加物、生产过程卫生状况。
4. 不确定或知识库中没有依据的内容，evidence 必须写 unverified，confidence 写 low，并放入 unconfirmed 数组。
5. 引用知识库时必须使用参考资料中的编号（如 [K3]），把对应信息写入 citations；严禁编造标准编号、条款、文献或来源名称。
6. nutrition_notes 只解读营养成分表里的数值（基准、NRV%、能量来源、钠等），缺少数值就保持空数组，不要写「未识别」。
7. 如果配料表只有「水」（或饮用水/纯净水/矿泉水）：summary 必须严格返回「这是纯净水，0卡0脂，无需评估」；tags 只返回 3 个绿色核心标签，例如「0能量/0脂肪/0添加」；ingredients 的 simple_desc 只写一句客观短句；不要输出任何营养缺乏警告、未识别提示或营养风险警告。
8. summary 必须是一句话结论，不超过 30 个汉字；不要写成多段小作文。
   页面已经展示商品名称，summary 开头不要再重复 food_name；直接给核心结论，例如「典型的高糖高脂零食，减脂控盐人群建议严格控制摄入。」
         必须结合 health_profile：如果用户目标包含减脂且产品高糖高脂，personalization.level 必须为 danger/warning 并给出明确替换建议；
         如果用户过敏原出现在配料中，必须给出 danger 级过敏警告，提醒立即停止食用并咨询医生；
         如果高血压/糖尿病画像与高钠/高糖冲突，必须给出个性化警告。
   必须严格核对 food_name：summary 只能描述用户传入的这份食品，优先点名 food_name；
   如果 food_name 里没有「苏打」，严禁写「苏打饼干」；不得把食品名称写成其他无关食品。
9. tags 固定 3 个，按重要性排序，status 只能是 high/medium/low/good/neutral，label 是给用户看的短语（如「钠偏高」「零脂肪」）。
10. ingredients[].simple_desc 必须是一句 20–45 字的短句；不要长篇大论，不要把 explanation 写成长文。
11. 不要输出任何 JSON 以外的文字。"""

USER_PROMPT_TEMPLATE = """【食品名称】{food_name}
【配料表原文】{ingredients_text}
【结构化配料（按标示顺序）】
{ingredient_list}
【营养成分（来自标签）】
{nutrition_summary}
【知识库参考（编号可直接引用）】
{knowledge_context}

请输出以下结构的 JSON（字段不可缺失，没有内容用空字符串或空数组）：
{{
  "summary": "一句话结论，例如：该食品高碳水、钠偏高，减脂人群建议少吃",
  "tags": [
    {{"name": "钠", "value": "480mg", "status": "high", "label": "钠偏高"}},
    {{"name": "脂肪", "value": "0g", "status": "good", "label": "零脂肪"}},
    {{"name": "碳水", "value": "62g", "status": "medium", "label": "碳水较高"}}
  ],
  "personalization": {{
    "level": "danger|warning|info|none",
    "title": "个性化健康预警",
    "message": "结合用户画像的一句话结论；例如：这与您的减脂目标冲突：该饼干含糖量高，建议替换为无糖全麦食品。",
    "reasons": ["命中的画像目标或过敏原"]
  }},
  "nutrition_notes": [
    "2-4 条营养成分解读：结合每 100g/每份的基准、NRV%、能量来源与钠含量，用普通人能理解的话说明",
    "缺少数值时要明确说「未识别」，不要估算或补全",
    "只做营养理解，不做「健康/不健康」「安全/不安全」的结论"
  ],
  "ingredients": [
    {{
      "name": "配料名（必须来自上面的结构化配料）",
      "category": "类别，如 主要原料/食品添加剂-防腐剂/营养强化剂/调味料",
      "role": "它在食品中承担的作用，如 增稠/防腐/提供甜味",
      "purpose": "20 字以内的用途短语",
      "simple_desc": "一句 20-45 字的客观短句，用于首屏配料标签和抽屉标题",
      "explanation": "不超过 120 字的客观补充，可包含常见使用场景与需要留意的对象；不要写成小作文",
      "confidence": "high|medium|low",
      "evidence": "knowledge_base|general_knowledge|unverified",
      "source_refs": ["[K3]"],
      "caution": "可选的注意事项（如某类人群需留意），没有则 null"
    }}
  ],
  "unknown_items": ["无法解释的成分名"],
  "unconfirmed": ["需要人工确认的结论或事项"],
  "citations": [
    {{"knowledge_id": 3, "title": "知识库条目标题", "source_name": "来源名称", "claim": "该引用支持的具体说法"}}
  ],
  "safety_note": "一句提醒：本结果不构成安全性或合规性判定"
}}
要求：ingredients 必须覆盖上面列出的每一种配料，顺序与配料表一致。"""


class AIServiceError(RuntimeError):
    def __init__(self, message: str, *, code: str = "ai_error", retryable: bool = True, status: int = 502):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.status = status


def ai_configured() -> bool:
    return bool((current_app.config.get("AI_API_KEY") or "").strip())


def resolve_mode() -> str:
    """返回实际可用的分析模式：ai / rule。"""
    provider = (current_app.config.get("AI_PROVIDER") or "auto").lower()
    if provider == "rule":
        return "rule"
    if provider == "openai" and not ai_configured():
        return "rule"
    return "ai" if ai_configured() else "rule"


def _norm(text: str) -> str:
    return re.sub(r"[\s()（）\[\]【】,，、;；:：。/\\-]", "", str(text or ""))


def _strip_code_fence(text: str) -> str:
    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if match:
        return match.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def _short_summary(text: str, max_chars: int = 30) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    sentence = cleaned.split("。")[0].strip()
    if len(sentence) <= max_chars:
        return sentence + ("。" if sentence and not sentence.endswith(("。", "！", "？")) else "")
    return sentence[: max_chars - 1].rstrip() + "…"


def _nutrition_summary(parsed: dict) -> str:
    if not parsed:
        return "未识别到营养成分数值"
    basis = {"per_100g": "每 100g", "per_100ml": "每 100mL", "per_serving": "每份"}.get(parsed.get("basis"), "基准未知")
    lines = []
    for item in parsed.get("items", []):
        if item.get("value") is None:
            continue
        nrv = item.get("nrv_percent")
        nrv_text = f"，NRV {nrv}%" if nrv is not None else ""
        lines.append(f"{item['name']} {item['value']}{item['unit']}（{basis}{nrv_text}）")
    return "；".join(lines) if lines else "未识别到营养成分数值"


def _build_messages(payload: dict) -> list[dict]:
    profile = payload.get("health_profile") or {}
    profile_text = json.dumps(profile, ensure_ascii=False)
    system = SYSTEM_PROMPT + (
        "\n【用户健康画像】" + profile_text +
        "\n健康总结与 personalization 必须结合该画像；不得忽略用户的减脂/控糖/高血压目标和过敏原。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(**payload)},
    ]


def _call_llm(messages: list[dict]) -> str:
    config = current_app.config
    base_url = (config.get("AI_BASE_URL") or "").rstrip("/")
    url = f"{base_url}/chat/completions"
    body = {
        "model": config.get("AI_MODEL"),
        "temperature": config.get("AI_TEMPERATURE", 0.2),
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {config.get('AI_API_KEY')}", "Content-Type": "application/json"}
    timeout = config.get("AI_TIMEOUT", 50)
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        if resp.status_code == 400 and "response_format" in resp.text:
            body.pop("response_format", None)
            resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    except requests.Timeout as exc:
        raise AIServiceError("大模型请求超时，请稍后重试", code="ai_timeout", status=504) from exc
    except requests.RequestException as exc:
        raise AIServiceError(f"大模型网络请求失败：{exc.__class__.__name__}", code="ai_network") from exc

    if resp.status_code in (401, 403):
        raise AIServiceError("大模型 API Key 无效或权限不足，请检查 .env 配置", code="ai_auth", retryable=False, status=502)
    if resp.status_code == 429:
        raise AIServiceError("大模型接口触发限流，请稍后重试", code="ai_rate_limited", status=503)
    if resp.status_code >= 500:
        raise AIServiceError(f"大模型服务异常（HTTP {resp.status_code}）", code="ai_upstream")
    if resp.status_code != 200:
        raise AIServiceError(f"大模型请求失败（HTTP {resp.status_code}）：{resp.text[:200]}", code="ai_bad_request", retryable=False)
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError) as exc:
        raise AIServiceError("大模型返回内容无法解析") from exc
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content


def _filter_output(model: IngredientAnalysisModel, item_names: list[str], allowed_knowledge: dict[int, dict]) -> dict:
    """过滤幻觉配料与虚构引用。"""
    normalized = {_norm(name): name for name in item_names}
    kept = []
    dropped: list[str] = []
    for explain in model.ingredients:
        target = _norm(explain.name)
        matched = normalized.get(target)
        if not matched:
            for norm_name, raw_name in normalized.items():
                if target and (target in norm_name or norm_name in target) and len(target) >= 2:
                    matched = raw_name
                    break
        if not matched:
            dropped.append(explain.name)
            continue
        data = explain.model_dump()
        data["name"] = matched
        data["source_refs"] = [ref for ref in data.get("source_refs") or []][:5]
        data["is_ai_generated"] = True
        kept.append(data)

    seen_names = {_norm(item["name"]) for item in kept}
    missing = [name for name in item_names if _norm(name) not in seen_names]

    citations = []
    rejected = 0
    for citation in model.citations:
        kid = citation.knowledge_id
        if kid is not None and kid in allowed_knowledge:
            entry = allowed_knowledge[kid]
            citations.append(
                {
                    "knowledge_id": kid,
                    "title": entry["title"],
                    "source_name": entry["source_name"],
                    "source_url": entry.get("source_url"),
                    "claim": citation.claim,
                    "verified": entry.get("verification_status") == "verified",
                }
            )
        else:
            rejected += 1

    unconfirmed = list(model.unconfirmed)
    if dropped:
        unconfirmed.append(f"模型返回了 {len(dropped)} 个不在配料表中的成分（已丢弃）：{'、'.join(dropped[:5])}")
    if missing:
        unconfirmed.append(f"以下配料未获得解释：{'、'.join(missing[:8])}")
    if rejected:
        unconfirmed.append(f"有 {rejected} 条引用无法对应到知识库条目，已丢弃以避免虚构来源")

    return {
        "summary": _short_summary(model.summary),
        "tags": [tag.model_dump() for tag in model.tags][:3],
        "personalization": model.personalization.model_dump() if model.personalization else None,
        "ingredients": kept,
        "nutrition_notes": list(model.nutrition_notes),
        "unknown_items": model.unknown_items + dropped,
        "unconfirmed": unconfirmed,
        "citations": citations,
        "safety_note": model.safety_note,
    }


def derive_tags(nutrition: dict, ingredient_items: list[dict] | None = None) -> list[dict]:
    """没有模型 tags 时，从已识别的营养数值生成 3 个首屏标签。"""
    items = {item.get("key"): item for item in (nutrition or {}).get("items", []) if item.get("value") is not None}
    tags = []
    for key, label in (("sodium", "钠"), ("fat", "脂肪"), ("sugar", "糖"), ("carbohydrate", "碳水"), ("protein", "蛋白质")):
        item = items.get(key)
        if not item:
            continue
        status = str(item.get("status") or "neutral")
        if status not in {"high", "medium", "low", "good", "neutral"}:
            status = "neutral"
        value = float(item.get("value") or 0)
        if key == "sodium":
            status = "high" if value >= 400 else "medium" if value >= 200 else "good"
        elif key == "fat":
            status = "high" if value >= 17.5 else "medium" if value >= 10 else "good"
        elif key == "sugar":
            status = "high" if value >= 15 else "medium" if value >= 5 else "good"
        elif key == "carbohydrate":
            status = "high" if value >= 60 else "medium" if value >= 30 else "good"
        elif key == "protein":
            status = "good" if value >= 10 else "medium"
        status_label = str(item.get("status_label") or "")
        tags.append({
            "name": item.get("name") or label,
            "value": f"{item.get('value')}{item.get('unit') or ''}",
            "status": status,
            "label": status_label or ("偏高" if status == "high" else "较优" if status == "good" else "适中"),
        })
        if len(tags) >= 3:
            break
    if not tags and ingredient_items:
        names = [str(item.get("name") or "") for item in ingredient_items if not item.get("is_category")]
        for name in names[:3]:
            tags.append({"name": name, "value": "", "status": "neutral", "label": "已收录"})
    return tags


def _sanitize_summary(summary: str, food_name: str) -> str:
    text = str(summary or "").strip()
    name = str(food_name or "").strip()
    # 页面标题已经显示商品名，摘要开头不再重复
    if name:
        for prefix in (name, name.replace(" ", "")):
            if prefix and text.startswith(prefix):
                text = text[len(prefix):].lstrip("：:，,。. ")
                break
        # 模型经常只取品牌名 + 品类（例如“奥利奥饼干……”），继续剥掉开头
        brand = name.split()[0] if " " in name else name
        if brand and len(brand) >= 2 and text.startswith(brand):
            text = text[len(brand):].lstrip("：:，,。. ")
        for category in ("饼干", "面包", "饮料", "零食", "食品"):
            if text.startswith(category) and category not in name:
                text = text[len(category):].lstrip("：:，,。. ")
                break
    # 防止模型把“奥利奥夹心饼干”写成“苏打饼干”等张冠李戴
    if "苏打" not in name:
        text = text.replace("原味苏打饼干", name or "该产品").replace("苏打饼干", name or "该产品")
    # 常见食品类型错写：只在本品名称不含该类型时替换为“该产品”
    for wrong in ("苏打饼干", "夹心饼干", "曲奇", "面包", "饮料"):
        if wrong not in name and wrong in text and wrong != "苏打饼干":
            text = text.replace(wrong, name or "该产品")
    return text


def _merge_personalization(ai_value, profile, ingredient_names, nutrition) -> dict:
    """用户画像硬规则兜底；过敏原永远优先于模型输出。"""
    fallback = build_personalization(profile, ingredient_names, nutrition)
    if not ai_value or str(ai_value.get("level") or "none") == "none":
        return fallback
    if fallback.get("level") == "danger" and fallback.get("reasons"):
        return fallback
    return ai_value


def build_personalization(profile: dict, ingredient_names: list[str], nutrition: dict) -> dict:
    conditions = set(profile.get("conditions") or [])
    goals = set(profile.get("goals") or [])
    allergies = [str(item).strip() for item in profile.get("allergies") or [] if str(item).strip()]
    names_text = "、".join(str(name) for name in ingredient_names)
    for allergy in allergies:
        if allergy and allergy in names_text:
            return {
                "level": "danger",
                "title": "⚠️ 过敏原风险",
                "message": f"检测到您对「{allergy}」过敏，配料中含「{allergy}」，请立即停止食用并咨询医生；如出现严重过敏反应请拨打120。",
                "reasons": [f"过敏原：{allergy}"],
            }
    items = {item.get("key"): item for item in (nutrition or {}).get("items", []) if item.get("value") is not None}
    sugar = float((items.get("sugar") or {}).get("value") or 0)
    fat = float((items.get("fat") or {}).get("value") or 0)
    sodium = float((items.get("sodium") or {}).get("value") or 0)
    fat_loss = "weight_loss" in goals or "fat_loss" in goals
    if fat_loss and (sugar >= 15 or fat >= 17.5):
        return {
            "level": "danger",
            "title": "⚠️ 个性化健康预警",
            "message": f"这与您的减脂目标冲突：该食品{('含糖量高' if sugar >= 15 else '脂肪偏高')}，建议替换为无糖全麦或低脂食品。",
            "reasons": ["减脂目标", "高糖/高脂"],
        }
    if "hypertension" in conditions and sodium >= 400:
        return {
            "level": "warning",
            "title": "⚠️ 个性化健康预警",
            "message": f"这与您的高血压画像冲突：该食品钠含量约 {sodium:g}mg，建议少食并优先选择低钠替代品。",
            "reasons": ["高血压", "高钠"],
        }
    if "diabetes" in conditions and sugar >= 15:
        return {
            "level": "warning",
            "title": "⚠️ 个性化健康预警",
            "message": f"这与您的糖尿病画像冲突：该食品糖含量约 {sugar:g}g，建议控制份量或选择无糖食品。",
            "reasons": ["糖尿病", "高糖"],
        }
    return {"level": "none", "title": "", "message": "", "reasons": []}


def run_ai_analysis(
    *,
    food_name: str,
    ingredients_text: str,
    ingredient_items: list[dict],
    nutrition: dict,
    knowledge_hits: list[dict],
    health_profile: dict | None = None,
) -> dict:
    """调用大模型并校验输出；失败时抛出 AIServiceError（上层决定是否重试/降级）。"""
    start = time.perf_counter()
    if not ai_configured():
        raise AIServiceError("未配置 AI_API_KEY", code="ai_not_configured", retryable=False, status=503)

    names = [item["name"] for item in ingredient_items if not item.get("is_category")]
    allowed_knowledge = {hit["id"]: hit for hit in knowledge_hits}
    payload = {
        "food_name": food_name or "未提供",
        "ingredients_text": (ingredients_text or "")[:1500],
        "ingredient_list": "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names)) or "（未解析出配料）",
        "nutrition_summary": _nutrition_summary(nutrition),
        "knowledge_context": knowledge_service.knowledge_context(knowledge_hits) or "（无匹配的知识库条目，请把 evidence 标为 unverified）",
        "health_profile": health_profile or {},
    }
    messages = _build_messages(payload)

    last_error: Exception | None = None
    for attempt in range(2):
        content = _call_llm(messages)
        try:
            raw = json.loads(_strip_code_fence(content))
            model = IngredientAnalysisModel.model_validate(raw)
            filtered = _filter_output(model, names, allowed_knowledge)
            filtered["summary"] = _short_summary(_sanitize_summary(filtered["summary"], food_name))
            return {
                "mode": "ai",
                "mode_label": MODE_LABELS["ai"],
                "model": current_app.config.get("AI_MODEL"),
                "prompt_version": PROMPT_VERSION,
                "summary": filtered["summary"] or "已生成配料解读。",
                "tags": filtered["tags"] or derive_tags(nutrition, ingredient_items),
                "personalization": _merge_personalization(
                    filtered.get("personalization"),
                    health_profile or {},
                    names,
                    nutrition,
                ),
                "ingredients": filtered["ingredients"],
                "nutrition_notes": filtered["nutrition_notes"],
                "unknown_items": filtered["unknown_items"],
                "unconfirmed": filtered["unconfirmed"],
                "citations": filtered["citations"],
                "disclaimer": DISCLAIMER + " " + (filtered["safety_note"] or ""),
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "raw_response": {"attempt": attempt + 1, "item_count": len(filtered["ingredients"])},
                "error": None,
            }
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            logger.warning("大模型输出校验失败（第 %s 次）：%s", attempt + 1, exc.__class__.__name__)
            messages = messages + [
                {"role": "assistant", "content": content[:2000]},
                {
                    "role": "user",
                    "content": "上面的内容不是合法 JSON 或缺少必需字段。请严格只输出符合约定结构的 JSON，不要包含任何解释文字。",
                },
            ]
    raise AIServiceError(
        f"大模型返回格式不符合要求（已重试）：{str(last_error)[:120]}",
        code="ai_invalid_output",
    )


def run_rule_analysis(
    *,
    food_name: str,
    ingredient_items: list[dict],
    nutrition: dict,
    knowledge_hits: list[dict],
    reason: str | None = None,
    health_profile: dict | None = None,
) -> dict:
    """基础规则模式：完全基于本地知识库与名称特征，结果明确标注为非大模型分析。"""
    start = time.perf_counter()
    by_name: dict[str, list[dict]] = {}
    for hit in knowledge_hits:
        by_name.setdefault(hit.get("ingredient"), []).append(hit)

    explanations = []
    unknown: list[str] = []
    unconfirmed: list[str] = []
    citations: list[dict] = []
    cited_ids: set[int] = set()

    for item in ingredient_items:
        if item.get("is_category"):
            continue
        name = item["name"]
        hits = by_name.get(name) or []
        if hits:
            best = hits[0]
            confidence = "high" if best["match_score"] >= 0.99 else "medium"
            explanation = best.get("summary") or ""
            entry = knowledge_service.get_by_id(best["id"])
            if entry and entry.content:
                explanation = entry.content[:260]
            explanations.append(
                {
                    "name": name,
                    "category": best.get("category_label", "未分类"),
                    "role": item.get("hint_category", "未分类"),
                    "purpose": (best.get("summary") or "")[:80],
                    "explanation": explanation,
                    "confidence": confidence,
                    "evidence": "knowledge_base",
                    "source_refs": [f"[K{best['id']}]"],
                    "caution": None,
                }
            )
            if best["id"] not in cited_ids:
                cited_ids.add(best["id"])
                citations.append(
                    {
                        "knowledge_id": best["id"],
                        "title": best["title"],
                        "source_name": best.get("source_name", ""),
                        "source_url": best.get("source_url"),
                        "claim": best.get("summary", "")[:160],
                        "verified": best.get("verification_status") == "verified",
                    }
                )
        else:
            unknown.append(name)
            explanations.append(
                {
                    "name": name,
                    "category": item.get("hint_category", "未分类") or "未分类",
                    "role": "未收录",
                    "purpose": "",
                    "explanation": (
                        f"知识库暂未收录「{name}」的说明，系统不会凭空编造。"
                        "可以查看包装上的具体名称，或到知识库按关键词搜索；"
                        "如果它属于复合配料的括号内容，也会影响营养与致敏信息。"
                    ),
                    "confidence": "low",
                    "evidence": "unverified",
                    "source_refs": [],
                    "caution": "该成分未收录，建议人工核实",
                }
            )

    if unknown:
        unconfirmed.append(f"有 {len(unknown)} 种成分未在知识库中找到说明：{'、'.join(unknown[:10])}")
    if nutrition.get("missing_core"):
        unconfirmed.append("部分核心营养数值未识别，营养解读不完整")

    summary_parts = [f"共解析出 {len([i for i in ingredient_items if not i.get('is_category')])} 种配料"]
    if explanations:
        additives = [e for e in explanations if e["evidence"] == "knowledge_base"]
        summary_parts.append(f"其中 {len(additives)} 种可在知识库中找到客观说明")
    if unknown:
        summary_parts.append(f"{len(unknown)} 种暂未收录")

    return {
        "mode": "rule",
        "mode_label": MODE_LABELS["rule"],
        "model": None,
        "prompt_version": "rule-v1",
        "summary": _short_summary("，".join(summary_parts) + "。"),
        "tags": derive_tags(nutrition, ingredient_items),
        "personalization": build_personalization(
            health_profile or {},
            [str(item.get("name") or "") for item in ingredient_items if not item.get("is_category")],
            nutrition,
        ),
        "ingredients": explanations,
        "nutrition_notes": build_rule_nutrition_notes(nutrition),
        "unknown_items": unknown,
        "unconfirmed": unconfirmed,
        "citations": citations,
        "disclaimer": DISCLAIMER + " 当前结果由规则引擎生成，不是大模型输出。",
        "duration_ms": int((time.perf_counter() - start) * 1000),
        "raw_response": {"engine": "local_rules", "reason": reason},
        "error": reason,
    }


def build_rule_nutrition_notes(nutrition: dict) -> list[str]:
    """规则模式下的营养解读：只用标签上的数值做算术与常识说明，不推断健康结论。"""
    from ..rules.label_rules import THRESHOLDS

    if not nutrition or not nutrition.get("items"):
        return []

    basis = nutrition.get("basis")
    basis_labels = {"per_100g": "每 100g", "per_100ml": "每 100mL", "per_serving": "每份"}
    basis_text = basis_labels.get(basis, "计量基准未确认")
    items = {item["key"]: item for item in nutrition.get("items", []) if item.get("value") is not None}
    notes: list[str] = []

    energy = items.get("energy")
    protein = items.get("protein")
    fat = items.get("fat")
    carb = items.get("carbohydrate")
    sodium = items.get("sodium")

    basis_sentences = {
        "per_100g": "营养成分表按「每 100g」标示，可直接与其他按每 100g 标示的产品比较。",
        "per_100ml": "营养成分表按「每 100mL」标示（液体食品常用），与按每 100g 标示的产品比较前需按密度换算。",
        "per_serving": "营养成分表按「每份」标示，跨产品比较前需要先知道每份的重量或体积。",
    }
    notes.append(basis_sentences.get(basis, f"计量基准为「{basis_text}」，跨产品比较前需先统一基准。"))

    if energy:
        nrv = energy.get("nrv_percent")
        nrv_text = f"，NRV 约占 {nrv:g}%" if nrv is not None else ""
        notes.append(f"能量 {energy['value']:g}{energy['unit']}{nrv_text}。")
    if protein and fat and carb and energy:
        factors = THRESHOLDS["energy_factors_kj_per_g"]
        p = protein["value"] / 1000 if protein["unit"] == "mg" else protein["value"]
        f = fat["value"] / 1000 if fat["unit"] == "mg" else fat["value"]
        c = carb["value"] / 1000 if carb["unit"] == "mg" else carb["value"]
        total = p * factors["protein"] + f * factors["fat"] + c * factors["carbohydrate"]
        if total > 0:
            carbs_share = round(c * factors["carbohydrate"] / total * 100)
            main_source = "碳水化合物" if carbs_share >= 50 else "脂肪"
            share = carbs_share if carbs_share >= 50 else 100 - carbs_share
            notes.append(f"按 Atwater 系数折算，能量主要来自{main_source}（约 {share}%）。")
    if sodium:
        salt = sodium["value"] / 393 if sodium["unit"] == "mg" else sodium["value"] / 1000 / 393
        threshold = THRESHOLDS["sodium_high_mg_per_100g"]
        is_high = (
            sodium["unit"] == "mg"
            and sodium["value"] >= threshold
            and nutrition.get("basis") == "per_100g"
        )
        note = f"钠 {sodium['value']:g}{sodium['unit']}，约相当于 {salt:.2f}g 食盐。"
        if is_high:
            note += f"高于平台提示阈值 {threshold:.0f}mg/100g，需要控制钠摄入的人群可重点关注。"
        else:
            note += "是否偏高需结合每日总摄入量与食用量判断。"
        notes.append(note)
    missing = nutrition.get("missing_core") or []
    if missing:
        from .nutrition_parser import CORE_NAMES

        notes.append(
            "以下核心项目未识别到数值：" + "、".join(CORE_NAMES.get(key, key) for key in missing) + "，相关解读暂不完整。"
        )
    return notes[:5]


__all__ = [
    "AIServiceError",
    "ai_configured",
    "resolve_mode",
    "run_ai_analysis",
    "run_rule_analysis",
    "build_rule_nutrition_notes",
    "DISCLAIMER",
    "PROMPT_VERSION",
]
