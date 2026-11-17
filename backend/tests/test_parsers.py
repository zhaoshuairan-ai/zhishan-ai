"""解析与核查规则的单元测试（不依赖 HTTP）。"""
from __future__ import annotations

import re
from datetime import date

from app.services.checker import add_months, compute_expiry, parse_shelf_life, run_checks
from app.services.field_parser import build_corrected_text, parse_fields
from app.services.ingredient_parser import parse_ingredients
from app.services.nutrition_parser import parse_nutrition
from app.services.text_utils import capture_after


SAMPLE_LINES = [
    ("测试牌 原味饼干", 0.99),
    ("净含量：150g", 0.98),
    ("配料：小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母、食品添加剂（碳酸钙）", 0.96),
    ("营养成分表（每100g）", 0.97),
    ("能量 1900kJ 23%   蛋白质 8.2g 14%", 0.95),
    ("脂肪 17.5g 29%    碳水化合物 66.1g 22%", 0.95),
    ("钠 420mg 21%", 0.94),
    ("生产日期：2026-02-10    保质期：12个月", 0.92),
    ("贮存条件：置于阴凉干燥处", 0.93),
    ("生产者：测试食品有限公司", 0.9),
    ("产品标准号：GB/T 20980", 0.88),
    ("致敏物质提示：含有小麦", 0.9),
]


def test_capture_after_uses_capture_group():
    text = "净含量：150g\n生产日期：2026-02-10 保质期：12个月"
    value, _ = capture_after(text, r"净含量\s*[:：]?\s*(\d+\s*(?:g|kg))")
    assert value == "150g"
    value, _ = capture_after(text, r"生产日期\s*[:：]?\s*(\d{4}-\d{1,2}-\d{1,2})")
    assert value == "2026-02-10"


def test_field_parser_extracts_all_fields():
    parsed = parse_fields(SAMPLE_LINES)
    fields = parsed["fields"]
    assert fields["food_name"] == "测试牌 原味饼干"
    assert fields["net_content"] == "150g"
    assert fields["production_date"] == "2026-02-10"
    assert fields["shelf_life"] == "12个月"
    assert fields["storage"] == "置于阴凉干燥处"
    assert "测试食品" in fields["producer"]
    assert fields["standard_no"].startswith("GB")
    assert "小麦" in fields["allergen"]
    assert "小麦粉" in fields["ingredients_text"]
    assert parsed["confidence"]["ingredients_text"] > 0.9
    # 未出现的字段必须为缺失，而不是编造
    assert "expiry_date" in parsed["missing"]
    assert parsed["flags"]["expiry_date"]["status"] == "missing"


def test_field_parser_does_not_invent_values():
    parsed = parse_fields([("随便一行文字", 0.5)])
    fields = parsed["fields"]
    for key in ("net_content", "production_date", "shelf_life", "producer", "standard_no"):
        assert fields[key] == ""


def test_build_corrected_text_skips_empty():
    text = build_corrected_text({"food_name": "饼干", "shelf_life": "", "net_content": "150g"})
    assert "食品名称：饼干" in text
    assert "净含量：150g" in text
    assert "保质期" not in text


def test_parse_ingredients_nested_additives():
    parsed = parse_ingredients("小麦粉、植物油、食品添加剂（碳酸氢钠、碳酸钙）、食用盐")
    names = [item["name"] for item in parsed["items"]]
    assert "小麦粉" in names
    assert "碳酸氢钠" in names
    assert "碳酸钙" in names
    children = [item for item in parsed["items"] if item["parent"]]
    assert len(children) == 2


def test_parse_ingredients_percent():
    parsed = parse_ingredients("小麦粉（≥30%）、白砂糖、水")
    first = parsed["items"][0]
    assert first["percent"] == 30
    assert first["name"] == "小麦粉"


def test_parse_nutrition_basic():
    parsed = parse_nutrition(
        "营养成分表（每100g）\n能量 1900kJ 23%\n蛋白质 8.2g 14%\n脂肪 17.5g 29%\n碳水化合物 66.1g 22%\n钠 420mg 21%"
    )
    assert parsed["basis"] == "per_100g"
    assert parsed["missing_core"] == []
    energy = next(item for item in parsed["items"] if item["key"] == "energy")
    assert energy["value"] == 1900
    assert energy["unit"] == "kJ"
    assert energy["nrv_percent"] == 23


def test_parse_nutrition_handles_split_nrv_line():
    parsed = parse_nutrition("蛋白质 8.2g\n14%\n脂肪 17.5g")
    protein = next(item for item in parsed["items"] if item["key"] == "protein")
    assert protein["value"] == 8.2
    assert protein["nrv_percent"] == 14


