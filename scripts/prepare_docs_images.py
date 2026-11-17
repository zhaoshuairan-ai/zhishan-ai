"""把响应式截图整理成适合文档展示的 JPEG（README / 演示文档使用）。

用法：python scripts/prepare_docs_images.py
输入：docs/screenshots/*.png（由 scripts/responsive_check.py 生成）
输出：docs/images/*.jpg
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "screenshots"
OUT = ROOT / "docs" / "images"

# (输出文件名, 源截图, 目标宽度, 最多保留的高度)
TARGETS = [
    ("dashboard-desktop.jpg", "1366-dashboard.png", 1200, 2200),
    ("dashboard-mobile.jpg", "390-dashboard.png", 390, 1500),
    ("result-desktop.jpg", "result-demo-1366.png", 1200, 2400),
    ("result-mobile.jpg", "result-demo-390.png", 390, 1700),
    ("analyze-mobile.jpg", "390-analyze.png", 390, 1300),
    ("report-desktop.jpg", "1366-report.png", 1200, 2000),
    ("knowledge-desktop.jpg", "1366-knowledge.png", 1100, 1500),
    ("history-desktop.jpg", "1366-history.png", 1100, 1200),
    ("login-desktop.jpg", "1366-login.png", 1100, 800),
    ("login-mobile.jpg", "390-login.png", 390, 1300),
    ("assistant-desktop.jpg", "assistant-1366.png", 1200, 1600),
    ("assistant-mobile.jpg", "assistant-390.png", 390, 1600),
    ("admin-dashboard-desktop.jpg", "admin-dashboard-1366.png", 1200, 900),
    ("admin-dashboard-mobile.jpg", "admin-dashboard-390.png", 390, 900),
    ("settings.jpg", "settings-new-390.png", 390, 900),
    ("settings-service.jpg", "settings-new-390-service.png", 390, 900),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    missing = []
    for name, source, width, max_height in TARGETS:
        path = SRC / source
        if not path.exists():
            missing.append(source)
            continue
        image = Image.open(path).convert("RGB")
        if image.height > max_height:
            image = image.crop((0, 0, image.width, max_height))
        if image.width > width:
            ratio = width / image.width
            image = image.resize((width, int(image.height * ratio)), Image.LANCZOS)
        target = OUT / name
        image.save(target, "JPEG", quality=82, optimize=True, progressive=True)
        print(f"生成 {target.relative_to(ROOT)}  {image.size[0]}x{image.size[1]}  {target.stat().st_size // 1024} KB")
    if missing:
        print("\n缺少以下源截图（请先运行 scripts/responsive_check.py）：")
        for item in missing:
            print("  -", item)
        return 1
    print("\n文档图片整理完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
