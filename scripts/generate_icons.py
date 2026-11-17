"""生成 PWA 图标（192/512/遮罩版/apple-touch-icon）。

用法：python scripts/generate_icons.py
依赖：Pillow（backend/.venv 中已安装）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "frontend" / "public" / "icons"

BRAND_TOP = (18, 160, 139)
BRAND_BOTTOM = (11, 101, 88)


def gradient(size: int) -> Image.Image:
    """竖向线性渐变背景。"""
    image = Image.new("RGB", (size, size), BRAND_TOP)
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / max(1, size - 1)
        color = tuple(
            int(BRAND_TOP[i] + (BRAND_BOTTOM[i] - BRAND_TOP[i]) * ratio) for i in range(3)
        )
        draw.line([(0, y), (size, y)], fill=color)
    return image


def shield_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    s = size
    points = [
        (s * 0.50, s * 0.19),
        (s * 0.74, s * 0.28),
        (s * 0.74, s * 0.53),
        (s * 0.50, s * 0.79),
        (s * 0.26, s * 0.53),
        (s * 0.26, s * 0.28),
    ]
    draw.polygon(points, fill=255)
    return mask


def check_stroke(size: int) -> Image.Image:
    layer = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(layer)
    s = size
    width = max(4, int(s * 0.075))
    draw.line(
        [(s * 0.36, s * 0.51), (s * 0.46, s * 0.61), (s * 0.66, s * 0.38)],
        fill=255,
        width=width,
        joint="curve",
    )
    return layer


def render(size: int, *, rounded: bool = True, maskable: bool = False) -> Image.Image:
    # 遮罩图标需要留出安全区（内容控制在中心 80% 以内）
    padding = int(size * 0.1) if maskable else 0
    base = gradient(size).convert("RGBA")

    if rounded and not maskable:
        radius = int(size * 0.26)
        round_mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(round_mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        image.paste(base, (0, 0), round_mask)
    else:
        image = base

    inner = size - padding * 2

    shield = Image.new("RGBA", (inner, inner), (255, 255, 255, 255))
    shield.putalpha(shield_mask(inner).point(lambda v: int(v * 0.16)))
    image.alpha_composite(shield, (padding, padding))

    check = Image.new("RGBA", (inner, inner), (255, 255, 255, 255))
    check.putalpha(check_stroke(inner))
    image.alpha_composite(check, (padding, padding))
    return image


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, True, False),
        ("icon-512.png", 512, True, False),
        ("icon-maskable-512.png", 512, False, True),
        ("apple-touch-icon-180.png", 180, False, False),
    ]
    for name, size, rounded, maskable in targets:
        image = render(size, rounded=rounded, maskable=maskable)
        path = OUT_DIR / name
        image.save(path, "PNG", optimize=True)
        print(f"生成 {path.relative_to(ROOT)} ({size}x{size})")
    print("图标生成完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
