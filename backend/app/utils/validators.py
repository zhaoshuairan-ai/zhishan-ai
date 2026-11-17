"""输入校验工具：文件名、图片、数字、日期与文本。"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .errors import ValidationError

SAFE_EXT = re.compile(r"^[a-z0-9]{2,5}$")
UNSAFE_CHARS = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def clean_text(value, *, max_len: int = 2000, field: str = "文本", allow_empty: bool = True) -> str:
    if value is None:
        if allow_empty:
            return ""
        raise ValidationError(f"{field}不能为空")
    if not isinstance(value, str):
        raise ValidationError(f"{field}必须是字符串")
    text = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").strip()
    if not text and not allow_empty:
        raise ValidationError(f"{field}不能为空")
    if len(text) > max_len:
        raise ValidationError(f"{field}长度不能超过 {max_len} 个字符")
    return text


def clean_multiline(value, *, max_len: int = 20000, field: str = "文本") -> str:
    """保留换行的长文本清理（用于 OCR 校正文本）。"""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError(f"{field}必须是字符串")
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch >= " " or ch == "\t")
    if len(text) > max_len:
        raise ValidationError(f"{field}长度不能超过 {max_len} 个字符")
    return text.strip()


def clean_filename(name: str, *, fallback: str = "upload") -> str:
    """只用于展示/记录，不参与磁盘路径拼接。"""
    base = Path(name or fallback).name
    base = UNSAFE_CHARS.sub("_", base).strip(" .")
    if not base:
        base = fallback
    return base[:120]


def new_stored_name(extension: str) -> str:
    """生成服务端文件名：uuid + 白名单扩展名，彻底避免路径穿越与重名。"""
    ext = extension.lower().lstrip(".")
    if not SAFE_EXT.match(ext):
        raise ValidationError("不支持的文件扩展名")
    return f"{uuid.uuid4().hex}.{ext}"


def detect_image(data: bytes, filename: str) -> tuple[str, int, int, str]:
    """校验图片真实类型（以 Pillow 解码结果为准，而非用户提供的扩展名）。

    返回 (扩展名, 宽, 高, MIME)。
    """
    if not data:
        raise ValidationError("上传文件为空")
    lower_name = (filename or "").lower()
    fmt_map = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
    try:
        with Image.open(__import__("io").BytesIO(data)) as img:
            fmt = (img.format or "").upper()
            img.verify()
        with Image.open(__import__("io").BytesIO(data)) as img:
            width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError):
        if lower_name.endswith((".heic", ".heif")) or b"ftypheic" in data[:32] or b"ftypheif" in data[:32]:
            raise ValidationError(
                "检测到 iPhone 的 HEIC/HEIF 照片，服务器暂不支持直接解码。"
                "请把手机「设置 → 相机 → 格式」改为「兼容性最佳」，或在相册中导出为 JPG 后再上传。",
                details={"format": "heic"},
            )
        raise ValidationError("无法识别的图片文件，请上传 JPG / PNG / WEBP 格式的食品包装照片")
    if fmt not in fmt_map:
        raise ValidationError(
            f"不支持的图片格式（{fmt or '未知'}），仅支持 JPG、JPEG、PNG、WEBP",
            details={"allowed": ["jpg", "jpeg", "png", "webp"]},
        )
    ext, mime = fmt_map[fmt]
    if width < 40 or height < 40:
        raise ValidationError("图片尺寸过小（至少 40×40 像素），无法识别标签")
    return ext, width, height, mime


def validate_size(size: int, limit_mb: int) -> None:
    if size <= 0:
        raise ValidationError("上传文件为空")
    if size > limit_mb * 1024 * 1024:
        raise ValidationError(
            f"图片大小超过限制（最大 {limit_mb} MB），请压缩后重试",
            details={"max_mb": limit_mb, "received_bytes": size},
        )


def to_float(value, *, field: str = "数值", minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        num = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{field}必须是数字")
    if num != num or num in (float("inf"), float("-inf")):
        raise ValidationError(f"{field}不是有效数字")
    if minimum is not None and num < minimum:
        raise ValidationError(f"{field}不能小于 {minimum}")
    if maximum is not None and num > maximum:
        raise ValidationError(f"{field}不能大于 {maximum}")
    return num


def to_int(value, *, field: str = "数值", minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        num = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{field}必须是整数")
    if minimum is not None and num < minimum:
        raise ValidationError(f"{field}不能小于 {minimum}")
    if maximum is not None and num > maximum:
        raise ValidationError(f"{field}不能大于 {maximum}")
    return num


DATE_PATTERNS = [
    ("%Y-%m-%d", re.compile(r"^(19|20)\d{2}-\d{1,2}-\d{1,2}$")),
    ("%Y-%m-%d", re.compile(r"^(19|20)\d{2}年\d{1,2}月\d{1,2}日$")),
    ("%Y/%m/%d", re.compile(r"^(19|20)\d{2}/\d{1,2}/\d{1,2}$")),
    ("%Y.%m.%d", re.compile(r"^(19|20)\d{2}\.\d{1,2}\.\d{1,2}$")),
    ("%Y%m%d", re.compile(r"^(19|20)\d{6}$")),
]


def parse_cn_date(value: str) -> date | None:
    """解析常见中文日期写法；解析失败返回 None（不猜测）。"""
    if not value:
        return None
    text = str(value).strip()
    for fmt, pattern in DATE_PATTERNS:
        if not pattern.match(text):
            continue
        normalized = text.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
        if fmt == "%Y%m%d":
            normalized = f"{text[:4]}-{text[4:6]}-{text[6:]}"
        parts = normalized.split("-")
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            return None
    return None


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.astimezone().isoformat()


def natural_key(name: str) -> str:
    return re.sub(r"\s+", "", name or "").lower()
