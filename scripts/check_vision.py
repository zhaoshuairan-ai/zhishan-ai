"""视觉模型连通性诊断脚本。

用途：不经过前端，直接用一张合成标签图调用「配置里的视觉模型」，
打印真正请求的地址、HTTP 状态、耗时与解析到的字段，快速定位 404/401/超时。

用法：
    cd food-safety-ai
    .\\backend\\.venv\\Scripts\\python.exe scripts\\check_vision.py
    # 只看地址、不真的发请求：
    .\\backend\\.venv\\Scripts\\python.exe scripts\\check_vision.py --dry-run
    # 用真实照片：
    .\\backend\\.venv\\Scripts\\python.exe scripts\\check_vision.py --image uploads\\xxx.jpg
"""
from __future__ import annotations

import argparse
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app import create_app  # noqa: E402
from app.services.ocr.vision_llm import VisionLlmProvider, candidate_urls, normalize_base_url  # noqa: E402


def make_sample_image() -> Path:
    """生成一张小号标签图，足够验证连通性。"""
    width, height = 900, 640
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 26)
    except OSError:  # pragma: no cover - 非 Windows 环境
        font = ImageFont.load_default()
    lines = [
        "测试牌 香脆薯片（OCR 连通性测试）",
        "净含量：70g",
        "配料：马铃薯、植物油、白砂糖、食用盐、碳酸氢钠",
        "营养成分表（每100g）",
        "能量 2200kJ 26%",
        "蛋白质 6.5g 11%",
        "脂肪 30.0g 50%",
        "碳水化合物 55.0g 18%",
        "钠 650mg 33%",
        "生产日期：2026-09-01   保质期：9个月",
        "致敏物质提示：含有小麦",
    ]
    y = 24
    for line in lines:
        draw.text((28, y), line, fill=(20, 20, 20), font=font)
        y += 52
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=92)
    tmp = Path(tempfile.gettempdir()) / "fsai_vision_probe.jpg"
    tmp.write_bytes(buffer.getvalue())
    return tmp


def mask(value: str | None) -> str:
    if not value:
        return "（未配置）"
    return f"已配置（{len(value)} 位，已隐藏）"


def main() -> int:
    parser = argparse.ArgumentParser(description="视觉模型连通性诊断")
    parser.add_argument("--image", help="使用指定图片而不是合成测试图")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要请求的地址，不发请求")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        config = app.config
        print("=" * 68)
        print("视觉模型配置")
        print(f"  OCR_PROVIDER        : {config.get('OCR_PROVIDER')}")
        print(f"  OCR_VISION_BASE_URL : {config.get('OCR_VISION_BASE_URL')}")
        print(f"  规范化后的地址      : {normalize_base_url(config.get('OCR_VISION_BASE_URL'))}")
        print(f"  OCR_VISION_MODEL    : {config.get('OCR_VISION_MODEL')}")
        print(f"  OCR_VISION_API_KEY  : {mask(config.get('OCR_VISION_API_KEY'))}")
        print(f"  OCR_TIMEOUT         : {config.get('OCR_TIMEOUT')} 秒")
        try:
            urls = candidate_urls(config.get("OCR_VISION_BASE_URL"))
        except Exception as exc:  # noqa: BLE001
            print(f"\n[配置错误] {exc}")
            return 2
        print("  将依次尝试的地址：")
        for url in urls:
            print(f"    - {url}")
        if args.dry_run:
            return 0

        image_path = Path(args.image) if args.image else make_sample_image()
        if not image_path.exists():
            print(f"\n[错误] 图片不存在：{image_path}")
            return 2
        print(f"\n发送测试图片：{image_path}（{image_path.stat().st_size // 1024} KB）")
        provider = VisionLlmProvider()
        try:
            output = provider.recognize(image_path)
        except Exception as exc:  # noqa: BLE001
            print(f"\n[失败] {exc}")
            print(
                "\n排查建议：\n"
                "  1) HTTP 404：OCR_VISION_BASE_URL 只填到站点根或 /v1，不要带 /chat/completions；\n"
                "  2) HTTP 401/403：Key 无效、未开通该模型，或 Key 与地址不属于同一家服务商；\n"
                "  3) HTTP 400 model not found：OCR_VISION_MODEL 写错了（DeepSeek 用 deepseek-flash）；\n"
                "  4) 超时：把 OCR_TIMEOUT 调大（如 90），并确认网络能访问该域名。"
            )
            return 1

        fields = (output.raw_payload or {}).get("fields") or {}
        print(f"\n[成功] 耗时 {output.duration_ms} ms，识别到 {len(output.lines)} 行文字")
        print(f"  实际请求地址：{output.raw_payload.get('endpoint')}")
        for key in ("food_name", "ingredients_text", "nutrition_text", "net_content", "production_date"):
            value = (fields.get(key) or "").replace("\n", " ")
            print(f"  {key:16s}: {value[:70] or '（空）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
