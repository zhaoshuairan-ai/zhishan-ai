"""家庭食材管家与食谱 Agent 测试。"""
from __future__ import annotations

import io
import json
from datetime import date, timedelta

import pytest


def _add_item(client, auth, **overrides):
    payload = {
        "name": "鸡胸肉",
        "category": "meat",
        "quantity": 1,
        "unit": "份",
        "purchased_at": date.today().isoformat(),
        "expires_at": (date.today() + timedelta(days=2)).isoformat(),
        "note": "",
    }
    payload.update(overrides)
    return client.post("/api/pantry", headers=auth, json=payload)


def test_pantry_crud_and_ownership(client, auth, other_auth):
    created = _add_item(client, auth, name="西兰花", category="vegetable")
    assert created.status_code == 201, created.get_json()
    item = created.get_json()["data"]["item"]
    assert item["name"] == "西兰花"
    assert item["status"] == "expiring"

    listing = client.get("/api/pantry", headers=auth)
    assert listing.status_code == 200
    assert listing.get_json()["data"]["total"] == 1

    updated = client.put(f"/api/pantry/{item['id']}", headers=auth, json={"quantity": 2, "name": "西兰花"})
    assert updated.status_code == 200
    assert updated.get_json()["data"]["item"]["quantity"] == 2

    # 其他用户不能访问/修改
    assert client.put(f"/api/pantry/{item['id']}", headers=other_auth, json={"quantity": 9}).status_code == 404
    assert client.delete(f"/api/pantry/{item['id']}", headers=other_auth).status_code == 404

    deleted = client.delete(f"/api/pantry/{item['id']}", headers=auth)
    assert deleted.status_code == 200
    assert client.get("/api/pantry", headers=auth).get_json()["data"]["total"] == 0


def test_pantry_validation(client, auth):
    assert _add_item(client, auth, category="unknown").status_code == 400
    assert _add_item(client, auth, quantity=0).status_code == 400
    assert _add_item(client, auth, expires_at="2020-01-01", purchased_at="2026-01-01").status_code == 400
    assert _add_item(client, auth, name="").status_code == 400


def test_reminders_include_expiring_and_expired(client, auth):
    today = date.today()
    _add_item(client, auth, name="今天到期", expires_at=today.isoformat())
    _add_item(
        client,
        auth,
        name="已过期",
        purchased_at=(today - timedelta(days=5)).isoformat(),
        expires_at=(today - timedelta(days=2)).isoformat(),
    )
    _add_item(client, auth, name="还很久", expires_at=(today + timedelta(days=30)).isoformat())
    _add_item(client, auth, name="没有日期", expires_at=None)

    data = client.get("/api/pantry/reminders", headers=auth).get_json()["data"]
    assert data["counts"]["expiring"] == 1
    assert data["counts"]["expired"] == 1
    assert data["expiring"][0]["name"] == "今天到期"
    assert data["urgent"]
    assert data["urgent"][0]["rescue"]["recipe_name"]
    assert data["expired"][0]["name"] == "已过期"
    assert "过期" in data["message"]


def test_health_profile_save_and_options(client, auth):
    initial = client.get("/api/health-profile", headers=auth).get_json()["data"]
    assert initial["conditions"] == []
    assert initial["options"]["conditions"]

    saved = client.put(
        "/api/health-profile",
        headers=auth,
        json={
            "conditions": ["hypertension", "diabetes", "unknown"],
            "goals": ["low_sodium", "weight_loss"],
            "allergies": ["花生", "花生", "  "],
            "notes": "控盐",
        },
    )
    assert saved.status_code == 200
    data = client.get("/api/health-profile", headers=auth).get_json()["data"]
    assert data["conditions"] == ["hypertension", "diabetes"]
    assert data["condition_labels"] == ["高血压", "糖尿病"]
    assert data["allergies"] == ["花生"]


def test_rule_recipe_plan_uses_expiring_and_respects_profile(client, auth):
    _add_item(client, auth, name="菠菜", category="vegetable", expires_at=(date.today() + timedelta(days=1)).isoformat())
    _add_item(client, auth, name="鸡胸肉", category="meat", expires_at=(date.today() + timedelta(days=2)).isoformat())
    _add_item(client, auth, name="大米", category="staple", expires_at=(date.today() + timedelta(days=300)).isoformat())
    _add_item(client, auth, name="花生米", category="other", expires_at=(date.today() + timedelta(days=100)).isoformat())
    client.put(
        "/api/health-profile",
        headers=auth,
        json={"conditions": ["hypertension", "diabetes"], "allergies": ["花生"]},
    )

    resp = client.post("/api/recipes/plan", headers=auth, json={"meals": 3, "max_minutes": 30})
    assert resp.status_code == 201, resp.get_json()
    plan = resp.get_json()["data"]
    assert plan["mode"] == "rule"
    assert plan["mode_label"] == "规则引擎食谱规划"
    assert len(plan["meals"]) == 3
    assert plan["nutrition_totals"]["energy_kcal"] > 0
    assert all("missing" in meal for meal in plan["meals"])
    assert any(item["name"] == "食用油" for meal in plan["meals"] for item in meal["missing"])
    assert any("临期" in line for line in plan["agent_trace"])
    assert any("高血压" in line for line in plan["agent_trace"])
    all_ingredients = [ingredient["name"] for meal in plan["meals"] for ingredient in meal["ingredients"]]
    assert all("花生" not in name for name in all_ingredients)
    assert plan["shopping_list"]
    assert plan["disclaimer"]
    assert plan["plan_id"]

    history = client.get("/api/recipes/history", headers=auth).get_json()["data"]["items"]
    assert history and history[0]["mode"] == "rule"


