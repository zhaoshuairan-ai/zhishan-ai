"""家庭共享：邀请码、库存共享与家庭健康提醒。"""
from __future__ import annotations


def test_family_sharing_and_gastritis_alert(client, auth, other_auth):
    family = client.get("/api/family", headers=auth).get_json()["data"]
    code = family["family"]["invite_code"]
    assert family["member_count"] == 1

    joined = client.post("/api/family/join", headers=other_auth, json={"invite_code": code})
    assert joined.status_code == 200, joined.get_json()
    joined_payload = joined.get_json()["data"]
    assert joined_payload["member_count"] == 2

    added = client.post(
        "/api/pantry",
        headers=other_auth,
        json={"name": "辣条", "category": "other", "quantity": 1, "unit": "包"},
    )
    assert added.status_code == 201, added.get_json()
    item_id = added.get_json()["data"]["item"]["id"]

    shared = client.get("/api/pantry", headers=auth).get_json()["data"]
    row = next(item for item in shared["items"] if item["id"] == item_id)
    assert row["is_shared"] is True
    assert row["owner_name"]

    # 没有胃炎画像时不提示，避免过度打扰
    assert client.get("/api/family/alert", headers=auth).get_json()["data"]["alert"] is None

    client.put(
        "/api/health-profile",
        headers=auth,
        json={"conditions": ["gastritis"], "goals": [], "allergies": [], "notes": ""},
    )
    alert = client.get("/api/family/alert", headers=auth).get_json()["data"]["alert"]
    assert alert is not None
    assert "检测到家人购买辛辣食品，提醒您注意肠胃健康" == alert["message"]
    assert alert["item_name"] == "辣条"

    # 只有户主可以移除成员
    owner_id = family["family"]["owner_id"]
    denied = client.delete(f"/api/family/members/{owner_id}", headers=other_auth)
    assert denied.status_code == 400

    removed = client.delete(f"/api/family/members/{joined_payload['members'][1]['id']}", headers=auth)
    assert removed.status_code == 200, removed.get_json()
    assert removed.get_json()["data"]["family"]["member_count"] == 1
