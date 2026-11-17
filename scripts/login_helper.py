"""脚本共用登录助手：自动获取并解答算术验证码。

验证码是「a + b = ?」或「a - b = ?」形式，接口返回 question 文本（答案不返回），
这里解析题目计算答案后提交，避免每个脚本重复实现。
"""
from __future__ import annotations

import re

import requests


def solve_question(question: str) -> int:
    match = re.search(r"(\d+)\s*([+\-])\s*(\d+)", question or "")
    if not match:
        raise ValueError(f"无法解析验证码题目：{question!r}")
    left, operator, right = int(match.group(1)), match.group(2), int(match.group(3))
    return left + right if operator == "+" else left - right


def fetch_captcha(session: requests.Session, api_base: str) -> tuple[str, int]:
    resp = session.get(f"{api_base.rstrip('/')}/captcha", timeout=15)
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["captcha_id"], solve_question(data.get("question", ""))


def login(
    session: requests.Session,
    api_base: str,
    username: str,
    password: str,
    *,
    admin: bool = False,
    timeout: int = 20,
):
    captcha_id, answer = fetch_captcha(session, api_base)
    path = "/admin/auth/login" if admin else "/auth/login"
    return session.post(
        f"{api_base.rstrip('/')}{path}",
        json={
            "username": username,
            "password": password,
            "captcha_id": captcha_id,
            "captcha_code": str(answer),
        },
        timeout=timeout,
    )
