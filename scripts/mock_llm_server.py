"""OpenAI 兼容的本地模拟大模型服务（仅用于开发/测试，不产生任何真实调用）。

用途：
1. 没有 API Key 时，也能验证「大模型模式」的完整链路（提示词 → 请求 → JSON 校验 → 落库 → 页面展示）；
2. 自动化测试中模拟成功、幻觉、非法 JSON、500 错误等场景，验证降级逻辑；
3. 同时模拟视觉模型 OCR（请求里带 image_url 时返回标签字段）。

启动：
    python scripts/mock_llm_server.py --port 5055

接入（修改 .env 后重启后端）：
    AI_PROVIDER=auto
    AI_BASE_URL=http://127.0.0.1:5055/v1
    AI_API_KEY=mock-key
    AI_MODEL=mock-model

    # 想同时用模拟视觉模型做 OCR：
    OCR_PROVIDER=vision
    OCR_VISION_BASE_URL=http://127.0.0.1:5055/v1
    OCR_VISION_API_KEY=mock-key
    OCR_VISION_MODEL=mock-vl

模式（--mode）：
    clean    正常返回（默认）
    noisy    额外返回一个不存在的配料 + 一个无效引用（用于测试幻觉过滤）
    invalid  返回非 JSON 文本（用于测试格式校验与重试）
    error500 返回 HTTP 500（用于测试降级为规则模式）
"""
from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INGREDIENT_RULES = [
    ("水", "基础配料", "构成产品主体，是饮料中含量最高的成分"),
    ("小麦粉", "主要原料", "提供面团结构与烘焙基础"),
    ("植物油", "油脂原料", "提供脂肪与口感"),
    ("白砂糖", "甜味原料", "提供甜味与能量"),
    ("食用盐", "调味料", "提供咸味，是钠的来源"),
    ("碳酸氢钠", "食品添加剂-膨松剂", "受热或遇酸产生二氧化碳，使产品膨松"),
    ("酵母", "发酵剂", "发酵产生二氧化碳与风味物质"),
    ("碳酸钙", "食品添加剂-营养强化剂", "补充钙，也可作酸度调节剂"),
    ("全脂乳粉", "乳制品原料", "提供乳蛋白、乳脂肪与乳糖"),
    ("赤藓糖醇", "食品添加剂-甜味剂", "糖醇类甜味剂，能量系数很低"),
    ("二氧化碳", "加工助剂", "提供气泡口感"),
    ("柠檬酸", "食品添加剂-酸度调节剂", "调节酸度、增强风味"),
    ("三氯蔗糖", "食品添加剂-甜味剂", "高倍甜味剂，甜度约为蔗糖的 600 倍"),
    ("食用香精", "食品添加剂-香料", "提供或补充香气"),
]

VISION_LABEL = {
    "raw_text": "模拟牌 原味苏打饼干（视觉模型样例）\n净含量：200g\n配料：小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母\n"
    "营养成分表\n能量 1980kJ 24%\n蛋白质 8.5g 14%\n脂肪 18.2g 30%\n碳水化合物 65.4g 22%\n钠 480mg 24%\n"
    "生产日期：2026-09-12\n保质期：12个月\n贮存条件：置于阴凉干燥处\n生产者：模拟食品有限公司\n"
    "产品标准号：GB/T 20980\n致敏物质提示：含有小麦",
    "fields": {
        "food_name": "模拟牌 原味苏打饼干",
        "ingredients_text": "小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母",
        "nutrition_text": "能量 1980kJ 24% 蛋白质 8.5g 14% 脂肪 18.2g 30% 碳水化合物 65.4g 22% 钠 480mg 24%",
        "net_content": "200g",
        "production_date": "2026-09-12",
        "shelf_life": "12个月",
        "storage": "置于阴凉干燥处",
        "producer": "模拟食品有限公司",
        "standard_no": "GB/T 20980",
        "allergen": "含有小麦",
    },
    "lines": [],
}


def _extract_ingredient_names(prompt: str) -> list[str]:
    """只从「结构化配料」段落里取编号项，避免把系统提示词里的编号规则当成配料。"""
    section = ""
    match = re.search(r"【结构化配料[^\n]*】\s*\n(.+?)(?=\n【|\Z)", prompt, re.S)
    if match:
        section = match.group(1)
    names = re.findall(r"^\s*\d+\.\s*(.+?)\s*$", section, re.M)
    return [name for name in names if 0 < len(name) <= 40]


def _extract_knowledge(prompt: str) -> list[dict]:
    entries: list[dict] = []
    # 只匹配知识库上下文里的「[K12] 碳酸钙」形式（编号后必须有空格），
    # 避免误匹配提示词模板中的示例 "source_refs": ["[K3]"]
    for match in re.finditer(r"\[K(\d+)\]\s+([^\n]+)", prompt):
        kid = int(match.group(1))
        title = match.group(2).strip()[:40]
        entries.append({"id": kid, "title": title})
    return entries


