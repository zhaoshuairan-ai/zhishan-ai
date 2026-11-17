"""本地开源 OCR 驱动（RapidOCR / PaddleOCR 模型，ONNX 推理）。

针对手机实拍（模糊、小字、反光）做了三步优化：
1. 识别使用原图，而不是压缩后的展示图；
2. 预处理：EXIF 方向校正 → 灰度 → 自动对比度 → 锐化，小图放大、超大图适度缩小；
3. 放宽检出阈值（text_score=0.30），首轮文字过少时自动用「增强模式」再试一次。

低置信度结果不会被丢弃，而是照常返回，由前端标黄提示用户核对。
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from .base import BaseOcrProvider, OcrLine, OcrOutput, OcrProviderError

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_engine = None
_engine_error: str | None = None
_package_name: str | None = None

# 小字标签放大到至少 1600px 再识别；过大的原图缩到 3200px，兼顾精度与耗时
OCR_MIN_EDGE = 1600
OCR_MAX_EDGE = 3200
OCR_TEXT_SCORE = 0.30
OCR_BOX_THRESH = 0.40


def _import_backend():
    """兼容 rapidocr-onnxruntime 1.3/1.4 与 rapidocr 2.x 的导入差异。"""
    global _package_name
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        _package_name = "rapidocr-onnxruntime"
        return RapidOCR
    except Exception:  # pragma: no cover - 取决于环境
        try:
            from rapidocr import RapidOCR  # type: ignore

            _package_name = "rapidocr"
            return RapidOCR
        except Exception as exc:  # pragma: no cover
            raise ImportError(str(exc)) from exc


class LocalRapidOcrProvider(BaseOcrProvider):
    name = "local_rapidocr"
    label = "本地 OCR 引擎（RapidOCR，离线）"

    @classmethod
    def available(cls) -> bool:
        global _engine_error
        if _engine is not None:
            return True
        try:
            _import_backend()
            return True
        except ImportError as exc:
            _engine_error = str(exc)
            return False

    @classmethod
    def version(cls) -> str:
        try:
            from importlib.metadata import version

            for pkg in ("rapidocr-onnxruntime", "rapidocr"):
                try:
                    return f"{pkg} {version(pkg)}"
                except Exception:
                    continue
        except Exception:  # pragma: no cover
            pass
        return "rapidocr (version unknown)"

    def _get_engine(self):
        global _engine, _engine_error
        if _engine is not None:
            return _engine
        with _lock:
            if _engine is not None:
                return _engine
            RapidOCR = _import_backend()
            try:
                # 放宽阈值：宁可多给一些低置信度结果（前端会标黄），也不要整段漏掉
                _engine = RapidOCR(text_score=OCR_TEXT_SCORE, box_thresh=OCR_BOX_THRESH)
            except TypeError:  # pragma: no cover - 旧版本不支持这些参数
                _engine = RapidOCR()
            except Exception as exc:  # pragma: no cover - 模型下载/推理库问题
                _engine_error = f"{exc.__class__.__name__}: {exc}"
                raise OcrProviderError(f"本地 OCR 引擎初始化失败：{_engine_error}")
        return _engine

    @staticmethod
    def _prepare_image(image_path: Path, *, boost: bool = False) -> Image.Image:
        """灰度 + 对比度 + 锐化 + 尺寸归一，提升模糊/小字标签的可读性。"""
        with Image.open(image_path) as raw:
            image = ImageOps.exif_transpose(raw).convert("L")
            width, height = image.size
            longest = max(width, height)
            if longest < OCR_MIN_EDGE:
                scale = min(OCR_MIN_EDGE / longest, 3.0)
            elif longest > OCR_MAX_EDGE:
                scale = OCR_MAX_EDGE / longest
            else:
                scale = 1.0
            if boost:
                # 增强版：再放大 1.6 倍，并做直方图均衡
                scale *= 1.6
            if abs(scale - 1.0) > 0.01:
                image = image.resize(
                    (max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS
                )
            image = ImageOps.autocontrast(image, cutoff=1)
            if boost:
                image = ImageOps.equalize(image)
            image = image.filter(ImageFilter.UnsharpMask(radius=1.6, percent=180, threshold=2))
            return image

    def _recognize_once(self, engine, image_path: Path, *, boost: bool) -> tuple[list[OcrLine], dict]:
        prepared = self._prepare_image(image_path, boost=boost)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="fsai_ocr_") as handle:
                tmp_path = handle.name
            prepared.save(tmp_path, "PNG", optimize=True)
            raw = engine(tmp_path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:  # pragma: no cover
                    pass
        result, elapse = (raw if isinstance(raw, tuple) and len(raw) == 2 else (raw, None))
        lines = self._normalize(result)
        meta = {
            "pass": "enhanced" if boost else "standard",
            "size": prepared.size,
            "elapse": elapse if isinstance(elapse, (int, float, list)) else None,
        }
        return lines, meta

    def recognize(self, image_path: Path) -> OcrOutput:
        start = self.timer()
        engine = self._get_engine()

        passes: list[dict] = []
        lines: list[OcrLine] = []
        used_meta: dict = {}
        try:
            lines, used_meta = self._recognize_once(engine, image_path, boost=False)
            passes.append({"pass": "standard", "lines": len(lines)})
            # 首轮几乎没读到文字时，用增强预处理再试一次（模糊 / 小字照片常见）
            if len(lines) < 3:
                boosted_lines, boosted_meta = self._recognize_once(engine, image_path, boost=True)
                passes.append({"pass": "enhanced", "lines": len(boosted_lines)})
                if len(boosted_lines) > len(lines):
                    lines, used_meta = boosted_lines, boosted_meta
        except OcrProviderError:
            raise
        except Exception as exc:  # pragma: no cover
            raise OcrProviderError(f"本地 OCR 识别失败：{exc.__class__.__name__}") from exc

        if not lines:
            raise OcrProviderError(
                "本地 OCR 未从图片中识别到任何文字。"
                "请尽量在光线均匀、文字占满画面、避免反光的情况下重拍，或改用「手动填写配料表」。"
            )
        return OcrOutput(
            provider=self.name,
            provider_label=self.label,
            engine_version=self.version(),
            is_demo=False,
            lines=lines,
            raw_payload={
                "line_count": len(lines),
                "passes": passes,
                "preprocess": {
                    "mode": used_meta.get("pass"),
                    "size": list(used_meta.get("size") or []),
                    "grayscale": True,
                    "autocontrast": True,
                    "unsharp": True,
                },
                "text_score": OCR_TEXT_SCORE,
                "box_thresh": OCR_BOX_THRESH,
            },
            duration_ms=self.elapsed_ms(start),
            warning=(
                "图片文字较少，已自动尝试增强模式；若仍有字段缺失，请补拍更清晰的照片。"
                if len(lines) < 5
                else None
            ),
        )

    @staticmethod
    def _normalize(result) -> list[OcrLine]:
        lines: list[OcrLine] = []
        if result is None:
            return lines
        # rapidocr 2.x: 返回对象，带 txts / scores
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if txts is not None:
            for idx, text in enumerate(txts):
                score = float(scores[idx]) if scores is not None and idx < len(scores) else 0.0
                if str(text).strip():
                    lines.append(OcrLine(text=str(text).strip(), confidence=score))
            return lines
        # 1.x: list[[box, text, score], ...]
        if isinstance(result, (list, tuple)):
            for item in result:
                try:
                    text = str(item[1]).strip()
                    score = float(item[2]) if len(item) > 2 else 0.0
                except (IndexError, TypeError, ValueError):
                    continue
                if text:
                    lines.append(OcrLine(text=text, confidence=score))
        return lines
