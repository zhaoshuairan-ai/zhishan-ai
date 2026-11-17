"""OCR 识别（成功 / 失败 / 校正）测试。"""
from __future__ import annotations

import pytest

from app.utils.errors import ServiceError


def test_ocr_success_and_fields(client, auth, record_factory):
    record_id = record_factory(run_ocr=True)
    resp = client.get(f"/api/records/{record_id}", headers=auth)
    assert resp.status_code == 200
    ocr = resp.get_json()["data"]["ocr"]
    assert ocr["provider"] == "demo"
    assert ocr["is_demo"] is True
    assert ocr["raw_text"]
    assert ocr["fields"]["ingredients_text"]
    assert ocr["fields"]["nutrition_text"]
    assert ocr["fields"]["production_date"]
    assert ocr["field_confidence"]["ingredients_text"] > 0
    assert isinstance(ocr["missing_fields"], list)


def test_ocr_requires_existing_record(client, auth):
    resp = client.post("/api/ocr", headers=auth, json={"record_id": 999999})
    assert resp.status_code == 404


def test_ocr_rejects_missing_record_id(client, auth):
    resp = client.post("/api/ocr", headers=auth, json={})
    assert resp.status_code == 400
    assert "record_id" in resp.get_json()["message"]


def test_ocr_other_user_cannot_access(client, auth, other_auth, record_factory):
    record_id = record_factory()
    resp = client.post("/api/ocr", headers=other_auth, json={"record_id": record_id})
    assert resp.status_code == 404


def test_ocr_service_failure_returns_readable_error(client, auth, record_factory, monkeypatch):
    record_id = record_factory()

    def _boom(path):
        raise ServiceError("文字识别失败：模拟引擎异常", code=50200, status=502, details={"retryable": True})

    monkeypatch.setattr("app.services.ocr.recognize", _boom)
    resp = client.post("/api/ocr", headers=auth, json={"record_id": record_id})
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["success"] is False
    assert "识别" in body["message"]
    assert body["details"]["retryable"] is True
    # 失败后记录仍可重试：记录本身没有被删除
    detail = client.get(f"/api/records/{record_id}", headers=auth).get_json()["data"]
    assert detail["record"]["status"] == "uploaded"


def test_correction_saved_and_confidence_updated(client, auth, record_factory):
    record_id = record_factory(run_ocr=True)
    resp = client.put(
        f"/api/records/{record_id}/ocr",
        headers=auth,
        json={"fields": {"food_name": "人工校正后的名称", "ingredients_text": "小麦粉、白砂糖"}},
    )
    assert resp.status_code == 200
    ocr = resp.get_json()["data"]["ocr"]
    assert ocr["fields"]["food_name"] == "人工校正后的名称"
    assert "人工校正后的名称" in ocr["corrected_text"]
    assert ocr["field_confidence"]["food_name"] == 1.0
    assert ocr["corrected_at"]
    # 原始文本必须保留
    assert ocr["raw_text"]


def test_correction_rejects_unknown_field(client, auth, record_factory):
    record_id = record_factory(run_ocr=True)
    resp = client.put(f"/api/records/{record_id}/ocr", headers=auth, json={"fields": {"hacker": "x"}})
    assert resp.status_code == 400
    assert "未知字段" in resp.get_json()["message"]


def test_correction_requires_ocr_first(client, auth, record_factory):
    record_id = record_factory()
    resp = client.put(f"/api/records/{record_id}/ocr", headers=auth, json={"fields": {"food_name": "x"}})
    assert resp.status_code == 404
