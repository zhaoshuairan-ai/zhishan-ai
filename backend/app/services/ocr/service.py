"""OCR 服务门面：驱动选择、可用性探测与统一错误包装。"""
from __future__ import annotations

import logging
from pathlib import Path

from flask import current_app

from ...utils.errors import ServiceError
from .base import BaseOcrProvider, OcrOutput
from .demo import DemoOcrProvider
from .local_rapidocr import LocalRapidOcrProvider
from .vision_llm import VisionLlmProvider

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, type[BaseOcrProvider]] = {
    "local": LocalRapidOcrProvider,
    "vision": VisionLlmProvider,
    "demo": DemoOcrProvider,
}

ALIASES = {
    "local_rapidocr": "local",
    "rapidocr": "local",
    "local": "local",
    "vision": "vision",
    "vision_llm": "vision",
    "llm": "vision",
    "demo": "demo",
    "mock": "demo",
}


def provider_status() -> list[dict]:
    """供 /api/settings/status 展示：哪些 OCR 驱动当前可用。"""
    result = []
    for key, cls in PROVIDERS.items():
        try:
            available = cls.available()
        except Exception as exc:  # pragma: no cover
            logger.warning("检测 OCR 驱动 %s 失败: %s", key, exc.__class__.__name__)
            available = False
        result.append(
            {
                "key": key,
                "name": cls.label,
                "available": bool(available),
                "is_demo": bool(getattr(cls, "is_demo", False)),
            }
        )
    return result


def resolve_provider_key() -> str:
    configured = (current_app.config.get("OCR_PROVIDER") or "auto").strip().lower()
    key = ALIASES.get(configured, configured)
    if key in PROVIDERS:
        if PROVIDERS[key].available():
            return key
        if key != "demo":
            logger.warning("配置的 OCR 驱动 %s 当前不可用，回退到 demo", key)
        return "demo"
    # auto
    if LocalRapidOcrProvider.available():
        return "local"
    if VisionLlmProvider.available():
        return "vision"
    return "demo"


def active_provider_label() -> str:
    key = resolve_provider_key()
    return PROVIDERS[key].label


def recognize(image_path: Path) -> OcrOutput:
    key = resolve_provider_key()
    provider = PROVIDERS[key]()
    try:
        output = provider.recognize(image_path)
    except ImportError as exc:  # pragma: no cover
        raise ServiceError(
            "本地 OCR 引擎未安装，无法识别图片。请执行 pip install -r backend/requirements.txt，"
            "或在 .env 中配置视觉模型 / 使用 OCR_PROVIDER=demo 进行演示。",
            code=50300,
            status=503,
            details={"provider": key, "reason": str(exc)[:200]},
        ) from exc
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        logger.warning("OCR 识别失败（%s）：%s", key, message)
        raise ServiceError(
            f"文字识别失败：{message}",
            code=50200,
            status=502,
            details={"provider": key, "provider_label": provider.label, "retryable": True},
        ) from exc
    if key != "demo" and output.is_demo:
        output.is_demo = True
    return output


__all__ = ["recognize", "provider_status", "resolve_provider_key", "active_provider_label", "PROVIDERS"]
