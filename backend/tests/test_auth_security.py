"""登录验证码与用户自助改密测试。"""
from __future__ import annotations

import pytest


def _enable_captcha(app):
    app.config["LOGIN_CAPTCHA"] = "1"
    app.config["CAPTCHA_ECHO"] = "1"


def _disable_captcha(app):
    app.config["LOGIN_CAPTCHA"] = "0"
    app.config["CAPTCHA_ECHO"] = "1"


def test_captcha_endpoint_returns_svg_and_question(client, app):
    _enable_captcha(app)
    try:
        resp = client.get("/api/captcha")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["captcha_id"]
        assert data["image"].startswith("data:image/svg+xml;base64,")
        assert "?" in data["question"]
        assert data["answer"].isdigit()
        assert resp.headers["Cache-Control"].startswith("no-store")
    finally:
        _disable_captcha(app)


def test_login_requires_correct_captcha(client, app):
    from tests.conftest import register_user

    register_user(client, username="captcha_user", password="Test123456")
    _enable_captcha(app)
    try:
        # 不传验证码 → 400
        missing = client.post("/api/auth/login", json={"username": "captcha_user", "password": "Test123456"})
        assert missing.status_code == 400
        assert "验证码" in missing.get_json()["message"]

        # 验证码错误 → 400
        cap = client.get("/api/captcha").get_json()["data"]
        wrong = client.post(
            "/api/auth/login",
            json={
                "username": "captcha_user",
                "password": "Test123456",
                "captcha_id": cap["captcha_id"],
                "captcha_code": "999",
            },
        )
        assert wrong.status_code == 400

        # 正确验证码 → 200
        cap2 = client.get("/api/captcha").get_json()["data"]
        ok = client.post(
            "/api/auth/login",
            json={
                "username": "captcha_user",
                "password": "Test123456",
                "captcha_id": cap2["captcha_id"],
                "captcha_code": cap2["answer"],
            },
        )
        assert ok.status_code == 200, ok.get_json()

        # 同一个验证码不能重复使用
        reused = client.post(
            "/api/auth/login",
            json={
                "username": "captcha_user",
                "password": "Test123456",
                "captcha_id": cap2["captcha_id"],
                "captcha_code": cap2["answer"],
            },
        )
        assert reused.status_code == 400
    finally:
        _disable_captcha(app)


def test_admin_login_requires_captcha(client, admin_auth, app):
    _enable_captcha(app)
    try:
        cap = client.get("/api/captcha").get_json()["data"]
        ok = client.post(
            "/api/admin/auth/login",
            json={
                "username": "admin_tester",
                "password": "AdminTest12345",
                "captcha_id": cap["captcha_id"],
                "captcha_code": cap["answer"],
            },
        )
        assert ok.status_code == 200, ok.get_json()
    finally:
        _disable_captcha(app)


def test_change_password_flow(client, auth, token):
    wrong_old = client.post(
        "/api/auth/change-password",
        headers=auth,
        json={"old_password": "wrong-pass", "new_password": "NewPass12345"},
    )
    assert wrong_old.status_code == 400
    assert "原密码" in wrong_old.get_json()["message"]

    weak = client.post(
        "/api/auth/change-password",
        headers=auth,
        json={"old_password": "Test123456", "new_password": "short"},
    )
    assert weak.status_code == 400

    same = client.post(
        "/api/auth/change-password",
        headers=auth,
        json={"old_password": "Test123456", "new_password": "Test123456"},
    )
    assert same.status_code == 400

    changed = client.post(
        "/api/auth/change-password",
        headers=auth,
        json={"old_password": "Test123456", "new_password": "NewPass12345"},
    )
    assert changed.status_code == 200
    new_token = changed.get_json()["data"]["token"]
    assert new_token and new_token != token

    # 旧令牌立即失效，新令牌可用
    assert client.get("/api/auth/me", headers=auth).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200

    # 旧密码不能登录，新密码可以
    assert client.post("/api/auth/login", json={"username": "tester", "password": "Test123456"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "tester", "password": "NewPass12345"}).status_code == 200


def test_change_password_requires_login(client):
    resp = client.post("/api/auth/change-password", json={"old_password": "a", "new_password": "NewPass12345"})
    assert resp.status_code == 401


def test_disabled_user_cannot_change_password(client, admin_auth, auth):
    user_id = next(
        item["id"]
        for item in client.get("/api/admin/users", headers=admin_auth, query_string={"per_page": 100})
        .get_json()["data"]["items"]
        if item["username"] == "tester"
    )
    client.patch(f"/api/admin/users/{user_id}", headers=admin_auth, json={"is_active": False})
    resp = client.post(
        "/api/auth/change-password",
        headers=auth,
        json={"old_password": "Test123456", "new_password": "NewPass12345"},
    )
    assert resp.status_code == 401
