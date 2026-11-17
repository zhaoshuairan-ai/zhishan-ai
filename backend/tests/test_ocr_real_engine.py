"""真实本地 OCR 集成测试（可选，需要 rapidocr-onnxruntime）。

没有安装 OCR 依赖时自动跳过，不会让测试套件失败。
"""
from __future__ import annotations

import io

import pytest

from .conftest import make_label_png

pytestmark = pytest.mark.slow


def _real_ocr_available() -> bool:
    try:
        from app.services.ocr.local_rapidocr import LocalRapidOcrProvider

        return LocalRapidOcrProvider.available()
    except Exception:  # pragma: no cover
        return False


@pytest.mark.skipif(not _real_ocr_available(), reason="未安装本地 OCR 引擎（rapidocr-onnxruntime）")
def test_local_ocr_recognizes_chinese_label(client, auth, app):
    original = app.config["OCR_PROVIDER"]
    app.config["OCR_PROVIDER"] = "local"
    try:
        image = make_label_png(
            [
                "真实识别测试 原味饼干",
                "净含量：150g",
                "配料：小麦粉、植物油、白砂糖、食用盐、碳酸氢钠",
                "营养成分表",
                "能量 1900kJ 23%",
                "蛋白质 8.2g 14%",
                "脂肪 17.5g 29%",
                "碳水化合物 66.1g 22%",
                "钠 420mg 21%",
                "生产日期：2026-02-10",
                "保质期：12个月",
            ]
        )
        resp = client.post(
            "/api/upload",
            headers=auth,
            data={"file": (io.BytesIO(image), "real_label.png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201
        record_id = resp.get_json()["data"]["record"]["id"]

        ocr_resp = client.post("/api/ocr", headers=auth, json={"record_id": record_id})
        assert ocr_resp.status_code == 200, ocr_resp.get_json()
        data = ocr_resp.get_json()["data"]
        assert data["provider"]["key"] == "local_rapidocr"
        assert data["provider"]["is_demo"] is False

        fields = data["fields"]
        assert "小麦粉" in fields["ingredients_text"]
        assert fields["nutrition_text"]
        assert fields["production_date"] == "2026-02-10"
        assert fields["shelf_life"] == "12个月"
        assert fields["net_content"] == "150g"

        # 真实 OCR 的结果不应被标记为演示数据
        detail = client.get(f"/api/records/{record_id}", headers=auth).get_json()["data"]
        assert detail["record"]["is_demo"] is False
    finally:
        app.config["OCR_PROVIDER"] = original