def test_parse_nutrition_vertical_cells():
    """真实 OCR 常把表格拆成「名称一行、数值一行、NRV% 一行」。"""
    parsed = parse_nutrition(
        "营养成分表\n项目\n每份\n营养素参考值%\n能量\n889干焦\n11%\n"
        "蛋白质\n2.3克\n4%\n脂肪\n13.3克\n22%\n碳水化合物\n20.6克\n7%\n钠\n323毫克\n16%"
    )
    assert parsed["basis"] == "per_serving"
    values = {item["key"]: item for item in parsed["items"] if item["value"] is not None}
    assert values["energy"]["value"] == 889
    assert values["energy"]["unit"] == "kJ"  # 「干焦」是「千焦」的 OCR 错字
    assert values["protein"]["value"] == 2.3
    assert values["protein"]["nrv_percent"] == 4
    assert values["sodium"]["value"] == 323
    assert values["sodium"]["unit"] == "mg"
    assert not parsed["missing_core"]


def test_parse_ingredients_soft_wraps():
    """OCR 行尾折行应被拼回，而不是拆成两个配料。"""
    parsed = parse_ingredients("水,白砂糖,山杏仁,聚甘油脂\n肪酸酯,碳酸氢钠,柠檬酸,食品用香\n料。")
    names = [item["name"] for item in parsed["items"]]
    assert "聚甘油脂肪酸酯" in names
    assert "食品用香料" in names
    assert "聚甘油脂" not in names


def test_parse_ingredients_unbalanced_bracket():
    """括号不配对时不能把后面的配料全部吞进同一项。"""
    parsed = parse_ingredients(
        "马铃薯、植物油、调味料（酱油粉（酿造酱油、食用盐）、白砂糖、乳清粉、食用盐、味精"
    )
    names = [item["name"] for item in parsed["items"]]
    assert len(names) >= 4, names
    assert "白砂糖" in names


def test_food_name_not_inferred_from_table_headers():
    """表格表头/营养素名/百分比行不能被当成食品名称。"""
    lines = [
        ("营养成分表", 0.99),
        ("每份食用量：1袋（40克）", 0.98),
        ("项目", 0.98),
        ("每份", 0.97),
        ("营养素参考值%", 0.97),
        ("能量", 0.96),
        ("889干焦", 0.95),
        ("11%", 0.95),
    ]
    parsed = parse_fields(lines)
    assert parsed["fields"]["food_name"] == ""
    assert "food_name" in parsed["missing"]


def test_ingredients_fallback_without_keyword():
    """「配料」两个字被识别坏或漏掉时，按分隔符密度推测配料段落。"""
    parsed = parse_fields(
        [
            ("马铃薯、植物油、白砂糖、食用盐、碳酸氢钠、酵母", 0.9),
            ("能量 1980kJ 24%", 0.9),
            ("蛋白质 8.5g 14%", 0.9),
        ]
    )
    text = parsed["fields"]["ingredients_text"]
    assert "马铃薯" in text and "碳酸氢钠" in text
    assert "推测" in (parsed["flags"]["ingredients_text"]["note"] or "")


def test_ingredients_fallback_handles_broken_keyword():
    """OCR 把「配料」识别成「配科/配枓」时仍应抽到配料段落。"""
    for keyword in ("配科：", "配枓:", "配料表："):
        parsed = parse_fields([(f"{keyword}小麦粉、植物油、白砂糖、食用盐", 0.95)])
        assert "小麦粉" in parsed["fields"]["ingredients_text"], keyword


def test_nutrition_fallback_without_header():
    """「营养成分表」标题缺失时，按营养素关键词推测表格范围。"""
    parsed = parse_fields(
        [
            ("配料：小麦粉、植物油", 0.9),
            ("能量 1900kJ 23%", 0.9),
            ("蛋白质 8.2g 14%", 0.9),
            ("钠 420mg 21%", 0.9),
            ("保质期：12个月", 0.9),
        ]
    )
    nutrition = parsed["fields"]["nutrition_text"]
    assert "能量" in nutrition and "蛋白质" in nutrition
    assert "12个月" not in nutrition, "不能把保质期混进营养成分"


def test_ocr_preprocess_upscales_small_image(tmp_path):
    """小图会被放大到便于识别的尺寸，并转为灰度。"""
    from PIL import Image

    from app.services.ocr.local_rapidocr import LocalRapidOcrProvider

    small = tmp_path / "small.png"
    Image.new("RGB", (400, 300), (250, 250, 250)).save(small)
    prepared = LocalRapidOcrProvider._prepare_image(small)
    assert prepared.mode == "L"
    # 小图会被放大（最多 3 倍，避免过度插值），比例保持不变
    assert max(prepared.size) > 400
    assert max(prepared.size) <= 1600
    assert abs(prepared.size[0] / prepared.size[1] - 400 / 300) < 0.02


