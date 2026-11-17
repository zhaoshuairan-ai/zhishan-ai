"""管理员后台测试：权限、认证、用户/记录/知识库/规则/监控/审计。"""
from __future__ import annotations

import json

import pytest

from app.utils.errors import ValidationError


ADMIN_GET_PATHS = [
    "/api/admin/dashboard",
    "/api/admin/users",
    "/api/admin/records",
    "/api/admin/knowledge",
    "/api/admin/rules",
    "/api/admin/monitor",
    "/api/admin/audit-logs",
]


def test_admin_api_requires_login(client):
    """未登录用户不能访问任何管理 API。"""
    for path in ADMIN_GET_PATHS:
        resp = client.get(path)
        assert resp.status_code == 401, path
        body = resp.get_json()
        assert body["success"] is False
    resp = client.post("/api/admin/knowledge", json={"title": "x"})
    assert resp.status_code == 401


def test_normal_user_cannot_use_admin_api(client, auth):
    """普通用户即使已登录，也必须被 403 拒绝。"""
    for path in ADMIN_GET_PATHS:
        resp = client.get(path, headers=auth)
        assert resp.status_code == 403, path
        assert resp.get_json()["message"] == "需要管理员权限"
    assert client.post("/api/admin/knowledge", headers=auth, json={"title": "x"}).status_code == 403
    assert client.get("/api/admin/auth/me", headers=auth).status_code == 403


