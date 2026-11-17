"""食材保质期与条码查询。

默认使用内置常识表（离线、可解释）；配置 TAVILY_API_KEY 后可联网检索补充。
条码商品库需要外部接口，未配置时会明确返回「未接入」，不会编造商品名。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import requests
from flask import current_app

# 常见家庭食材的推荐保存天数（冷藏/常温），仅作录入默认值，不是食品安全标准
SHELF_LIFE: list[tuple[tuple[str, ...], int, str, str]] = [
    (("牛奶", "鲜奶", "巴氏奶"), 7, "冷藏", "开封后尽快饮用"),
    (("果切", "鲜切水果"), 1, "冷藏", "切开水果建议当天食用"),
    (("奶茶", "饮料", "果汁", "汽水", "可乐"), 270, "常温", "未开封按包装；开封后冷藏并尽快饮用"),
    (("坚果", "核桃", "腰果", "巴旦木", "开心果"), 180, "常温", "未开封；开封后密封防潮"),
    (("酸奶",), 14, "冷藏", "按包装标注为准"),
    (("鸡蛋", "鸭蛋"), 30, "冷藏", "冷藏保存，避免清洗后久放"),
    (("菠菜", "生菜", "油麦菜", "青菜", "小白菜"), 3, "冷藏", "叶菜建议 3 天内食用"),
    (("西兰花", "花菜"), 5, "冷藏", ""),
    (("番茄", "西红柿"), 7, "常温", "熟透后冷藏"),
    (("黄瓜", "茄子", "青椒"), 7, "冷藏", ""),
    (("土豆", "红薯", "南瓜"), 14, "常温", "避光通风"),
    (("苹果", "梨", "橙", "柑橘"), 14, "冷藏", ""),
    (("香蕉",), 5, "常温", "不宜冷藏"),
    (("草莓", "蓝莓", "葡萄"), 4, "冷藏", ""),
    (("猪肉", "排骨", "肉末"), 2, "冷藏", "冷冻可延长至 90 天"),
    (("鸡胸", "鸡腿", "鸡肉"), 2, "冷藏", "冷冻可延长至 90 天"),
    (("牛肉", "羊肉"), 3, "冷藏", "冷冻可延长至 90 天"),
    (("鱼", "虾", "海鲜", "贝"), 1, "冷藏", "建议当天食用"),
    (("豆腐", "豆干", "豆皮"), 3, "冷藏", ""),
    (("大米", "米"), 365, "常温", "密封防潮"),
    (("面粉", "面条"), 180, "常温", "密封防潮"),
    (("饼干", "曲奇", "甜饼", "糕点"), 180, "常温", "按包装；开封后密封防潮"),
    (("巧克力", "糖果"), 365, "常温", "避免高温和阳光直射"),
    (("燕麦",), 365, "常温", ""),
    (("面包", "馒头"), 5, "常温", "冷冻可延长保存"),
    (("食用油", "花生油", "菜籽油", "橄榄油"), 540, "常温", "避光密封"),
    (("酱油", "醋", "蚝油"), 365, "常温", "开封后冷藏"),
    (("蜂蜜",), 730, "常温", ""),
]

CATEGORY_GUESS = [
    ("vegetable", ("菜", "番茄", "西红柿", "黄瓜", "萝卜", "茄子", "青椒", "蘑菇", "菌", "南瓜", "土豆", "西兰花")),
    ("fruit", ("苹果", "香蕉", "橙", "梨", "葡萄", "草莓", "蓝莓", "桃", "西瓜")),
    ("meat", ("猪肉", "排骨", "牛肉", "羊肉", "鸡胸", "鸡腿", "鸡肉", "肉末")),
    ("seafood", ("鱼", "虾", "蟹", "贝", "海鲜")),
    ("egg_dairy", ("鸡蛋", "鸭蛋", "牛奶", "酸奶", "奶酪")),
    ("staple", ("大米", "米", "面粉", "面条", "燕麦", "面包", "馒头", "红薯")),
    ("bean", ("豆腐", "豆干", "豆皮", "豆浆")),
    ("condiment", ("油", "盐", "酱油", "醋", "蚝油", "糖")),
]


@dataclass
class ShelfLifeResult:
    name: str
    days: int | None
    storage: str = "常温"
    note: str = ""
    source: str = "builtin"
    confidence: str = "medium"
    search_url: str | None = None
    search_snippet: str | None = None
    warning: str | None = None
    confidence_percent: int = 0
    confidence_label: str = "未估算"
    alternatives: list[int] = field(default_factory=list)
    basis: str = ""

    def to_public(self) -> dict:
        return {
            "name": self.name,
            "days": self.days,
            "storage": self.storage,
            "note": self.note,
            "source": self.source,
            "confidence": self.confidence,
            "search_url": self.search_url,
            "search_snippet": self.search_snippet,
            "warning": self.warning,
            "confidence_percent": self.confidence_percent,
            "confidence_label": self.confidence_label,
            "alternatives": self.alternatives,
            "basis": self.basis,
        }


def guess_category(name: str) -> str:
    for category, words in CATEGORY_GUESS:
        if any(word in name for word in words):
            return category
    return "other"


def _confidence_for(days: int, *, source: str = "builtin") -> tuple[int, str]:
    if source == "web":
        return 55, "较低"
    if days <= 7:
        return 85, "较高"
    if days <= 30:
        return 75, "中等"
    return 70, "中等"


def _alternatives_for(days: int | None) -> list[int]:
    if not days:
        return []
    if days <= 14:
        return sorted({days, days + 2})
    return sorted({days, days + 30})


def builtin_shelf_life(name: str) -> ShelfLifeResult:
    for words, days, storage, note in SHELF_LIFE:
        if any(word in name for word in words):
            percent, label = _confidence_for(days)
            return ShelfLifeResult(
                name=name,
                days=days,
                storage=storage,
                note=note,
                confidence="medium",
                confidence_percent=percent,
                confidence_label=label,
                alternatives=_alternatives_for(days),
                basis=f"内置常识表：命中「{'/'.join(words[:2])}」的通用保存建议",
            )
    return ShelfLifeResult(
        name=name,
        days=None,
        storage="常温",
        note="内置表未收录，建议按包装标注填写",
        confidence="low",
        warning="未找到该食材的常规保质期，已留空，请核对包装。",
    )


def _tavily_search(name: str) -> dict | None:
    key = str(current_app.config.get("TAVILY_API_KEY") or "").strip()
    if not key:
        return None
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": f"{name} 保质期 冷藏 多少天",
                "search_depth": "basic",
                "max_results": 3,
                "include_answer": True,
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        answer = str(data.get("answer") or "")
        urls = [item.get("url") for item in data.get("results") or [] if item.get("url")]
        return {"answer": answer, "url": urls[0] if urls else None, "raw": data}
    except requests.RequestException:
        return None


def _days_from_text(text: str) -> int | None:
    match = re.search(r"(\d+)\s*[-–~至]\s*(\d+)\s*天", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*天", text)
    if match:
        return int(match.group(1))
    if "一周" in text:
        return 7
    if "两周" in text:
        return 14
    if "一个月" in text:
        return 30
    return None


def lookup_shelf_life(name: str, *, use_web: bool = True) -> dict:
    name = (name or "").strip()
    if not name:
        return builtin_shelf_life("").to_public()
    base = builtin_shelf_life(name)
    if base.days is not None and base.confidence != "low":
        return base.to_public()
    if not use_web:
        return base.to_public()
    found = _tavily_search(name)
    if not found:
        if not current_app.config.get("TAVILY_API_KEY"):
            base.warning = "内置表未收录，无法估算；请手动选择到期日，或按包装标注填写。"
        return base.to_public()
    answer = found.get("answer") or ""
    days = _days_from_text(answer)
    if days:
        return ShelfLifeResult(
            name=name,
            days=days,
            storage="按搜索结果",
            note="联网检索结果，仅供参考，请核对包装标注",
            source="web",
            confidence="low",
            search_url=found.get("url"),
            search_snippet=answer[:200],
            confidence_percent=55,
            confidence_label="较低",
            alternatives=_alternatives_for(days),
            basis="联网检索结果，仅供参考",
        ).to_public()
    base.warning = "联网检索没有找到明确天数，请按包装标注填写。"
    base.search_url = found.get("url")
    base.search_snippet = answer[:200] or None
    return base.to_public()


def _bgr_from_path(image_path: str | Path):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        rgb = np.array(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _decode_once(image, *, formats=None) -> dict | None:
    import zxingcpp

    try:
        results = zxingcpp.read_barcodes(
            image,
            formats=formats or zxingcpp.BarcodeFormat.AllLinear,
            try_rotate=True,
            try_downscale=False,
            try_invert=True,
        )
    except Exception:
        return None
    for result in results:
        text = str(getattr(result, "text", "") or "").strip()
        if text:
            fmt = str(getattr(result, "format", "") or "")
            return {"found": True, "barcode": text, "format": fmt.split(".")[-1], "message": ""}
    return None


def _variants(image):
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    yield image
    yield gray
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        yield clahe
        yield cv2.convertScaleAbs(clahe, alpha=1.25, beta=-10)
    except Exception:
        pass


def _tiles(image, grid: int):
    h, w = image.shape[:2]
    if h < 80 or w < 80:
        return
    tile_h, tile_w = h // grid, w // grid
    margin_y, margin_x = int(tile_h * 0.18), int(tile_w * 0.18)
    for row in range(grid):
        for col in range(grid):
            y0 = max(0, row * tile_h - margin_y)
            x0 = max(0, col * tile_w - margin_x)
            y1 = min(h, (row + 1) * tile_h + margin_y)
            x1 = min(w, (col + 1) * tile_w + margin_x)
            crop = image[y0:y1, x0:x1]
            if crop.shape[0] >= 60 and crop.shape[1] >= 60:
                yield crop


def decode_barcode_image(image_path: str | Path) -> dict:
    """服务端条码解码：全图 + 多尺度/分块预处理，条码不在正中也能尝试识别。"""
    try:
        import cv2
        import numpy as np
        import zxingcpp
    except ImportError:
        return {"found": False, "message": "服务端未安装条码解码组件"}
    try:
        image = _bgr_from_path(image_path)
    except Exception:
        return {"found": False, "message": "图片无法读取，请重拍条码"}
    if image is None or image.size == 0:
        return {"found": False, "message": "图片无法读取，请重拍条码"}

    h, w = image.shape[:2]
    # 先全图；再灰度/增强；最后分块，覆盖不在画面中央的小条码
    for variant in _variants(image):
        result = _decode_once(variant)
        if result:
            return result

    # 小图放大，避免条码占画面太小
    if max(h, w) < 1600:
        scale = min(2.0, 1800 / max(h, w))
        if scale > 1.05:
            enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            for variant in _variants(enlarged):
                result = _decode_once(variant)
                if result:
                    return result

    for grid in (2, 3):
        for variant in _variants(image):
            for tile in _tiles(variant, grid):
                result = _decode_once(tile)
                if result:
                    return result

    # 最后尝试整图旋转 180°（90° 已由 zxing try_rotate 覆盖）
    rotated = cv2.rotate(image, cv2.ROTATE_180)
    for variant in _variants(rotated):
        result = _decode_once(variant)
        if result:
            return result
    return {
        "found": False,
        "message": "没有识别到条码，请让条码占画面更大一些、对焦清晰后重拍，或手动输入数字",
    }


NON_FOOD_WORDS = (
    "沐浴",
    "洗发",
    "护发",
    "洗衣",
    "清洁",
    "护理",
    "化妆品",
    "牙膏",
    "纸巾",
    "湿巾",
    "洗洁精",
    "消毒",
    "驱蚊",
    "宠物",
)


def _is_food_product(name: str, goods_type: str = "") -> bool:
    text = f"{name} {goods_type}"
    return not any(word in text for word in NON_FOOD_WORDS)


def _product_shelf_life(name: str, goods_type: str = "") -> dict:
    if not _is_food_product(name, goods_type):
        return {
            "name": name,
            "days": None,
            "storage": "常温",
            "note": "非食品商品，请按包装标注填写保质期",
            "source": "barcode",
            "confidence": "low",
            "warning": None,
        }
    return lookup_shelf_life(name, use_web=False)


def _cache_get(barcode: str) -> dict | None:
    from datetime import datetime, timedelta

    from ..models import BarcodeCache

    cache = BarcodeCache.query.filter_by(barcode=barcode).first()
    if cache is None:
        return None
    if cache.updated_at and datetime.utcnow() - cache.updated_at > timedelta(days=30):
        return None
    return cache.to_public()


def _cache_store(barcode: str, result: dict) -> None:
    from ..extensions import db
    from ..models import BarcodeCache

    cache = BarcodeCache.query.filter_by(barcode=barcode).first()
    if cache is None:
        cache = BarcodeCache(barcode=barcode)
        db.session.add(cache)
    cache.name = str(result.get("name") or "")[:200]
    cache.brand = str(result.get("brand") or "")[:120]
    cache.spec = str(result.get("spec") or "")[:120]
    cache.manufacturer = str(result.get("manufacturer") or "")[:200]
    cache.category = str(result.get("category") or "other")[:30]
    cache.source = str(result.get("source") or "commercial")[:30]
    payload = {key: value for key, value in result.items() if key not in {"image_url"}}
    cache.payload = payload
    db.session.commit()


def _provider() -> str:
    configured = str(current_app.config.get("BARCODE_PROVIDER") or "auto").strip().lower()
    if configured in {"showapi", "generic", "openfoodfacts", "none"}:
        return configured
    if current_app.config.get("SHOWAPI_APP_KEY"):
        return "showapi"
    if current_app.config.get("BARCODE_API_URL"):
        return "generic"
    return "openfoodfacts"


def _not_configured(barcode: str) -> dict:
    return {
        "found": False,
        "barcode": barcode,
        "message": "商业条码库未配置：请设置 SHOWAPI_APP_KEY，或配置 BARCODE_PROVIDER/BARCODE_API_URL；也可以手动补充商品名称。",
        "source": "none",
    }


def _showapi_lookup(barcode: str) -> dict:
    key = str(current_app.config.get("SHOWAPI_APP_KEY") or "").strip()
    if not key:
        return {
            "found": False,
            "barcode": barcode,
            "message": "已选择 ShowAPI 商业条码库，但未配置 SHOWAPI_APP_KEY。",
            "source": "showapi",
        }
    try:
        resp = requests.post(
            "https://route.showapi.com/66-22",
            params={"appKey": key},
            data={"code": barcode},
            timeout=10,
        )
        if resp.status_code != 200:
            return {
                "found": False,
                "barcode": barcode,
                "message": f"商业条码库 HTTP {resp.status_code}，请稍后重试或检查资源包。",
                "source": "showapi",
            }
        payload = resp.json()
        if str(payload.get("showapi_res_code")) not in {"0", "None"}:
            return {
                "found": False,
                "barcode": barcode,
                "message": str(payload.get("showapi_res_error") or "商业条码库鉴权失败，请检查 ShowAPI AppKey 或余额。"),
                "source": "showapi",
            }
        body = payload.get("showapi_res_body") or {}
        if str(body.get("ret_code")) != "0":
            return {
                "found": False,
                "barcode": barcode,
                "message": str(body.get("remark") or "条码库未收录该商品"),
                "source": "showapi",
            }
        name = str(body.get("goodsName") or "").strip()
        if not name:
            return {"found": False, "barcode": barcode, "message": "条码库返回了空商品名", "source": "showapi"}
        goods_type = str(body.get("goodsType") or "")
        category = "other" if not _is_food_product(name, goods_type) else guess_category(f"{name} {goods_type}")
        return {
            "found": True,
            "barcode": barcode,
            "name": name,
            "brand": str(body.get("trademark") or "").strip(),
            "spec": str(body.get("spec") or "").strip(),
            "manufacturer": str(body.get("manuName") or "").strip(),
            "goods_type": goods_type,
            "gpc": str(body.get("gpc") or ""),
            "price": str(body.get("price") or ""),
            "category": category,
            "shelf_life": _product_shelf_life(name, goods_type),
            "source": "showapi",
            "provider_label": "ShowAPI 商品条码库（万维易源 66-22）",
            "cached": False,
        }
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {
            "found": False,
            "barcode": barcode,
            "message": f"商业条码库连接失败：{exc.__class__.__name__}，请稍后重试或手动补充名称。",
            "source": "showapi",
        }


def _generic_lookup(barcode: str) -> dict:
    url_template = str(current_app.config.get("BARCODE_API_URL") or "").strip()
    if not url_template:
        return {
            "found": False,
            "barcode": barcode,
            "message": "未配置 BARCODE_API_URL（自建/代理条码库地址）。",
            "source": "generic",
        }
    headers = {}
    key = str(current_app.config.get("BARCODE_API_KEY") or "").strip()
    if key:
        headers[str(current_app.config.get("BARCODE_API_KEY_HEADER") or "X-API-Key")] = key
    try:
        resp = requests.get(url_template.format(barcode=barcode), headers=headers, timeout=10)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        data = resp.json()
        if isinstance(data.get("data"), dict):
            data = data["data"]
        name = str(data.get("name") or data.get("title") or "").strip()
        if not name:
            raise RuntimeError("条码库未返回商品名称")
        category = str(data.get("category") or guess_category(name))
        goods_type = str(data.get("goods_type") or data.get("type") or "")
        return {
            "found": True,
            "barcode": barcode,
            "name": name,
            "brand": str(data.get("brand") or "").strip(),
            "spec": str(data.get("spec") or "").strip(),
            "manufacturer": str(data.get("manufacturer") or data.get("manuName") or "").strip(),
            "category": category,
            "shelf_life": _product_shelf_life(name, goods_type),
            "source": "generic",
            "provider_label": "自定义商业条码库",
            "cached": False,
        }
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        return {
            "found": False,
            "barcode": barcode,
            "message": f"条码库查询失败：{exc.__class__.__name__}，请手动补充商品名称。",
            "source": "generic",
        }


def _off_product_result(barcode: str, product: dict) -> dict | None:
    name = str(
        product.get("product_name_zh")
        or product.get("product_name")
        or product.get("product_name_en")
        or product.get("generic_name")
        or ""
    ).strip()
    if not name:
        return None
    brand = str(product.get("brands") or "").strip()
    spec = str(product.get("quantity") or "").strip()
    categories = str(product.get("categories") or product.get("categories_tags") or "")
    category = guess_category(f"{name} {categories}")
    return {
        "found": True,
        "barcode": barcode,
        "name": name,
        "brand": brand,
        "spec": spec,
        "manufacturer": str(product.get("manufacturing_places") or product.get("brands_owner") or "").strip(),
        "category": category,
        "goods_type": categories,
        "shelf_life": _product_shelf_life(name, categories),
        "source": "openfoodfacts",
        "provider_label": "Open Food Facts 公开商品库（非商业）",
        "source_url": f"https://world.openfoodfacts.org/product/{barcode}",
        "cached": False,
    }


def _openfoodfacts_lookup(barcode: str) -> dict | None:
    try:
        resp = requests.get(
            f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json",
            headers={"User-Agent": "food-safety-ai/1.0 (local pantry demo)"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if str(payload.get("status")) != "1":
            return None
        return _off_product_result(barcode, payload.get("product") or {})
    except (requests.RequestException, ValueError, KeyError):
        return None


def _local_catalog_lookup(barcode: str) -> dict | None:
    from ..seed.barcode_catalog import CATALOG_VERSION, LOCAL_BARCODE_CATALOG

    entry = LOCAL_BARCODE_CATALOG.get(barcode)
    if not entry:
        return None
    name = entry["name"]
    return {
        "found": True,
        "barcode": barcode,
        "name": name,
        "brand": entry.get("brand", ""),
        "spec": entry.get("spec", ""),
        "manufacturer": entry.get("manufacturer", ""),
        "category": entry.get("category", "other"),
        "shelf_life": _product_shelf_life(name),
        "source": "local_catalog",
        "provider_label": f"本地公开数据缓存（{CATALOG_VERSION}，非商业库）",
        "source_url": entry.get("source_url"),
        "catalog_note": entry.get("note"),
        "cached": False,
    }


def lookup_barcode(barcode: str) -> dict:
    """查询商业条码库，成功结果缓存 30 天，避免重复扣费。"""
    barcode = re.sub(r"\D", "", barcode or "")
    if not barcode:
        return {"found": False, "barcode": "", "message": "请输入条形码数字", "source": "none"}
    cached = _cache_get(barcode)
    if cached:
        return cached
    provider = _provider()
    if provider == "none":
        return _not_configured(barcode)
    if provider == "showapi":
        result = _showapi_lookup(barcode)
    elif provider == "generic":
        result = _generic_lookup(barcode)
    else:
        result = _openfoodfacts_lookup(barcode)
        if not result:
            result = _local_catalog_lookup(barcode)
        if not result:
            result = {
                "found": False,
                "barcode": barcode,
                "message": "免费公开商品库未收录该条码；可手动补充商品名称，或配置商业条码库获得更完整的国内商品覆盖。",
                "source": "openfoodfacts",
            }
    if result.get("found"):
        try:
            _cache_store(barcode, result)
        except Exception:
            # 缓存失败不影响本次查询结果
            pass
    return result

__all__ = ["lookup_shelf_life", "lookup_barcode", "guess_category", "builtin_shelf_life"]
