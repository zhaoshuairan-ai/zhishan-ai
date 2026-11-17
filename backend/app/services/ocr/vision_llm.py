"""视觉大模型 OCR 驱动（OpenAI 兼容的 /chat/completions 多模态接口）。

适配对象：通义千问 qwen-vl、智谱 glm-4v、OpenAI gpt-4o 系列、
以及任何提供 OpenAI 兼容协议且支持 image_url 的服务。
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

import requests
from flask import current_app

from .base import BaseOcrProvider, OcrLine, OcrOutput, OcrProviderError

logger = logging.getLogger(__name__)

OCR_FIELDS = [
    "food_name",
    "ingredients_text",
    "nutrition_text",
    "net_content",
    "production_date",
    "shelf_life",
    "storage",
    "producer",
    "standard_no",
    "allergen",
]

SYSTEM_PROMPT = (
    "你是专业的食品标签 OCR 识别助手。请只依据图片中真实可见的文字进行识别，"
    "严禁编造或补全图片中不存在的任何信息。看不清的字用「□」占位。"
)

USER_PROMPT = """请识别这张食品包装照片中的标签文字，并严格按以下 JSON 结构返回，不要输出 JSON 以外的任何内容：
{
  "raw_text": "按视觉顺序逐行转写的完整文字，保留换行",
  "fields": {
    "food_name": "真实食品品类名称（如苏打饼干、纯牛奶、饮用水），不要填营销口号/广告语；如果只有营销口号、无法判断真实品类，填写「[待完善] 某品牌食品」；完全没有则为空字符串",
    "ingredients_text": "配料表全文（含「配料：」之后的内容），没有则为空字符串",
    "nutrition_text": "营养成分表全文（含项目、数值、单位、NRV%），没有则为空字符串",
    "net_content": "净含量，没有则为空字符串",
    "production_date": "生产日期，没有则为空字符串",
    "shelf_life": "保质期，没有则为空字符串",
    "storage": "贮存条件，没有则为空字符串",
    "producer": "生产者/制造商名称与地址，没有则为空字符串",
    "standard_no": "产品标准号，没有则为空字符串",
    "allergen": "致敏物质提示，没有则为空字符串"
  },
  "lines": [{"text": "单行文字", "confidence": 0~1 的数字}]
}
要求：
1. 只填写图片中确实可见的内容，看不清或不存在的一律留空字符串；
2. 数字、单位、日期必须原样转写，不要换算；
3. 若图片不是食品标签，fields 全部留空并在 raw_text 中说明。"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def normalize_base_url(raw: str | None) -> str:
    """规范化用户填写的接口地址。

    常见错误：把完整的 .../v1/chat/completions 粘进来，或末尾多了斜杠，
    会导致程序拼出 .../chat/completions/chat/completions 并返回 404。
    """
    url = (raw or "").strip()
    if not url:
        return ""
    url = url.split("#", 1)[0].strip()
    url = re.sub(r"/chat/completions/?$", "", url, flags=re.I)
    return url.rstrip("/")


def candidate_urls(raw_base: str | None) -> list[str]:
    """返回候选的请求地址：优先按填写的地址，404 时再试带/不带 /v1 的版本。"""
    base = normalize_base_url(raw_base)
    if not base:
        return []
    if not re.match(r"^https?://[^\s]+$", base):
        raise OcrProviderError(
            f"OCR_VISION_BASE_URL 格式不正确：{base}。"
            "请填写以 http:// 或 https:// 开头的地址，例如 https://api.deepseek.com"
        )
    urls = [f"{base}/chat/completions"]
    if base.lower().endswith("/v1"):
        alternative = f"{base[:-3]}/chat/completions"
    else:
        alternative = f"{base}/v1/chat/completions"
    if alternative not in urls:
        urls.append(alternative)
    return urls


