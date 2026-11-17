"""OCR 驱动抽象层。

三种驱动：
- local_rapidocr：本地开源 OCR 引擎（离线可用，无需 Key，中文支持好）
- vision_llm：具备视觉能力的多模态大模型（OpenAI 兼容协议）
- demo：内置样例文本，仅在完全没有 OCR 能力时启用，且强制标注为演示
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OcrLine:
    text: str
    confidence: float = 0.0


@dataclass
class OcrOutput:
    provider: str
    provider_label: str
    engine_version: str
    is_demo: bool
    lines: list[OcrLine] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    warning: str | None = None

    @property
    def raw_text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())

    def to_public(self) -> dict:
        return {
            "provider": self.provider,
            "provider_label": self.provider_label,
            "engine_version": self.engine_version,
            "is_demo": self.is_demo,
            "raw_text": self.raw_text,
            "line_count": len(self.lines),
            "duration_ms": self.duration_ms,
            "warning": self.warning,
            "lines": [{"text": l.text, "confidence": round(l.confidence, 3)} for l in self.lines],
        }


class OcrProviderError(RuntimeError):
    """驱动内部错误，由 OcrService 包装为可读的 API 错误。"""


class BaseOcrProvider:
    name = "base"
    label = "未配置的 OCR 驱动"
    is_demo = False

    @classmethod
    def available(cls) -> bool:
        return False

    def recognize(self, image_path: Path) -> OcrOutput:  # pragma: no cover - 抽象方法
        raise NotImplementedError

    @staticmethod
    def timer() -> float:
        return time.perf_counter()

    @staticmethod
    def elapsed_ms(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)
