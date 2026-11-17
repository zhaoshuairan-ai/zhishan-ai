"""图片文件的受控存储：安全文件名、格式校验、缩略图、删除策略。

磁盘上只使用服务端生成的 UUID 文件名，绝不使用用户原始文件名拼接路径。
"""
from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps

from ..utils.errors import NotFoundError, ValidationError
from ..utils.validators import detect_image, validate_size

logger = logging.getLogger(__name__)


def upload_root() -> Path:
    root = Path(current_app.config["UPLOAD_DIR"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(stored_name: str) -> Path:
    """仅接受「无路径分隔符的简单文件名」，并确认最终路径仍在 uploads 目录内。"""
    if not stored_name or "/" in stored_name or "\\" in stored_name or stored_name.startswith("."):
        raise NotFoundError("文件不存在")
    root = upload_root()
    path = (root / stored_name).resolve()
    if root not in path.parents:
        raise NotFoundError("文件不存在")
    return path


def display_name(stored_name: str) -> str:
    return f"display_{stored_name.rsplit('.', 1)[0]}.jpg"


def save_image(
    raw: bytes,
    *,
    original_name: str,
    max_mb: int,
    max_edge: int,
) -> dict:
    """校验并保存上传图片，返回用于入库的元数据。"""
    validate_size(len(raw), max_mb)
    ext, width, height, mime = detect_image(raw, original_name)
    from ..utils.validators import new_stored_name

    stored = new_stored_name(ext)
    path = _safe_path(stored)
    path.write_bytes(raw)

    # 生成展示用压缩版本（保持比例，禁止拉伸），避免手机原图过大拖慢页面
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img)
            if max(img.size) > max_edge:
                ratio = max_edge / max(img.size)
                new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
                img = img.resize(new_size, Image.LANCZOS)
            if img.mode not in ("RGB", "L"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA", "P"):
                    rgba = img.convert("RGBA")
                    background.paste(rgba, mask=rgba.split()[-1])
                else:
                    background.paste(img.convert("RGB"))
                img = background
            img.convert("RGB").save(_safe_path(display_name(stored)), "JPEG", quality=86, optimize=True)
    except Exception as exc:  # pragma: no cover - 展示图失败不影响主流程
        logger.warning("生成展示图失败: %s", exc.__class__.__name__)

    return {
        "stored_name": stored,
        "original_name": original_name,
        "ext": ext,
        "mime": mime,
        "size_bytes": len(raw),
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def read_image(stored_name: str, *, display: bool = False) -> tuple[bytes, str]:
    name = display_name(stored_name) if display else stored_name
    path = _safe_path(name)
    if not path.exists():
        # 展示图缺失时回退原图
        path = _safe_path(stored_name)
    if not path.exists():
        raise NotFoundError("图片文件不存在或已被删除")
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else (
        "image/png" if path.suffix.lower() == ".png" else "image/webp"
    )
    return path.read_bytes(), mime


def image_path(stored_name: str) -> Path:
    path = _safe_path(stored_name)
    if not path.exists():
        raise NotFoundError("图片文件不存在或已被删除")
    return path


def ocr_target(stored_name: str) -> Path:
    """OCR 使用的图片：优先原图（保留细节），找不到时回退到展示图。

    展示图为了页面加载做过压缩（长边 2200、JPEG q86），小字标签容易被压糊；
    识别阶段改用原图，再由 OCR 驱动内部做灰度 / 放大 / 锐化预处理。
    """
    try:
        return image_path(stored_name)
    except NotFoundError:
        candidate = _safe_path(display_name(stored_name))
        if candidate.exists() and candidate.is_file():
            return candidate
        raise


def delete_image(stored_name: str) -> list[str]:
    """删除原图与展示图，返回实际删除的文件名（用于审计）。"""
    deleted: list[str] = []
    for name in (stored_name, display_name(stored_name)):
        try:
            path = _safe_path(name)
        except (ValidationError, NotFoundError):
            continue
        if path.exists() and path.is_file():
            try:
                path.unlink()
                deleted.append(name)
            except OSError as exc:  # pragma: no cover
                logger.warning("删除文件失败 %s: %s", name, exc)
    return deleted


def storage_stats() -> dict:
    root = upload_root()
    total = 0
    count = 0
    for path in root.glob("*"):
        # 统计时忽略 .gitkeep 等隐藏占位文件
        if path.name.startswith("."):
            continue
        if path.is_file():
            total += path.stat().st_size
            count += 1
    return {"file_count": count, "total_bytes": total, "directory": str(root)}
