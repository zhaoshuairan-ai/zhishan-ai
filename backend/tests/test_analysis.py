"""分析流水线测试：结果结构、校验、AI 失败降级。"""
from __future__ import annotations

import pytest

from app.services import ai_service


def test_analyze_produces_full_result(client, auth, analyzed_record):
    resp = client.get(f"/api/records/{analyzed_record}", headers=auth)
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    record = data["record"]
    assert record["status"] == "analyzed"
    assert record["analysis_mode"] == "rule"
    assert record["overall_check"] in {"none_found", "needs_review", "suspected"}
    assert record["ingredient_count"] >= 3

    ingredient = data["ingredient"]
    assert ingredient["mode"] == "rule"
    assert ingredient["summary"]
    assert len(ingredient["ingredients"]) >= 3
    for item in ingredient["ingredients"]:
        assert item["name"]
        assert item["confidence"] in {"high", "medium", "low"}
        assert item["evidence"] in {"knowledge_base", "general_knowledge", "unverified"}
        assert isinstance(item["source_refs"], list)

    nutrition = data["nutrition"]
    assert nutrition["basis"] in {"per_100g", "per_100ml", "per_serving"}
    keys = {item["key"] for item in nutrition["items"]}
    assert {"energy", "protein", "fat", "carbohydrate", "sodium"} <= keys
    energy = next(item for item in nutrition["items"] if item["key"] == "energy")
    assert energy["value"] is not None
    assert energy["unit"] in {"kJ", "kcal"}

    check = data["check"]
    assert check["overall"] in {"none_found", "needs_review", "suspected"}
    assert len(check["items"]) >= 10
    for item in check["items"]:
        assert item["rule_id"]
        assert item["level"] in {"pass", "info", "review", "suspected", "skip"}
        assert item["reason"]
        assert item["rule_version"]

    assert data["meta"]["disclaimer"]


def test_rule_mode_generates_nutrition_notes(client, auth, analyzed_record):
    """规则模式也要给出营养解读（基准、能量、钠），但不做健康结论。"""
    data = client.get(f"/api/records/{analyzed_record}", headers=auth).get_json()["data"]
    notes = data["ingredient"]["nutrition_notes"]
    assert isinstance(notes, list) and len(notes) >= 2
    joined = " ".join(notes)
    assert "每 100g" in joined
    assert "钠" in joined
    assert "食盐" in joined
    # 不允许出现健康/安全结论式表述
    for word in ("健康", "安全", "有毒", "致癌"):
        assert word not in joined


def test_analyze_requires_ocr(client, auth, record_factory):
    record_id = record_factory()
    resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 404
    assert "识别" in resp.get_json()["message"]


def test_analyze_rejects_empty_content(client, auth, record_factory):
    record_id = record_factory(run_ocr=True)
    resp = client.put(
        f"/api/records/{record_id}/ocr",
        headers=auth,
        json={"fields": {"ingredients_text": "", "nutrition_text": ""}},
    )
    assert resp.status_code == 200
    resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 400
    assert "无法分析" in resp.get_json()["message"]


def test_analyze_falls_back_when_ai_fails(client, auth, record_factory, app, monkeypatch):
    record_id = record_factory(run_ocr=True)
    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_API_KEY"] = "test-key-for-failure"

    def _fail(**kwargs):
        raise ai_service.AIServiceError("模拟大模型超时", code="ai_timeout", status=504)

    monkeypatch.setattr(ai_service, "run_ai_analysis", _fail)
    try:
        resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert body["result"]["analysis_mode"] == "rule"
        assert body["result"]["errors"]
        assert "大模型调用失败" in " ".join(body["detail"]["ingredient"]["unconfirmed"])
        assert "未调用大模型" in body["detail"]["meta"]["mode_notice"]
    finally:
        app.config["AI_PROVIDER"] = "rule"
        app.config["AI_API_KEY"] = ""


def test_reanalyze_updates_existing_record(client, auth, analyzed_record):
    resp = client.post(f"/api/records/{analyzed_record}/reanalyze", headers=auth, json={})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["result"]["status"] == "analyzed"


def test_analyze_other_user_record_denied(client, other_auth, record_factory):
    record_id = record_factory(run_ocr=True)
    resp = client.post("/api/analyze", headers=other_auth, json={"record_id": record_id})
    assert resp.status_code == 404


def test_nutrition_missing_fields_are_reported_as_missing(client, auth, record_factory):
    record_id = record_factory(run_ocr=True)
    client.put(
        f"/api/records/{record_id}/ocr",
        headers=auth,
        json={"fields": {"nutrition_text": "能量 900kJ 11%"}},
    )
    resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 200
    nutrition = resp.get_json()["data"]["detail"]["nutrition"]
    protein = next(item for item in nutrition["items"] if item["key"] == "protein")
    assert protein["value"] is None
    assert protein["status"] == "missing"
    assert any("未识别" in warning["message"] or "基准" in warning["message"] for warning in nutrition["warnings"])


def test_edit_record_name_and_manual_nutrition(client, auth, analyzed_record):
    resp = client.put(
        f"/api/records/{analyzed_record}",
        headers=auth,
        json={
            "food_name": "手工完善苏打饼干",
            "nutrition": {"energy": 2000, "protein": 8.5, "fat": 20, "carbohydrate": 60, "sodium": 300, "sugar": 5},
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["record"]["food_name"] == "手工完善苏打饼干"
    items = {item["key"]: item for item in data["nutrition"]["items"]}
    assert items["energy"]["value"] == 2000
    assert items["protein"]["value"] == 8.5
    assert items["sodium"]["value"] == 300
    assert data["nutrition"]["source"] == "manual"


def test_water_only_notice_and_marketing_name_fallback():
    from app.services.analysis_service import apply_water_notice, is_water_only, normalize_food_name

    assert is_water_only({"items": [{"name": "水"}]}) is True
    result = apply_water_notice({"summary": "这是饮用水。", "nutrition_notes": [], "unconfirmed": ["营养数据缺失"]})
    assert result["summary"] == "这是纯净水，0卡0脂，无需评估"
    assert result["nutrition_notes"] == []
    assert result["unconfirmed"] == []
    assert result["water_only"] is True
    assert len(result["tags"]) == 3
    assert normalize_food_name("#您·新鲜·养自己!") == "[待完善] 某品牌食品"
    assert normalize_food_name("") == ""
    assert normalize_food_name("苏打饼干") == "苏打饼干"