def test_recipe_plan_requires_pantry(client, auth):
    resp = client.post("/api/recipes/plan", headers=auth, json={"meals": 3})
    assert resp.status_code == 400
    assert "食材" in resp.get_json()["message"]


def test_recipe_ai_mode_with_valid_json(client, auth, monkeypatch):
    from app.services import recipe_agent_service

    _add_item(client, auth, name="番茄", category="vegetable")
    _add_item(client, auth, name="鸡蛋", category="egg_dairy")
    _add_item(client, auth, name="大米", category="staple")

    fake = {
        "summary": "AI 规划的两餐",
        "meals": [
            {
                "meal_type": "午餐",
                "name": "番茄炒蛋配米饭",
                "ingredients": [
                    {"name": "番茄", "amount": "200g", "from_pantry": True, "expiring": True},
                    {"name": "鸡蛋", "amount": "2 个", "from_pantry": True, "expiring": False},
                    {"name": "大米", "amount": "80g", "from_pantry": True, "expiring": False},
                ],
                "steps": ["番茄切块", "鸡蛋炒熟后混合", "少盐调味"],
                "nutrition": {"energy_kcal": 420, "protein_g": 18, "fat_g": 12, "carbs_g": 55, "sodium_mg": 480, "sugar_g": 5},
                "suitability": {"高血压": "少盐"},
                "tips": "搭配蔬菜",
            },
            {
                "meal_type": "晚餐",
                "name": "蔬菜蛋汤",
                "ingredients": [{"name": "番茄", "amount": "100g", "from_pantry": True, "expiring": True}],
                "steps": ["煮汤"],
                "nutrition": {"energy_kcal": 120, "protein_g": 6, "fat_g": 3, "carbs_g": 15, "sodium_mg": 200, "sugar_g": 3},
                "suitability": {},
                "tips": "",
            },
        ],
        "shopping_list": ["食用油"],
        "agent_trace": ["优先使用番茄"],
        "warnings": [],
    }
    monkeypatch.setattr(recipe_agent_service, "_allow_ai", lambda: True)
    monkeypatch.setattr(recipe_agent_service, "_call_llm", lambda messages: json.dumps(fake, ensure_ascii=False))
    monkeypatch.setattr(recipe_agent_service, "_config", lambda: {"base": "http://mock", "key": "k", "model": "mock", "timeout": 5, "mode": "auto"})

    resp = client.post("/api/recipes/plan", headers=auth, json={"meals": 2})
    assert resp.status_code == 201, resp.get_json()
    plan = resp.get_json()["data"]
    assert plan["mode"] == "ai"
    assert plan["mode_label"] == "AI Agent 食谱规划"
    assert len(plan["meals"]) == 2
    assert plan["nutrition_totals"]["energy_kcal"] == 540
    assert plan["ai_error"] is None


def test_recipe_ai_invalid_json_falls_back_to_rule(client, auth, monkeypatch):
    from app.services import recipe_agent_service

    _add_item(client, auth, name="青菜", category="vegetable")
    monkeypatch.setattr(recipe_agent_service, "_allow_ai", lambda: True)
    monkeypatch.setattr(recipe_agent_service, "_call_llm", lambda messages: "这不是 JSON")
    monkeypatch.setattr(recipe_agent_service, "_config", lambda: {"base": "http://mock", "key": "k", "model": "mock", "timeout": 5, "mode": "auto"})

    resp = client.post("/api/recipes/plan", headers=auth, json={"meals": 2})
    assert resp.status_code == 201
    plan = resp.get_json()["data"]
    assert plan["mode"] == "rule"
    assert plan["ai_error"]
    assert any("规则引擎" in warning for warning in plan["warnings"])


def test_recipe_ai_allergen_output_falls_back(client, auth, monkeypatch):
    from app.services import recipe_agent_service

    _add_item(client, auth, name="鸡蛋", category="egg_dairy")
    client.put("/api/health-profile", headers=auth, json={"allergies": ["鸡蛋"]})
    fake = {
        "summary": "含过敏原",
        "meals": [
            {
                "meal_type": "午餐",
                "name": "炒蛋",
                "ingredients": [{"name": "鸡蛋", "amount": "2 个", "from_pantry": True, "expiring": False}],
                "steps": [],
                "nutrition": {},
                "suitability": {},
                "tips": "",
            }
        ],
        "shopping_list": [],
        "agent_trace": [],
        "warnings": [],
    }
    monkeypatch.setattr(recipe_agent_service, "_allow_ai", lambda: True)
    monkeypatch.setattr(recipe_agent_service, "_call_llm", lambda messages: json.dumps(fake, ensure_ascii=False))
    monkeypatch.setattr(recipe_agent_service, "_config", lambda: {"base": "http://mock", "key": "k", "model": "mock", "timeout": 5, "mode": "auto"})

    resp = client.post("/api/recipes/plan", headers=auth, json={"meals": 2})
    plan = resp.get_json()["data"]
    assert plan["mode"] == "rule"
    assert plan["ai_error"]


