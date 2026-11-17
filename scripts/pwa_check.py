"""PWA 与打印能力检查（Playwright，针对生产构建）。

验证：
1. Service Worker 是否注册并激活；
2. 缓存中是否包含 `/api` 数据（必须为 0）；
3. 断网后是否还能打开缓存的应用外壳并显示离线提示；
4. 报告页能否打印成 PDF（保存样例文件）；
5. 是否可通过局域网 IP 访问（可选，自动探测）。

用法：
    python scripts/pwa_check.py
    python scripts/pwa_check.py --base-url https://your-domain.com --pdf-out docs/sample-report.pdf

前置：以生产模式启动（SERVE_FRONTEND=1，端口 8000），并已执行过 npm run build。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests
from login_helper import login as solve_login
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def lan_ip() -> str:
    try:
        output = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-NetIPAddress -AddressFamily IPv4 | "
                "Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' } | "
                "Select-Object -First 1).IPAddress",
            ],
            text=True,
            timeout=20,
        ).strip()
        return output
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="PWA 与打印能力检查")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo123456")
    parser.add_argument("--pdf-out", default="docs/sample-report.pdf")
    parser.add_argument("--no-lan", action="store_true")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(("[PASS] " if ok else "[FAIL] ") + name + (f" — {detail}" if detail else ""))

    try:
        login = solve_login(requests.Session(), f"{base}/api", args.username, args.password)
        login.raise_for_status()
        token = login.json()["data"]["token"]
        records = requests.get(
            f"{base}/api/records", headers={"Authorization": f"Bearer {token}"}, timeout=20
        ).json()["data"]["items"]
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] 无法连接服务或登录失败：{exc}")
        return 2

    report_id = next((item["id"] for item in records if item["status"] == "analyzed"), None)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1366, "height": 900}, locale="zh-CN")
        context.add_init_script("window.localStorage.setItem('fsai_token', %s)" % json.dumps(token))
        page = context.new_page()
        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_timeout(1800)

        sw = page.evaluate(
            """async () => {
                if (!('serviceWorker' in navigator)) return { supported: false };
                const reg = await navigator.serviceWorker.ready;
                return { supported: true, active: !!reg.active, script: reg.active ? reg.active.scriptURL : '' };
            }"""
        )
        check("Service Worker 已注册并激活", bool(sw.get("active")), sw.get("script", ""))

        cache_info = page.evaluate(
            """async () => {
                const names = await caches.keys();
                const urls = [];
                for (const name of names) {
                    const cache = await caches.open(name);
                    const requests = await cache.keys();
                    urls.push(...requests.map((request) => request.url));
                }
                return { names, urls };
            }"""
        )
        api_urls = [url for url in cache_info["urls"] if "/api/" in url]
        check("缓存中没有 /api 数据", len(api_urls) == 0, f"{len(cache_info['urls'])} 个缓存项，{len(api_urls)} 个 API 项")
        check("应用外壳（JS/CSS）已预缓存", len(cache_info["urls"]) >= 4, "、".join(cache_info["names"]))

        context.set_offline(True)
        offline_ok = False
        detail = ""
        try:
            page.goto(f"{base}/history", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2200)
            offline_info = page.evaluate(
                """() => ({
                    children: document.querySelector('#app') ? document.querySelector('#app').children.length : 0,
                    text: (document.body.innerText || '').slice(0, 120),
                    banner: !!document.querySelector('.offline-banner'),
                })"""
            )
            offline_ok = offline_info["children"] > 0 and ("离线" in offline_info["text"] or offline_info["banner"])
            detail = "页面已渲染并提示离线" if offline_ok else offline_info["text"][:60]
        except Exception as exc:  # noqa: BLE001
            detail = exc.__class__.__name__
        check("断网后可打开缓存页面并提示离线", offline_ok, detail)
        context.set_offline(False)
        context.close()

        if report_id:
            pdf_context = browser.new_context(viewport={"width": 1200, "height": 900}, locale="zh-CN")
            pdf_context.add_init_script("window.localStorage.setItem('fsai_token', %s)" % json.dumps(token))
            pdf_page = pdf_context.new_page()
            pdf_page.goto(f"{base}/report/{report_id}", wait_until="networkidle")
            pdf_page.wait_for_timeout(1200)
            pdf_bytes = pdf_page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"},
            )
            out_path = ROOT / args.pdf_out if not Path(args.pdf_out).is_absolute() else Path(args.pdf_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(pdf_bytes)
            check("报告可打印为 PDF", len(pdf_bytes) > 20000, f"{len(pdf_bytes) // 1024} KB -> {out_path.name}")
            pdf_context.close()
        else:
            check("报告可打印为 PDF", False, "没有已分析的记录，跳过")

        browser.close()

    if not args.no_lan and base.startswith("http://127.0.0.1"):
        ip = lan_ip()
        if ip:
            try:
                lan_ok = requests.get(f"http://{ip}:8000/api/health", timeout=6).status_code == 200
            except Exception:  # noqa: BLE001
                lan_ok = False
            check("可通过局域网 IP 访问生产服务", lan_ok, f"http://{ip}:8000")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n通过 {passed} / {len(results)} 项")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