def build_ingredient_payload(prompt: str, mode: str) -> dict:
    names = _extract_ingredient_names(prompt)
    knowledge = _extract_knowledge(prompt)
    rule_map = {name: (cat, purpose) for name, cat, purpose in INGREDIENT_RULES}

    ingredients = []
    for index, name in enumerate(names):
        category, purpose = rule_map.get(name, ("未分类", "该成分的常见用途"))
        ref = knowledge[index % len(knowledge)] if knowledge else None
        ingredients.append(
            {
                "name": name,
                "category": category,
                "role": purpose[:20],
                "purpose": purpose,
                "explanation": f"{name}在本产品中主要用作{category}，{purpose}。"
                "该说明为模拟服务生成，仅用于验证链路，不构成安全性判断。",
                "confidence": "medium",
                "evidence": "knowledge_base" if ref else "unverified",
                "source_refs": [f"[K{ref['id']}]"] if ref else [],
                "caution": None,
            }
        )

    citations = [
        {
            "knowledge_id": ref["id"],
            "title": ref["title"],
            "source_name": "模拟来源（仅测试）",
            "claim": f"{ref['title']} 的相关说明",
        }
        for ref in knowledge[:2]
    ]

    if mode == "noisy":
        ingredients.append(
            {
                "name": "火星矿石粉",
                "category": "未知",
                "role": "虚构成分",
                "purpose": "用于验证幻觉过滤",
                "explanation": "这条内容不应出现在最终结果中。",
                "confidence": "low",
                "evidence": "unverified",
                "source_refs": [],
                "caution": None,
            }
        )
        citations.append(
            {"knowledge_id": 999999, "title": "不存在的条目", "source_name": "虚构来源", "claim": "用于验证引用过滤"}
        )

    return {
        "summary": f"模拟服务解析了 {len(names)} 种配料，仅用于验证大模型链路。",
        "nutrition_notes": [
            "本表按每 100g/每份标示，跨产品比较前需要换算到同一基准。",
            "能量与三大营养素折算基本一致（模拟服务不参与真实计算）。",
            "钠含量可换算为食盐估算，需结合每日总摄入量判断。",
        ],
        "ingredients": ingredients,
        "unknown_items": [],
        "unconfirmed": [],
        "citations": citations,
        "safety_note": "本结果为模拟服务生成，不构成任何结论。",
    }


class MockHandler(BaseHTTPRequestHandler):
    mode = "clean"
    calls: list[dict] = []

    def log_message(self, fmt, *args):  # 精简日志
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in {"", "/health"}:
            self._send_json(200, {"status": "ok", "mode": self.mode, "calls": len(self.calls)})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": {"message": "invalid json"}})
            return

        messages = payload.get("messages") or []
        text = ""
        has_image = False
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                text += content
            elif isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        text += part.get("text", "")
                    elif part.get("type") == "image_url":
                        has_image = True

        # 记录到当前子类的 calls（每次 start_server 会创建一个独立子类）
        type(self).calls.append({"has_image": has_image, "mode": self.mode, "model": payload.get("model")})

        if self.mode == "error500":
            self._send_json(500, {"error": {"message": "mock server error"}})
            return

        if has_image:
            content = json.dumps(VISION_LABEL, ensure_ascii=False)
        elif "检索助手" in text:
            # 科普助手兜底：只让模型在候选条目里选一条；refuse / none_rerank 模式返回 NONE
            content = "NONE" if self.mode in {"refuse", "none_rerank"} else "1"
        elif "不替代专业意见" in text:
            # 科普助手「通用大模型回答」分支（不引用本站条目）
            if self.mode == "refuse":
                content = "暂时无法回答这个问题。"
            else:
                content = (
                    "这一类问题需要谨慎：药物与酒精同用可能带来风险，具体要看药品说明书。\n\n"
                    "如果不确定，最稳妥的做法是咨询医生或药师，不要自行尝试。[通用回答，未引用本站资料]"
                )
        elif "食品安全科普助手" in text:
            # 科普助手（RAG）改写：前两句有依据，第三句故意编造，用于验证逐句依据校验
            content = (
                "冷藏保存、吃前彻底加热的隔夜菜通常可以吃。[K1]\n\n"
                "风险主要来自微生物繁殖和蔬菜中的亚硝酸盐，而不是“隔夜”本身。[K1]\n\n"
                "每天喝三杯咖啡能延寿十年。[K1]"
            )
        elif self.mode == "invalid":
            content = "抱歉，我无法按你要求的 JSON 格式输出。"
        else:
            content = json.dumps(build_ingredient_payload(text, self.mode), ensure_ascii=False)

        self._send_json(
            200,
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 0,
                "model": payload.get("model") or "mock-model",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
            },
        )


def start_server(port: int = 0, mode: str = "clean") -> ThreadingHTTPServer:
    """在后台线程启动模拟服务，返回 server 实例（port=0 自动分配）。"""
    handler = type("Handler", (MockHandler,), {"mode": mode, "calls": []})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.mock_mode = mode  # type: ignore[attr-defined]
    server.mock_calls = handler.calls  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI 兼容的本地模拟大模型服务")
    parser.add_argument("--port", type=int, default=5055)
    parser.add_argument("--mode", default="clean", choices=["clean", "noisy", "invalid", "error500"])
    args = parser.parse_args()

    server = start_server(port=args.port, mode=args.mode)
    host, port = server.server_address[:2]
    print("=" * 62)
    print("  模拟大模型服务已启动（仅用于开发/测试，不产生真实调用）")
    print(f"  地址：http://{host}:{port}/v1")
    print(f"  模式：{args.mode}")
    print("  可用端点：POST /v1/chat/completions   GET /health")
    print("=" * 62)
    print("\n在 .env 中配置：")
    print(f"  AI_BASE_URL=http://127.0.0.1:{port}/v1")
    print("  AI_API_KEY=mock-key")
    print("  AI_MODEL=mock-model")
    print(f"  OCR_VISION_BASE_URL=http://127.0.0.1:{port}/v1")
    print("  OCR_VISION_API_KEY=mock-key")
    print("\n按 Ctrl+C 停止。")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        print("\n已停止。")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
