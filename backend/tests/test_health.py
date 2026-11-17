"""健康检查与统一错误格式测试。"""
from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["checks"]["database"]["status"] == "ok"
    assert "storage" in body["data"]["checks"]


def test_health_response_has_request_id(client):
    resp = client.get("/api/health")
    assert resp.headers.get("X-Request-ID")
    assert resp.headers.get("X-Response-Time")


def test_unknown_api_returns_json_404(client):
    resp = client.get("/api/not-exists")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["success"] is False
    assert body["code"] == 40400
    assert isinstance(body["message"], str) and body["message"]


def test_protected_endpoint_requires_login(client):
    resp = client.get("/api/records")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["success"] is False
    assert body["code"] == 40100


def test_settings_status_does_not_leak_keys(client):
    resp = client.get("/api/settings/status")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["ai"]["api_key"] in {"未配置"} or "隐藏" in data["ai"]["api_key"]
    assert data["ocr"]["vision_key"] in {"未配置"} or "隐藏" in data["ocr"]["vision_key"]
    # 只描述哈希算法，绝不返回哈希本身或明文
    assert data["security"]["password_hashing"].startswith("scrypt")
    assert "password_hash" not in data["security"]
    assert data["security"]["api_key_in_logs"] is False


def test_ruleset_endpoint_lists_rules(client):
    resp = client.get("/api/rules")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["rule_count"] >= 20
    assert data["version"]
    assert data["categories"]
    for category in data["categories"]:
        for rule in category["rules"]:
            assert rule["source"]["name"]
