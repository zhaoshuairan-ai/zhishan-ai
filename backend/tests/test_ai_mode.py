"""大模型模式与视觉模型 OCR 的集成测试。

通过本地 OpenAI 兼容模拟服务（scripts/mock_llm_server.py）验证完整链路：
提示词 → HTTP 请求 → JSON 校验 → 幻觉/引用过滤 → 落库 → 接口返回。

说明：这里测试的是**协议与业务链路**，不是某家厂商模型的真实输出质量；
真实厂商 API 需要在 .env 中配置自己的 Key 后人工验证（见 docs/TESTING.md）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from mock_llm_server import start_server  # noqa: E402

CONFIG_KEYS = (
    "AI_PROVIDER",
    "AI_API_KEY",
    "AI_BASE_URL",
    "AI_MODEL",
    "OCR_PROVIDER",
    "OCR_VISION_API_KEY",
    "OCR_VISION_BASE_URL",
    "OCR_VISION_MODEL",
)


@pytest.fixture()
def mock_llm():
    """启动模拟大模型服务，返回 (base_url, server)。"""
    servers = []

    def _start(mode: str = "clean"):
        server = start_server(port=0, mode=mode)
        servers.append(server)
        host, port = server.server_address[:2]
        return f"http://{host}:{port}/v1", server

    yield _start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def restore_config(app):
    original = {key: app.config.get(key) for key in CONFIG_KEYS}
    yield
    for key, value in original.items():
        app.config[key] = value


def _configure_ai(app, base_url: str) -> None:
    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_API_KEY"] = "mock-key"
    app.config["AI_BASE_URL"] = base_url
    app.config["AI_MODEL"] = "mock-model"


def test_ai_mode_full_pipeline(client, auth, record_factory, app, mock_llm):
    base_url, server = mock_llm("clean")
    _configure_ai(app, base_url)
    record_id = record_factory(run_ocr=True)

    resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 200, resp.get_json()
    detail = resp.get_json()["data"]["detail"]

    assert detail["record"]["analysis_mode"] == "ai"
    ingredient = detail["ingredient"]
    assert ingredient["mode"] == "ai"
    assert ingredient["model"] == "mock-model"
    assert ingredient["summary"]
    assert len(ingredient["ingredients"]) >= 6
    for item in ingredient["ingredients"]:
        assert item["evidence"] in {"knowledge_base", "general_knowledge", "unverified"}
        assert item["confidence"] in {"high", "medium", "low"}
    assert ingredient["citations"], "模拟服务应返回引用"
    assert all(c["knowledge_id"] != 999999 for c in ingredient["citations"])
    assert len(ingredient["nutrition_notes"]) >= 2, "AI 模式应返回营养解读"
    assert any("基准" in note for note in ingredient["nutrition_notes"])
    # AI 模式不应出现「规则模式」的说明
    assert "mode_notice" not in detail["meta"]
    # 至少发生了一次真实 HTTP 调用
    assert server.mock_calls, "模拟服务没有收到请求"


def test_ai_filters_hallucinated_ingredient_and_citation(client, auth, record_factory, app, mock_llm):
    base_url, _ = mock_llm("noisy")
    _configure_ai(app, base_url)
    record_id = record_factory(run_ocr=True)

    resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 200
    ingredient = resp.get_json()["data"]["detail"]["ingredient"]

    names = [item["name"] for item in ingredient["ingredients"]]
    assert "火星矿石粉" not in names, "模型编造的配料必须被过滤"
    assert "火星矿石粉" in ingredient["unknown_items"]
    assert any("丢弃" in text for text in ingredient["unconfirmed"])
    assert all(c["knowledge_id"] != 999999 for c in ingredient["citations"]), "虚构引用必须被丢弃"
    assert any("引用" in text for text in ingredient["unconfirmed"])


def test_ai_invalid_json_falls_back_to_rule(client, auth, record_factory, app, mock_llm):
    base_url, server = mock_llm("invalid")
    _configure_ai(app, base_url)
    record_id = record_factory(run_ocr=True)

    resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["result"]["analysis_mode"] == "rule"
    assert data["result"]["errors"], "应记录降级原因"
    assert "未调用大模型" in data["detail"]["meta"]["mode_notice"]
    # 输出非法时应当重试一次
    assert len(server.mock_calls) >= 2


def test_ai_server_error_falls_back_to_rule(client, auth, record_factory, app, mock_llm):
    base_url, _ = mock_llm("error500")
    _configure_ai(app, base_url)
    record_id = record_factory(run_ocr=True)

    resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["result"]["analysis_mode"] == "rule"
    assert data["result"]["errors"]
    assert any("大模型调用失败" in text for text in data["detail"]["ingredient"]["unconfirmed"])


def test_ai_provider_rule_forces_rule_mode(client, auth, record_factory, app, mock_llm):
    base_url, server = mock_llm("clean")
    _configure_ai(app, base_url)
    app.config["AI_PROVIDER"] = "rule"
    record_id = record_factory(run_ocr=True)

    resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["result"]["analysis_mode"] == "rule"
    assert not server.mock_calls, "强制规则模式时不应调用大模型"


def test_vision_ocr_provider(client, auth, app, mock_llm, image_bytes):
    base_url, server = mock_llm("clean")
    app.config["OCR_PROVIDER"] = "vision"
    app.config["OCR_VISION_API_KEY"] = "mock-key"
    app.config["OCR_VISION_BASE_URL"] = base_url
    app.config["OCR_VISION_MODEL"] = "mock-vl"

    import io

    resp = client.post(
        "/api/upload",
        headers=auth,
        data={"file": (io.BytesIO(image_bytes), "label.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    record_id = resp.get_json()["data"]["record"]["id"]

    ocr_resp = client.post("/api/ocr", headers=auth, json={"record_id": record_id})
    assert ocr_resp.status_code == 200, ocr_resp.get_json()
    data = ocr_resp.get_json()["data"]

    assert data["provider"]["key"] == "vision_llm"
    assert data["provider"]["is_demo"] is False
    assert data["fields"]["food_name"] == "模拟牌 原味苏打饼干"
    assert "小麦粉" in data["fields"]["ingredients_text"]
    assert data["fields"]["production_date"] == "2026-09-12"
    assert data["ocr"]["raw_text"]
    assert server.mock_calls and server.mock_calls[0]["has_image"] is True

    detail = client.get(f"/api/records/{record_id}", headers=auth).get_json()["data"]
    assert detail["record"]["is_demo"] is False
    assert detail["record"]["ocr_provider"] == "vision_llm"


def test_vision_provider_without_key_falls_back_to_demo(client, auth, app, image_bytes):
    app.config["OCR_PROVIDER"] = "vision"
    app.config["OCR_VISION_API_KEY"] = ""

    import io

    resp = client.post(
        "/api/upload",
        headers=auth,
        data={"file": (io.BytesIO(image_bytes), "label.png")},
        content_type="multipart/form-data",
    )
    record_id = resp.get_json()["data"]["record"]["id"]
    ocr_resp = client.post("/api/ocr", headers=auth, json={"record_id": record_id})
    assert ocr_resp.status_code == 200
    data = ocr_resp.get_json()["data"]
    assert data["provider"]["key"] == "demo"
    assert data["provider"]["is_demo"] is True
    assert data["demo_warning"]
