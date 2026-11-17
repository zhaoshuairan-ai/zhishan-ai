"""演示数据：内置样例图片 + 完整分析记录。

重要说明：
- 这些记录在数据库中有 is_demo=True 标记，接口与页面都会显示「演示数据」；
- 前端首页会把演示记录与真实记录分开统计，不会把演示数据当成真实用户数据；
- 演示账号密码来自 .env（默认 demo / demo123456），仅用于比赛演示。
"""
from __future__ import annotations

import io
import logging
from datetime import date, timedelta
from pathlib import Path

from flask import current_app
from PIL import Image, ImageDraw, ImageFont

from ..extensions import db
from ..services import analysis_service, storage
from ..models import AnalysisRecord, UploadedImage, User
from ..services.field_parser import parse_fields
from ..services.ocr.base import OcrLine, OcrOutput

logger = logging.getLogger(__name__)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]

def _cracker_lines() -> list[str]:
    today = date.today()
    production = today - timedelta(days=60)
    expiry = date(production.year + 1, production.month, production.day)
    return [
        "乐脆牌 原味苏打饼干（演示样例）",
        "净含量：200g",
        "配料：小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母、",
        "食品添加剂（碳酸钙）、全脂乳粉",
        "营养成分表（每100g）",
        "能量 1980kJ 24%   蛋白质 8.5g 14%",
        "脂肪 18.2g 30%    碳水化合物 65.4g 22%",
        "钠 480mg 24%",
        f"生产日期：{production.isoformat()}    保质期：12个月",
        "贮存条件：置于阴凉干燥处，避免阳光直射",
        "生产者：乐脆食品有限公司（演示样例）",
        "地址：示例省示例市示例区示例路88号",
        "产品标准号：GB/T 20980",
        "致敏物质提示：含有小麦、乳制品",
    ]


def _soda_lines() -> list[str]:
    today = date.today()
    production = today - timedelta(days=45)
    return [
        "清汽牌 无糖青柠气泡水（演示样例）",
        "净含量：330mL",
        "配料：水、赤藓糖醇、二氧化碳、柠檬酸、三氯蔗糖、食用香精",
        "营养成分表（每100mL）",
        "能量 0kJ 0%   蛋白质 0g 0%",
        "脂肪 0g 0%    碳水化合物 0g 0%",
        "钠 12mg 1%",
        f"生产日期：{production.isoformat()}    保质期：9个月",
        "贮存条件：常温避光保存，冷藏后风味更佳",
        "生产者：清汽饮品有限公司（演示样例）",
        "地址：示例省示例市示例区示例路 66 号",
        "产品标准号：GB/T 10792",
        "致敏物质提示：本产品不含常见致敏物质",
    ]


def _load_font(size: int):
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:  # pragma: no cover
                continue
    return ImageFont.load_default()


def make_label_image(lines: list[str], *, width: int = 980, title: str = "演示样例图片 · 非真实商品") -> bytes:
    """生成一张「像食品标签」的演示图片（用于演示账号的示例记录）。"""
    font_body = _load_font(26)
    font_title = _load_font(30)
    line_height = 38
    height = 70 + line_height * len(lines) + 40
    image = Image.new("RGB", (width, height), (252, 252, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle([8, 8, width - 9, height - 9], outline=(200, 200, 200), width=2)
    draw.text((32, 22), title, fill=(200, 60, 60), font=font_title)
    y = 70
    for line in lines:
        draw.text((32, y), line, fill=(30, 30, 30), font=font_body)
        y += line_height
    draw.text((32, height - 34), "本图片由系统生成，仅用于功能演示", fill=(150, 150, 150), font=font_body)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _demo_output(lines: list[str]) -> OcrOutput:
    return OcrOutput(
        provider="demo",
        provider_label="演示模式（内置样例文字，不是对图片的真实识别）",
        engine_version="demo-sample-2025.11",
        is_demo=True,
        lines=[OcrLine(text=text, confidence=0.9) for text in lines],
        raw_payload={"demo": True, "source": "builtin_sample"},
        duration_ms=5,
        warning="演示记录：文字来自内置样例，不是对上传图片的真实识别。",
    )


def _create_demo_record(user: User, *, title: str, lines: list[str], note: str) -> AnalysisRecord:
    record = AnalysisRecord(
        user_id=user.id,
        food_name=title,
        status="uploaded",
        data_source="demo",
        is_demo=True,
        note=note,
    )
    db.session.add(record)
    db.session.flush()

    raw = make_label_image(lines)
    meta = storage.save_image(
        raw,
        original_name=f"demo_{record.id}.png",
        max_mb=int(current_app.config["MAX_CONTENT_LENGTH_MB"]),
        max_edge=int(current_app.config["IMAGE_MAX_EDGE"]),
    )
    image = UploadedImage(record_id=record.id, user_id=user.id, **meta)
    db.session.add(image)
    record.image = image

    output = _demo_output(lines)
    parsed = parse_fields([(line.text, line.confidence) for line in output.lines])
    analysis_service.save_ocr(record, output, parsed)

    # 演示记录固定使用规则模式，避免初始化时产生真实 API 调用费用
    original_provider = current_app.config.get("AI_PROVIDER")
    current_app.config["AI_PROVIDER"] = "rule"
    try:
        analysis_service.analyze(record)
    finally:
        current_app.config["AI_PROVIDER"] = original_provider
    return record


def seed_demo() -> dict:
    username = current_app.config.get("DEMO_USERNAME", "demo")
    user = User.query.filter_by(username=username).first()
    if user is None:
        return {"created": 0, "message": "演示账号不存在，跳过演示数据"}

    existing = AnalysisRecord.query.filter_by(user_id=user.id).count()
    if existing:
        return {"created": 0, "message": f"已有历史记录 {existing} 条，跳过演示数据"}

    try:
        _create_demo_record(
            user,
            title="乐脆牌 原味苏打饼干（演示）",
            lines=_cracker_lines(),
            note="[演示] 内置样例：标签字段较完整，用于展示配料解读、营养图表与核查结论。",
        )
        _create_demo_record(
            user,
            title="清汽牌 无糖青柠气泡水（演示）",
            lines=_soda_lines(),
            note="[演示] 内置样例：零能量饮料，用于展示 0 值营养数据与钠含量提示。",
        )
        db.session.commit()
    except Exception as exc:  # pragma: no cover - 初始化失败不应阻塞启动
        db.session.rollback()
        logger.warning("生成演示数据失败：%s", exc.__class__.__name__)
        return {"created": 0, "message": f"演示数据生成失败：{exc.__class__.__name__}"}

    count = AnalysisRecord.query.filter_by(user_id=user.id, is_demo=True).count()
    logger.info("已生成 %s 条演示记录", count)
    return {"created": count, "message": f"已生成 {count} 条演示记录（均标记为演示数据）"}