class VisionLlmProvider(BaseOcrProvider):
    name = "vision_llm"
    label = "视觉大模型识别"

    @classmethod
    def available(cls) -> bool:
        return bool(current_app.config.get("OCR_VISION_API_KEY"))

    @classmethod
    def version(cls) -> str:
        return f"{current_app.config.get('OCR_VISION_MODEL')} @ {current_app.config.get('OCR_VISION_BASE_URL')}"

    def recognize(self, image_path: Path) -> OcrOutput:
        start = self.timer()
        config = current_app.config
        key = (config.get("OCR_VISION_API_KEY") or "").strip()
        if not key:
            raise OcrProviderError("未配置视觉模型 API Key（OCR_VISION_API_KEY）")
        mime = "image/jpeg"
        suffix = image_path.suffix.lower()
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        try:
            b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        except OSError as exc:
            raise OcrProviderError("读取图片文件失败") from exc
        payload = {
            "model": config.get("OCR_VISION_MODEL"),
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                },
            ],
        }
        urls = candidate_urls(config.get("OCR_VISION_BASE_URL", ""))
        if not urls:
            raise OcrProviderError("未配置视觉模型接口地址（OCR_VISION_BASE_URL）")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        timeout = config.get("OCR_TIMEOUT", 45)

        # 大多数 OpenAI 兼容服务支持 JSON 模式，能降低「返回非 JSON」的概率；
        # 少数服务不认识 response_format 会报 400，此时去掉该字段重试。
        # 404/405 通常是地址不对，换下一个候选地址（带/不带 /v1）。
        resp = None
        used_url = ""
        last_detail = ""
        not_found: list[str] = []
        for url in urls:
            for index, extra in enumerate(({"response_format": {"type": "json_object"}}, {})):
                body = {**payload, **extra}
                try:
                    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
                except requests.Timeout as exc:
                    raise OcrProviderError("视觉模型请求超时，请稍后重试或换用其他 OCR 服务") from exc
                except requests.RequestException as exc:
                    raise OcrProviderError(f"视觉模型网络请求失败：{exc.__class__.__name__}") from exc
                used_url = url
                if resp.status_code == 200:
                    break
                last_detail = resp.text[:300]
                if (
                    index == 0
                    and resp.status_code == 400
                    and ("response_format" in last_detail or "json_object" in last_detail)
                ):
                    logger.info("视觉模型不支持 response_format，改为普通模式重试")
                    continue
                break
            if resp is not None and resp.status_code == 200:
                break
            if resp is not None and resp.status_code in (404, 405):
                not_found.append(f"{url}（HTTP {resp.status_code}）")
                continue
            break

        if resp is None or resp.status_code != 200:
            if not_found and resp is not None and resp.status_code in (404, 405):
                raise OcrProviderError(
                    "视觉模型接口不存在（HTTP 404）。已尝试："
                    + "、".join(not_found)
                    + "。请检查 OCR_VISION_BASE_URL：只填到站点根或 /v1（例如 "
                    "https://api.deepseek.com 或 https://api.deepseek.com/v1），不要带 /chat/completions。"
                )
            status = resp.status_code if resp is not None else "unknown"
            raise OcrProviderError(f"视觉模型返回错误（HTTP {status}，{used_url}）：{last_detail}")
        try:
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):  # 少数服务返回分段内容
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        except (ValueError, KeyError, IndexError) as exc:
            raise OcrProviderError("视觉模型返回内容无法解析") from exc

        try:
            data = json.loads(_strip_code_fence(content))
        except json.JSONDecodeError as exc:
            raise OcrProviderError("视觉模型未按要求返回 JSON，无法提取标签字段") from exc

        fields = data.get("fields") or {}
        lines: list[OcrLine] = []
        for item in data.get("lines") or []:
            if isinstance(item, dict) and str(item.get("text", "")).strip():
                try:
                    conf = float(item.get("confidence", 0.85))
                except (TypeError, ValueError):
                    conf = 0.85
                lines.append(OcrLine(text=str(item["text"]).strip(), confidence=max(0.0, min(conf, 1.0))))
        if not lines:
            raw_text = str(data.get("raw_text") or "")
            lines = [OcrLine(text=t.strip(), confidence=0.8) for t in raw_text.splitlines() if t.strip()]
        if not lines:
            raise OcrProviderError("视觉模型未识别到文字，请确认图片清晰度与内容")

        return OcrOutput(
            provider=self.name,
            provider_label=self.label,
            engine_version=self.version(),
            is_demo=False,
            lines=lines,
            raw_payload={
                "fields": {k: str(v or "") for k, v in fields.items() if k in OCR_FIELDS},
                "endpoint": used_url,
                "model": config.get("OCR_VISION_MODEL"),
            },
            duration_ms=self.elapsed_ms(start),
        )
