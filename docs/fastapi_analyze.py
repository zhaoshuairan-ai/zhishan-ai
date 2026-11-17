"""FastAPI `/api/analyze` 参考实现：Base64 图片 JSON + mode，SSE 流式返回。

这是一个独立于当前 Flask 后端的 FastAPI 版本，可直接运行：

    pip install fastapi "uvicorn[standard]" httpx pydantic Pillow
    set DASHSCOPE_API_KEY=sk-xxx
    uvicorn fastapi_analyze:app --host 0.0.0.0 --port 8001

环境变量：
    DASHSCOPE_API_KEY   必填，通义千问 API Key
    DASHSCOPE_BASE_URL  默认 https://dashscope.aliyuncs.com/compatible-mode/v1
    VISION_MODEL        默认 qwen-vl-max-latest
    TEXT_MODEL          默认 qwen-plus
    ADDITIVES_JSON      默认与本文件同目录的 additives.json
    FOODS_JSON          默认与本文件同目录的 foods.json
    MAX_IMAGE_MB        默认 10

请求体（application/json）：
    {
      "image_base64": "data:image/jpeg;base64,/9j/4AAQ...",
      "mode": "packaging",
      "health_profile": {"uric_acid": "high", "goal": "lose_weight"}
    }

后端会：
    1. 剥离 data URL 前缀；
    2. 用 base64 解码；
    3. 用 Pillow 校验并还原为图片；
    4. 再调用视觉模型 / 本地 RAG / 文本模型。

本地数据格式（字段可多不可少，代码做了兼容）：

additives.json:
[
  {
    "name": "阿斯巴甜",
    "aliases": ["E951", "天冬酰苯丙氨酸甲酯"],
    "harmful": true,
    "risk_level": "medium",
    "hazard": "苯丙酮尿症患者需避免摄入；部分人群需控制摄入量。",
    "standard": "GB 2760-2024",
    "limit": "按食品类别规定最大使用量"
  }
]

foods.json:
[
  {
    "name": "西红柿炒鸡蛋",
    "aliases": ["番茄炒蛋", "番茄炒鸡蛋"],
    "calories_per_100g": 86,
    "protein_per_100g": 4.5,
    "fat_per_100g": 5.2,
    "carbs_per_100g": 5.8
  }
]
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import difflib
import io
import json
import logging
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger("food_safety_analyze")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent


def _env_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, str(BASE_DIR / default))).expanduser()


ADDITIVES_PATH = _env_path("ADDITIVES_JSON", "additives.json")
FOODS_PATH = _env_path("FOODS_JSON", "foods.json")

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).rstrip("/")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen-vl-max-latest")
TEXT_MODEL = os.getenv("TEXT_MODEL", "qwen-plus")
MAX_IMAGE_MB = int(os.getenv("MAX_IMAGE_MB", "10"))
MODEL_TIMEOUT = float(os.getenv("MODEL_TIMEOUT", "180"))


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class HealthProfile(BaseModel):
    """健康画像。允许前端传任意扩展字段，同时保留常用字段提示。"""

    model_config = ConfigDict(extra="allow")

    uric_acid: str | None = None
    goal: str | None = None
    blood_pressure: str | None = None
    blood_sugar: str | None = None
    blood_lipid: str | None = None
    allergies: list[str] | str | None = None
    kidney: str | None = None
    pregnancy: str | None = None
    age: int | str | None = None
    sex: str | None = None


class Base64AnalyzeRequest(BaseModel):
    """`POST /api/analyze` 的 JSON 请求体。"""

    image_base64: str = Field(..., min_length=1, description="data:image/jpeg;base64,...")
    mode: Literal["packaging", "dish"] = Field(..., description="packaging 或 dish")
    health_profile: dict[str, Any] = Field(default_factory=dict)


class PackagingVision(BaseModel):
    ingredients: list[str] = Field(default_factory=list)
    additives: list[str] = Field(default_factory=list)
    nutrition: dict[str, Any] = Field(default_factory=dict)
    raw_text: str | None = None


class DishVision(BaseModel):
    dish_name: str
    estimated_weight_g: float
    confidence: float | None = None


class MatchedAdditive(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    harmful: bool
    hazard: str
    standard: str
    limit: str


class MatchedFood(BaseModel):
    matched: bool
    dish_name: str
    matched_name: str | None = None
    calories_per_100g: float | None = None
    estimated_weight_g: float
    total_calories: float | None = None
    protein_per_100g: float | None = None
    fat_per_100g: float | None = None
    carbs_per_100g: float | None = None


# ---------------------------------------------------------------------------
# 本地 JSON / RAG 匹配
# ---------------------------------------------------------------------------


def _load_records(path: Path) -> list[dict[str, Any]]:
    """兼容 list、{items: []}、{data: []}、{additives: []} 等常见结构。"""
    if not path.exists():
        logger.warning("本地数据文件不存在：%s", path)
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("本地数据文件读取失败：%s", path)
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "additives", "foods", "dishes", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # 兼容 { "阿斯巴甜": { ... }, "山梨酸钾": { ... } } 这种以名称为 key 的结构。
        if payload and all(isinstance(value, dict) for value in payload.values()):
            return [
                {**value, "name": value.get("name") or name}
                for name, value in payload.items()
            ]
        return [payload]
    return []


@lru_cache(maxsize=1)
def load_additives() -> tuple[dict[str, Any], ...]:
    return tuple(_load_records(ADDITIVES_PATH))


@lru_cache(maxsize=1)
def load_foods() -> tuple[dict[str, Any], ...]:
    return tuple(_load_records(FOODS_PATH))


def normalize_text(value: Any) -> str:
    """用于匹配的归一化：全角转半角、去空格和常见标点。"""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"[\s\-_/\\（）()【】\[\]、，,。.;；:：·]+", "", text)


def as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("name") or item.get("text") or item.get("value")
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    return [str(value).strip()]


def as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def _additive_names(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("name", "title", "additive_name", "additive", "code", "e_number"):
        names.extend(as_text_list(item.get(key)))
    for key in ("aliases", "alias", "synonyms", "other_names", "names"):
        names.extend(as_text_list(item.get(key)))
    # 去重但保持顺序
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        key = normalize_text(name)
        if key and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def _additive_is_harmful(item: dict[str, Any]) -> bool:
    flag = item.get("harmful", item.get("is_harmful"))
    if isinstance(flag, bool):
        return flag
    if isinstance(flag, str) and flag.strip().lower() in {"true", "yes", "1", "有害"}:
        return True
    if isinstance(flag, str) and flag.strip().lower() in {"false", "no", "0", "无害"}:
        return False

    risk = normalize_text(item.get("risk_level") or item.get("level") or item.get("risk"))
    if any(token in risk for token in ("high", "medium", "高风险", "中风险", "有害", "慎用", "避免")):
        return True
    return bool(item.get("hazard") or item.get("harm") or item.get("risk_description"))


def _additive_view(item: dict[str, Any], matched_name: str) -> MatchedAdditive:
    hazard = (
        item.get("hazard")
        or item.get("harm")
        or item.get("risk_description")
        or item.get("description")
        or "本地数据未提供具体危害描述"
    )
    standard = (
        item.get("standard")
        or item.get("gb_standard")
        or item.get("gb")
        or item.get("standard_name")
        or "未提供国标编号"
    )
    limit = item.get("limit") or item.get("max_usage") or item.get("usage_limit") or "未提供限量信息"
    return MatchedAdditive(
        name=str(item.get("name") or item.get("title") or matched_name),
        aliases=_additive_names(item),
        harmful=_additive_is_harmful(item),
        hazard=str(hazard),
        standard=str(standard),
        limit=str(limit),
    )


def match_additives(
    additive_names: list[str],
    ingredients: list[str],
) -> list[MatchedAdditive]:
    """从视觉模型提取的配料/添加剂中匹配本地 additives.json。

    匹配方式：添加剂名称/别名是否出现在「视觉提取的添加剂名」或「配料表」中。
    这样即使视觉模型只返回了完整配料表，也能匹配到其中的防腐剂、甜味剂等。
    """
    haystacks = [
        normalized
        for text in [*additive_names, *ingredients]
        if (normalized := normalize_text(text))
    ]
    if not haystacks:
        return []

    matched: dict[str, MatchedAdditive] = {}
    for item in load_additives():
        names = _additive_names(item)
        matched_name: str | None = None
        for name in names:
            normalized = normalize_text(name)
            # 过短的名称（如单个“酸”）容易误匹配。
            if len(normalized) < 2:
                continue
            if any(normalized in haystack for haystack in haystacks):
                matched_name = name
                break
        if not matched_name:
            continue

        view = _additive_view(item, matched_name)
        key = normalize_text(view.name)
        if key not in matched:
            matched[key] = view

    return sorted(matched.values(), key=lambda item: (not item.harmful, item.name))


def _food_names(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("name", "dish_name", "title", "food_name"):
        names.extend(as_text_list(item.get(key)))
    for key in ("aliases", "alias", "synonyms", "other_names", "names"):
        names.extend(as_text_list(item.get(key)))
    return list(dict.fromkeys(name for name in names if name))


def _food_calories_per_100g(item: dict[str, Any]) -> float | None:
    for key in (
        "calories_per_100g",
        "calories",
        "kcal_per_100g",
        "energy_kcal",
        "energy_per_100g",
        "热量",
    ):
        value = as_number(item.get(key))
        if value is not None:
            return value
    return None


def match_food(dish_name: str) -> MatchedFood | None:
    """优先精确/别名匹配，其次包含匹配，最后用相似度兜底。"""
    target = normalize_text(dish_name)
    if not target:
        return None

    best_item: dict[str, Any] | None = None
    best_name: str | None = None
    best_score = 0.0

    for item in load_foods():
        for name in _food_names(item):
            normalized = normalize_text(name)
            if not normalized:
                continue
            if target == normalized:
                score = 1.0
            elif target in normalized or normalized in target:
                score = 0.92
            else:
                score = difflib.SequenceMatcher(None, target, normalized).ratio()

            if score > best_score:
                best_score = score
                best_item = item
                best_name = name

    if best_item is None or best_score < 0.72:
        return None

    per_100g = _food_calories_per_100g(best_item)
    return MatchedFood(
        matched=True,
        dish_name=dish_name,
        matched_name=best_name or str(best_item.get("name") or dish_name),
        calories_per_100g=per_100g,
        estimated_weight_g=0,
        total_calories=None,
        protein_per_100g=as_number(
            best_item.get("protein_per_100g") or best_item.get("protein")
        ),
        fat_per_100g=as_number(best_item.get("fat_per_100g") or best_item.get("fat")),
        carbs_per_100g=as_number(
            best_item.get("carbs_per_100g")
            or best_item.get("carbohydrate_per_100g")
            or best_item.get("carbs")
        ),
    )


# ---------------------------------------------------------------------------
# 视觉模型 & 文本模型
# ---------------------------------------------------------------------------


def parse_json_object(text: str) -> dict[str, Any]:
    """兼容 ```json 包裹、前后解释文字等模型输出。"""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("视觉模型没有返回 JSON 对象")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("视觉模型返回的 JSON 不是对象")
    return payload


def decode_base64_image(image_base64: str) -> tuple[bytes, str]:
    """剥离 data URL 前缀，用 base64 + Pillow 还原图片。

    返回可以直接交给视觉模型的 JPEG bytes 和 MIME。
    """
    text = (image_base64 or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="image_base64 不能为空")

    mime = "image/jpeg"
    encoded = text
    if text.startswith("data:"):
        header, separator, payload = text.partition(",")
        if not separator or ";base64" not in header.lower():
            raise HTTPException(status_code=422, detail="image_base64 必须是合法的 Base64 data URL")
        mime = header[5:].split(";", 1)[0].strip().lower() or "image/jpeg"
        encoded = payload

    if not mime.startswith("image/"):
        raise HTTPException(status_code=422, detail="image_base64 的 MIME 类型必须是 image/*")

    compact = re.sub(r"\s+", "", encoded)
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="image_base64 不是合法的 Base64 数据") from exc

    if not raw:
        raise HTTPException(status_code=422, detail="image_base64 解码后图片为空")
    if len(raw) > MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"图片不能超过 {MAX_IMAGE_MB}MB")

    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            if width < 2 or height < 2:
                raise ValueError("图片尺寸过小")
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=92)
            normalized = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="image_base64 不是有效图片") from exc

    return normalized, "image/jpeg"


def _image_data_url(image_bytes: bytes, content_type: str | None) -> str:
    mime = content_type or "image/jpeg"
    if not mime.startswith("image/"):
        mime = "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_message_content(payload: dict[str, Any]) -> str:
    choice = (payload.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content")
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        )
    return str(content or "")


async def call_vision_model(
    image_bytes: bytes,
    mode: Literal["packaging", "dish"],
    content_type: str | None,
) -> dict[str, Any]:
    """调用通义千问 VL，返回严格 JSON。"""
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")

    if mode == "packaging":
        prompt = """你是食品标签信息提取助手。请只读取图片中清晰可见的信息，不要推测、不要补全。
只输出一个 JSON 对象，格式：
{
  "ingredients": ["配料表原文中的每一项"],
  "additives": ["配料表中出现的食品添加剂名称"],
  "nutrition": {
    "energy_kj": 1900,
    "energy_kcal": 454,
    "protein_g": 8.2,
    "fat_g": 17.5,
    "carbohydrate_g": 66.1,
    "sodium_mg": 420
  },
  "raw_text": "识别到的关键原文"
}
要求：
1. 配料表按包装原文顺序拆分；
2. additives 只列食品添加剂名称，不要列普通食材；
3. 营养成分表按每 100g 提取，看不清的字段填 null；
4. 不要输出 Markdown，不要输出 JSON 以外的文字。"""
    else:
        prompt = """你是菜品识别助手。请识别图片中的一道主要菜品，并估算可食用重量。
只输出一个 JSON 对象，格式：
{
  "dish_name": "菜品名称",
  "estimated_weight_g": 250,
  "confidence": 0.8
}
要求：
1. dish_name 使用常见中文菜名；
2. estimated_weight_g 是整份菜的可食用重量，单位为克；
3. 无法识别时 dish_name 填 null，不要编造菜名；
4. 不要输出 Markdown，不要输出 JSON 以外的文字。"""

    body = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_data_url(image_bytes, content_type)},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
    }
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(MODEL_TIMEOUT)) as client:
        response = await client.post(
            f"{DASHSCOPE_BASE_URL}/chat/completions",
            headers=headers,
            json=body,
        )
        if response.status_code >= 400:
            logger.error("vision model error: %s %s", response.status_code, response.text[:500])
            response.raise_for_status()
        payload = response.json()

    return parse_json_object(_extract_message_content(payload))


async def stream_text_model(prompt: str, profile: HealthProfile) -> AsyncIterator[str]:
    """调用文本模型，并把 OpenAI 兼容 SSE 的 content 增量转换为纯文本。"""
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")

    system_prompt = """你是一名严谨的注册营养师和食品安全科普助手。
你必须只依据用户提供的【健康画像】和【本地精准数据】回答，不要编造未提供的检测结果、成分、国标或热量。
请用中文、Markdown 输出，结构清晰，但不要使用过度恐吓性的表达。
如果信息不足，明确写“当前图片/本地数据未提供”，不要猜测。
你不能做疾病诊断；涉及疾病、孕期、儿童、严重过敏或肾功能问题时，提醒用户咨询医生或临床营养师。
对于添加剂，只说明本地数据中给出的危害、GB 标准与限量；不能仅凭“有添加剂”就判定食品有害。
"""
    user_prompt = f"""{prompt}

【用户健康画像】
{json.dumps(profile.model_dump(exclude_none=True), ensure_ascii=False, indent=2)}

请结合上述画像生成定制化建议。"""
    body = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(MODEL_TIMEOUT)) as client:
        async with client.stream(
            "POST",
            f"{DASHSCOPE_BASE_URL}/chat/completions",
            headers=headers,
            json=body,
        ) as response:
            if response.status_code >= 400:
                body_text = (await response.aread()).decode("utf-8", errors="replace")
                logger.error("text model error: %s %s", response.status_code, body_text[:500])
                raise RuntimeError(f"文本模型调用失败（HTTP {response.status_code}）")

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    if data == "[DONE]":
                        break
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if isinstance(content, list):
                    content = "".join(
                        str(part.get("text", ""))
                        for part in content
                        if isinstance(part, dict)
                    )
                if content:
                    yield str(content)


# ---------------------------------------------------------------------------
# Prompt 组装
# ---------------------------------------------------------------------------


PROFILE_LABELS = {
    "uric_acid": "尿酸",
    "goal": "健康目标",
    "blood_pressure": "血压",
    "blood_sugar": "血糖",
    "blood_lipid": "血脂",
    "allergies": "过敏原",
    "kidney": "肾功能",
    "pregnancy": "孕期",
    "age": "年龄",
    "sex": "性别",
}
VALUE_LABELS = {
    "high": "偏高",
    "low": "偏低",
    "normal": "正常",
    "lose_weight": "减重",
    "gain_muscle": "增肌",
    "maintain": "维持体重",
    "yes": "是",
    "no": "否",
}


def describe_profile(profile: HealthProfile) -> str:
    values = profile.model_dump(exclude_none=True)
    if not values:
        return "未提供健康画像"
    lines: list[str] = []
    for key, value in values.items():
        label = PROFILE_LABELS.get(key, key)
        if isinstance(value, str):
            value = VALUE_LABELS.get(value, value)
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def build_analysis_prompt(
    mode: Literal["packaging", "dish"],
    profile: HealthProfile,
    vision: PackagingVision | DishVision,
    matched_additives: list[MatchedAdditive],
    matched_food: MatchedFood | None,
) -> str:
    profile_text = describe_profile(profile)

    if mode == "packaging":
        assert isinstance(vision, PackagingVision)
        harmful_additives = [item for item in matched_additives if item.harmful]
        local_data = {
            "配料表": vision.ingredients,
            "本地匹配到的有害添加剂": [item.model_dump() for item in harmful_additives],
            "本地匹配到的全部添加剂": [item.model_dump() for item in matched_additives],
            "营养成分表": vision.nutrition,
            "识别原文": vision.raw_text,
        }
        task = """请完成包装食品分析：
1. 先用一句话概括这是什么类型的食品；
2. 结合配料表和营养成分表，指出主要健康关注点（糖、盐、脂肪、能量等）；
3. 逐项说明本地标记为有害的添加剂：危害、GB 标准、限量；没有匹配到时明确写“本地数据未匹配到有害添加剂”，不要因此断言食品绝对安全；
4. 结合用户的尿酸、血压、血糖、减重等健康目标，给出“能不能吃、吃多少、怎么搭配”的具体建议；
5. 最后给出 2-3 条可执行建议。"""
    else:
        assert isinstance(vision, DishVision)
        local_data = {
            "菜品": vision.dish_name,
            "估算重量_g": vision.estimated_weight_g,
            "本地匹配到的菜品": matched_food.model_dump() if matched_food else None,
            "总热量_kcal": matched_food.total_calories if matched_food else None,
        }
        task = """请完成菜品营养分析：
1. 说明识别到的菜品与估算重量；
2. 只使用本地匹配数据计算并解释总热量；如果本地未匹配到，明确写“菜品库未收录，无法给出精准热量”，不要编造；
3. 说明蛋白质、脂肪、碳水情况（本地有数据时才写）；
4. 结合用户健康画像，给出份量、搭配和下一餐建议；
5. 涉及高尿酸、高血压、高血糖、减重目标时，给出具体但温和的提醒。"""

    return f"""【分析模式】{"包装食品" if mode == "packaging" else "菜品"}
【用户健康画像】
{profile_text}

【本地精准数据】
{json.dumps(local_data, ensure_ascii=False, indent=2)}

【任务】
{task}
"""


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------


app = FastAPI(title="智膳 AI · Analyze API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "*").split(",")
        if item.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "vision_model": VISION_MODEL,
        "text_model": TEXT_MODEL,
        "additives_loaded": len(load_additives()),
        "foods_loaded": len(load_foods()),
    }


@app.post("/api/analyze")
async def analyze(payload: Base64AnalyzeRequest):
    """接收 Base64 JSON，以 SSE 返回分析结果。

    前端示例：
        fetch("/api/analyze", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            image_base64: dataUrl,
            mode: "packaging"
          })
        })
    """
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="服务端未配置 DASHSCOPE_API_KEY")

    image_bytes, content_type = decode_base64_image(payload.image_base64)
    mode = payload.mode

    try:
        profile = HealthProfile.model_validate(payload.health_profile or {})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"health_profile 不合法：{exc.errors()}") from exc

    async def event_stream() -> AsyncIterator[str]:
        yield sse_event(
            "status",
            {"stage": "start", "message": "已收到图片，开始分析…"},
        )
        try:
            yield sse_event(
                "status",
                {"stage": "vision", "message": "正在调用视觉模型…"},
            )
            raw_vision = await call_vision_model(image_bytes, mode, content_type)

            if mode == "packaging":
                raw_nutrition = (
                    raw_vision.get("nutrition")
                    or raw_vision.get("nutrition_per_100g")
                    or raw_vision.get("营养成分表")
                    or {}
                )
                if isinstance(raw_nutrition, list):
                    nutrition = {"rows": raw_nutrition}
                elif isinstance(raw_nutrition, dict):
                    nutrition = raw_nutrition
                else:
                    nutrition = {"raw": raw_nutrition}

                vision = PackagingVision(
                    ingredients=as_text_list(
                        raw_vision.get("ingredients")
                        or raw_vision.get("ingredient_list")
                        or raw_vision.get("配料表")
                    ),
                    additives=as_text_list(
                        raw_vision.get("additives")
                        or raw_vision.get("additive_list")
                        or raw_vision.get("添加剂")
                    ),
                    nutrition=nutrition,
                    raw_text=raw_vision.get("raw_text") or raw_vision.get("text"),
                )
                matched_additives = match_additives(vision.additives, vision.ingredients)
                harmful_additives = [item for item in matched_additives if item.harmful]
                matched_food = None
                meta = {
                    "mode": mode,
                    "ingredients": vision.ingredients,
                    "additives": vision.additives,
                    "matched_additives": [item.model_dump() for item in matched_additives],
                    "harmful_additives": [item.model_dump() for item in harmful_additives],
                    "nutrition": vision.nutrition,
                }
            else:
                dish_name = str(
                    raw_vision.get("dish_name")
                    or raw_vision.get("name")
                    or raw_vision.get("菜品名称")
                    or ""
                ).strip()
                weight = as_number(
                    raw_vision.get("estimated_weight_g")
                    or raw_vision.get("weight_g")
                    or raw_vision.get("重量")
                )
                if not dish_name or weight is None or weight <= 0:
                    raise ValueError("视觉模型未能识别出有效菜品或重量")

                weight = min(max(round(weight, 1), 1.0), 5000.0)
                vision = DishVision(
                    dish_name=dish_name,
                    estimated_weight_g=weight,
                    confidence=as_number(raw_vision.get("confidence")),
                )
                matched_food = match_food(dish_name)
                if matched_food:
                    matched_food = matched_food.model_copy(
                        update={
                            "estimated_weight_g": weight,
                            "total_calories": (
                                round(matched_food.calories_per_100g * weight / 100, 1)
                                if matched_food.calories_per_100g is not None
                                else None
                            ),
                        }
                    )
                matched_additives = []
                meta = {
                    "mode": mode,
                    "dish": vision.model_dump(),
                    "matched_food": matched_food.model_dump() if matched_food else None,
                    "total_calories": matched_food.total_calories if matched_food else None,
                }

            yield sse_event("meta", meta)
            yield sse_event(
                "status",
                {"stage": "rag", "message": "已完成本地数据匹配，正在生成健康建议…"},
            )

            prompt = build_analysis_prompt(
                mode,
                profile,
                vision,
                matched_additives,
                matched_food,
            )
            wrote = False
            async for chunk in stream_text_model(prompt, profile):
                wrote = True
                yield sse_event("delta", {"text": chunk})
            if not wrote:
                raise RuntimeError("文本模型没有返回内容")

            yield sse_event("done", {"done": True})
        except asyncio.CancelledError:
            # 客户端断开时让 ASGI 正常取消上游流
            raise
        except Exception as exc:  # noqa: BLE001 - SSE 内部不能把异常抛给已建立连接
            logger.exception("analyze failed: %s", exc)
            message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "分析失败，请稍后重试"
            yield sse_event("error", {"message": message})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    uvicorn.run("fastapi_analyze:app", host="0.0.0.0", port=8001, reload=False)