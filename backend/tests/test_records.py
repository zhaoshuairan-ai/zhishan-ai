"""历史记录：列表、分页、筛选、删除、权限隔离。"""
from __future__ import annotations


def test_records_list_empty(client, auth):
    resp = client.get("/api/records", headers=auth)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["items"] == []
    assert data["total"] == 0
    assert data["stats"]["total"] == 0


def test_records_list_pagination(client, auth, record_factory):
    for _ in range(5):
        record_factory()
    resp = client.get("/api/records?page=1&per_page=2", headers=auth)
    data = resp.get_json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["pages"] == 3

    resp = client.get("/api/records?page=3&per_page=2", headers=auth)
    assert len(resp.get_json()["data"]["items"]) == 1


def test_records_status_filter(client, auth, record_factory):
    record_factory()
    record_factory(run_ocr=True, analyze=True)
    resp = client.get("/api/records?status=analyzed", headers=auth)
    data = resp.get_json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["status"] == "analyzed"

    resp = client.get("/api/records?status=bad-value", headers=auth)
    assert resp.status_code == 400


def test_records_query_filter(client, auth, record_factory):
    record_factory(run_ocr=True, analyze=True)
    # 测试环境使用内置演示 OCR，识别文本固定为「乐脆牌…」，因此用它作为搜索关键词
    resp = client.get("/api/records?query=乐脆", headers=auth)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["total"] >= 1

    resp = client.get("/api/records?query=完全不存在的名字", headers=auth)
    assert resp.get_json()["data"]["total"] == 0


def test_record_detail_shape(client, auth, analyzed_record):
    resp = client.get(f"/api/records/{analyzed_record}", headers=auth)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert set(data.keys()) >= {"record", "ocr", "ingredient", "nutrition", "check", "meta"}
    assert data["record"]["image_url"].endswith("/image")


def test_record_delete_removes_files_and_row(client, auth, record_factory, app):
    record_id = record_factory(run_ocr=True)
    upload_dir = __import__("pathlib").Path(app.config["UPLOAD_DIR"])
    before = len(list(upload_dir.glob("*")))
    assert before >= 2  # 原图 + 展示图

    resp = client.delete(f"/api/records/{record_id}", headers=auth)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["deleted_id"] == record_id

    resp = client.get(f"/api/records/{record_id}", headers=auth)
    assert resp.status_code == 404

    after = len(list(upload_dir.glob("*")))
    assert after == 0


def test_record_ownership_isolation(client, auth, other_auth, analyzed_record):
    for method, path in (
        ("get", f"/api/records/{analyzed_record}"),
        ("delete", f"/api/records/{analyzed_record}"),
        ("get", f"/api/records/{analyzed_record}/image"),
    ):
        resp = getattr(client, method)(path, headers=other_auth)
        assert resp.status_code == 404, f"{method} {path} 应为 404"

    resp = client.get("/api/records", headers=other_auth)
    assert resp.get_json()["data"]["total"] == 0


def test_record_image_requires_auth(client, analyzed_record):
    resp = client.get(f"/api/records/{analyzed_record}/image")
    assert resp.status_code == 401


def test_dashboard_reflects_records(client, auth, analyzed_record):
    resp = client.get("/api/dashboard", headers=auth)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["totals"]["records"] == 1
    assert data["totals"]["analyzed"] == 1
    assert len(data["trend"]) == 14
    assert data["onboarding"]["steps"]
    assert isinstance(data["recent_records"], list)
    # 测试环境固定使用演示 OCR，因此该记录会被标记为演示数据（真实部署下为 False）
    assert data["totals"]["demo_records"] == 1
    assert data["totals"]["real_records"] == 0


def test_clear_all_records_removes_current_users_history(client, auth, record_factory):
    record_factory()
    record_factory(run_ocr=True)
    assert client.get("/api/records", headers=auth).get_json()["data"]["total"] == 2

    resp = client.delete("/api/records", headers=auth)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["deleted_count"] == 2

    data = client.get("/api/records", headers=auth).get_json()["data"]
    assert data["total"] == 0
    assert data["stats"]["total"] == 0
