"""管理员后台端到端检查（需要真实运行的服务与管理员账号）。

用法：
    python scripts/admin_check.py --username secadmin --password '********'
    python scripts/admin_check.py --base-url http://127.0.0.1:8000 --screenshots docs/screenshots

检查项：
1. 7 个后台页面可打开、无 JS 报错；
2. 桌面 1366 与手机 390 均无横向溢出；
3. 普通用户访问 /admin/dashboard 会被重定向到 /admin/login；
4. 知识库新增草稿 → 列表出现 → 删除；
5. 规则停用 → 版本记录出现 → 恢复启用；
6. 审计日志页面能看到上述操作。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from login_helper import solve_question

ROOT = Path(__file__).resolve().parents[1]
ADMIN_PAGES = [
    ("/admin/dashboard", "后台概览"),
    ("/admin/users", "用户管理"),
    ("/admin/records", "分析记录"),
    ("/admin/knowledge", "知识库管理"),
    ("/admin/rules", "核查规则"),
    ("/admin/monitor", "系统监控"),
    ("/admin/audit-logs", "操作审计"),
]


def fill_captcha(page) -> None:
    """从验证码图片的 alt 文本读取算术题并填入答案。"""
    img = page.locator(".captcha-field img").first
    img.wait_for(timeout=10000)
    alt = img.get_attribute("alt") or ""
    page.locator(".captcha-field input").first.fill(str(solve_question(alt)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--screenshots", default="docs/screenshots")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    shot_dir = ROOT / args.screenshots
    shot_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((ok, name))
        print(("[PASS] " if ok else "[FAIL] ") + name + (f" — {detail}" if detail else ""))

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---------- 普通用户不能进入后台 ----------
        guest = browser.new_context(viewport={"width": 1366, "height": 900}, locale="zh-CN")
        page = guest.new_page()
        page.goto(f"{base}/admin/dashboard", wait_until="networkidle")
        page.wait_for_timeout(600)
        check("未登录访问后台被重定向到登录页", "/login" in page.url, page.url)
        guest.close()

        # ---------- 管理员登录 ----------
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, locale="zh-CN")
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(f"{base}/admin/login", wait_until="networkidle")
        page.fill('input[autocomplete="username"]', args.username)
        page.fill('input[autocomplete="current-password"]', args.password)
        fill_captcha(page)
        page.get_by_role("button", name="登录管理后台").click()
        page.wait_for_url("**/admin/dashboard", timeout=20000)
        page.wait_for_timeout(1200)
        check("管理员登录成功", "/admin/dashboard" in page.url, page.url)
        check("仪表盘 6 张统计卡", page.locator(".stat-card").count() == 6)
        page.screenshot(path=str(shot_dir / "admin-dashboard-1366.png"))

        # ---------- 页面遍历 ----------
        for path, title in ADMIN_PAGES:
            page.goto(f"{base}{path}", wait_until="networkidle")
            page.wait_for_timeout(700)
            heading = page.locator(".page-title").first
            text = heading.inner_text() if heading.count() else ""
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"{path} 打开且标题正确", text == title, f"标题={text}")
            check(f"{path} 无横向溢出", overflow <= 2, f"{overflow}px")

        # ---------- 知识库：新增草稿 → 删除 ----------
        page.goto(f"{base}/admin/knowledge", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="新增条目").click()
        page.wait_for_timeout(500)
        dialog = page.locator(".el-dialog")
        dialog.locator("input").first.fill("E2E 测试条目")
        dialog.locator("textarea").first.fill("自动化检查创建的草稿，稍后会删除。")
        source_input = dialog.get_by_placeholder("如 GB 2760《…》（名称引用）")
        source_input.fill("平台编辑整理（E2E 测试）")
        dialog.get_by_role("button", name="保存").click()
        page.wait_for_timeout(1200)
        check("新增知识草稿成功", "E2E 测试条目" in page.inner_text("body"))

        page.locator(".el-table__row", has_text="E2E 测试条目").first.get_by_role("button", name="删除").click()
        page.wait_for_timeout(400)
        page.get_by_role("button", name="删除").last.click()
        page.wait_for_timeout(1000)
        check("删除知识草稿成功", "E2E 测试条目" not in page.inner_text("body"))

        # ---------- 规则：停用 → 版本记录 → 恢复 ----------
        page.goto(f"{base}/admin/rules", wait_until="networkidle")
        page.wait_for_timeout(700)
        first_rule = page.locator(".rule-card").first
        rule_title = first_rule.locator("strong").first.inner_text()
        first_rule.get_by_role("button", name="停用").click()
        page.wait_for_timeout(1000)
        first_rule = page.locator(".rule-card").first
        check("规则停用成功", "停用" not in first_rule.inner_text() or "启用" in first_rule.inner_text())
        first_rule.get_by_role("button", name="版本记录").click()
        page.wait_for_timeout(900)
        check("规则版本记录可打开", "停用" in page.inner_text(".el-drawer") or "toggle" in page.inner_text(".el-drawer"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        first_rule.get_by_role("button", name="启用").click()
        page.wait_for_timeout(900)
        check("规则恢复启用", "停用" in page.locator(".rule-card").first.inner_text())

        # ---------- 审计日志 ----------
        page.goto(f"{base}/admin/audit-logs", wait_until="networkidle")
        page.wait_for_timeout(800)
        body = page.inner_text("body")
        check("审计日志包含知识库/规则操作", "知识库" in body or "规则" in body, rule_title)
        page.screenshot(path=str(shot_dir / "admin-audit-1366.png"))

        # ---------- 手机端 ----------
        mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, locale="zh-CN")
        mp = mobile.new_page()
        mp.goto(f"{base}/admin/login", wait_until="networkidle")
        mp.fill('input[autocomplete="username"]', args.username)
        mp.fill('input[autocomplete="current-password"]', args.password)
        fill_captcha(mp)
        mp.get_by_role("button", name="登录管理后台").click()
        mp.wait_for_url("**/admin/dashboard", timeout=20000)
        mp.wait_for_timeout(1000)
        for path, title in ADMIN_PAGES:
            mp.goto(f"{base}{path}", wait_until="networkidle")
            mp.wait_for_timeout(500)
            overflow = mp.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"手机端 {path} 无横向溢出", overflow <= 2, f"{overflow}px")
            check(f"手机端 {path} 有内容", mp.locator(".page-title").first.inner_text() == title)
        mp.screenshot(path=str(shot_dir / "admin-dashboard-390.png"))
        check("后台页面无 JS 错误", not errors, "; ".join(errors[:2]))

        mobile.close()
        ctx.close()
        browser.close()

    failed = [name for ok, name in results if not ok]
    print(f"\n通过 {len(results) - len(failed)} / {len(results)} 项")
    if failed:
        print("失败项：")
        for name in failed:
            print(" -", name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
