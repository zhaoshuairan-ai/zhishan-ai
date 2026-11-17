"""演示 OCR 驱动：仅在没有任何可用 OCR 能力时启用。

返回的是内置样例文本（虚构品牌，仅用于功能演示），
结果对象与接口响应中都会带有 is_demo=True，前端会以显著横幅标注。
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .base import BaseOcrProvider, OcrLine, OcrOutput

# 演示样例的日期按「当天」动态生成，避免演示时出现「已过期」的尴尬结论
_TODAY = date.today()
_PRODUCTION = _TODAY - timedelta(days=60)
_EXPIRY = date(_PRODUCTION.year + 1, _PRODUCTION.month, _PRODUCTION.day)

DEMO_LINES = [
    ("乐脆牌 原味苏打饼干（演示样例）", 0.99),
    ("净含量：200g", 0.97),
    ("配料：小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母、食品添加剂（碳酸钙）、全脂乳粉", 0.95),
    ("营养成分表", 0.96),
    ("项目 每100g NRV%", 0.93),
    ("能量 1980kJ 24%", 0.92),
    ("蛋白质 8.5g 14%", 0.94),
    ("脂肪 18.2g 30%", 0.94),
    ("碳水化合物 65.4g 22%", 0.94),
    ("钠 480mg 24%", 0.93),
    (f"生产日期：{_PRODUCTION.isoformat()}", 0.88),
    ("保质期：12个月", 0.95),
    (f"保质期至：{_EXPIRY.isoformat()}", 0.86),
    ("贮存条件：置于阴凉干燥处，避免阳光直射", 0.9),
    ("生产者：乐脆食品有限公司", 0.86),
    ("地址：示例省示例市示例区示例路88号", 0.8),
    ("产品标准号：GB/T 20980", 0.85),
    ("致敏物质提示：含有小麦、乳制品", 0.87),
]


class DemoOcrProvider(BaseOcrProvider):
    name = "demo"
    label = "演示模式（内置样例文字，不是对图片的真实识别）"
    is_demo = True

    @classmethod
    def available(cls) -> bool:
        # 始终可用，但优先级最低，只有其他驱动都不可用时才会被选中
        return True

    @classmethod
    def version(cls) -> str:
        return "demo-sample-2025.11"

    def recognize(self, image_path: Path) -> OcrOutput:
        start = self.timer()
        lines = [OcrLine(text=text, confidence=conf) for text, conf in DEMO_LINES]
        return OcrOutput(
            provider=self.name,
            provider_label=self.label,
            engine_version=self.version(),
            is_demo=True,
            lines=lines,
            raw_payload={"demo": True, "source": "builtin_sample"},
            duration_ms=max(1, self.elapsed_ms(start)),
            warning="当前未配置可用的 OCR 服务，展示的是内置演示样例文字，并非对上传图片的真实识别。",
        )