def test_admin_login_and_me(client, admin_auth):
    me = client.get("/api/admin/auth/me", headers=admin_auth)
    assert me.status_code == 200
    assert me.get_json()["data"]["user"]["role"] == "admin"

    resp = client.post(
        "/api/admin/auth/login", json={"username": "admin_tester", "password": "AdminTest12345"}
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["user"]["role"] == "admin"
    assert data["token"]

    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}
    logout = client.post("/api/admin/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert client.get("/api/admin/auth/me", headers=headers).status_code == 401


def test_admin_login_rejects_normal_user(client, auth):
    resp = client.post("/api/admin/auth/login", json={"username": "tester", "password": "Test123456"})
    assert resp.status_code == 400
    assert "管理员权限" in resp.get_json()["message"]


def test_admin_login_rate_limited(client):
    for _ in range(5):
        resp = client.post("/api/admin/auth/login", json={"username": "ratelimit_admin", "password": "wrong-pass1"})
        assert resp.status_code == 400
    blocked = client.post(
        "/api/admin/auth/login", json={"username": "ratelimit_admin", "password": "wrong-pass1"}
    )
    assert blocked.status_code == 429
    assert blocked.get_json()["code"] == 42900


def test_dashboard_uses_real_counts(client, admin_auth, record_factory):
    record_factory()
    record_factory(run_ocr=True, analyze=True)
    resp = client.get("/api/admin/dashboard", headers=admin_auth)
    assert resp.status_code == 200
    totals = resp.get_json()["data"]["totals"]
    assert totals["users"] >= 2
    assert totals["records"] >= 2
    assert totals["analyzed"] >= 1
    assert totals["knowledge"] > 0
    assert totals["rules"] > 0
    assert 0 <= totals["success_rate"] <= 100
    trend = resp.get_json()["data"]["trend"]
    assert len(trend) == 14
    assert all("date" in point and "count" in point for point in trend)


def test_user_disable_and_restore(client, admin_auth, auth):
    listing = client.get("/api/admin/users", headers=admin_auth, query_string={"q": "tester"})
    assert listing.status_code == 200
    users = client.get("/api/admin/users", headers=admin_auth, query_string={"per_page": 100}).get_json()["data"]["items"]
    user_id = next(item["id"] for item in users if item["username"] == "tester")

    disabled = client.patch(f"/api/admin/users/{user_id}", headers=admin_auth, json={"is_active": False})
    assert disabled.status_code == 200
    assert disabled.get_json()["data"]["user"]["is_active"] is False

    # 被停用用户的现有会话立即失效，且不能再次登录
    assert client.get("/api/auth/me", headers=auth).status_code == 401
    assert (
        client.post("/api/auth/login", json={"username": "tester", "password": "Test123456"}).status_code == 401
    )

    restored = client.patch(f"/api/admin/users/{user_id}", headers=admin_auth, json={"is_active": True})
    assert restored.status_code == 200
    login = client.post("/api/auth/login", json={"username": "tester", "password": "Test123456"})
    assert login.status_code == 200


def test_admin_cannot_disable_self(client, admin_auth):
    me = client.get("/api/admin/auth/me", headers=admin_auth).get_json()["data"]["user"]
    resp = client.patch(f"/api/admin/users/{me['id']}", headers=admin_auth, json={"is_active": False})
    assert resp.status_code == 400
    assert "当前登录" in resp.get_json()["message"]


def test_password_reset_revokes_old_session(client, admin_auth, auth):
    users = client.get("/api/admin/users", headers=admin_auth, query_string={"per_page": 100}).get_json()["data"]["items"]
    user_id = next(item["id"] for item in users if item["username"] == "tester")
    resp = client.post(f"/api/admin/users/{user_id}/reset-password", headers=admin_auth)
    assert resp.status_code == 200
    temp = resp.get_json()["data"]["temporary_password"]
    assert len(temp) >= 10

    # 旧令牌立即失效
    assert client.get("/api/auth/me", headers=auth).status_code == 401
    # 临时密码可以登录
    login = client.post("/api/auth/login", json={"username": "tester", "password": temp})
    assert login.status_code == 200


def test_record_detail_note_and_delete(client, admin_auth, analyzed_record):
    detail = client.get(f"/api/admin/records/{analyzed_record}", headers=admin_auth)
    assert detail.status_code == 200
    data = detail.get_json()["data"]
    assert data["owner"]["username"] == "tester"
    assert data["ocr"] is not None
    assert data["ingredient"] is not None
    assert data["check"] is not None
    assert "items" in data["check"]

    note = client.post(
        f"/api/admin/records/{analyzed_record}/notes", headers=admin_auth, json={"content": "已人工复核标签"}
    )
    assert note.status_code == 201
    detail2 = client.get(f"/api/admin/records/{analyzed_record}", headers=admin_auth).get_json()["data"]
    assert detail2["notes"][0]["content"] == "已人工复核标签"

    # 未确认时拒绝删除
    assert client.delete(f"/api/admin/records/{analyzed_record}", headers=admin_auth).status_code == 400
    deleted = client.delete(f"/api/admin/records/{analyzed_record}", headers=admin_auth, json={"confirm": True})
    assert deleted.status_code == 200
    assert client.get(f"/api/admin/records/{analyzed_record}", headers=admin_auth).status_code == 404

    logs = client.get("/api/admin/audit-logs", headers=admin_auth, query_string={"action": "record.delete"})
    assert logs.get_json()["data"]["total"] == 1


def test_knowledge_create_update_delete_and_visibility(client, admin_auth):
    payload = {
        "title": "测试条目：后台新增",
        "category": "safety",
        "summary": "用于验证后台知识库 CRUD 的测试条目。",
        "content": "这是测试正文。",
        "source_name": "GB 2760《食品安全国家标准 食品添加剂使用标准》（名称引用）",
        "source_type": "standard_name",
        "verification_status": "pending",
        "status": "draft",
        "scope": "预包装食品标签",
        "version": "1.0",
    }
    created = client.post("/api/admin/knowledge", headers=admin_auth, json=payload)
    assert created.status_code == 201
    entry = created.get_json()["data"]["entry"]
    entry_id = entry["id"]
    assert entry["status"] == "draft"

    # 草稿不会出现在公开知识库（用关键词搜索，避免分页影响）
    public = client.get("/api/knowledge", query_string={"query": "已修改", "per_page": 50}).get_json()["data"]
    assert all(item["id"] != entry_id for item in public["items"])

    updated = client.put(
        f"/api/admin/knowledge/{entry_id}",
        headers=admin_auth,
        json={**payload, "title": "测试条目：已修改", "status": "published"},
    )
    assert updated.status_code == 200
    assert "已修改" in updated.get_json()["data"]["entry"]["title"]

    public2 = client.get("/api/knowledge", query_string={"query": "已修改", "per_page": 50}).get_json()["data"]
    assert any(item["id"] == entry_id for item in public2["items"])

    deleted = client.delete(f"/api/admin/knowledge/{entry_id}", headers=admin_auth)
    assert deleted.status_code == 200
    public3 = client.get("/api/knowledge", query_string={"query": "已修改", "per_page": 50}).get_json()["data"]
    assert all(item["id"] != entry_id for item in public3["items"])


def test_unverified_editorial_content_cannot_be_published(client, admin_auth):
    payload = {
        "title": "AI 草稿：未核验内容",
        "category": "safety",
        "summary": "未核验的 AI 生成草稿不应作为权威内容发布。",
        "source_name": "平台编辑整理",
        "source_type": "editorial",
        "verification_status": "pending",
        "status": "draft",
    }
    created = client.post("/api/admin/knowledge", headers=admin_auth, json=payload)
    assert created.status_code == 201
    entry_id = created.get_json()["data"]["entry"]["id"]

    blocked = client.post(
        f"/api/admin/knowledge/{entry_id}/publish", headers=admin_auth, json={"status": "published"}
    )
    assert blocked.status_code == 400
    assert "核验" in blocked.get_json()["message"]

    # 直接创建为 published 也会被拒绝
    blocked_create = client.post(
        "/api/admin/knowledge", headers=admin_auth, json={**payload, "title": "另一条", "status": "published"}
    )
    assert blocked_create.status_code == 400


def test_rule_update_keeps_revisions_and_audit(client, admin_auth):
    rules = client.get("/api/admin/rules", headers=admin_auth).get_json()["data"]["items"]
    rule = rules[0]
    updated = client.put(
        f"/api/admin/rules/{rule['rule_id']}",
        headers=admin_auth,
        json={
            "title": "字段检查（已调整）",
            "category": rule["category"],
            "basis": "调整后的依据说明",
            "source_name": rule["source_name"],
            "scope": rule["scope"],
            "version": "2026.01",
            "effective_date": "2026-01-01",
            "change_note": "测试修改",
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["rule"]["version"] == "2026.01"

    history = client.get(f"/api/admin/rules/{rule['rule_id']}/revisions", headers=admin_auth)
    assert history.status_code == 200
    revisions = history.get_json()["data"]["revisions"]
    assert revisions
    latest = revisions[0]
    assert latest["action"] == "update"
    assert latest["before"]["title"] == rule["title"]
    assert "已调整" in latest["after"]["title"]
    assert latest["changed_by"] == "admin_tester"

    logs = client.get("/api/admin/audit-logs", headers=admin_auth, query_string={"action": "rule.update"})
    assert logs.get_json()["data"]["total"] >= 1


def test_rule_toggle_and_enabled_count(client, admin_auth):
    rules = client.get("/api/admin/rules", headers=admin_auth).get_json()["data"]
    rule = rules["items"][0]
    toggled = client.post(
        f"/api/admin/rules/{rule['rule_id']}/toggle", headers=admin_auth, json={"enabled": False}
    )
    assert toggled.status_code == 200
    assert toggled.get_json()["data"]["rule"]["enabled"] is False

    stats = client.get("/api/admin/rules", headers=admin_auth).get_json()["data"]["stats"]
    assert stats["disabled"] == 1
    assert stats["enabled"] == rules["stats"]["total"] - 1

    # 再启用，避免影响其他用例
    client.post(f"/api/admin/rules/{rule['rule_id']}/toggle", headers=admin_auth, json={"enabled": True})


def test_monitor_does_not_leak_secrets(client, admin_auth):
    resp = client.get("/api/admin/monitor", headers=admin_auth)
    assert resp.status_code == 200
    text = json.dumps(resp.get_json()["data"], ensure_ascii=False).lower()
    for forbidden in ("api_key", "password", "secret", "sk-"):
        assert forbidden not in text
    data = resp.get_json()["data"]
    assert "services" in data and "requests" in data
    assert "avg_ocr_ms" in data["performance"]


def test_audit_logs_are_admin_only(client, auth, admin_auth):
    assert client.get("/api/admin/audit-logs", headers=auth).status_code == 403
    logs = client.get("/api/admin/audit-logs", headers=admin_auth)
    assert logs.status_code == 200
    data = logs.get_json()["data"]
    assert data["items"]
    assert {"actor_username", "action", "target_type", "created_at", "result"} <= set(data["items"][0].keys())
    actions = {item["action"] for item in data["items"]}
    assert "admin.bootstrap" in actions or "admin.login" in actions


def test_feedback_submit_and_resolve(client, auth, admin_auth):
    submitted = client.post("/api/feedback", headers=auth, json={"content": "识别结果里生产日期看错了"})
    assert submitted.status_code == 201
    feedback_id = submitted.get_json()["data"]["feedback"]["id"]

    listing = client.get("/api/admin/feedback", headers=admin_auth, query_string={"status": "open"})
    assert listing.get_json()["data"]["total"] >= 1

    resolved = client.patch(
        f"/api/admin/feedback/{feedback_id}",
        headers=admin_auth,
        json={"status": "resolved", "reply": "已修正识别并联系用户"},
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["feedback"]["status"] == "resolved"

    logs = client.get("/api/admin/audit-logs", headers=admin_auth, query_string={"action": "feedback.resolve"})
    assert logs.get_json()["data"]["total"] == 1


def test_admin_password_policy():
    from app.services.admin_service import validate_admin_password

    with pytest.raises(ValidationError):
        validate_admin_password("admin123456")
    with pytest.raises(ValidationError):
        validate_admin_password("short1")
    with pytest.raises(ValidationError):
        validate_admin_password("onlyletterslong")
    assert validate_admin_password("Str0ngPassw0rd!") == "Str0ngPassw0rd!"


def test_disabled_admin_is_blocked(client, admin_auth, app):
    """管理员账号被停用后，其令牌也不能继续调用管理接口。"""
    me = client.get("/api/admin/auth/me", headers=admin_auth).get_json()["data"]["user"]
    with app.app_context():
        from app.extensions import db
        from app.models import User

        other = User(
            username="admin_second",
            display_name="第二管理员",
            password_hash="x",
            role="admin",
            is_active=True,
        )
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        # 再建一个可用管理员，避免触发「至少保留一个管理员」保护
        target = db.session.get(User, me["id"])
        target.is_active = False
        db.session.commit()

    assert client.get("/api/admin/dashboard", headers=admin_auth).status_code == 401
    assert client.post("/api/admin/auth/login", json={"username": "admin_tester", "password": "AdminTest12345"}).status_code == 400

    with app.app_context():
        from app.extensions import db
        from app.models import User

        db.session.get(User, me["id"]).is_active = True
        db.session.get(User, other_id).is_active = False
        db.session.commit()

def test_admin_can_promote_and_demote_user(client, admin_auth, auth):
    users = client.get("/api/admin/users", headers=admin_auth, query_string={"per_page": 100}).get_json()["data"]["items"]
    user_id = next(item["id"] for item in users if item["username"] == "tester")

    promoted = client.patch(f"/api/admin/users/{user_id}", headers=admin_auth, json={"role": "admin"})
    assert promoted.status_code == 200
    assert promoted.get_json()["data"]["user"]["role"] == "admin"
    # 提升后原令牌立即拥有管理员权限
    assert client.get("/api/admin/dashboard", headers=auth).status_code == 200

    demoted = client.patch(f"/api/admin/users/{user_id}", headers=admin_auth, json={"role": "user"})
    assert demoted.status_code == 200
    assert client.get("/api/admin/dashboard", headers=auth).status_code == 403

    logs = client.get("/api/admin/audit-logs", headers=admin_auth, query_string={"action": "user.role"})
    assert logs.get_json()["data"]["total"] == 2


def test_admin_cannot_demote_self(client, admin_auth):
    me = client.get("/api/admin/auth/me", headers=admin_auth).get_json()["data"]["user"]
    resp = client.patch(f"/api/admin/users/{me['id']}", headers=admin_auth, json={"role": "user"})
    assert resp.status_code == 400


def test_admin_can_delete_user_and_their_records(client, admin_auth, auth, record_factory):
    record_id = record_factory()
    users = client.get("/api/admin/users", headers=admin_auth, query_string={"per_page": 100}).get_json()["data"]["items"]
    user_id = next(item["id"] for item in users if item["username"] == "tester")

    deleted = client.delete(f"/api/admin/users/{user_id}", headers=admin_auth)
    assert deleted.status_code == 200
    assert deleted.get_json()["data"]["deleted"] is True

    assert client.get(f"/api/admin/records/{record_id}", headers=admin_auth).status_code == 404
    assert client.post("/api/auth/login", json={"username": "tester", "password": "Test123456"}).status_code == 401

    logs = client.get("/api/admin/audit-logs", headers=admin_auth, query_string={"action": "user.delete"})
    entry = logs.get_json()["data"]["items"][0]
    assert entry["target_id"] == str(user_id)


def test_admin_cannot_delete_self_or_last_admin(client, admin_auth):
    me = client.get("/api/admin/auth/me", headers=admin_auth).get_json()["data"]["user"]
    assert client.delete(f"/api/admin/users/{me['id']}", headers=admin_auth).status_code == 400


def test_normal_user_cannot_delete_or_promote(client, auth, other_auth):
    target = client.get("/api/auth/me", headers=other_auth).get_json()["data"]["user"]
    assert client.delete(f"/api/admin/users/{target['id']}", headers=auth).status_code == 403
    assert client.patch(f"/api/admin/users/{target['id']}", headers=auth, json={"role": "admin"}).status_code == 403


def test_admin_can_filter_and_verify_ai_knowledge(client, admin_auth, app):
    from app.extensions import db
    from app.models import KnowledgeEntry

    with app.app_context():
        entry = KnowledgeEntry(
            slug="ai-test-verify",
            title="测试AI配料",
            category="ingredient",
            summary="AI 生成的测试解释",
            content="AI 生成的测试解释",
            source_name="AI生成（待官方核实）",
            source_type="editorial",
            verification_status="pending",
            status="draft",
            created_by="AI",
            updated_by="AI",
        )
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    listed = client.get(
        "/api/admin/knowledge?source=ai&verification=pending",
        headers=admin_auth,
    ).get_json()["data"]
    assert any(item["id"] == entry_id for item in listed["items"])
    target = next(item for item in listed["items"] if item["id"] == entry_id)
    assert target["is_ai_generated"] is True

    verified = client.post(f"/api/admin/knowledge/{entry_id}/verify", headers=admin_auth)
    assert verified.status_code == 200, verified.get_json()
    assert verified.get_json()["data"]["entry"]["verification_status"] == "verified"
    assert verified.get_json()["data"]["entry"]["status"] == "published"
