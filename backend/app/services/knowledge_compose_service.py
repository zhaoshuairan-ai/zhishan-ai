"""AI 一键建库：根据菜名生成正文、摘要和营养数据。"""
from __future__ import annotations

import json
import logging

from . import ai_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是资深中国营养学专家和食品编辑。
请根据用户提供的菜名，生成一条可直接入库的中文知识条目，并严格返回 JSON。

要求：
1. content：150-300 字正文，必须包含核心食材、营养特点、健康红线和适宜人群，不能只重复菜名。
2. summary：50 字以内的卡片摘要，直接写出健康结论，不能等于菜名。
3. calories：每 100g 热量，单位 kcal。
4. carbs、protein、fat：每 100g 的碳水、蛋白质、脂肪，单位 g。
5. 参考《中国食物成分表》常识加权估算；红烧、炖肉、油炸、驴肉火烧等高脂高碳水菜品不能给出明显偏低的数值。
6. 热量应约等于 4×碳水 + 4×蛋白质 + 9×脂肪（允许合理误差）。
7. 只输出 JSON，不要 Markdown、解释或代码块。

返回结构必须是：
{
  "content": "……",
  "summary": "……",
  "calories": 0,
  "carbs": 0,
  "protein": 0,
  "fat": 0
}"""


def _number(value, *, minimum: float, maximum: float, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return round(min(max(number, minimum), maximum), 1)


def compose_knowledge(title: str) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("请先填写标题")

    raw = ai_service._call_llm(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"菜名：{title}\n"
                    "请生成适合普通消费者阅读的正文、摘要和每 100g 营养估算。"
                ),
            },
        ]
    )

    print(f"[knowledge-compose] title={title} raw={raw[:1200]}", flush=True)

    data = json.loads(ai_service._strip_code_fence(raw))
    if not isinstance(data, dict):
        raise ValueError("AI 未返回 JSON 对象")

    content = str(data.get("content") or "").strip()
    summary = str(data.get("summary") or "").strip().strip('"“”\'')
    summary = " ".join(summary.split())

    if len(content) < 30:
        raise ValueError("AI 生成的正文过短")
    if not summary or summary == title:
        raise ValueError("AI 生成的摘要无效")

    return {
        "content": content[:4000],
        "summary": summary[:120],
        "calories": _number(data.get("calories"), minimum=1, maximum=2000),
        "carbs": _number(data.get("carbs"), minimum=0, maximum=200),
        "protein": _number(data.get("protein"), minimum=0, maximum=200),
        "fat": _number(data.get("fat"), minimum=0, maximum=200),
    }