def test_voice_text_import_parses_chinese_quantities(client, auth):
    resp = client.post(
        "/api/pantry/import/text",
        headers=auth,
        json={"text": "今天买了3个西红柿、2斤排骨，放冷藏", "source": "voice"},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["mode"] == "rule"
    names = {item["name"]: item for item in data["items"]}
    assert "西红柿" in names and "排骨" in names
    assert names["西红柿"]["quantity"] == 3
    assert names["西红柿"]["unit"] == "个"
    assert names["排骨"]["quantity"] == 2
    assert names["排骨"]["unit"] == "斤"
    assert names["排骨"]["category"] == "meat"
    assert names["西红柿"]["expires_at"] > date.today().isoformat()
    assert all("放冷藏" not in item["name"] for item in data["items"])


def test_batch_import_and_shelf_life_lookup(client, auth):
    items = [
        {"name": "牛奶", "category": "egg_dairy", "quantity": 2, "unit": "盒", "expires_at": (date.today() + timedelta(days=7)).isoformat()},
        {"name": "菠菜", "category": "vegetable", "quantity": 1, "unit": "把", "expires_at": (date.today() + timedelta(days=3)).isoformat()},
    ]
    resp = client.post("/api/pantry/batch", headers=auth, json={"items": items})
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["data"]["count"] == 2
    assert client.get("/api/pantry", headers=auth).get_json()["data"]["total"] == 2

    shelf = client.get("/api/pantry/lookup/shelf-life", headers=auth, query_string={"name": "牛奶"}).get_json()["data"]
    assert shelf["days"] == 7
    assert shelf["source"] == "builtin"
    unknown = client.get("/api/pantry/lookup/shelf-life", headers=auth, query_string={"name": "外星果"}).get_json()["data"]
    assert unknown["days"] is None
    assert unknown["warning"]
    barcode = client.get("/api/pantry/lookup/barcode", headers=auth, query_string={"barcode": "6901234567890"}).get_json()["data"]
    assert barcode["found"] is False
    assert "未收录" in barcode["message"] or "公开" in barcode["message"]


def test_receipt_import_with_mocked_ocr(client, auth, monkeypatch):
    import io
    from types import SimpleNamespace
    from PIL import Image
    from app.api import pantry as pantry_api

    def fake_recognize(path):
        return SimpleNamespace(
            raw_text="西红柿 3个 12.00\n排骨 2斤 30.00\n合计 42.00",
            provider="test",
            provider_label="测试 OCR",
            is_demo=True,
            lines=[],
            warning=None,
        )

    monkeypatch.setattr(pantry_api.ocr, "recognize", fake_recognize)
    buf = io.BytesIO()
    Image.new("RGB", (120, 120), "white").save(buf, "PNG")
    buf.seek(0)
    resp = client.post(
        "/api/pantry/import/receipt",
        headers=auth,
        data={"file": (buf, "receipt.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    names = {item["name"] for item in data["items"]}
    assert "西红柿" in names and "排骨" in names
    assert data["ocr"]["provider"] == "test"


def test_sse_stream_once_returns_reminder(client, auth):
    _add_item(client, auth, name="酸奶", expires_at=(date.today() + timedelta(days=1)).isoformat())
    resp = client.get("/api/pantry/stream?once=1", headers=auth)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type
    body = resp.get_data(as_text=True)
    assert body.startswith("event: reminder")
    assert "酸奶" in body


def test_notify_test_simulates_email_and_reports_channels(client, auth):
    _add_item(client, auth, name="牛奶", expires_at=date.today().isoformat())
    resp = client.post("/api/pantry/notify-test", headers=auth)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["counts"]["expiring"] == 1
    channels = {item["channel"]: item for item in data["channels"]}
    assert channels["email"]["status"] == "simulated"
    assert channels["wecom"]["status"] == "unconfigured"


def test_rescue_recipe_focuses_expiring_item(client, auth):
    item = _add_item(
        client, auth, name="菠菜", category="vegetable",
        expires_at=(date.today() + timedelta(days=1)).isoformat(),
    ).get_json()["data"]["item"]
    _add_item(client, auth, name="鸡蛋", category="egg_dairy")
    resp = client.post("/api/recipes/rescue", headers=auth, json={"item_id": item["id"], "meals": 2})
    assert resp.status_code == 201, resp.get_json()
    plan = resp.get_json()["data"]
    assert plan["focus_item"]["id"] == item["id"]
    names = [ingredient["name"] for meal in plan["meals"] for ingredient in meal["ingredients"]]
    assert "菠菜" in names
    assert plan["focus_in_final"] is True
    assert not any("未优先使用指定的临期食材" in item for item in plan.get("rule_vetoes", []))
    assert plan["requested_meals"] == 2
    assert plan["actual_meals"] == len(plan["meals"])
    assert plan["mode"] == "rule"


def test_ai_plan_is_vetoed_then_regenerated(client, auth, monkeypatch):
    from app.services import recipe_agent_service

    _add_item(client, auth, name="番茄", category="vegetable")
    _add_item(client, auth, name="料酒", category="condiment")
    client.put("/api/health-profile", headers=auth, json={"conditions": ["pregnancy"]})

    def meal(name, ingredient):
        return {
            "meal_type": "午餐",
            "name": name,
            "ingredients": [{"name": ingredient, "amount": "100g", "from_pantry": True, "expiring": False}],
            "steps": [],
            "nutrition": {"energy_kcal": 200, "protein_g": 5, "fat_g": 3, "carbs_g": 30, "sodium_mg": 100, "sugar_g": 3},
            "suitability": {},
            "tips": "",
        }

    bad = {"summary": "含酒", "meals": [meal("料酒炒番茄", "料酒")], "shopping_list": [], "agent_trace": [], "warnings": []}
    good = {"summary": "安全版", "meals": [meal("清炒番茄", "番茄")], "shopping_list": [], "agent_trace": [], "warnings": []}
    calls = {"n": 0}

    def fake_llm(messages):
        calls["n"] += 1
        return json.dumps(bad if calls["n"] == 1 else good, ensure_ascii=False)

    monkeypatch.setattr(recipe_agent_service, "_allow_ai", lambda: True)
    monkeypatch.setattr(recipe_agent_service, "_call_llm", fake_llm)
    monkeypatch.setattr(recipe_agent_service, "_config", lambda: {"base": "http://mock", "key": "k", "model": "mock", "timeout": 5, "mode": "auto"})

    resp = client.post("/api/recipes/plan", headers=auth, json={"meals": 2})
    assert resp.status_code == 201, resp.get_json()
    plan = resp.get_json()["data"]
    assert plan["mode"] == "ai"
    assert calls["n"] == 2
    assert plan["rule_vetoes"]
    assert any("孕期" in item for item in plan["rule_vetoes"])
    assert any("AI 智能修正" in line for line in plan["agent_trace"])


def test_branded_processed_foods_get_shelf_life_defaults(client, auth):
    cases = {
        "蓝凌记*坚果盛宴": 180,
        "水果果切": 1,
        "软式甜饼巧克力味": 180,
        "康师傅经典奶茶 500ml": 270,
    }
    for name, days in cases.items():
        data = client.get(
            "/api/pantry/lookup/shelf-life", headers=auth, query_string={"name": name}
        ).get_json()["data"]
        assert data["days"] == days, name
        assert data["source"] == "builtin"
        assert not data["warning"], name


def test_unknown_import_warnings_are_aggregated_without_technical_key_text(client, auth):
    resp = client.post(
        "/api/pantry/import/text",
        headers=auth,
        json={"text": "今天买了蓝凌记坚果盛宴、水果果切、软式甜饼、康师傅经典奶茶", "source": "voice"},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    shelf_warnings = [item for item in data["warnings"] if "保质期" in item]
    # 这些名称都能命中内置表，不应出现“未配置 Key”的逐条警告
    assert not shelf_warnings
    assert all("Key" not in item for item in data["warnings"])


def test_server_side_barcode_decode_for_unsupported_browsers(client, auth):
    import cv2
    import numpy as np
    import zxingcpp

    barcode = zxingcpp.create_barcode("5901234123457", zxingcpp.BarcodeFormat.EAN13)
    image = np.array(zxingcpp.write_barcode_to_image(barcode, scale=3, add_hrt=True, add_quiet_zones=True))
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    resp = client.post(
        "/api/pantry/decode-barcode",
        headers=auth,
        data={"file": (io.BytesIO(encoded.tobytes()), "barcode.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["found"] is True
    assert data["barcode"] == "5901234123457"
    assert "EAN" in data["format"]


def test_showapi_barcode_lookup_and_cache(client, auth, app, monkeypatch):
    from app.services import shelf_life_service

    app.config["BARCODE_PROVIDER"] = "showapi"
    app.config["SHOWAPI_APP_KEY"] = "test-key"
    calls = {"n": 0}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "showapi_res_code": 0,
                "showapi_res_error": "",
                "showapi_res_body": {
                    "ret_code": "0",
                    "code": "6907376500056",
                    "goodsName": "强生婴儿牛奶沐浴露300毫升",
                    "manuName": "强生(中国)有限公司",
                    "spec": "300毫升",
                    "trademark": "强生婴儿",
                    "goodsType": "个人护理用品>>洗浴、身体护理品",
                    "gpc": "10000330",
                    "price": "",
                    "img": "https://example.invalid/temp.jpg",
                },
            }

    def fake_post(url, **kwargs):
        calls["n"] += 1
        assert url == "https://route.showapi.com/66-22"
        assert kwargs["params"]["appKey"] == "test-key"
        assert kwargs["data"]["code"] == "6907376500056"
        return FakeResponse()

    monkeypatch.setattr(shelf_life_service.requests, "post", fake_post)
    first = client.get(
        "/api/pantry/lookup/barcode", headers=auth, query_string={"barcode": "6907376500056"}
    ).get_json()["data"]
    assert first["found"] is True
    assert first["name"].startswith("强生婴儿牛奶沐浴露")
    assert first["brand"] == "强生婴儿"
    assert first["spec"] == "300毫升"
    assert first["manufacturer"].startswith("强生")
    assert first["source"] == "showapi"
    assert first["cached"] is False
    # 沐浴露不是食品，不能套用牛奶的 7 天保质期
    assert first["shelf_life"]["days"] is None
    assert first["category"] == "other"

    second = client.get(
        "/api/pantry/lookup/barcode", headers=auth, query_string={"barcode": "6907376500056"}
    ).get_json()["data"]
    assert second["found"] is True
    assert second["cached"] is True
    assert calls["n"] == 1


def test_showapi_barcode_not_found_returns_clear_message(client, auth, app, monkeypatch):
    from app.services import shelf_life_service

    app.config["BARCODE_PROVIDER"] = "showapi"
    app.config["SHOWAPI_APP_KEY"] = "test-key"

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "showapi_res_code": 0,
                "showapi_res_body": {"ret_code": "-1", "remark": "未查询到该商品"},
            }

    monkeypatch.setattr(shelf_life_service.requests, "post", lambda url, **kwargs: FakeResponse())
    data = client.get(
        "/api/pantry/lookup/barcode", headers=auth, query_string={"barcode": "6900000000000"}
    ).get_json()["data"]
    assert data["found"] is False
    assert "未查询到" in data["message"]


def test_openfoodfacts_public_lookup_mapping(client, auth, app, monkeypatch):
    from app.services import shelf_life_service

    app.config["BARCODE_PROVIDER"] = "openfoodfacts"

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": 1,
                "product": {
                    "product_name_zh": "测试燕麦饼干",
                    "brands": "测试品牌",
                    "quantity": "200g",
                    "categories": "饼干",
                },
            }

    monkeypatch.setattr(shelf_life_service.requests, "get", lambda url, **kwargs: FakeResponse())
    data = client.get(
        "/api/pantry/lookup/barcode", headers=auth, query_string={"barcode": "1234567890123"}
    ).get_json()["data"]
    assert data["found"] is True
    assert data["source"] == "openfoodfacts"
    assert data["name"] == "测试燕麦饼干"
    assert data["brand"] == "测试品牌"
    assert "非商业" in data["provider_label"]
    assert data["shelf_life"]["days"] == 180


def test_public_mode_falls_back_to_local_public_catalog(client, auth, app):
    app.config["BARCODE_PROVIDER"] = "openfoodfacts"
    data = client.get(
        "/api/pantry/lookup/barcode", headers=auth, query_string={"barcode": "6954767410388"}
    ).get_json()["data"]
    assert data["found"] is True
    assert data["source"] in {"openfoodfacts", "local_catalog"}
    assert data["name"]
    # 首次可能来自本地公开缓存，不应伪装成商业库
    assert "非商业" in data["provider_label"] or "公开" in data["provider_label"]


def test_barcode_decode_handles_off_center_rotated_photo(client, auth):
    import cv2
    import numpy as np
    import zxingcpp

    barcode = zxingcpp.create_barcode("6954767410388", zxingcpp.BarcodeFormat.EAN13)
    image = np.array(zxingcpp.write_barcode_to_image(barcode, scale=3, add_hrt=True, add_quiet_zones=True))
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    small = cv2.resize(image, (260, 130))
    # 大图 + 条码在左下角，模拟“不在正中间”的照片
    canvas = np.full((1800, 2400, 3), 245, np.uint8)
    canvas[1550:1680, 120:380] = small
    matrix = cv2.getRotationMatrix2D((1200, 900), 12, 1)
    rotated = cv2.warpAffine(canvas, matrix, (2400, 1800), borderValue=(245, 245, 245))
    ok, encoded = cv2.imencode(".jpg", rotated, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    assert ok
    resp = client.post(
        "/api/pantry/decode-barcode",
        headers=auth,
        data={"file": (io.BytesIO(encoded.tobytes()), "offcenter.jpg")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["barcode"] == "6954767410388"


def test_shelf_life_estimate_exposes_confidence_and_alternatives(client, auth):
    data = client.get(
        "/api/pantry/lookup/shelf-life", headers=auth, query_string={"name": "青菜"}
    ).get_json()["data"]
    assert data["days"] == 3
    assert data["confidence_percent"] == 85
    assert data["confidence_label"] == "较高"
    assert data["alternatives"] == [3, 5]
    assert data["basis"]

    unknown = client.get(
        "/api/pantry/lookup/shelf-life", headers=auth, query_string={"name": "神秘野菜"}
    ).get_json()["data"]
    assert unknown["days"] is None
    assert unknown["confidence_percent"] == 0
    assert unknown["alternatives"] == []


def test_smart_import_keeps_unknown_expiry_blank_for_human_decision(client, auth):
    known = client.post(
        "/api/pantry/import/text", headers=auth, json={"text": "今天买了青菜", "source": "voice"}
    ).get_json()["data"]["items"][0]
    assert known["shelf_life_days"] == 3
    assert known["shelf_life_confidence"] == 85
    assert known["shelf_life_alternatives"] == [3, 5]
    assert known["expires_at"]

    unknown = client.post(
        "/api/pantry/import/text", headers=auth, json={"text": "今天买了神秘野菜", "source": "voice"}
    ).get_json()["data"]["items"][0]
    assert unknown["shelf_life_days"] is None
    assert unknown["shelf_life_confidence"] == 0
    assert unknown["expires_at"] == ""
    warnings = client.post(
        "/api/pantry/import/text", headers=auth, json={"text": "今天买了神秘野菜", "source": "voice"}
    ).get_json()["data"]["warnings"]
    assert any("未做估算" in item for item in warnings)
    assert all("已暂按" not in item for item in warnings)


def test_complete_meal_deducts_inventory_and_is_idempotent(client, auth):
    _add_item(client, auth, name="大米", category="staple", quantity=1000, unit="g",
              expires_at=(date.today() + timedelta(days=300)).isoformat())
    _add_item(client, auth, name="鸡蛋", category="egg_dairy", quantity=10, unit="个",
              expires_at=(date.today() + timedelta(days=20)).isoformat())
    _add_item(client, auth, name="菠菜", category="vegetable", quantity=2, unit="把",
              expires_at=(date.today() + timedelta(days=2)).isoformat())
    plan = client.post("/api/recipes/plan", headers=auth, json={"meals": 2}).get_json()["data"]
    target = None
    for index, meal in enumerate(plan["meals"]):
        if any(item["name"] == "大米" for item in meal["ingredients"]):
            target = index
            break
    assert target is not None
    result = client.post(
        "/api/recipes/complete", headers=auth, json={"plan_id": plan["plan_id"], "meal_index": target}
    ).get_json()["data"]
    assert result["completed"] is True
    assert result["already_done"] is False
    assert any(item["name"] == "大米" for item in result["consumed"])
    pantry = {item["name"]: item for item in client.get("/api/pantry", headers=auth).get_json()["data"]["items"]}
    assert pantry["大米"]["quantity"] < 1000

    again = client.post(
        "/api/recipes/complete", headers=auth, json={"plan_id": plan["plan_id"], "meal_index": target}
    ).get_json()["data"]
    assert again["already_done"] is True
    pantry_again = {item["name"]: item for item in client.get("/api/pantry", headers=auth).get_json()["data"]["items"]}
    assert pantry_again["大米"]["quantity"] == pantry["大米"]["quantity"]


def test_recipe_plan_scales_with_servings(client, auth):
    _add_item(client, auth, name="大米", category="staple", quantity=2000, unit="g")
    _add_item(client, auth, name="鸡胸肉", category="meat", quantity=2, unit="块")
    _add_item(client, auth, name="菠菜", category="vegetable", quantity=2, unit="把")
    two = client.post("/api/recipes/plan", headers=auth, json={"meals": 2, "servings": 2}).get_json()["data"]
    four = client.post("/api/recipes/plan", headers=auth, json={"meals": 2, "servings": 4}).get_json()["data"]
    assert two["servings"] == 2
    assert four["servings"] == 4
    assert four["nutrition_totals"]["energy_kcal"] > two["nutrition_totals"]["energy_kcal"]
    assert four["nutrition_totals"]["protein_g"] > two["nutrition_totals"]["protein_g"]


def test_household_measure_conversion():
    from app.services.household_service import describe_amount

    assert describe_amount("200g", "大米") == "一杯半（电饭煲量杯，约200g）"
    assert describe_amount("5ml", "食用油") == "1小勺（约5ml）"
    assert describe_amount("3g", "食盐") == "1小勺（约3g）"
    assert describe_amount("3个", "鸡蛋") == "3个"
    assert "3个（约150g）" == describe_amount("150g", "鸡蛋")
    for text in ("一杯半（电饭煲量杯，约200g）", "1小勺（约5ml）", "一小撮（约1g）"):
        assert "茶匙" not in text and "汤匙" not in text and "盎司" not in text


def test_plan_ingredients_include_household_measures(client, auth):
    _add_item(client, auth, name="大米", category="staple", quantity=1000, unit="g")
    _add_item(client, auth, name="鸡胸肉", category="meat", quantity=2, unit="块")
    _add_item(client, auth, name="菠菜", category="vegetable", quantity=2, unit="把")
    plan = client.post("/api/recipes/plan", headers=auth, json={"meals": 2, "servings": 2}).get_json()["data"]
    amounts = [item["amount"] for meal in plan["meals"] for item in meal["ingredients"]]
    assert any("电饭煲量杯" in amount for amount in amounts)
    assert any("掌心大小" in amount for amount in amounts)
    assert all("茶匙" not in amount and "汤匙" not in amount and "盎司" not in amount for amount in amounts)
    assert any("（约" in amount for amount in amounts)


def test_shopping_list_checkout_adds_and_merges_inventory(client, auth):
    _add_item(client, auth, name="鸡蛋", category="egg_dairy", quantity=2, unit="个",
              expires_at=(date.today() + timedelta(days=10)).isoformat())
    labels = [
        "鸡蛋 1个（早餐蛋白质来源）",
        "食用油 15ml（约1汤勺）",
        "鸡胸肉 100g（午餐主蛋白）",
        "鸡蛋 2个（另一餐）",
    ]
    resp = client.post("/api/pantry/shopping/checkout", headers=auth, json={"items": labels})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["count"] == 2
    egg = next(item for item in data["purchased"] if item["name"] == "鸡蛋")
    assert egg["merged"] is True
    assert egg["quantity"] == 3
    assert "同城急送" in data["message"] and "送达" in data["message"]
    assert data["estimated_arrival"]
    pantry = {item["name"]: item for item in client.get("/api/pantry", headers=auth).get_json()["data"]["items"]}
    assert pantry["鸡蛋"]["quantity"] == 5
    assert "同城急送（已送达）" in pantry["鸡蛋"]["note"]
    assert "AI科学存储建议" in pantry["鸡蛋"]["note"]
    assert "AI科学存储建议" in pantry["鸡胸肉"]["note"]
    assert pantry["鸡胸肉"]["quantity"] == 100
    assert "食用油" in data["staples"]
    assert "食用油" not in pantry

    only_staples = client.post(
        "/api/pantry/shopping/checkout", headers=auth, json={"items": ["食用油 1瓶", "盐 1袋"]}
    )
    assert only_staples.status_code == 400

    empty = client.post("/api/pantry/shopping/checkout", headers=auth, json={"items": []})
    assert empty.status_code == 400


def test_complete_meal_skips_staple_condiments(client, auth, app):
    from app.extensions import db
    from app.models import RecipePlan, User

    _add_item(client, auth, name="鸡胸肉", category="meat", quantity=500, unit="g")
    _add_item(client, auth, name="盐", category="condiment", quantity=100, unit="g")
    _add_item(client, auth, name="食用油", category="condiment", quantity=500, unit="ml")
    plan = client.post("/api/recipes/plan", headers=auth, json={"meals": 2}).get_json()["data"]
    with app.app_context():
        user = User.query.filter_by(username="tester").first()
        row = RecipePlan.query.filter_by(id=plan["plan_id"], user_id=user.id).first()
        result = dict(row.result)
        meal = dict(result["meals"][0])
        ingredients = list(meal["ingredients"])
        ingredients.extend([
            {"name": "盐", "amount": "1小勺（约3g）", "from_pantry": True, "expiring": False},
            {"name": "食用油", "amount": "1汤勺（约15ml）", "from_pantry": True, "expiring": False},
        ])
        meal["ingredients"] = ingredients
        result["meals"] = [meal, *result["meals"][1:]]
        row.result = result
        db.session.commit()
    completed = client.post(
        "/api/recipes/complete", headers=auth, json={"plan_id": plan["plan_id"], "meal_index": 0}
    ).get_json()["data"]
    assert not any(item["name"] in {"盐", "食用油"} for item in completed["consumed"])
    assert any(item["name"] in {"盐", "食用油"} for item in completed["staples"])
    pantry = {item["name"]: item for item in client.get("/api/pantry", headers=auth).get_json()["data"]["items"]}
    assert pantry["盐"]["quantity"] == 100
    assert pantry["食用油"]["quantity"] == 500


def test_condiments_do_not_create_expiry_reminders(client, auth):
    _add_item(client, auth, name="盐", category="condiment", quantity=1, unit="袋",
              expires_at=(date.today() - timedelta(days=1)).isoformat())
    _add_item(client, auth, name="菠菜", category="vegetable", quantity=1, unit="把",
              expires_at=(date.today() + timedelta(days=1)).isoformat())
    reminders = client.get("/api/pantry/reminders", headers=auth).get_json()["data"]
    names = {item["name"] for item in reminders["expiring"]} | {item["name"] for item in reminders["expired"]}
    assert "盐" not in names
    assert "菠菜" in names


def test_batch_delete_only_removes_owned_items(client, auth):
    ids = []
    for name in ["番茄", "鸡蛋", "菠菜"]:
        response = client.post(
            "/api/pantry",
            headers=auth,
            json={"name": name, "category": "vegetable", "quantity": 1, "unit": "份"},
        )
        assert response.status_code == 201
        ids.append(response.get_json()["data"]["item"]["id"])
    result = client.post(
        "/api/pantry/batch-delete",
        headers=auth,
        json={"ids": [ids[0], ids[1], 999999]},
    ).get_json()["data"]
    assert result["deleted"] == 2
    assert result["missing"] == [999999]
    remaining = client.get("/api/pantry", headers=auth).get_json()["data"]["items"]
    assert [item["name"] for item in remaining] == ["菠菜"]

    empty = client.post("/api/pantry/batch-delete", headers=auth, json={"ids": []})
    assert empty.status_code == 400


def test_checkout_mixed_fresh_and_staples_has_two_delivery_modes(client, auth):
    resp = client.post(
        "/api/pantry/shopping/checkout",
        headers=auth,
        json={"items": ["鸡蛋 1个", "生抽 250ml"], "include_staples": True},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["fresh_count"] == 1
    assert data["staple_count"] == 1
    assert "同城急送（已送达）" in data["message"] and "常规发货（已送达）" in data["message"]
    items = {item["name"]: item for item in client.get("/api/pantry", headers=auth).get_json()["data"]["items"]}
    assert "鸡蛋" in items
    assert "生抽" in items
    soy = next(item for item in data["purchased"] if item["name"] == "生抽")
    assert "常规发货" in soy["delivery"]


def test_health_profile_tip_mentions_hypertension(client, auth):
    resp = client.post(
        "/api/health-profile/tip",
        headers=auth,
        json={"conditions": ["hypertension"], "goals": ["low_sodium"], "allergies": [], "notes": ""},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["tip"]
    assert "钠" in data["tip"] or "盐" in data["tip"]
    assert data["source"] in {"ai", "rule"}


def test_rule_plan_meals_are_breakfast_lunch_dinner_order(client, auth):
    for payload in [
        {"name": "大米", "category": "staple", "quantity": 1000, "unit": "g"},
        {"name": "鸡蛋", "category": "egg_dairy", "quantity": 6, "unit": "个"},
        {"name": "菠菜", "category": "vegetable", "quantity": 2, "unit": "把"},
    ]:
        client.post("/api/pantry", headers=auth, json=payload)
    plan = client.post("/api/recipes/plan", headers=auth, json={"meals": 3}).get_json()["data"]
    assert [meal["meal_type"] for meal in plan["meals"]] == ["早餐", "午餐", "晚餐"]


def test_rule_recipe_does_not_use_aromatics_as_main_dish(client, auth):
    for payload in [
        {"name": "鲤鱼", "category": "seafood", "quantity": 1, "unit": "条"},
        {"name": "大葱", "category": "vegetable", "quantity": 1, "unit": "根"},
        {"name": "豆腐", "category": "bean", "quantity": 1, "unit": "块"},
        {"name": "大米", "category": "staple", "quantity": 500, "unit": "g"},
    ]:
        _add_item(client, auth, **payload)
    plan = client.post("/api/recipes/plan", headers=auth, json={"meals": 2}).get_json()["data"]
    names = [meal["name"] for meal in plan["meals"]]
    assert all("大葱炒" not in name for name in names)
    for meal in plan["meals"]:
        main_names = [item["name"] for item in meal.get("main_ingredients") or []]
        aux_names = [item["name"] for item in meal.get("auxiliary_ingredients") or []]
        assert "大葱" not in main_names
        if "鲤鱼" in main_names:
            assert "清蒸" in meal["name"] or "红烧" in meal["name"]
        assert all(role != "auxiliary" for role in [item.get("role") for item in meal.get("main_ingredients") or []])
        assert all(name not in (main_names or []) for name in aux_names)


def test_favorite_recipe_crud_and_schedule(client, auth):
    payload = {
        "recipe_name": "红烧肉",
        "recipe_data": {
            "title": "红烧肉",
            "main_ingredients": [{"name": "五花肉", "amount": "300g"}],
            "ingredients": ["五花肉 300g", "生抽 1汤勺"],
            "steps": ["五花肉切块焯水。", "加入生抽炖煮。"],
            "nutrition": {"energy_kcal": 520, "protein_g": 24},
        },
    }
    added = client.post("/api/favorites", headers=auth, json=payload)
    assert added.status_code == 200, added.get_json()
    favorite = added.get_json()["data"]["favorite"]
    assert favorite["recipe_name"] == "红烧肉"
    assert favorite["main_ingredients"][0]["name"] == "五花肉"
    assert favorite["missing"][0]["name"] == "五花肉"

    listed = client.get("/api/favorites", headers=auth).get_json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["energy_kcal"] == 520

    scheduled = client.post(f"/api/favorites/{favorite['id']}/schedule", headers=auth)
    assert scheduled.status_code == 200, scheduled.get_json()
    plan = scheduled.get_json()["data"]["plan"]
    assert plan["meals"][0]["name"] == "红烧肉"
    assert plan["meals"][0]["from_favorite"] is True
    assert plan["shopping_list"]

    history = client.get("/api/recipes/history", headers=auth).get_json()["data"]["items"]
    assert history[0]["result"]["meals"][0]["name"] == "红烧肉"

    removed = client.delete(f"/api/favorites/{favorite['id']}", headers=auth)
    assert removed.status_code == 200
    assert client.get("/api/favorites", headers=auth).get_json()["data"]["total"] == 0


def test_consume_recipe_deducts_matching_ingredients(client, auth):
    _add_item(client, auth, name="五花肉", category="meat", quantity=500, unit="g")
    resp = client.post(
        "/api/pantry/consume",
        headers=auth,
        json={"recipe_name": "红烧肉", "ingredients": [{"name": "五花肉", "amount": "300g"}]},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["consumed"][0]["name"] == "五花肉"
    assert data["consumed"][0]["remaining"] == 200
    pantry = {item["name"]: item for item in client.get("/api/pantry", headers=auth).get_json()["data"]["items"]}
    assert pantry["五花肉"]["quantity"] == 200


def test_rule_plan_supports_six_meal_slots(client, auth, monkeypatch):
    from app.services import recipe_agent_service

    monkeypatch.setattr(recipe_agent_service, "_allow_ai", lambda: False)
    for name, category in [
        ("大米", "staple"),
        ("鸡蛋", "egg_dairy"),
        ("菠菜", "vegetable"),
        ("鸡胸肉", "meat"),
        ("豆腐", "bean"),
        ("苹果", "fruit"),
    ]:
        _add_item(client, auth, name=name, category=category, quantity=1, unit="份")

    plan = client.post("/api/recipes/plan", headers=auth, json={"meals": 6}).get_json()["data"]
    assert [meal["meal_type"] for meal in plan["meals"]] == [
        "早餐", "上午加餐", "午餐", "下午加餐", "晚餐", "夜宵"
    ]
