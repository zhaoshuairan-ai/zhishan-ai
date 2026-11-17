"""手机端完整流程自动化验证（Playwright，移动端触摸模拟）。

在 390×844、is_mobile + has_touch 的移动端环境中走一遍真实流程：
选择图片 → 自动上传与 OCR → 批量校正 → 保存并分析 → 结果页渲染 → 截图。
结束后会自动删除本次创建的记录，不污染演示数据。

用法：
    python scripts/mobile_flow_check.py
    python scripts/mobile_flow_check.py --base-url http://127.0.0.1:8000 --keep

前置：服务已启动，且已安装 playwright + chromium。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import requests
from login_helper import login as solve_login
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "docs" / "screenshots"

LABEL_LINES = [
    ("手机流程测试 原味苏打饼干", 36),
    ("净含量：200g", 28),
    ("配料：小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母", 26),
    ("营养成分表（每100g）", 26),
    ("能量 1980kJ 24%", 26),
    ("蛋白质 8.5g 14%", 26),
    ("脂肪 18.2g 30%", 26),
    ("碳水化合物 65.4g 22%", 26),
    ("钠 480mg 24%", 26),
    ("生产日期：2026-09-12    保质期：12个月", 24),
    ("贮存条件：置于阴凉干燥处", 24),
    ("生产者：手机流程测试食品有限公司", 24),
]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def make_label(path: Path) -> None:
    font_path = next((c for c in FONT_CANDIDATES if Path(c).exists()), None)
    image = Image.new("RGB", (960, 760), (252, 252, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle([6, 6, 953, 753], outline=(205, 205, 205), width=2)
    y = 34
    for text, size in LABEL_LINES:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        draw.text((34, y), text, fill=(25, 25, 25), font=font)
        y += size + 22
    image.save(path, "PNG", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="手机端完整流程验证")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo123456")
    parser.add_argument("--keep", action="store_true", help="保留测试记录（默认删除）")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    label_path = Path(__import__("tempfile").gettempdir()) / "mobile_flow_label.png"
    make_label(label_path)

    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(("[PASS] " if ok else "[FAIL] ") + name + (f" — {detail}" if detail else ""))

    login = solve_login(requests.Session(), f"{base}/api", args.username, args.password)
    if login.status_code != 200:
        print("[错误] 登录失败，请确认服务与演示账号可用")
        return 2
    token = login.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    record_id: int | None = None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            device_scale_factor=2,
            locale="zh-CN",
        )
        context.add_init_script("window.localStorage.setItem('fsai_token', %s)" % json.dumps(token))
        page = context.new_page()
        page.goto(f"{base}/analyze", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOT_DIR / "mobile-flow-1-upload.png"), full_page=True)
        check("打开手机端上传页", page.locator(".uploader input[type=file]").count() == 1)

        page.set_input_files(".uploader input[type=file]", str(label_path))
        # 上传 + OCR 完成后会出现校正表单
        page.wait_for_selector(".correct-form", timeout=180000)
        page.wait_for_timeout(600)
        page.screenshot(path=str(SHOT_DIR / "mobile-flow-2-correct.png"), full_page=True)
        check("自动完成上传与 OCR 并进入校正页", page.locator(".correct-form textarea").count() >= 2)

        ingredients = page.locator(".correct-form textarea").first.input_value()
        check("校正页已填入识别出的配料表", "小麦粉" in ingredients, ingredients[:40])

        name_input = page.locator(".correct-form input").first
        name_input.fill("手机流程测试 苏打饼干（已校正）")

        page.get_by_role("button", name="保存并开始分析").click()
        page.wait_for_url("**/result/**", timeout=180000)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(SHOT_DIR / "mobile-flow-3-result.png"), full_page=True)
        check("分析完成并跳转到结果页", "/result/" in page.url, page.url)

        body = page.inner_text("body")
        check("结果页包含配料分析", "配料分析" in body)
        check("结果页包含营养分析", "营养成分分析" in body)
        check("结果页包含标签核查", "标签辅助核查" in body)

        # 结果页不能出现横向溢出
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("结果页无横向溢出", overflow <= 2, f"overflow={overflow}px")

        page.goto(f"{base}/history", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOT_DIR / "mobile-flow-4-history.png"), full_page=True)
        history_text = page.inner_text("body")
        check("历史记录中出现本次记录", "手机流程测试" in history_text)

        record_id = int(page.url.rstrip("/").split("/")[-1]) if "/result/" in page.url else None
        context.close()
        browser.close()

    # 从历史记录里找到刚才那条记录的 ID（用于清理）
    listing = requests.get(f"{base}/api/records", headers=headers, params={"query": "手机流程测试"}, timeout=20).json()
    items = listing["data"]["items"]
    if items:
        target = items[0]["id"]
        if args.keep:
            print(f"    已保留测试记录 #{target}")
        else:
            deleted = requests.delete(f"{base}/api/records/{target}", headers=headers, timeout=20)
            check("清理测试记录", deleted.status_code == 200, f"#{target}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n通过 {passed} / {len(results)} 项")
    print(f"截图：{SHOT_DIR}\\mobile-flow-*.png")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
