"""视觉模型地址处理与 404 自动纠错的测试（不依赖外网）。"""
from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from app.config import _clean
from app.services.ocr.base import OcrProviderError
from app.services.ocr.vision_llm import VisionLlmProvider, candidate_urls, normalize_base_url


class FakeVisionHandler(BaseHTTPRequestHandler):
    """模拟 OpenAI 兼容的视觉接口：/v1/chat/completions 故意 404。"""

    hits: list[str] = []
    always_404 = False

    def do_POST(self) -> None:  # noqa: N802
        type(self).hits.append(self.path)
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        if type(self).always_404 or self.path.endswith("/v1/chat/completions"):
            body = b'{"error":{"message":"not found"}}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        content = json.dumps(
            {
                "raw_text": "测试牌 香脆薯片\n配料：马铃薯、植物油",
                "fields": {
                    "food_name": "测试牌 香脆薯片",
                    "ingredients_text": "马铃薯、植物油",
                    "nutrition_text": "每100g\n能量 2200kJ 26%",
                },
                "lines": [{"text": "测试牌 香脆薯片", "confidence": 0.95}, {"text": "配料：马铃薯、植物油", "confidence": 0.9}],
            },
            ensure_ascii=False,
        )
        payload = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:  # 静默
        pass


@pytest.fixture()
def vision_server():
    FakeVisionHandler.hits = []
    FakeVisionHandler.always_404 = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeVisionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def sample_image(tmp_path):
    path = tmp_path / "label.png"
    Image.new("RGB", (320, 240), (250, 250, 250)).save(path)
    return path


def test_env_value_strips_inline_comment():
    """行内注释紧贴值（无空格）时也要能清洗，避免拼出带 # 的非法地址。"""
    assert _clean("60#45") == "60"
    assert _clean("https://api.deepseek.com#https://dashscope.aliyuncs.com") == "https://api.deepseek.com"
    assert _clean("  deepseek-flash  ") == "deepseek-flash"
    assert _clean("'sk-abc'") == "sk-abc"


def test_candidate_urls_normalization():
    assert normalize_base_url("https://api.deepseek.com/chat/completions") == "https://api.deepseek.com"
    assert normalize_base_url("https://api.deepseek.com/v1/") == "https://api.deepseek.com/v1"
    assert candidate_urls("https://api.deepseek.com") == [
        "https://api.deepseek.com/chat/completions",
        "https://api.deepseek.com/v1/chat/completions",
    ]
    assert candidate_urls("https://api.deepseek.com/v1")[0] == "https://api.deepseek.com/v1/chat/completions"
    assert candidate_urls("https://api.deepseek.com/v1")[1] == "https://api.deepseek.com/chat/completions"


def test_invalid_base_url_raises_clear_error():
    with pytest.raises(OcrProviderError) as exc:
        candidate_urls("api.deepseek.com")
    assert "OCR_VISION_BASE_URL" in str(exc.value)


def test_vision_provider_falls_back_when_v1_returns_404(app, sample_image, vision_server):
    """填了 /v1 但服务端只认根路径时，应自动换地址重试并成功。"""
    app.config.update(
        OCR_VISION_BASE_URL=f"http://127.0.0.1:{vision_server}/v1",
        OCR_VISION_API_KEY="test-key",
        OCR_VISION_MODEL="deepseek-flash",
        OCR_TIMEOUT=10,
    )
    with app.app_context():
        output = VisionLlmProvider().recognize(sample_image)

    assert output.lines, "应返回识别到的文字"
    assert output.raw_payload["fields"]["food_name"] == "测试牌 香脆薯片"
    assert output.raw_payload["endpoint"] == f"http://127.0.0.1:{vision_server}/chat/completions"
    assert FakeVisionHandler.hits[0] == "/v1/chat/completions", "应先尝试用户填写的地址"
    assert "/chat/completions" in FakeVisionHandler.hits


def test_vision_provider_404_reports_attempted_urls(app, sample_image, vision_server):
    """两个地址都 404 时，错误信息要给出尝试过的完整地址和修改建议。"""
    FakeVisionHandler.always_404 = True
    app.config.update(
        OCR_VISION_BASE_URL=f"http://127.0.0.1:{vision_server}/v1",
        OCR_VISION_API_KEY="test-key",
        OCR_VISION_MODEL="deepseek-flash",
        OCR_TIMEOUT=10,
    )
    with app.app_context():
        with pytest.raises(OcrProviderError) as exc:
            VisionLlmProvider().recognize(sample_image)

    message = str(exc.value)
    assert "HTTP 404" in message
    assert "/v1/chat/completions" in message and "/chat/completions" in message
    assert "OCR_VISION_BASE_URL" in message
