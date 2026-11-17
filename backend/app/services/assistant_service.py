"""食安科普与辟谣助手：检索增强问答（RAG）服务。

设计原则（对应「不产生幻觉」的要求）：
1. 回答只可能来自 `assistant_entries` 表里的条目，检索不到就明确说“未收录”，绝不调用模型编造；
2. 默认使用「检索直答」：把条目的结论/原因/依据原样组织成回答，并附来源清单；
3. 可选 AI 改写（`ASSISTANT_MODE=ai`）：只允许基于检索到的段落改写，输出里
   的引用编号会被白名单过滤，逐句做 n-gram 依据校验，未落地的句子直接丢弃；
   丢弃过多时自动退回检索直答，并在回答里说明。
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app
from sqlalchemy import func, select

from ..extensions import db
from ..models.assistant import (
    ASSISTANT_CATEGORIES,
    VERIFICATION_LABELS,
    AssistantEntry,
    ChatMessage,
    ChatSession,
)
from ..models.pantry import HEALTH_CONDITIONS, HEALTH_GOALS, HealthProfile, PantryItem
from ..models.user import utcnow
from ..seed.assistant_seed import ASSISTANT_ENTRIES
from . import cooking_service, recipe_agent_service

logger = logging.getLogger(__name__)

MODE_LABELS = {
    "retrieval": "检索直答（逐字来自知识库，不调用大模型）",
    "ai": "RAG 知识提炼（基于权威知识库，已溯源防幻觉）",
    "ai_rerank": "AI 匹配相近条目后作答（内容来自条目原文）",
    "ai_general": "通用大模型回答（AI 补充）",
    "recipe": "家常菜谱 · 新手分步做法",
    "recipe_ai": "AI 烹饪步骤 · 新手版",
    "recipe_options": "推荐做法 · 先选一个",
    "context_ai": "当前菜谱 · 专属问答",
    "pantry_agent": "食材管家推荐 · 结合现有库存",
    "inventory_ai": "结合食材库存 · AI 科普",
    "inventory_rule": "结合食材库存 · 规则兜底",
    "profile_ai": "健康画像 · 专属营养建议",
}

DISCLAIMER = (
    "回答仅基于本站收录的公开资料整理，用于科普参考，不构成医疗诊断或食品安全结论；"
    "如有身体不适请及时就医，具体标准以官方原文为准。"
)

MATCH_THRESHOLD = 4.0
MATCH_COVERAGE = 0.5

# 口语化问法里的填充词：算覆盖率前先去掉，避免“和 / 可以 / 吗”这类字把覆盖率冲淡
_QUERY_FILLERS = (
    "到底", "究竟", "请问", "麻烦", "能不能", "可不可以", "会不会", "是不是", "要不要",
    "一起", "同时", "之后", "然后", "为什么", "怎么样", "怎么", "如何", "可以", "需要",
    "应该", "我们", "你们", "他们", "这个", "那个", "哪些", "什么", "一下", "有点",
    "吗", "呢", "吧", "啊", "呀", "哦", "的", "了", "着", "过", "和", "与", "跟", "同",
    "及", "或", "还", "也", "就", "都", "很", "太", "最",
)

_lock = threading.Lock()
_rate_buckets: dict[int, list[datetime]] = {}
_index_cache: dict = {"version": None, "index": None}


# ---------------------------------------------------------------- 分词与索引
_PUNCT_RE = re.compile(r"[\s，。！？、；：,.!?;:\"'“”‘’（）()\[\]【】《》<>/\\|+*~`^%$#@=_—-]+")


def _normalize(text: str) -> str:
    return _PUNCT_RE.sub("", unicodedata.normalize("NFKC", (text or "").lower()))


def _tokens(text: str) -> list[str]:
    """中文按字符二元组切分，英文/数字按词切分。"""
    normalized = _normalize(text)
    if not normalized:
        return []
    tokens: list[str] = []
    buffer = ""
    for ch in normalized:
        if "\u4e00" <= ch <= "\u9fff":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(ch)
        else:
            buffer += ch
    if buffer:
        tokens.append(buffer)
    # 中文二元组（比单字更有区分度）
    cjk = [ch for ch in normalized if "\u4e00" <= ch <= "\u9fff"]
    for index in range(len(cjk) - 1):
        tokens.append(cjk[index] + cjk[index + 1])
    return tokens


def _entry_tokens(entry: AssistantEntry) -> list[str]:
    weighted: list[str] = []
    for field, weight in (
        (entry.title, 4),
        (entry.aliases.replace(",", ""), 5),
        (entry.keywords, 3),
        (entry.summary, 2),
        (entry.detail, 1),
        (entry.evidence, 1),
    ):
        field_tokens = _tokens(field or "")
        weighted.extend(field_tokens * weight)
    return weighted


def _alias_list(entry: AssistantEntry) -> list[str]:
    return [item.strip() for item in (entry.aliases or "").split(",") if item.strip()]


def _build_index() -> dict:
    entries = AssistantEntry.query.order_by(AssistantEntry.sort_order.asc()).all()
    version = (len(entries), max((entry.updated_at.timestamp() for entry in entries), default=0))
    if _index_cache["version"] == version and _index_cache["index"] is not None:
        return _index_cache["index"]

    docs: dict[int, list[str]] = {}
    df: Counter = Counter()
    for entry in entries:
        tokens = _entry_tokens(entry)
        docs[entry.id] = tokens
        df.update(set(tokens))
    total = max(len(entries), 1)
    avg_len = sum(len(tokens) for tokens in docs.values()) / total or 1.0
    index = {
        "entries": {entry.id: entry for entry in entries},
        "docs": docs,
        "df": df,
        "total": total,
        "avg_len": avg_len,
        "version": version,
    }
    _index_cache["version"] = version
    _index_cache["index"] = index
    return index


def _idf(index: dict, token: str) -> float:
    df = index["df"].get(token, 0)
    return math.log(1 + (index["total"] - df + 0.5) / (df + 0.5))


def _bigrams(text: str) -> set[str]:
    cjk = [ch for ch in _normalize(text) if "\u4e00" <= ch <= "\u9fff"]
    return {cjk[index] + cjk[index + 1] for index in range(len(cjk) - 1)}


def _content_bigrams(text: str) -> set[str]:
    """去掉口语填充词后再取二元组，用于判断「问题是否真的被条目覆盖」。"""
    normalized = _normalize(text)
    for filler in _QUERY_FILLERS:
        normalized = normalized.replace(filler, "")
    cjk = [ch for ch in normalized if "\u4e00" <= ch <= "\u9fff"]
    return {cjk[index] + cjk[index + 1] for index in range(len(cjk) - 1)}


def _entry_text(entry: AssistantEntry) -> str:
    return " ".join(
        [
            entry.title or "",
            (entry.aliases or "").replace(",", " "),
            entry.keywords or "",
            entry.summary or "",
            entry.detail or "",
            entry.evidence or "",
        ]
    )


def search(question: str, *, limit: int = 3) -> list[dict]:
    """返回按相关度排序的候选条目（含分数），供回答与“未收录”建议使用。"""
    index = _build_index()
    if not index["entries"]:
        return []
    query_tokens = _tokens(question)
    if not query_tokens:
        return []
    query_set = list(dict.fromkeys(query_tokens))
    normalized_query = _normalize(question)
    query_bigrams = _content_bigrams(question)

    scored: list[dict] = []
    for entry_id, tokens in index["docs"].items():
        tf = Counter(tokens)
        length = len(tokens)
        score = 0.0
        for token in query_set:
            freq = tf.get(token, 0)
            if not freq:
                continue
            idf = _idf(index, token)
            denominator = freq + 1.2 * (1 - 0.75 + 0.75 * length / index["avg_len"])
            score += idf * freq * 2.2 / denominator if denominator else 0

        entry = index["entries"][entry_id]
        alias_hit = False
        # 别名 / 标题命中给强加权：口语化问法往往只有别名能对上
        for alias in _alias_list(entry):
            alias_norm = _normalize(alias)
            if len(alias_norm) >= 3 and (alias_norm in normalized_query or normalized_query in alias_norm):
                score += 8.0
                alias_hit = True
                break
        title_norm = _normalize(entry.title)
        title_hit = bool(title_norm) and (title_norm in normalized_query or normalized_query in title_norm)
        if title_hit:
            score += 6.0

        entry_bigrams = _content_bigrams(_entry_text(entry))
        coverage = (
            len(query_bigrams & entry_bigrams) / len(query_bigrams) if query_bigrams else 0.0
        )
        if score <= 0:
            continue
        matched = score >= MATCH_THRESHOLD and (alias_hit or title_hit or coverage >= MATCH_COVERAGE)
        scored.append(
            {
                "entry": entry,
                "score": round(score, 3),
                "alias_hit": alias_hit,
                "title_hit": title_hit,
                "coverage": round(coverage, 3),
                "matched": matched,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


# ---------------------------------------------------------------- 回答组装
def _sources(entry: AssistantEntry) -> list[dict]:
    from ..models.assistant import SOURCE_KINDS

    result = []
    for index, source in enumerate(entry.sources or [], start=1):
        if not isinstance(source, dict):
            continue
        result.append(
            {
                "id": f"K{index}",
                "name": source.get("name", ""),
                "publisher": source.get("publisher", ""),
                "year": source.get("year"),
                "url": source.get("url"),
                "kind": source.get("kind", ""),
                "kind_label": SOURCE_KINDS.get(source.get("kind", ""), source.get("kind", "")),
                "verified": bool(source.get("verified")),
                "verified_label": "已核对到具体文件" if source.get("verified") else "机构公开资料",
            }
        )
    return result


def _sections(entry: AssistantEntry) -> list[dict]:
    sections = [
        {"key": "conclusion", "label": "结论", "text": entry.summary},
        {"key": "explanation", "label": "为什么", "text": entry.detail},
        {"key": "evidence", "label": "依据", "text": entry.evidence},
    ]
    if entry.caveat:
        sections.append({"key": "caution", "label": "注意事项", "text": entry.caveat})
    return [section for section in sections if section["text"]]


def _plain_content(entry: AssistantEntry) -> str:
    parts = [f"结论：{entry.summary}", f"为什么：{entry.detail}", f"依据：{entry.evidence}"]
    if entry.caveat:
        parts.append(f"注意：{entry.caveat}")
    return "\n\n".join(part for part in parts if part and not part.endswith("："))


def _llm_config() -> dict:
    """科普助手专用大模型配置：优先 ASSISTANT_LLM_*，留空则回退到 AI_*。"""
    config = current_app.config
    base = str(config.get("ASSISTANT_LLM_BASE_URL") or config.get("AI_BASE_URL") or "").strip().rstrip("/")
    key = str(config.get("ASSISTANT_LLM_API_KEY") or config.get("AI_API_KEY") or "").strip()
    model = str(config.get("ASSISTANT_LLM_MODEL") or config.get("AI_MODEL") or "").strip()
    timeout = config.get("ASSISTANT_LLM_TIMEOUT") or 0
    if not timeout:
        timeout = config.get("AI_TIMEOUT", 50)
    temperature = config.get("ASSISTANT_LLM_TEMPERATURE")
    if temperature is None or float(temperature or 0) == 0:
        temperature = 0.2
    return {
        "base": base,
        "key": key,
        "model": model,
        "timeout": int(timeout),
        "temperature": float(temperature),
    }


def _resolve_mode() -> str:
    configured = str(current_app.config.get("ASSISTANT_MODE", "auto")).strip().lower()
    if configured == "retrieval":
        return "retrieval"
    if configured in {"ai", "auto"} and _allow_ai():
        return "ai"
    return "retrieval"


def _allow_ai() -> bool:
    return bool(_llm_config()["key"])


def _allow_fallback() -> bool:
    """知识库未命中时，是否允许大模型在相近条目范围内判断（默认允许）。"""
    return _allow_ai() and str(current_app.config.get("ASSISTANT_AI_FALLBACK", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _allow_general() -> bool:
    """知识库与相近条目都答不了时，是否允许通用大模型回答（会明确标注未核验）。"""
    return _allow_ai() and str(current_app.config.get("ASSISTANT_GENERAL_ANSWER", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


# ---------------------------------------------------------------- AI 改写与校验
MEDICAL_SAFETY = (
    "如果用户询问用药、药物相互作用、中毒急救、误食、严重过敏等医疗问题，"
    "不要给具体药物、剂量或治疗方案，必须明确引导用户立即拨打120或前往医院，"
    "并咨询医生或药师；食品安全科普不能替代医疗诊断。"
)

AI_SYSTEM = (
    "你是食品安全科普助手。只能使用用户消息中提供的资料回答问题，"
    "不得引入资料以外的任何事实、数字、标准号或机构名称。对话历史只用于理解指代，不得把历史中的助手回答当作资料或事实依据。"
    "每个要点后面标注对应资料编号，如 [K1]；资料没有提到的内容直接说“资料中未提及”。"
    "不要给出医疗诊断，不要编造引用。回答控制在 200 字以内，分 2-3 段。"
    + MEDICAL_SAFETY
)


def _context(entries: list[AssistantEntry]) -> str:
    blocks = []
    for index, entry in enumerate(entries, start=1):
        blocks.append(
            f"[K{index}] 标题：{entry.title}\n结论：{entry.summary}\n原因：{entry.detail}\n依据：{entry.evidence}"
        )
    return "\n\n".join(blocks)


def _chat(messages: list[dict]) -> str:
    cfg = _llm_config()
    if not cfg["key"]:
        raise RuntimeError("未配置科普助手大模型 API Key")
    base = cfg["base"]
    url = base if base.endswith("/chat/completions") else base + "/chat/completions"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": cfg["model"],
            "temperature": cfg["temperature"],
            "messages": messages,
        },
        timeout=cfg["timeout"],
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content or "").strip()


def _trigrams(text: str) -> set[str]:
    normalized = _normalize(text)
    return {normalized[i : i + 3] for i in range(max(len(normalized) - 2, 0))}


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")


def _ground_filter(text: str, context: str) -> tuple[str, int, int]:
    """逐句校验：与资料的三元组重合度过低的句子会被丢弃。"""
    context_grams = _trigrams(context)
    kept: list[str] = []
    dropped = 0
    for raw in _SENTENCE_SPLIT.split(text):
        sentence = raw.strip()
        if not sentence:
            continue
        if len(_normalize(sentence)) < 8:
            kept.append(sentence)
            continue
        grams = _trigrams(sentence)
        if not grams:
            kept.append(sentence)
            continue
        overlap = len(grams & context_grams) / len(grams)
        if overlap >= 0.2:
            kept.append(sentence)
        else:
            dropped += 1
    return "".join(kept).strip(), len(kept), dropped


def _clean_citations(text: str, allowed: int) -> str:
    def replace(match: re.Match) -> str:
        number = int(match.group(1))
        return match.group(0) if 1 <= number <= allowed else ""

    return re.sub(r"\[K(\d{1,2})\]", replace, text)


def _ai_answer(question: str, entries: list[AssistantEntry], history: str = "") -> tuple[str, dict] | None:
    if not entries:
        return None
    context = _context(entries)
    prefix = f"对话历史（仅供理解指代，不得作为依据）：\n{history}\n\n" if history else ""
    messages = [
        {"role": "system", "content": AI_SYSTEM},
        {"role": "user", "content": f"{prefix}资料：\n{context}\n\n问题：{question}"},
    ]
    try:
        raw = _chat(messages)
    except Exception as exc:  # noqa: BLE001 - 任何失败都退回检索直答
        logger.warning("科普助手 AI 改写失败，退回检索直答：%s", exc.__class__.__name__)
        return None
    cleaned = _clean_citations(raw, len(entries))
    grounded, kept, dropped = _ground_filter(cleaned, context)
    if not grounded or kept < 2 or dropped > kept:
        logger.info("AI 改写未通过依据校验（保留 %s / 丢弃 %s），退回检索直答", kept, dropped)
        return None
    return grounded, {"kept_sentences": kept, "dropped_sentences": dropped, "citations": len(entries)}


AI_RERANK_SYSTEM = (
    "你是食品安全知识库的检索助手。用户会给出一个问题和若干条候选知识条目，"
    "请判断哪一条最有可能回答这个问题。只输出一个阿拉伯数字编号；"
    "如果这些条目都无法回答，只输出 NONE。不要输出任何解释。"
)


def _ai_pick_entry(question: str, candidates: list[AssistantEntry], history: str = "") -> tuple[AssistantEntry | None, str | None]:
    """检索未直接命中时，让模型在候选条目里做「选择」。返回 (条目, 错误信息)。"""
    if not candidates:
        return None, None
    lines = []
    for index, entry in enumerate(candidates, start=1):
        lines.append(f"{index}. 标题：{entry.title}\n   结论：{entry.summary}")
    try:
        raw = _chat(
            [
                {"role": "system", "content": AI_RERANK_SYSTEM},
                {"role": "user", "content": (f"对话历史（仅供理解指代）：\n{history}\n\n" if history else "") + f"问题：{question}\n\n候选条目：\n" + "\n".join(lines)},
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("科普助手条目匹配失败：%s", exc.__class__.__name__)
        return None, str(exc)[:200]
    text = (raw or "").strip()
    upper = text.upper()
    if "NONE" in upper:
        return None, None
    match = re.search(r"\d{1,2}", text)
    if not match:
        return None, None
    index = int(match.group(0))
    if 1 <= index <= len(candidates):
        return candidates[index - 1], None
    return None, None


AI_GENERAL_SYSTEM = (
    "你是严谨的食品安全与饮食健康科普助手。用普通人能懂的话回答问题，分 2-3 点，200 字以内。"
    "必须遵守：1) 不编造标准号、具体数值、机构名称和文献，没有把握就说“这一点需要查证”；"
    "2) 涉及药物、酒精、中毒、过敏、婴幼儿、孕妇时，必须提醒咨询医生或药师、必要时及时就医；"
    "3) 不做疾病诊断，不推荐具体药物或剂量；4) 明确说明这是一般性科普，不替代专业意见。"
    + MEDICAL_SAFETY
)


AI_PROFILE_SYSTEM = (
    "你是用户的专属营养师，必须优先依据下面提供的《用户健康档案》回答问题。"
    "回答开头必须直接写“根据您的档案（列出档案中的疾病/状况、健康目标和过敏原）”，"
    "不能只给通用建议，不能输出 Step 1 / Step 2 这类空泛模板。"
    "档案中的过敏原必须使用“绝对禁止/必须避免”表述；高血压、胃炎等状况要给出对应的低钠、清淡、易消化建议。"
    "如果档案没有提供某项信息，不要逐项罗列“未填写”，统一在结尾用温馨提醒说明；绝不能自行编造疾病、过敏原或用药信息。"
    "只要当前请求已提供健康档案，严禁回答“没有获取到画像/没有你的健康信息”，必须直接依据档案作答。"
    "回答要具体、可执行，控制在 250 字以内。"
    + MEDICAL_SAFETY
)


def _string_list(value: object, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for raw in value[:limit]:
        text = str(raw or "").strip()[:60]
        if text and text not in items:
            items.append(text)
    return items


def _health_profile(
    user_id: int,
    provided: dict | None = None,
) -> tuple[dict | None, str]:
    """优先使用前端本次携带的实时画像，缺失时回退数据库画像。"""
    profile = None
    conditions: list[str] = []
    goals: list[str] = []
    allergies: list[str] = []
    notes = ""

    if isinstance(provided, dict):
        raw_conditions = _string_list(provided.get("conditions"))
        raw_goals = _string_list(provided.get("goals"))
        allergies = _string_list(provided.get("allergies"))
        notes = str(provided.get("notes") or "").strip()[:300]

        condition_labels = _string_list(provided.get("condition_labels"))
        goal_labels = _string_list(provided.get("goal_labels"))
        conditions = condition_labels or [
            HEALTH_CONDITIONS.get(item, item)
            for item in raw_conditions
        ]
        goals = goal_labels or [
            HEALTH_GOALS.get(item, item)
            for item in raw_goals
        ]

    if not (conditions or goals or allergies or notes):
        profile = HealthProfile.query.filter_by(user_id=user_id).first()
        if profile is not None:
            conditions = [
                HEALTH_CONDITIONS.get(item, item)
                for item in (profile.conditions or [])
            ]
            goals = [
                HEALTH_GOALS.get(item, item)
                for item in (profile.goals or [])
            ]
            allergies = [str(item) for item in (profile.allergies or [])]
            notes = str(profile.notes or "").strip()

    lines = []
    if conditions:
        lines.append("疾病/状况：" + "、".join(conditions))
    if goals:
        lines.append("健康目标：" + "、".join(goals))
    if allergies:
        lines.append("过敏原/忌口：" + "、".join(allergies))
    if notes:
        lines.append("补充说明：" + notes)
    text = "\n".join(lines)
    if not text:
        return None, ""
    return {
        "conditions": conditions,
        "goals": goals,
        "allergies": allergies,
        "notes": notes,
        "source": "client" if isinstance(provided, dict) and provided else "database",
    }, text


def _wants_health_profile(question: str) -> bool:
    return bool(
        re.search(
            r"健康画像|健康档案|我的档案|我的画像|我的健康|我的身体|身体状况|身体情况|"
            r"基础疾病|饮食禁忌|我的忌口|忌口|营养建议|怎么吃|饮食搭配|"
            r"推荐.*食谱|食谱结构|三餐搭配|"
            r"根据.*(?:画像|档案|身体)|整理.*(?:禁忌|忌口)|"
            r"(?:我|本人).*(?:过敏|忌口)",
            question,
        )
    )


AI_PROFILE_TABOO_SYSTEM = (
    "你是用户的专属营养师。当前用户询问的是饮食禁忌/不能吃什么。"
    "只做负向排雷：直接列出档案中的过敏原、必须禁止的食物和容易忽略的隐形雷区"
    "（酱料、汤底、加工食品、交叉污染），并简要说明原因。"
    "禁止写推荐食谱、三餐搭配、“建议多吃”等正向内容，不要输出通用 Step 1 / Step 2 模板。"
    "过敏原必须使用“绝对禁止/必须避免”表述。不要写“档案未填写”；"
    "结尾使用温馨提醒，语气自然。"
    "回答控制在 250 字以内，分点清晰。"
    + MEDICAL_SAFETY
)

AI_PROFILE_NUTRITION_SYSTEM = (
    "你是用户的专属营养师。当前用户询问的是营养建议/怎么吃/食谱搭配。"
    "只做正向推荐：直接告诉用户推荐吃什么，给出具体食物、三餐结构、每日蔬菜/蛋白质量、"
    "烹饪方式和替换方案，例如清蒸鱼、豆腐、瘦肉、燕麦杂粮、绿叶菜。"
    "严禁罗列禁忌清单，不要使用“不能吃/禁止/避免/忌口/雷区”等负向词；"
    "如果档案有过敏原，只在最后用一句“安全前提：避开某某”提醒，不要展开。"
    "结合用户的疾病和饮食目标做差异化搭配，不要输出通用 Step 1 / Step 2 模板。"
    "不要写“档案未填写”；结尾使用温馨提醒，语气自然。"
    "回答控制在 250 字以内，分点清晰。"
    + MEDICAL_SAFETY
)


def _profile_intent(question: str) -> str:
    if re.search(
        r"禁忌|不能吃|避免|忌口|不能碰|过敏|红灯|禁食|雷区",
        question,
    ):
        return "taboo"
    if re.search(
        r"营养建议|怎么吃|吃什么|饮食建议|搭配|推荐.*食谱|食谱结构|三餐|绿灯",
        question,
    ):
        return "nutrition"
    return "general"


def _profile_system_prompt(question: str) -> str:
    intent = _profile_intent(question)
    if intent == "taboo":
        return AI_PROFILE_TABOO_SYSTEM
    if intent == "nutrition":
        return AI_PROFILE_NUTRITION_SYSTEM
    return AI_PROFILE_SYSTEM


def _profile_rule_answer(
    data: dict | None,
    *,
    intent: str = "general",
) -> str:
    if not data:
        return "未获取到您的实时健康档案，请前往【健康画像】页面完善并保存您的信息。"

    if intent == "nutrition":
        conditions = "、".join(data.get("conditions", [])) or "健康需求"
        goals = "、".join(data.get("goals", [])) or "均衡饮食"
        allergies = "、".join(data.get("allergies", []))
        lines = [
            f"根据您的档案（{conditions}；{goals}），以下是绿灯饮食建议：",
            "1. 早餐：无糖豆浆或燕麦奶 + 鸡蛋 + 一小份杂粮或粥，避免油炸和含糖饮料。",
            "2. 午餐：清蒸鱼/鸡胸肉/豆腐 + 两份蔬菜 + 一拳主食，少盐少油。",
            "3. 晚餐：清淡汤菜 + 瘦肉或豆制品，七分饱，避免辛辣、过烫和难消化食物。",
            "搭配原则：优先蒸、煮、炖；每餐保证优质蛋白和蔬菜，主食定量。",
        ]
        if allergies:
            lines.append(f"安全前提：避开{allergies}，购买加工食品时核对配料表。")
        lines.append(_profile_warm_ending(data))
        return "\n".join(lines)

    parts = []
    if data.get("conditions"):
        parts.append(f"您有{ '、'.join(data['conditions']) }，建议优先选择低钠、清淡、易消化的食物，少吃腌制、油炸和高盐调味品")
    if data.get("allergies"):
        parts.append(f"您对{ '、'.join(data['allergies']) }过敏，绝对禁止食用含有这些成分的食物，购买包装食品时务必逐项核对配料表")
    if data.get("goals"):
        parts.append(f"结合您的{ '、'.join(data['goals']) }目标，建议每餐保证优质蛋白和蔬菜，控制精制碳水与添加糖")
    if data.get("notes"):
        parts.append(f"档案补充说明：{data['notes']}")
    if not parts:
        return (
            "您的健康档案内容较少，建议先补充疾病、目标和过敏原，我再给出更精准的建议。"
            "\n\n" + _profile_warm_ending(data)
        )
    return (
        "根据您的档案（"
        + "、".join(
            [*data.get("conditions", []), *data.get("goals", []), *data.get("allergies", [])]
        )
        + "）：\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(parts, start=1))
        + "\n\n"
        + _profile_warm_ending(data)
    )


PROFILE_WARM_ENDING = (
    "💡 温馨提示：您的档案中暂未记录胃部与用药情况，"
    "如涉及特殊用药，请以医生医嘱为准。"
)

PROFILE_WARM_ENDING_STOMACH = "💡 温馨提示：如涉及特殊用药，请以医生医嘱为准。"


def _profile_warm_ending(data: dict | None) -> str:
    conditions = "".join(str(item) for item in (data or {}).get("conditions", []))
    if "胃" in conditions:
        return PROFILE_WARM_ENDING_STOMACH
    return PROFILE_WARM_ENDING


def _finalize_profile_answer(text: str, data: dict | None) -> str:
    # 清掉模型生硬的“未填写/未记录”句子，统一使用温馨结尾
    cleaned = re.sub(
        r"[^。\n]*(?:未填写|未记录|暂未记录|没有记录)[^。\n]*[。！？]?",
        "",
        str(text or ""),
    ).strip()
    ending = _profile_warm_ending(data)
    if ending not in cleaned:
        cleaned = f"{cleaned}\n\n{ending}" if cleaned else ending
    return cleaned


def _profile_answer(
    question: str,
    user_id: int,
    history_text: str = "",
    profile_data: dict | None = None,
    profile_text: str = "",
) -> tuple[str, str | None]:
    data = profile_data
    if not profile_text:
        data, profile_text = _health_profile(user_id)
    intent = _profile_intent(question)
    fallback = _profile_rule_answer(data, intent=intent)
    if not profile_text:
        return fallback, None

    user_content = (
        (f"对话历史（仅供理解指代，不得作为健康事实）：\n{history_text}\n\n" if history_text else "")
        + f"用户健康档案：\n{profile_text}\n\n用户问题：{question}"
    )
    try:
        text = _chat([
            {"role": "system", "content": _profile_system_prompt(question)},
            {"role": "user", "content": user_content},
        ])
    except Exception as exc:  # noqa: BLE001
        logger.warning("健康画像专属回答失败，使用档案规则兜底：%s", exc.__class__.__name__)
        return fallback, str(exc)[:200]

    if not text:
        return fallback, "模型返回为空"

    summary = "、".join(
        [
            *data.get("conditions", []),
            *data.get("goals", []),
            *data.get("allergies", []),
        ]
    )
    cleaned = text.strip()
    if cleaned.startswith("根据"):
        return _finalize_profile_answer(cleaned, data), None
    prefix = f"根据您的档案（{summary}），" if summary else "根据您的健康档案，"
    return _finalize_profile_answer(prefix + cleaned, data), None


def _ai_general_answer(
    question: str,
    history: str = "",
    profile_text: str = "",
) -> tuple[str | None, str | None]:
    """最后一层兜底：通用大模型回答（明确标注未引用本站资料）。"""
    system = AI_GENERAL_SYSTEM
    if profile_text:
        system += (
            "\n\n以下是当前用户的健康档案，回答涉及饮食建议时必须结合，"
            "并在开头直接引用档案中的疾病、目标和过敏原：\n" + profile_text
        )
    try:
        text = _chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": (f"对话历史（仅供理解指代）：\n{history}\n\n" if history else "") + question},
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("科普助手通用回答失败：%s", exc.__class__.__name__)
        return None, str(exc)[:200]
    if not text:
        return None, "模型返回为空"
    return text, None


# ---------------------------------------------------------------- 对外接口
def upsert_entries(entries: list[dict] | None = None) -> dict:
    """按 slug 幂等写入，便于后续替换为权威资料。"""
    entries = entries if entries is not None else ASSISTANT_ENTRIES
    created = updated = 0
    for data in entries:
        entry = AssistantEntry.query.filter_by(slug=data["slug"]).first()
        payload = {
            "title": data["title"],
            "aliases": data.get("aliases", ""),
            "keywords": data.get("keywords", ""),
            "category": data.get("category", "safety"),
            "summary": data.get("summary", ""),
            "detail": data.get("detail", ""),
            "evidence": data.get("evidence", ""),
            "caveat": data.get("caveat", ""),
            "sources": data.get("sources", []),
            "verification_status": data.get("verification_status", "pending"),
            "is_featured": bool(data.get("is_featured")),
            "sort_order": data.get("sort_order", 100),
        }
        if entry is None:
            db.session.add(AssistantEntry(slug=data["slug"], **payload))
            created += 1
        else:
            for key, value in payload.items():
                setattr(entry, key, value)
            updated += 1
    db.session.commit()
    _index_cache["version"] = None
    return {"total": AssistantEntry.query.count(), "created": created, "updated": updated}


def stats() -> dict:
    total = db.session.execute(select(func.count(AssistantEntry.id))).scalar_one()
    verified = db.session.execute(
        select(func.count(AssistantEntry.id)).where(AssistantEntry.verification_status == "verified")
    ).scalar_one()
    return {
        "entries": total,
        "verified": verified,
        "pending": total - verified,
        "categories": [
            {"key": key, "label": label} for key, label in ASSISTANT_CATEGORIES.items()
        ],
        "verification_labels": VERIFICATION_LABELS,
        "mode": _resolve_mode(),
        "mode_label": MODE_LABELS[_resolve_mode()],
    }


def featured_questions(limit: int = 6) -> list[dict]:
    entries = (
        AssistantEntry.query.filter_by(is_featured=True)
        .order_by(AssistantEntry.sort_order.asc())
        .limit(limit)
        .all()
    )
    if len(entries) < limit:
        extra = (
            AssistantEntry.query.filter(AssistantEntry.is_featured.is_(False))
            .order_by(AssistantEntry.sort_order.asc())
            .limit(limit - len(entries))
            .all()
        )
        entries = entries + extra
    return [
        {
            "slug": entry.slug,
            "title": entry.title,
            "question": entry.aliases.split(",")[0] if entry.aliases else entry.title,
            "category_label": ASSISTANT_CATEGORIES.get(entry.category, entry.category),
        }
        for entry in entries
    ]


def _throttle(user_id: int) -> None:
    now = datetime.now(timezone.utc)
    window = now - timedelta(seconds=60)
    with _lock:
        bucket = [item for item in _rate_buckets.get(user_id, []) if item > window]
        if len(bucket) >= 20:
            _rate_buckets[user_id] = bucket
            raise ValueError("提问太频繁，请稍后再试（每分钟最多 20 个问题）")
        bucket.append(now)
        _rate_buckets[user_id] = bucket


REFERENTIAL_MARKERS = (
    "这个",
    "那个",
    "它",
    "这种",
    "该类",
    "上面",
    "刚才",
    "前面",
    "还有",
    "为什么",
    "真的",
    "可以吗",
    "能吃吗",
    "怎么办",
    "然后",
    "具体",
    "详细",
    "展开",
    "呢",
)


def _recent_history(user_id: int, session_id: int | None, *, limit: int = 6) -> list[dict]:
    if not session_id:
        return []
    session = db.session.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        return []
    rows = (
        ChatMessage.query.filter_by(session_id=session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    result = []
    for row in rows:
        if row.role not in {"user", "assistant"} or not (row.content or "").strip():
            continue
        payload = row.payload or {}
        entry = payload.get("entry") if isinstance(payload, dict) else None
        result.append(
            {
                "role": row.role,
                "content": row.content or "",
                "entry_title": (entry or {}).get("title") if isinstance(entry, dict) else None,
                "recipe_title": payload.get("recipe_title") if isinstance(payload, dict) else None,
            }
        )
    return result


def _history_text(history: list[dict], *, limit: int = 4) -> str:
    lines = []
    for item in history[-limit:]:
        content = item["content"].strip().replace("\n", " ")
        if len(content) > 260:
            content = content[:260] + "…"
        lines.append(f"{'用户' if item['role'] == 'user' else '助手'}：{content}")
    return "\n".join(lines)


FOLLOW_UP_PREFIXES = (
    "那",
    "为什么",
    "怎么",
    "还有",
    "然后",
    "具体",
    "展开",
    "真的",
    "它",
    "这个",
    "那个",
    "这种",
    "上面",
    "前面",
    "还能",
    "能",
    "可以",
    "会",
    "要",
    "该",
    "是否",
    "一天",
    "一次",
    "多少",
    "多久",
)
FOLLOW_UP_EXACT = {"可以吗", "能吃吗", "能吗", "行吗", "安全吗", "然后呢", "还有呢", "为什么", "怎么回事"}


def _looks_like_follow_up(text: str) -> bool:
    text = text.strip()
    if text in FOLLOW_UP_EXACT:
        return True
    if text.startswith(FOLLOW_UP_PREFIXES):
        return True
    return any(marker in text for marker in ("这个", "那个", "它", "这种", "上面", "刚才", "前面"))


def _needs_context(question: str, history: list[dict]) -> bool:
    if not history:
        return False
    return _looks_like_follow_up(question)


def _is_follow_up(text: str) -> bool:
    return _looks_like_follow_up(text)


def _contextual_query(history: list[dict], question: str) -> str:
    # 找最近一个“带主题”的用户问题，跳过“为什么/那这个呢”这类追问，
    # 不要把更早的话题一起拼进来。
    user_questions = [item["content"].strip() for item in history if item["role"] == "user" and item["content"].strip()]
    topic = ""
    for content in reversed(user_questions):
        if not _is_follow_up(content):
            topic = content
            break
    if not topic and user_questions:
        topic = user_questions[-1]
    combined = f"{topic} {question}".strip() if topic else question
    return combined[-300:]


def _recipe_answer(question: str, user_id: int, session_id: int | None, cooking: dict) -> dict:
    session = _resolve_session(user_id, session_id, question)
    db.session.add(ChatMessage(session_id=session.id, role="user", content=question, mode="user"))
    mode = str(cooking.get("mode") or "recipe")
    mode_note = (
        "菜谱为新手烹饪参考，不是本站知识库核验的食品安全结论；"
        "生熟分开、肉类蛋类彻底加热，具体以食材实际状态为准。"
    )
    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=cooking["answer"],
        mode=mode,
        matched_slug=None,
        sources=[],
        payload={
            "sections": cooking.get("sections") or [],
            "evidence": "",
            "ai": None,
            "mode_note": mode_note,
            "matched": True,
            "coverage": "recipe",
            "ai_error": cooking.get("ai_error"),
            "entry": None,
            "retrieval": [],
            "related": [],
            "context_used": bool(cooking.get("context_used")),
            "recipe_title": cooking.get("title"),
            "recipe_source": cooking.get("source_label"),
            "recipe_data": cooking.get("recipe"),
            "recipe_summary": cooking_service._recipe_summary(cooking.get("recipe") or {}),
            "recipe_versions": cooking.get("versions"),
        },
    )
    db.session.add(message)
    session.updated_at = utcnow()
    db.session.commit()
    _index_cache["version"] = None
    return {
        "session_id": session.id,
        "message_id": message.id,
        "matched": True,
        "coverage": "recipe",
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "mode_note": mode_note,
        "answer": cooking["answer"],
        "sections": cooking.get("sections") or [],
        "evidence": "",
        "sources": [],
        "entry": None,
        "related": [],
        "disclaimer": DISCLAIMER,
        "ai_check": None,
        "ai_error": cooking.get("ai_error"),
        "context_used": bool(cooking.get("context_used")),
        "recipe_title": cooking.get("title"),
        "recipe_source": cooking.get("source_label"),
        "recipe_data": cooking.get("recipe"),
        "recipe_summary": cooking_service._recipe_summary(cooking.get("recipe") or {}),
        "recipe_versions": cooking.get("versions"),
    }


def _recipe_options_answer(question: str, user_id: int, session_id: int | None, cooking: dict) -> dict:
    session = _resolve_session(user_id, session_id, question)
    db.session.add(ChatMessage(session_id=session.id, role="user", content=question, mode="user"))
    options = cooking.get("options") or []
    subject = cooking.get("subject") or "这道食材"
    answer = cooking.get("answer") or f"先选一个{subject}的做法，我再展开步骤。"
    mode_note = "先选做法，再展开详细步骤；菜谱为烹饪参考，不是食品安全结论。"
    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        mode="recipe_options",
        matched_slug=None,
        sources=[],
        payload={
            "sections": [],
            "evidence": "",
            "ai": None,
            "mode_note": mode_note,
            "matched": True,
            "coverage": "recipe_options",
            "ai_error": cooking.get("ai_error"),
            "entry": None,
            "retrieval": [],
            "related": [],
            "context_used": bool(cooking.get("context_used")),
            "recipe_title": cooking.get("title"),
            "recipe_subject": subject,
            "recipe_options": options,
            "recipe_source": cooking.get("source_label"),
        },
    )
    db.session.add(message)
    session.updated_at = utcnow()
    db.session.commit()
    return {
        "session_id": session.id,
        "message_id": message.id,
        "matched": True,
        "coverage": "recipe_options",
        "mode": "recipe_options",
        "mode_label": MODE_LABELS.get("recipe_options"),
        "mode_note": mode_note,
        "answer": answer,
        "sections": [],
        "evidence": "",
        "sources": [],
        "entry": None,
        "related": [],
        "disclaimer": DISCLAIMER,
        "ai_check": None,
        "ai_error": cooking.get("ai_error"),
        "context_used": bool(cooking.get("context_used")),
        "recipe_title": cooking.get("title"),
        "recipe_subject": subject,
        "recipe_options": options,
        "recipe_source": cooking.get("source_label"),
    }


def _clean_topic(text: str) -> str:
    value = text.strip()
    for word in (
        "有什么",
        "有哪些",
        "什么",
        "哪些",
        "怎么",
        "如何",
        "为什么",
        "可以",
        "能不能",
        "能不能",
        "能",
        "吃",
        "喝",
        "买",
        "做",
        "挑选",
        "保存",
        "到底",
        "才",
        "吗",
        "呢",
        "？",
        "?",
        "，",
        ",",
        "。",
    ):
        value = value.replace(word, "")
    return value.strip()


def _heuristic_rewrite(question: str, history: list[dict]) -> str | None:
    # 优先用上一条助手条目的标题，其次从最近一个带主题的问题里提取名词
    for item in reversed(history):
        if item.get("recipe_title"):
            return f"{item['recipe_title']} {question}".strip()
        if item.get("entry_title"):
            return f"{item['entry_title']} {question}".strip()
    topic = ""
    for item in reversed(history):
        if item["role"] != "user":
            continue
        if _looks_like_follow_up(item["content"]):
            continue
        topic = _clean_topic(item["content"])
        if topic:
            break
    if not topic:
        return None
    return f"{topic} {question}".strip()


def _rewrite_question(question: str, history: list[dict], history_text: str) -> str | None:
    """把“能和酒一起吃吗”改写成“蘑菇和酒能一起吃吗”，仅补全省略成分。"""
    heuristic = _heuristic_rewrite(question, history)
    system = (
        "你是多轮对话查询改写器。根据对话历史，把用户最后一句改写成不依赖上文的完整问题。"
        "只补全省略的主语、宾语或指代；不要回答问题，不要解释，不要添加历史中没有的新主题。"
        "如果最后一句已经完整，或明显开启新话题，原样输出。只输出一句问句。"
    )
    try:
        raw = _chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"对话历史：\n{history_text}\n\n最后一句：{question}"},
            ]
        )
    except Exception:
        return heuristic
    text = (raw or "").strip().splitlines()[0].strip().strip('"').strip("“”").strip()
    if not text or len(text) > 80 or text == question:
        return heuristic
    # 防止模型凭空换话题：改写后必须仍包含历史中的某个两字片段
    history_chars = "".join(item["content"] for item in history if item["role"] == "user")
    grams = {history_chars[index : index + 2] for index in range(max(len(history_chars) - 1, 0))}
    if grams and not any(gram in text for gram in grams):
        return heuristic
    return text


PANTRY_RECOMMEND_MARKERS = (
    "推荐",
    "吃什么",
    "做什么菜",
    "做什么饭",
    "用我的食材",
    "现有食材",
    "已有的食材",
    "冰箱里",
    "食材管家",
    "根据食材",
    "根据库存",
    "清一点",
    "清淡",
    "减脂",
    "低脂",
    "少油",
    "控糖",
)


def _wants_pantry_recommendation(question: str) -> bool:
    text = question.strip()
    return any(marker in text for marker in PANTRY_RECOMMEND_MARKERS)


CHINESE_SERVINGS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}


def _servings_from_question(question: str) -> int:
    match = re.search(r"([1-6一二两三四五六])\s*(?:个?人|人份)", question or "")
    if not match:
        return 2
    raw = match.group(1)
    return CHINESE_SERVINGS.get(raw, int(raw) if raw.isdigit() else 2)


def _pantry_answer(question: str, user_id: int, session_id: int | None, plan: dict | None, error: str | None = None) -> dict:
    session = _resolve_session(user_id, session_id, question)
    db.session.add(ChatMessage(session_id=session.id, role="user", content=question, mode="user"))
    dishes = []
    sections = []
    plan_id = None
    if plan:
        plan_id = plan.get("plan_id")
        for index, meal in enumerate(plan.get("meals") or []):
            missing = meal.get("missing")
            if missing is None:
                missing = [item for item in (meal.get("ingredients") or []) if item.get("from_pantry") is False]
            dishes.append(
                {
                    "meal_index": index,
                    "meal_type": meal.get("meal_type"),
                    "name": meal.get("name"),
                    "ingredients": meal.get("ingredients") or [],
                    "steps": meal.get("steps") or [],
                    "nutrition": meal.get("nutrition") or {},
                    "missing": missing,
                    "tips": meal.get("tips") or "",
                }
            )
        sections = [
            {"key": "summary", "label": "匹配思路", "text": plan.get("summary") or "根据库存与健康画像推荐。"},
            {
                "key": "trace",
                "label": "🤖 AI 营养师的思考过程",
                "text": "\n".join(f"{index}. {line}" for index, line in enumerate(plan.get("agent_trace") or [], start=1)),
            },
        ]
        if plan.get("shopping_list"):
            sections.append(
                {"key": "shopping", "label": "可能缺少的食材", "text": "\n".join(f"· {item}" for item in plan["shopping_list"])}
            )
        sections.append(
            {
                "key": "note",
                "label": "说明",
                "text": "点击「去做」查看步骤；点击「已完成」会从食材管家扣减这道菜用到的库存。扣减是估算，份量不明确时会单独提示。",
            }
        )
        answer = f"根据你现有的 {plan.get('pantry_count')} 项食材，按 {plan.get('servings', 2)} 人份推荐 {len(dishes)} 道菜。{plan.get('summary') or ''}"
    else:
        sections = [
            {"key": "empty", "label": "食材管家", "text": error or "食材管家还没有食材，请先在小票/语音/手动录入里添加食材，我再按库存推荐。"}
        ]
        answer = error or "食材管家还没有食材，请先添加食材后再让我推荐。"

    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        mode="pantry_agent",
        matched_slug=None,
        sources=[],
        payload={
            "sections": sections,
            "evidence": "",
            "ai": None,
            "mode_note": "推荐由食材管家生成，只使用当前库存与健康画像；不是食品安全结论。",
            "matched": True,
            "coverage": "pantry_recipe",
            "ai_error": error,
            "entry": None,
            "retrieval": [],
            "related": [],
            "context_used": False,
            "pantry_plan_id": plan_id,
            "pantry_dishes": dishes,
            "pantry_shopping": (plan or {}).get("shopping_list") or [],
            "pantry_trace": (plan or {}).get("agent_trace") or [],
            "pantry_servings": (plan or {}).get("servings", 2),
        },
    )
    db.session.add(message)
    session.updated_at = utcnow()
    db.session.commit()
    return {
        "session_id": session.id,
        "message_id": message.id,
        "matched": True,
        "coverage": "pantry_recipe",
        "mode": "pantry_agent",
        "mode_label": MODE_LABELS.get("pantry_agent"),
        "mode_note": "推荐由食材管家生成，只使用当前库存与健康画像；不是食品安全结论。",
        "answer": answer,
        "sections": sections,
        "evidence": "",
        "sources": [],
        "entry": None,
        "related": [],
        "disclaimer": DISCLAIMER,
        "ai_check": None,
        "ai_error": error,
        "context_used": False,
        "pantry_plan_id": plan_id,
        "pantry_dishes": dishes,
        "pantry_shopping": (plan or {}).get("shopping_list") or [],
        "pantry_trace": (plan or {}).get("agent_trace") or [],
        "pantry_servings": (plan or {}).get("servings", 2),
    }


INVENTORY_SAFETY_MARKERS = (
    "冰箱", "库存", "食材管家", "我的食材", "家里有", "我家有", "快过期", "过期", "保质期",
    "变质", "胀包", "胀袋", "还能喝", "还能吃", "安全吗", "能喝吗", "能吃吗", "坏了",
)


def _inventory_items(user_id: int) -> list[PantryItem]:
    return (
        PantryItem.query.filter_by(user_id=user_id)
        .order_by(PantryItem.expires_at.is_(None), PantryItem.expires_at.asc())
        .all()
    )


def _qty(value: float) -> str:
    return str(int(value)) if abs(value - round(value)) < 0.01 else f"{value:.1f}"


def _inventory_lines(items: list[PantryItem]) -> list[str]:
    lines = []
    for item in items:
        _, status_text = item.status()
        expiry = f"，保质期至 {item.expires_at.isoformat()}" if item.expires_at else ""
        lines.append(f"- {item.name} {_qty(float(item.quantity))}{item.unit}（{status_text}{expiry}）")
    return lines


STRONG_SAFETY_MARKERS = (
    "快过期", "过期", "保质期", "变质", "胀包", "胀袋", "还能喝", "还能吃",
    "安全吗", "能喝吗", "能吃吗", "坏了",
)


def _wants_inventory_context(question: str, items: list[PantryItem]) -> bool:
    text = question or ""
    if not items:
        return False
    strong_safety = any(marker in text for marker in STRONG_SAFETY_MARKERS)
    if _wants_pantry_recommendation(text) and not strong_safety:
        return False
    safety = any(marker in text for marker in INVENTORY_SAFETY_MARKERS)
    if safety:
        return True
    names = [item.name for item in items if item.name]
    return any(name and name in text for name in names) and any(word in text for word in ("我的", "我家", "冰箱"))


def _parse_json_object(raw: str) -> dict | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _inventory_fallback(question: str, items: list[PantryItem]) -> str:
    names = [item.name for item in items]
    points = []
    if any("牛奶" in name or "奶" in name for name in names):
        points.append("牛奶临期不等于变质：包装没有胀包、没有异味、一直冷藏，充分加热后一般可以喝；一旦胀包、异味、分层或超过保质期，直接丢弃。")
    if any("番茄" in name or "西红柿" in name for name in names) and any("鸡蛋" in name or "蛋" in name for name in names):
        points.append("番茄炒蛋一般没问题，关键是鸡蛋彻底加热、番茄洗净；蛋壳破损、有异味或蛋液浑浊就不要用。")
    if not points:
        points.append("结合你现有的食材，先检查包装是否胀包、是否有异味、是否在保质期内；拿不准的不要吃。")
    points.append("以上是一般性食品安全建议，不替代医生诊断；涉及中毒、过敏或持续不适请及时就医。")
    return "\n".join(points[:3])


def _inventory_answer(question: str, user_id: int, session_id: int | None, items: list[PantryItem]) -> dict:
    lines = _inventory_lines(items)
    inventory_text = "\n".join(lines)
    prompt = (
        "你是一个食品安全助手。请注意，该用户家里目前的食材库存有：\n"
        f"{inventory_text}\n\n"
        "请结合用户的问题和这些库存来回答，优先提醒临期/过期食材。只返回一个 JSON 对象，不要 Markdown，不要额外解释，格式：\n"
        '{"answer":"给用户的中文回答，2-3 点，200 字以内","action":"jump_to_inventory","action_label":"管理我的冰箱库存","used_items":["用到的食材名"],"safety_notes":["关键安全提醒"]}\n'
        "action 必须固定为 jump_to_inventory；如果问题与库存无关，action 设为 null。不要编造标准号、机构名和具体检测数据。"
        + MEDICAL_SAFETY
    )
    ai_error = None
    answer = None
    action = "jump_to_inventory"
    action_label = "管理我的冰箱库存"
    used = [item.name for item in items if item.name and item.name in question] or [item.name for item in items[:3]]
    safety_notes = []
    mode = "inventory_rule"
    if _allow_ai():
        try:
            raw = _chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": question},
                ]
            )
            parsed = _parse_json_object(raw)
            if parsed and parsed.get("answer"):
                answer = str(parsed["answer"]).strip()[:1500]
                action = parsed.get("action") if parsed.get("action") in {None, "jump_to_inventory"} else action
                action_label = str(parsed.get("action_label") or action_label)[:40]
                if isinstance(parsed.get("used_items"), list):
                    used = [str(item)[:40] for item in parsed["used_items"] if item][:8]
                if isinstance(parsed.get("safety_notes"), list):
                    safety_notes = [str(item)[:120] for item in parsed["safety_notes"] if item][:4]
                mode = "inventory_ai"
            else:
                ai_error = "模型返回格式不是可解析的 JSON"
        except Exception as exc:  # noqa: BLE001
            ai_error = str(exc)[:200]
    if not answer:
        answer = _inventory_fallback(question, items)

    sections = [
        {"key": "inventory", "label": "已读取的食材库存", "text": inventory_text},
    ]
    if safety_notes:
        sections.append({"key": "safety", "label": "安全提醒", "text": "\n".join(f"· {note}" for note in safety_notes)})

    session = _resolve_session(user_id, session_id, question)
    db.session.add(ChatMessage(session_id=session.id, role="user", content=question, mode="user"))
    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        mode=mode,
        payload={
            "sections": sections,
            "evidence": "",
            "ai": None,
            "mode_note": "回答已结合当前家庭食材库存；属于一般性科普，不替代专业意见。",
            "matched": True,
            "coverage": "inventory",
            "ai_error": ai_error,
            "entry": None,
            "retrieval": [],
            "related": [],
            "context_used": False,
            "action": action,
            "action_label": action_label,
            "inventory_items": [item.to_public() for item in items[:20]],
            "used_items": used,
            "safety_notes": safety_notes,
        },
    )
    db.session.add(message)
    session.updated_at = utcnow()
    db.session.commit()
    return {
        "session_id": session.id,
        "message_id": message.id,
        "matched": True,
        "coverage": "inventory",
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "mode_note": "回答已结合当前家庭食材库存；属于一般性科普，不替代专业意见。",
        "answer": answer,
        "sections": sections,
        "evidence": "",
        "sources": [],
        "entry": None,
        "related": [],
        "disclaimer": DISCLAIMER,
        "ai_check": None,
        "ai_error": ai_error,
        "context_used": False,
        "action": action,
        "action_label": action_label,
        "inventory_items": [item.to_public() for item in items[:20]],
        "used_items": used,
        "safety_notes": safety_notes,
    }


KNOWLEDGE_INTENT_WORDS = (
    "营养", "添加剂", "防腐剂", "阿斯巴甜", "甜味剂", "色素", "香精", "相克", "同吃",
    "一起吃", "维生素", "蛋白质", "热量", "卡路里", "胆固醇", "嘌呤", "升糖",
    "亚硝酸", "致癌", "谣言",
)


def _wants_knowledge(question: str) -> bool:
    text = question or ""
    return any(word in text for word in KNOWLEDGE_INTENT_WORDS)


def _context_recipe_answer(question: str, context: dict, history_text: str) -> str | None:
    """带菜谱上下文的连续追问：把完整菜谱 JSON 注入 System Prompt。"""
    name = str(context.get("title") or context.get("name") or context.get("recipe_name") or "").strip()
    if not name:
        return None
    detail = json.dumps(context, ensure_ascii=False)[:8000]
    system = (
        f"你是食安专家。当前用户正在询问关于【{name}】的食品/食谱问题。"
        f"菜谱详情为：{detail}。"
        "请结合该菜谱回答用户；如果用户问“能换白糖吗”这类省略问题，"
        "默认他是指这道菜里的冰糖或对应配料。回答要具体、可执行，控制在 200 字以内。"
        "不要编造标准号、机构或检测数据。"
        + MEDICAL_SAFETY
    )
    user = (f"对话历史（仅供理解指代）：\n{history_text}\n\n" if history_text else "") + f"用户问题：{question}"
    try:
        raw = _chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
    except Exception as exc:  # noqa: BLE001
        logger.warning("带菜谱上下文回答失败，回退普通问答：%s", exc.__class__.__name__)
        return None
    return (raw or "").strip() or None


def _save_context_answer(question: str, user_id: int, session_id: int | None, answer: str, context: dict) -> dict:
    session = _resolve_session(user_id, session_id, question)
    db.session.add(ChatMessage(session_id=session.id, role="user", content=question, mode="user"))
    mode = "context_ai"
    mode_note = "回答已结合当前菜谱上下文；属于烹饪与营养参考，不替代专业意见。"
    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        mode=mode,
        matched_slug=None,
        sources=[],
        payload={
            "sections": [],
            "evidence": "",
            "ai": None,
            "mode_note": mode_note,
            "matched": True,
            "coverage": "context",
            "ai_error": None,
            "entry": None,
            "retrieval": [],
            "related": [],
            "context_used": True,
            "context_recipe": context,
        },
    )
    db.session.add(message)
    session.updated_at = utcnow()
    db.session.commit()
    return {
        "session_id": session.id,
        "message_id": message.id,
        "matched": True,
        "coverage": "context",
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "mode_note": mode_note,
        "answer": answer,
        "sections": [],
        "evidence": "",
        "sources": [],
        "entry": None,
        "related": [],
        "disclaimer": DISCLAIMER,
        "ai_check": None,
        "ai_error": None,
        "context_used": True,
        "retrieval_query": question,
    }


def _save_profile_answer(
    question: str,
    user_id: int,
    session_id: int | None,
    answer: str,
    profile_data: dict | None,
) -> dict:
    session = _resolve_session(user_id, session_id, question)
    db.session.add(
        ChatMessage(session_id=session.id, role="user", content=question, mode="user")
    )

    mode = "profile_ai"
    mode_note = "回答已结合您的健康档案；属于营养与饮食参考，不替代医生诊断。"
    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        mode=mode,
        matched_slug=None,
        sources=[],
        payload={
            "mode": mode,
            "mode_note": mode_note,
            "matched": True,
            "coverage": "profile",
            "profile_used": True,
            "health_profile": profile_data or {},
            "ai_error": None,
            "entry": None,
            "retrieval": [],
            "related": [],
            "context_used": False,
        },
    )
    db.session.add(message)
    session.updated_at = utcnow()
    db.session.commit()
    return {
        "session_id": session.id,
        "message_id": message.id,
        "matched": True,
        "coverage": "profile",
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "mode_note": mode_note,
        "answer": answer,
        "sections": [],
        "evidence": "",
        "sources": [],
        "entry": None,
        "related": [],
        "ai_check": None,
        "ai_error": None,
        "context_used": False,
        "profile_used": True,
        "health_profile": profile_data or {},
    }


def ask(
    question: str,
    user_id: int,
    session_id: int | None = None,
    context: dict | None = None,
    health_profile: dict | None = None,
) -> dict:
    _throttle(user_id)
    question = question.strip()
    history = _recent_history(user_id, session_id)
    history_text = _history_text(history)
    profile_data, profile_text = _health_profile(user_id, health_profile)

    # 健康画像/身体状况/饮食禁忌类问题：优先直接走画像回答，绝不进入 RAG 检索。
    if _wants_health_profile(question):
        profile_answer, profile_error = _profile_answer(
            question,
            user_id,
            history_text,
            profile_data,
            profile_text,
        )
        if profile_error:
            logger.info("健康画像 AI 调用失败，已使用档案规则兜底：%s", profile_error)
        return _save_profile_answer(
            question,
            user_id,
            session_id,
            profile_answer,
            profile_data,
        )

    if isinstance(context, dict) and context:
        context_answer = _context_recipe_answer(question, context, history_text)
        if context_answer:
            return _save_context_answer(question, user_id, session_id, context_answer, context)
    cooking = cooking_service.maybe_answer(question, history_text)
    if cooking:
        if cooking.get("mode") == "recipe_options":
            return _recipe_options_answer(question, user_id, session_id, cooking)
        return _recipe_answer(question, user_id, session_id, cooking)
    knowledge_intent = _wants_knowledge(question)
    inventory_items = _inventory_items(user_id)
    if not knowledge_intent and _wants_inventory_context(question, inventory_items):
        return _inventory_answer(question, user_id, session_id, inventory_items)
    if not knowledge_intent and _wants_pantry_recommendation(question):
        try:
            stock = PantryItem.query.filter_by(user_id=user_id).count()
            if stock < 2:
                return _pantry_answer(
                    question,
                    user_id,
                    session_id,
                    None,
                    "食材管家里的库存太少（至少录入 2 项），先补充蔬菜、蛋白质或主食，我再按现有食材推荐。",
                )
            plan = recipe_agent_service.plan_recipes(
                user_id,
                meals=2,
                max_minutes=30,
                preference=question,
                force_rule=True,
                servings=_servings_from_question(question),
            )
            return _pantry_answer(question, user_id, session_id, plan)
        except Exception as exc:  # 库存为空/生成失败都给出可读提示
            return _pantry_answer(question, user_id, session_id, None, str(exc)[:160])
    needs_context = _needs_context(question, history)
    context_used = False
    retrieval_query = question
    # 先做一次“省略成分补全”：把“能和酒一起吃吗”还原成“蘑菇和酒能一起吃吗”。
    # 只对明确追问执行，新话题保持原样。
    if needs_context and history:
        rewritten = _rewrite_question(question, history, history_text)
        if rewritten and rewritten != question:
            retrieval_query = rewritten
            context_used = True
    hits = search(retrieval_query)
    direct = bool(hits) and hits[0]["matched"]
    # 改写失败时再用“上一轮主题 + 当前问题”做一次检索兜底
    if not direct and needs_context and history and retrieval_query == question:
        combined_query = _contextual_query(history, question)
        if combined_query and combined_query != question:
            combined_hits = search(combined_query)
            combined_direct = bool(combined_hits) and combined_hits[0]["matched"]
            if combined_hits and (combined_direct or not direct):
                hits = combined_hits
                direct = combined_direct
                context_used = True
                retrieval_query = combined_query
    candidates = [hit["entry"] for hit in hits]

    mode = _resolve_mode()
    ai_text = None
    ai_meta = None
    ai_error = None
    mode_note = None
    coverage = "direct" if direct else "none"
    sources: list[dict] = []
    entry = None
    sections: list[dict] = []

    if direct:
        entry = candidates[0]
        if mode == "ai":
            # 只用最相关的一条作为资料：引用链是「句子 → 条目 → 来源文档」，不会串条目
            result = _ai_answer(question, [entry], history_text)
            if result:
                ai_text, ai_meta = result
            else:
                mode = "retrieval"
                mode_note = "RAG 提炼未通过依据校验，已自动改为检索直答"
        content = ai_text or _plain_content(entry)
        sources = _sources(entry)
        sections = [] if ai_text else _sections(entry)
        related_entries = candidates[1:3]
    else:
        content = "未在国标库中匹配到完全一致的答案。您可以换个更具体的问法，或从下面的相关问题里选择一个；涉及健康画像的问题，请直接说“根据我的健康画像”。"
        related_entries = candidates[:3]
        picked = None
        if _allow_ai() and _allow_fallback():
            # 第一层兜底：让模型只做「选条目」，答案仍来自条目原文
            picked, ai_error = _ai_pick_entry(question, candidates[:5], history_text)
        if picked is not None:
            entry = picked
            content = _plain_content(picked)
            sections = _sections(picked)
            sources = _sources(picked)
            mode = "ai_rerank"
            coverage = "related"
            mode_note = f"知识库未直接命中：AI 从相近条目中选出「{picked.title}」，回答内容取自该条目原文"
            related_entries = [item for item in candidates if item.slug != picked.slug][:3]
        elif _allow_ai() and _allow_general() and not knowledge_intent:
            # 第二层兜底：通用大模型回答，明确标注未引用本站资料
            general, general_error = _ai_general_answer(
                question,
                history_text,
                profile_text,
            )
            if general_error:
                ai_error = ai_error or general_error
            if general:
                content = (
                    "未在国标库中匹配到完全一致的答案，以下是 AI 营养师结合常识与您的健康画像给出的综合建议：\n\n"
                    + general
                )
                mode = "ai_general"
                coverage = "general"
                mode_note = "未在国标库中匹配到完全一致的答案，已结合常识与您的健康档案补充；涉及用药、中毒、过敏请咨询医生或药师。"
                # 通用回答没有命中的条目，不再塞入可能跑题的“相关问题”
                related_entries = []
            else:
                mode = "retrieval"
                mode_note = "AI 调用失败，未能生成回答" + (f"（{ai_error}）" if ai_error else "")
        elif _allow_ai():
            mode = "retrieval"
            mode_note = "AI 判断知识库中没有能回答该问题的条目，因此不作答"
        else:
            mode = "retrieval"
            mode_note = "未检索到可核实的条目，未调用大模型"

    matched_slug = entry.slug if entry else None
    related = [
        {"slug": item.slug, "title": item.title, "category_label": ASSISTANT_CATEGORIES.get(item.category, "")}
        for item in related_entries
    ]

    session = _resolve_session(user_id, session_id, question)
    db.session.add(ChatMessage(session_id=session.id, role="user", content=question, mode="user"))
    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=content,
        mode=mode,
        matched_slug=matched_slug,
        sources=sources,
        payload={
            "sections": sections,
            "evidence": entry.evidence if entry else "",
            "ai": ai_meta,
            "mode_note": mode_note,
            "matched": coverage != "none",
            "coverage": coverage,
            "ai_error": ai_error,
            "entry": entry.to_public(brief=True) if entry else None,
            "retrieval": [{"slug": hit["entry"].slug, "score": hit["score"]} for hit in hits],
            "related": related,
            "context_used": context_used,
            "retrieval_query": retrieval_query,
        },
    )
    db.session.add(message)
    session.updated_at = utcnow()
    db.session.commit()
    _index_cache["version"] = None

    return {
        "session_id": session.id,
        "message_id": message.id,
        "matched": coverage != "none",
        "coverage": coverage,
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "mode_note": mode_note,
        "answer": content,
        "sections": sections,
        "evidence": entry.evidence if entry else "",
        "sources": sources,
        "entry": entry.to_public(brief=True) if entry else None,
        "related": related,
        "disclaimer": DISCLAIMER,
        "ai_check": ai_meta,
        "ai_error": ai_error,
        "context_used": context_used,
        "retrieval_query": retrieval_query,
    }


def _resolve_session(user_id: int, session_id: int | None, question: str) -> ChatSession:
    if session_id:
        session = db.session.get(ChatSession, session_id)
        if session is None or session.user_id != user_id:
            raise LookupError("会话不存在或无权访问")
        return session
    session = ChatSession(user_id=user_id, title=question[:40] or "新的对话")
    db.session.add(session)
    db.session.flush()
    return session


def list_sessions(user_id: int, *, limit: int = 20) -> list[dict]:
    rows = (
        db.session.query(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [session.to_public(message_count=count) for session, count in rows]


def get_session(user_id: int, session_id: int) -> dict:
    session = db.session.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        raise LookupError("会话不存在或无权访问")
    return session.to_public(with_messages=True)


def delete_session(user_id: int, session_id: int) -> None:
    session = db.session.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        raise LookupError("会话不存在或无权访问")
    db.session.delete(session)
    db.session.commit()


def clear_sessions(user_id: int) -> int:
    sessions = ChatSession.query.filter_by(user_id=user_id).all()
    count = len(sessions)
    for session in sessions:
        db.session.delete(session)
    db.session.commit()
    return count


def entry_detail(slug: str) -> dict | None:
    entry = AssistantEntry.query.filter_by(slug=slug).first()
    return entry.to_public() if entry else None


__all__ = [
    "ask",
    "clear_sessions",
    "delete_session",
    "entry_detail",
    "featured_questions",
    "get_session",
    "list_sessions",
    "search",
    "stats",
    "upsert_entries",
    "MODE_LABELS",
    "DISCLAIMER",
]
