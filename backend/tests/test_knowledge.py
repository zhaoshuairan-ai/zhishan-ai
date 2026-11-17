"""知识库检索测试。"""
from __future__ import annotations


def test_knowledge_list_and_categories(client):
    resp = client.get("/api/knowledge")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["total"] >= 40
    assert data["items"]
    assert data["categories"][0]["value"] == "all"
    assert any(category["value"] == "additive" for category in data["categories"])
    entry = data["items"][0]
    assert entry["source_name"]
    assert entry["verification_status"] in {"verified", "pending"}


def test_knowledge_keyword_search(client):
    resp = client.get("/api/knowledge?query=山梨酸钾")
    data = resp.get_json()["data"]
    assert data["total"] >= 1
    assert any("山梨酸钾" in item["title"] for item in data["items"])


def test_knowledge_search_by_keyword_field(client):
    resp = client.get("/api/knowledge?query=奶油")
    assert resp.status_code == 200


def test_knowledge_category_filter(client):
    resp = client.get("/api/knowledge?category=nutrition")
    data = resp.get_json()["data"]
    assert data["total"] >= 1
    assert all(item["category"] == "nutrition" for item in data["items"])


def test_knowledge_invalid_category(client):
    resp = client.get("/api/knowledge?category=not-exist")
    assert resp.status_code == 400


def test_knowledge_detail(client):
    listing = client.get("/api/knowledge?query=反式脂肪酸").get_json()["data"]
    entry_id = listing["items"][0]["id"]
    resp = client.get(f"/api/knowledge/{entry_id}")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["entry"]["content"]
    assert data["entry"]["source_name"]
    assert isinstance(data["related"], list)


def test_knowledge_detail_not_found(client):
    resp = client.get("/api/knowledge/999999")
    assert resp.status_code == 404


def test_knowledge_no_fabricated_links(client):
    """知识库条目的来源 URL 只能是空或 http(s) 链接。"""
    data = client.get("/api/knowledge?per_page=50").get_json()["data"]
    for item in data["items"]:
        url = item["source_url"]
        assert url is None or url.startswith("http"), url


def test_seed_has_at_least_120_entries_with_unique_slugs():
    """知识库扩充后，种子数据要保证规模、唯一性与必填字段完整。"""
    from app.seed.knowledge_seed import KNOWLEDGE_ENTRIES

    slugs = [entry["slug"] for entry in KNOWLEDGE_ENTRIES]
    assert len(slugs) >= 120, f"知识库条目偏少：{len(slugs)}"
    assert len(slugs) == len(set(slugs)), "存在重复 slug"
    categories = {"additive", "ingredient", "nutrition", "label_rule", "safety"}
    for entry in KNOWLEDGE_ENTRIES:
        assert entry["category"] in categories, entry["slug"]
        assert entry["title"] and entry["summary"] and entry["source_name"], entry["slug"]
        assert entry["verification_status"] in {"verified", "pending"}, entry["slug"]
        assert entry["source_url"] is None or entry["source_url"].startswith("http"), entry["slug"]


def test_import_template_is_valid_json():
    """随仓库提供的导入模板必须能被解析，避免用户拿到坏模板。"""
    import json
    from pathlib import Path

    template = Path(__file__).resolve().parents[2] / "docs" / "knowledge-import-template.json"
    rows = json.loads(template.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and len(rows) >= 2
    for row in rows:
        for key in ("slug", "title", "category", "summary", "source_name"):
            assert row.get(key), key
