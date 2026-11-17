"""健康评估（自建模型）测试：评分、反式脂肪、糖、添加剂与安全边界。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services import health_service


def _nutrition(items: list[dict], basis: str = "per_100g"):
    return SimpleNamespace(items=items, basis=basis)


def _item(key: str, value, unit: str, status: str = "ok"):
    return {"key": key, "value": value, "unit": unit, "status": status}


def _record(*, nutrition=None, ingredients=None, net_content="100g"):
    ocr = SimpleNamespace(fields={"net_content": net_content})
    ingredient = SimpleNamespace(ingredients=ingredients or [])
    return SimpleNamespace(nutrition=nutrition, ingredient=ingredient, ocr=ocr)


def test_health_assessment_flags_high_sugar_sodium_and_trans_fat():
    record = _record(
        nutrition=_nutrition(
            [
                _item("energy", 2000, "kJ"),
                _item("protein", 5, "g"),
                _item("fat", 22, "g"),
                _item("saturated_fat", 12, "g"),
                _item("trans_fat", 2, "g"),
                _item("carbohydrate", 60, "g"),
                _item("sugar", 32, "g"),
                _item("sodium", 900, "mg"),
                _item("dietary_fiber", 1, "g"),
            ]
        ),
        net_content="80g",
    )
    result = health_service.assess(record)
    assert result["score"] is not None
    assert result["score"] < 55
    assert result["grade"] in {"D", "E"}
    trans = next(item for item in result["findings"] if item["key"] == "trans_fat")
    assert trans["level"] == "watch"
    assert trans["summary"].startswith("反式脂肪酸供能约")
    sugar = next(item for item in result["findings"] if item["key"] == "sugar")
    assert sugar["level"] == "watch"
    assert result["sugar"]["value_g"] == 32
    assert result["sugar"]["daily_ratio"] > 100
    assert result["sugar"]["package_sugar_g"] is not None
    sodium = next(item for item in result["findings"] if item["key"] == "sodium")
    assert sodium["level"] == "watch"
    assert result["sodium"]["nrv_percent"] > 40


def test_health_assessment_good_product_scores_higher():
    record = _record(
        nutrition=_nutrition(
            [
                _item("energy", 600, "kJ"),
                _item("protein", 15, "g"),
                _item("fat", 3, "g"),
                _item("saturated_fat", 1, "g"),
                _item("trans_fat", 0, "g"),
                _item("carbohydrate", 20, "g"),
                _item("sugar", 2, "g"),
                _item("sodium", 80, "mg"),
                _item("dietary_fiber", 6, "g"),
            ]
        )
    )
    result = health_service.assess(record)
    assert result["score"] is not None
    assert result["score"] >= 80
    assert result["grade"] in {"A", "B"}
    trans = next(item for item in result["findings"] if item["key"] == "trans_fat")
    assert trans["level"] == "good"
    assert "0" in trans["summary"]


def test_health_assessment_without_nutrition_has_no_numeric_score():
    record = _record(nutrition=_nutrition([], basis=""))
    result = health_service.assess(record)
    assert result["score"] is None
    assert result["grade"] == "NA"
    assert "数据不足" in result["grade_label"]
    assert result["headline"].startswith("标签营养数据不足")


def test_additive_detection_marks_compliance_as_pending(app):
    record = _record(
        nutrition=_nutrition([_item("energy", 900, "kJ"), _item("sodium", 600, "mg")]),
        ingredients=[
            {"name": "亚硝酸钠", "category": "护色剂"},
            {"name": "山梨酸钾", "category": "防腐剂"},
        ],
    )
    with app.app_context():
        result = health_service.assess(record)
    additives = result["additives"]
    assert additives["count"] >= 2
    assert all(item["compliance"] == "待核实" for item in additives["items"])
    nitrite = next(item for item in additives["items"] if "亚硝酸" in item["name"])
    assert nitrite["risk_note"]
    finding = next(item for item in result["findings"] if item["key"] == "additives")
    assert finding["level_label"] == "待核实"
    assert "无法判断本产品是否合规" in finding["detail"]


def test_health_assessment_exposes_disclaimer_and_no_false_compliance_claim():
    record = _record(
        nutrition=_nutrition([_item("energy", 800, "kJ"), _item("sugar", 12, "g"), _item("sodium", 200, "mg")])
    )
    result = health_service.assess(record)
    assert "不是国家标准" in result["disclaimer"]
    text = " ".join(item["detail"] for item in result["findings"])
    assert "无法判断本产品是否合规" in text or "无法判定" in text
    # 不使用「超标」这种法规判定措辞，只用「高于参考」
    assert "超标" not in text or "不是法规意义上的" in text


def test_record_detail_and_report_include_health_assessment(client, auth, analyzed_record):
    detail = client.get(f"/api/records/{analyzed_record}", headers=auth).get_json()["data"]
    health = detail["health"]
    assert health is not None
    assert health["score"] is None or 0 <= health["score"] <= 100
    assert health["grade"] in {"A", "B", "C", "D", "E", "NA"}
    assert {item["key"] for item in health["findings"]} >= {"trans_fat", "sugar", "additives"}
    assert "不是国家标准" in health["disclaimer"]

    report = client.get(f"/api/reports/{analyzed_record}", headers=auth).get_json()["data"]
    assert report["health"] is not None
    assert report["health"]["model_version"] == health["model_version"]