def test_parse_nutrition_ignores_table_border_noise():
    """OCR 会把表格边框带进行首（如「-饱和脂肪酸」），不能因此漏掉该项目。"""
    parsed = parse_nutrition("-饱和脂肪酸\n6.6克\n33%\n|能量| 889千焦 11%")
    values = {item["key"]: item for item in parsed["items"] if item["value"] is not None}
    assert values["saturated_fat"]["value"] == 6.6
    assert values["saturated_fat"]["nrv_percent"] == 33
    assert values["energy"]["value"] == 889
    assert values["energy"]["unit"] == "kJ"


def test_nutrition_drops_interleaved_ingredient_lines():
    """两列排版（配料表在左、营养表在右）时，营养成分表字段不能混入配料文字。"""
    lines = [
        ("表", 0.9),
        ("项目", 0.9),
        ("每100克营养素参", 0.9),
        ("碳酸钠.六偏磷酸钠、磷酸二氢钠、三聚磷酸钠.谷氨酸钠、", 0.9),
        ("能量", 0.9),
        ("1994千售", 0.9),
        ("蛋白质", 0.9),
        ("8.7克", 0.9),
        ("黄原胶、海藻酸钠、食用玉米淀粉、魔芋粉、全蛋粉)、羧甲基纤", 0.9),
        ("脂肪", 0.9),
        ("24.3克", 0.9),
        ("碳水化合物", 0.9),
        ("55.7克", 0.9),
        ("酱包:精炼棕榈油、葱、食用盐、蒜、食用牛油、味精、姜、牛肉复合调", 0.9),
        ("钠", 0.9),
        ("2492豪克", 0.9),
    ]
    parsed = parse_fields(lines)
    text = parsed["fields"]["nutrition_text"]
    assert "能量 1994千售" in text
    assert "蛋白质 8.7克" in text
    assert "钠 2492豪克" in text
    # 配料片段不能出现
    for word in ("酱包", "黄原胶", "碳酸钠", "复配", "精炼棕榈油"):
        assert word not in text, word
    # 每行都是「名称 + 数值」，不是零散单元格
    rows = [line for line in text.split("\n") if line.strip()]
    assert len(rows) == 5
    assert all(re.search(r"\d", row) for row in rows)


def test_ingredients_drops_nutrition_rows():
    """配料表字段不能混入营养表行（同样的双列串行场景）。"""
    lines = [
        ("配料：小麦粉、植物油、碳酸氢钠、酵母", 0.9),
        ("能量", 0.9),
        ("1994千售", 0.9),
        ("蛋白质", 0.9),
        ("8.7克", 0.9),
        ("脂肪", 0.9),
        ("24.3克", 0.9),
        ("白砂糖、食用盐、全脂乳粉", 0.9),
    ]
    parsed = parse_fields(lines)
    text = parsed["fields"]["ingredients_text"]
    assert "小麦粉" in text
    assert "白砂糖" in text
    for word in ("能量", "蛋白质", "1994", "8.7克"):
        assert word not in text, word


def test_nutrition_unit_ocr_typos():
    """「千售」「豪克」这类 OCR 错字要能归一为 kJ / mg。"""
    parsed = parse_nutrition("能量 1994千售 24%\n钠 2492豪克 125%")
    values = {item["key"]: item for item in parsed["items"] if item["value"] is not None}
    assert values["energy"]["unit"] == "kJ"
    assert values["energy"]["status"] == "ok"
    assert values["sodium"]["unit"] == "mg"
    assert values["sodium"]["value"] == 2492


def test_parse_nutrition_missing_marks_missing():
    parsed = parse_nutrition("钠 420mg")
    missing = {item["key"] for item in parsed["items"] if item["status"] == "missing"}
    assert {"energy", "protein", "fat", "carbohydrate"} <= missing


def test_parse_nutrition_kcal_conversion_note():
    parsed = parse_nutrition("能量 450kcal")
    energy = next(item for item in parsed["items"] if item["key"] == "energy")
    assert energy["unit"] == "kcal"
    assert energy["value_kj"] == round(450 * 4.184, 1)


def test_parse_shelf_life_and_expiry():
    assert parse_shelf_life("21天")[0] == 21
    assert parse_shelf_life("12个月")[0] == 360
    expiry, _ = compute_expiry("2026-01-15", "12个月")
    assert expiry == date(2027, 1, 15)
    expiry, _ = compute_expiry("2026-01-15", "30天")
    assert expiry == date(2026, 2, 14)


