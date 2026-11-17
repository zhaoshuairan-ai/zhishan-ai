"""为公网站点生成二维码（比赛现场让评委扫码访问）。

用法：
    python scripts/generate_qr.py --url https://your-site.example.com
    python scripts/generate_qr.py --url https://your-site.example.com --out docs/qr-code.png --label "智膳 AI"

依赖：
    backend\\.venv\\Scripts\\python.exe -m pip install "qrcode[pil]"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    print("缺少依赖：请先安装 qrcode 与 Pillow")
    print('  backend\\.venv\\Scripts\\python.exe -m pip install "qrcode[pil]"')
    sys.exit(2)


FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def load_font(size: int):
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def build(url: str, label: str, note: str) -> Image.Image:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="#0b4f45", back_color="white").convert("RGB")

    width = max(qr_image.width, 760)
    header = 150
    footer = 130
    canvas = Image.new("RGB", (width, qr_image.height + header + footer), "#ffffff")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, width, header - 24], fill="#0f7b6c")

    title_font = load_font(38)
    sub_font = load_font(24)
    url_font = load_font(20)
    note_font = load_font(18)

    draw.text((36, 30), label, font=title_font, fill="#ffffff")
    draw.text((36, 84), "扫码打开 · 手机与电脑同一站点", font=sub_font, fill="#d6f0ea")

    canvas.paste(qr_image, ((width - qr_image.width) // 2, header))

    y = header + qr_image.height + 18
    for line in _wrap(url, url_font, width - 72):
        draw.text((36, y), line, font=url_font, fill="#16211e")
        y += 26
    y += 10
    for line in _wrap(note, note_font, width - 72):
        draw.text((36, y), line, font=note_font, fill="#7a8a84")
        y += 24
    return canvas


def _wrap(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        test = current + char
        if font.getlength(test) > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines or [""]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成站点二维码")
    parser.add_argument("--url", required=True, help="已部署并验证可访问的 HTTPS 地址")
    parser.add_argument("--out", default="docs/qr-code.png")
    parser.add_argument("--label", default="智膳 AI")
    parser.add_argument(
        "--note",
        default="请用手机相机或微信扫码；若无法打开，请确认部署已完成且地址正确。",
    )
    args = parser.parse_args()

    if not args.url.startswith(("http://", "https://")):
        print("[错误] --url 需要以 http:// 或 https:// 开头")
        return 1
    if args.url.startswith("http://localhost") or args.url.startswith("http://127."):
        print("[警告] 该地址只能在生成二维码的电脑上访问，手机扫码无法打开。")
        print("       公网演示请使用部署后的 HTTPS 域名。")

    image = build(args.url, args.label, args.note)
    out_path = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, "PNG", optimize=True)
    print(f"二维码已生成：{out_path}")
    print(f"内容：{args.url}")
    print("请先用手机实际扫码验证可访问，再放进演示 PPT。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
