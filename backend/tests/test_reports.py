"""报告接口与权限测试。"""
from __future__ import annotations


def test_report_payload_complete(client, auth, analyzed_record):
    resp = client.get(f"/api/reports/{analyzed_record}", headers=auth)
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["report"]["report_no"].startswith("FS-")
    assert data["report"]["generated_at"]
    assert data["meta"]["disclaimer"]
    assert data["check"]["items"]
    assert data["ruleset"]["version"]
    assert data["ruleset"]["disclaimer"]
    assert isinstance(data["sources"], list)
    assert isinstance(data["rule_sources"], list)
    assert data["rule_sources"], "报告必须列出核查规则来源"
    for source in data["rule_sources"]:
        assert source["name"]
        assert source["rule_ids"]


def test_report_requires_analyzed_record(client, auth, record_factory):
    record_id = record_factory(run_ocr=True)
    resp = client.get(f"/api/reports/{record_id}", headers=auth)
    assert resp.status_code == 409
    assert "尚未完成分析" in resp.get_json()["message"]


def test_report_requires_owner(client, other_auth, analyzed_record):
    resp = client.get(f"/api/reports/{analyzed_record}", headers=other_auth)
    assert resp.status_code == 404


def test_report_requires_login(client, analyzed_record):
    resp = client.get(f"/api/reports/{analyzed_record}")
    assert resp.status_code == 401


def test_report_idempotent_number(client, auth, analyzed_record):
    first = client.get(f"/api/reports/{analyzed_record}", headers=auth).get_json()["data"]["report"]
    second = client.get(f"/api/reports/{analyzed_record}", headers=auth).get_json()["data"]["report"]
    assert first["report_no"] == second["report_no"]


def test_report_regenerated_after_reanalysis(client, auth, analyzed_record):
    before = client.get(f"/api/reports/{analyzed_record}", headers=auth).get_json()["data"]["report"]["report_no"]
    client.post(f"/api/records/{analyzed_record}/reanalyze", headers=auth, json={})
    after = client.get(f"/api/reports/{analyzed_record}", headers=auth).get_json()["data"]["report"]["report_no"]
    assert before != after