def test_add_months_leap_year():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert add_months(date(2025, 12, 15), 1) == date(2026, 1, 15)


BASE_FIELDS = {
    "food_name": "测试饼干",
    "ingredients_text": "小麦粉、植物油、食用盐",
    "nutrition_text": "能量 1900kJ 蛋白质 8.2g 脂肪 17.5g 碳水化合物 66.1g 钠 420mg",
    "net_content": "150g",
    "production_date": "2026-02-10",
    "shelf_life": "12个月",
    "expiry_date": "",
    "storage": "置于阴凉干燥处",
    "producer": "测试食品有限公司",
    "standard_no": "GB/T 20980",
    "allergen": "含有小麦",
}

BASE_CONFIDENCE = {key: 0.95 for key in BASE_FIELDS}
BASE_CONFIDENCE["allergen"] = 0.6


def _run(fields=None, nutrition_text=None, today=None, mode="rule"):
    from app.services.field_parser import parse_fields

    fields = dict(fields or BASE_FIELDS)
    if nutrition_text is not None:
        fields["nutrition_text"] = nutrition_text
    parsed_fields = parse_fields([(f"{k}：{v}", 0.95) for k, v in fields.items() if v])
    ingredients = parse_ingredients(fields["ingredients_text"])
    nutrition = parse_nutrition(fields["nutrition_text"])
    return run_checks(
        fields=fields,
        confidence=BASE_CONFIDENCE,
        flags={},
        ingredients=ingredients,
        nutrition=nutrition,
        analysis_mode=mode,
        is_demo=False,
        today=today,
    )


def test_checker_flags_expired_product():
    result = _run(today=date(2027, 6, 1))
    assert result["overall"] == "suspected"
    assert any(item["rule_id"] == "DATE_EXPIRY" and item["level"] == "suspected" for item in result["items"])
    assert "过期" in " ".join(item["result"] for item in result["items"] if item["rule_id"] == "DATE_EXPIRY")


def test_checker_flags_future_production_date():
    result = _run(fields={**BASE_FIELDS, "production_date": "2099-01-01", "shelf_life": "12个月"})
    assert any(item["rule_id"] == "DATE_FUTURE" and item["level"] == "suspected" for item in result["items"])


def test_checker_marks_missing_fields_as_review_not_defect():
    fields = dict(BASE_FIELDS)
    fields["nutrition_text"] = ""
    fields["store"] = ""
    result = _run(fields=fields)
    missing_items = [item for item in result["items"] if item["rule_id"] == "FIELD_NUTRITION"]
    assert missing_items
    assert missing_items[0]["level"] == "review"
    assert "不代表包装上实际缺少" in missing_items[0]["reason"]


def test_checker_detects_implausible_nutrition():
    result = _run(nutrition_text="能量 1900kJ 蛋白质 60g 脂肪 50g 碳水化合物 40g 钠 400mg")
    assert any(item["rule_id"] == "NUTRI_SUM" and item["level"] == "suspected" for item in result["items"])


def test_checker_energy_consistency_pass():
    result = _run()
    energy = next(item for item in result["items"] if item["rule_id"] == "NUTRI_ENERGY")
    assert energy["level"] == "pass"


def test_checker_high_sodium_is_info_not_problem():
    result = _run(nutrition_text="能量 800kJ 蛋白质 2g 脂肪 1g 碳水化合物 10g 钠 900mg")
    sodium = next(item for item in result["items"] if item["rule_id"] == "NUTRI_HIGH_SODIUM")
    assert sodium["level"] == "info"
    assert "不代表食品不合格" in sodium["reason"]


def test_checker_none_found_when_everything_ok():
    """字段齐全、日期正常、数值合理时应给出「未发现明显问题」。"""
    result = _run(today=date(2026, 3, 1))
    review_items = [item for item in result["items"] if item["level"] in {"review", "suspected"}]
    assert result["overall"] == ("needs_review" if review_items else "none_found")
    if not review_items:
        assert result["overall"] == "none_found"


def test_checker_demo_mode_is_disclosed():
    from app.services.ingredient_parser import parse_ingredients as parse_ing

    result = run_checks(
        fields=BASE_FIELDS,
        confidence=BASE_CONFIDENCE,
        flags={},
        ingredients=parse_ing(BASE_FIELDS["ingredients_text"]),
        nutrition=parse_nutrition(BASE_FIELDS["nutrition_text"]),
        analysis_mode="rule",
        is_demo=True,
        today=date(2026, 3, 1),
    )
    disclosure = next(item for item in result["items"] if item["rule_id"] == "MODE_DISCLOSURE")
    assert disclosure["level"] == "review"
    assert "演示" in disclosure["result"]
