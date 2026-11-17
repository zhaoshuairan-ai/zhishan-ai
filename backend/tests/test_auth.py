"""账号与鉴权测试。"""
from __future__ import annotations

from .conftest import register_user


def test_register_and_login(client):
    token = register_user(client, username="alice", password="Alice12345")
    assert token

    resp = client.post("/api/auth/login", json={"username": "alice", "password": "Alice12345"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["token"]
    assert data["user"]["username"] == "alice"
    assert data["user"]["is_demo"] is False


def test_register_rejects_weak_password(client):
    resp = client.post("/api/auth/register", json={"username": "bob", "password": "short"})
    assert resp.status_code == 400
    assert "密码" in resp.get_json()["message"]


def test_register_rejects_password_without_digit(client):
    resp = client.post("/api/auth/register", json={"username": "bob", "password": "abcdefgh"})
    assert resp.status_code == 400


def test_register_rejects_duplicate_username(client):
    register_user(client, username="carol")
    resp = client.post("/api/auth/register", json={"username": "CAROL", "password": "Carol12345"})
    assert resp.status_code == 409


def test_login_wrong_password(client):
    register_user(client, username="dave")
    resp = client.post("/api/auth/login", json={"username": "dave", "password": "Wrong12345"})
    assert resp.status_code == 401
    assert "不正确" in resp.get_json()["message"]


def test_me_requires_token(client, auth):
    resp = client.get("/api/auth/me", headers=auth)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["user"]["username"] == "tester"

    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_password_is_hashed_not_plaintext(client, app):
    register_user(client, username="erin", password="Erin123456")
    from app.models import User

    with app.app_context():
        user = User.query.filter_by(username="erin").first()
        assert user is not None
        assert "Erin123456" not in user.password_hash
        assert len(user.password_hash) > 40


def test_logout_revokes_token(client, auth):
    resp = client.post("/api/auth/logout", headers=auth, json={})
    assert resp.status_code == 200
    resp = client.get("/api/auth/me", headers=auth)
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
