"""生产模式（单服务）冒烟测试：验证前端静态托管、PWA 资源与 API 同源可用。

用法：
    python scripts/prod_smoke_test.py
    python scripts/prod_smoke_test.py --base-url https://your-site.com

前提：以 SERVE_FRONTEND=1 启动后端（或已部署到公网）。
"""
from __future__ import annotations

import argparse
import sys

import requests
from login_helper import login as solve_login

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(("[PASS] " if ok else "[FAIL] ") + name + (f" — {detail}" if detail else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="生产模式冒烟测试")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo123456")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    print(f"\n== 目标：{base} ==\n")

    session = requests.Session()

    resp = session.get(f"{base}/", timeout=15)
    check("GET / 返回前端页面", resp.status_code == 200 and '<div id="app">' in resp.text, f"HTTP {resp.status_code}")
    check("首页引用构建后的 JS", "/assets/index-" in resp.text)

    resp = session.get(f"{base}/api/health", timeout=15)
    check("GET /api/health", resp.status_code == 200 and resp.json()["data"]["status"] == "ok")

    resp = session.get(f"{base}/manifest.webmanifest", timeout=15)
    ok_manifest = resp.status_code == 200 and resp.json().get("short_name") == "智膳"
    check("PWA manifest 可访问且合法", ok_manifest, resp.headers.get("Content-Type", ""))
    icons = resp.json().get("icons", []) if ok_manifest else []
    icon_ok = True
    for icon in icons:
        icon_resp = session.get(base + icon["src"], timeout=15)
        icon_ok = icon_ok and icon_resp.status_code == 200 and icon_resp.headers["Content-Type"].startswith("image/")
    check("PWA 图标全部可访问", icon_ok, f"{len(icons)} 个图标")

    resp = session.get(f"{base}/sw.js", timeout=15)
    check(
        "Service Worker 可访问",
        resp.status_code == 200
        and "self.addEventListener('fetch'" in resp.text
        and "const VERSION" in resp.text,
    )

    resp = session.get(f"{base}/history", timeout=15)
    check("SPA 路由回退到 index.html", resp.status_code == 200 and '<div id="app">' in resp.text)
    resp = session.get(f"{base}/offline.html", timeout=15)
    check("离线提示页可访问", resp.status_code == 200)

    resp = session.get(f"{base}/api/not-exist", timeout=15)
    check("未知 API 返回统一 JSON 404", resp.status_code == 404 and resp.json()["success"] is False)

    resp = solve_login(session, f"{base}/api", args.username, args.password)
    check("同源登录成功", resp.status_code == 200, f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:200])
        return 1
    token = resp.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = session.get(f"{base}/api/records", headers=headers, timeout=20)
    items = resp.json()["data"]["items"] if resp.status_code == 200 else []
    check("记录列表可读", resp.status_code == 200, f"{len(items)} 条")
    if items:
        record_id = items[0]["id"]
        resp = session.get(f"{base}/api/records/{record_id}/image", headers=headers, timeout=20)
        check("受保护的图片接口", resp.status_code == 200 and resp.headers["Content-Type"].startswith("image/"))
        # 报告只对已完成分析的记录生成；挑一条 analyzed 的记录验证，避免被未完成记录干扰
        analyzed = next((item for item in items if item.get("status") == "analyzed"), None)
        if analyzed:
            resp = session.get(f"{base}/api/reports/{analyzed['id']}", headers=headers, timeout=30)
            check("报告接口", resp.status_code == 200 and resp.json()["data"]["report"]["report_no"])
        else:
            check("报告接口", False, "没有已完成分析的记录，无法验证报告")

    print(f"\n结果：通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
