"""响应式与页面溢出检查（Playwright）。

用法：
    python scripts/responsive_check.py --base-url http://127.0.0.1:5173
    python scripts/responsive_check.py --base-url https://your-site.com --screenshots docs/screenshots

做的事：
1. 通过登录接口拿到令牌，注入 localStorage（与真实前端登录态一致）；
2. 在 360/390/430/768/1024/1366/1920 七种宽度下逐个打开主要路由；
3. 检测横向溢出（文档宽度、超宽元素、图片越界）；
4. 保存整页截图，输出 JSON 报告。

依赖：pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests
from login_helper import login as solve_login
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

VIEWPORTS = [
    ("360", 360, 800),
    ("390", 390, 844),
    ("430", 430, 932),
    ("768", 768, 1024),
    ("1024", 1024, 768),
    ("1366", 1366, 768),
    ("1920", 1920, 1080),
]

OVERFLOW_JS = """
() => {
  const doc = document.documentElement;
  const innerWidth = window.innerWidth;
  const offenders = [];
  const nodes = document.querySelectorAll('body *');
  for (const el of nodes) {
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.position === 'fixed') continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    if (rect.right > innerWidth + 1.5) {
      const cls = typeof el.className === 'string' ? el.className.slice(0, 60) : '';
      offenders.push({
        tag: el.tagName.toLowerCase(),
        cls,
        right: Math.round(rect.right * 10) / 10,
        width: Math.round(rect.width * 10) / 10,
        text: (el.textContent || '').trim().slice(0, 40),
      });
      if (offenders.length >= 8) break;
    }
  }
  return {
    scrollWidth: doc.scrollWidth,
    clientWidth: doc.clientWidth,
    overflow: doc.scrollWidth - doc.clientWidth,
    offenders,
    bodyOverflowX: getComputedStyle(document.body).overflowX,
  };
}
"""


def login_token(base_url: str, username: str, password: str) -> str:
    resp = solve_login(requests.Session(), f"{base_url.rstrip('/')}/api", username, password)
    resp.raise_for_status()
    return resp.json()["data"]["token"]


def pick_record(base_url: str, token: str) -> int | None:
    resp = requests.get(
        f"{base_url.rstrip('/')}/api/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"per_page": 20},
        timeout=20,
    )
    if resp.status_code != 200:
        return None
    for item in resp.json()["data"]["items"]:
        if item["status"] == "analyzed":
            return int(item["id"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="响应式页面检查")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo123456")
    parser.add_argument("--screenshots", default="docs/screenshots")
    parser.add_argument("--widths", default="", help="只检查指定宽度，逗号分隔，例如 360,768")
    parser.add_argument("--no-shots", action="store_true")
    parser.add_argument("--json-out", default="docs/responsive-report.json")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    try:
        token = login_token(base, args.username, args.password)
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] 登录失败，无法开始检查：{exc}")
        return 2
    record_id = pick_record(base, token)
    if record_id is None:
        print("[警告] 没有可用的已分析记录，结果页与报告页将被跳过")

    routes = [
        ("login", "/login"),
        ("dashboard", "/"),
        ("analyze", "/analyze"),
        ("history", "/history"),
        ("knowledge", "/knowledge"),
        ("assistant", "/assistant"),
        ("pantry", "/pantry"),
        ("settings", "/settings"),
        ("about", "/about"),
    ]
    if record_id:
        routes.append(("result", f"/result/{record_id}"))
        routes.append(("report", f"/report/{record_id}"))

    wanted = {w.strip() for w in args.widths.split(",") if w.strip()}
    shots_dir = ROOT / args.screenshots if not Path(args.screenshots).is_absolute() else Path(args.screenshots)
    if not args.no_shots:
        shots_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, width, height in VIEWPORTS:
            if wanted and label not in wanted:
                continue
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
                is_mobile=width < 768,
                has_touch=width < 768,
                locale="zh-CN",
            )
            context.add_init_script(
                f"window.localStorage.setItem('fsai_token', {json.dumps(token)});"
            )
            page = context.new_page()
            for name, path in routes:
                if name == "login":
                    # 登录页在已登录状态下会被重定向，这里用无登录态的上下文单独检查
                    anon = browser.new_context(
                        viewport={"width": width, "height": height},
                        is_mobile=width < 768,
                        has_touch=width < 768,
                        locale="zh-CN",
                    )
                    anon_page = anon.new_page()
                    anon_page.goto(f"{base}{path}", wait_until="networkidle")
                    anon_page.wait_for_timeout(400)
                    info = anon_page.evaluate(OVERFLOW_JS)
                    info.update({"route": name, "path": path, "width": width})
                    results.append(info)
                    if info["overflow"] > 2:
                        failures.append(f"{name}@{width}: 文档横向溢出 {info['overflow']}px")
                    if not args.no_shots:
                        anon_page.screenshot(path=str(shots_dir / f"{label}-{name}.png"), full_page=True)
                    anon.close()
                    continue

                wait_until = "domcontentloaded" if path == "/pantry" else "networkidle"
                page.goto(f"{base}{path}", wait_until=wait_until)
                page.wait_for_timeout(700)
                info = page.evaluate(OVERFLOW_JS)
                info.update({"route": name, "path": path, "width": width})
                results.append(info)
                if info["overflow"] > 2:
                    failures.append(
                        f"{name}@{width}: 文档横向溢出 {info['overflow']}px；超宽元素："
                        + ", ".join(f"{o['tag']}.{o['cls']}" for o in info["offenders"][:3])
                    )
                if not args.no_shots:
                    page.screenshot(path=str(shots_dir / f"{label}-{name}.png"), full_page=True)
            context.close()
        browser.close()

    report_path = ROOT / args.json_out if not Path(args.json_out).is_absolute() else Path(args.json_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"base_url": base, "results": results, "failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n检查了 {len(results)} 个页面/宽度组合")
    print(f"截图目录：{shots_dir if not args.no_shots else '（已跳过）'}")
    print(f"报告文件：{report_path}")
    if failures:
        print(f"\n发现 {len(failures)} 处横向溢出：")
        for item in failures:
            print("  -", item)
        return 1
    print("\n所有页面在全部宽度下均无横向溢出 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
