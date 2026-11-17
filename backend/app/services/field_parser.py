"""把 OCR 文本行解析为结构化标签字段。

设计要点：
- 只用图片中真实出现的文字，找不到就是空（绝不填充默认值）；
- 每个字段都带置信度与状态标记（ok / low / inferred / missing / format_suspect）；
- 同时保留「原始 OCR 文本」与「用户校正文本」，两者分别入库。
"""
from __future__ import annotations

import re
from datetime import date

from ..utils.validators import parse_cn_date
from .text_utils import capture_after, extract_section, is_probably_text, normalize

FIELD_ORDER = [
    "food_name",
    "ingredients_text",
    "nutrition_text",
    "net_content",
    "production_date",
    "shelf_life",
    "expiry_date",
    "storage",
    "producer",
    "standard_no",
    "allergen",
]

LOW_CONFIDENCE_THRESHOLD = 0.80

_STOP_GENERAL = [
    "净含量",
    "生产日期",
    "保质期",
    "贮存条件",
    "储存条件",
    "生产者",
    "生产商",
    "制造商",
    "地址",
    "电话",
    "服务热线",
    "产品标准",
    "执行标准",
    "致敏",
    "过敏",
    "营养成分",
    "配料",
]

_STOP_INGREDIENT = [
    "营养成分表",
    "营养成分",
    "净含量",
    "生产日期",
    "制造日期",
    "保质期",
    "贮存条件",
    "储存条件",
    "贮藏条件",
    "生产者",
    "生产商",
    "制造商",
    "地址",
    "电话",
    "服务热线",
    "产品标准",
    "执行标准",
    "致敏",
    "过敏",
    "温馨提示",
    "食用方法",
    "注意事项",
    "规格",
    "净重",
]

_STOP_NUTRITION = [
    "生产日期",
    "制造日期",
    "保质期",
    "贮存条件",
    "储存条件",
    "生产者",
    "生产商",
    "地址",
    "电话",
    "配料",
    "致敏",
    "过敏",
    "温馨提示",
    "食用方法",
    "服务热线",
    "产品标准",
]

_NAME_PATTERN = r"(?:产品名称|食品名称|商品名称|品名|名称)\s*[:：]"
_NET_PATTERN = r"净含量(?:\([^)]{0,12}\))?\s*[:：]?"
_PRODUCER_PATTERN = r"(?:生产者|生产商|制造商|生产厂家|出品方|委托方)(?:名称)?\s*[:：]?"
_STANDARD_PATTERN = r"(?:产品标准号|执行标准(?:号)?|标准号)\s*[:：]?"
_STORAGE_PATTERN = r"(?:贮存条件|储存条件|贮藏条件|保存条件|贮存|储存|贮藏)\s*[:：]?"
_ALLERGEN_PATTERN = r"(?:致敏(?:物质|原|信息)?|过敏原)(?:提示|信息)?\s*[:：]?"

_DATE_VALUE = r"((?:19|20)\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}\s*日?|(?:19|20)\d{6})"
_SHELF_VALUE = r"(\d+(?:\.\d+)?\s*(?:个月|月|天|日|年|周))"
_NET_VALUE = r"(\d+(?:\.\d+)?\s*(?:kg|g|ml|mL|L|克|千克|毫升|升))"

# ---------- 双列排版（配料表与营养成分表并排）分离用 ----------
_NUTRIENT_START_RE = re.compile(
    r"^(能量|蛋白质|饱和脂肪酸|反式脂肪酸|碳水化合物|膳食纤维|脂肪|糖|钠|胆固醇|钙|铁|锌)"
    r"(?=$|[\s:：]|\d)"
)
_NUTRITION_HEADER_RE = re.compile(r"^(项目|每\s*100|每份|每袋|每包|每支|NRV|营养素参考值)")
_NUTRITION_VALUE_RE = re.compile(r"^\d+(?:\.\d+)?\s*[^\d\s]{0,4}\s*[%％]?$")
_INGREDIENT_HINTS = ("复配", "添加剂", "香精", "酱包", "菜包", "调味料", "浓缩", "粉)", "钠、")

# 配料段落遇到这些词就该结束（印刷上的提示语，不属于配料）
_STOP_INGREDIENT_TEXT = (
    "请依个人口味",
    "请依口味",
    "温馨提示",
    "食用方法",
    "冲泡方法",
    "建议食用",
    "致敏物质提示",
)


def _is_nutrition_line(line: str) -> bool:
    """判断一行是否属于营养成分表（名称行 / 数值行 / 表头行）。"""
    compact = line.replace(" ", "")
    if not compact:
        return False
    if _NUTRITION_HEADER_RE.match(compact):
        return True
    if _NUTRIENT_START_RE.match(compact):
        return True
    if _NUTRITION_VALUE_RE.match(compact):
        return True
    return False


def _looks_like_ingredient_fragment(line: str) -> bool:
    """营养成分段落里混进来的配料片段（双列排版的常见问题）。"""
    compact = line.replace(" ", "")
    if _NUTRIENT_START_RE.match(compact) or _NUTRITION_HEADER_RE.match(compact):
        return False
    separators = sum(compact.count(ch) for ch in "、,，;；")
    if separators >= 2:
        return True
    if any(word in compact for word in _INGREDIENT_HINTS):
        return True
    # 长句且不以营养素名开头，基本是配料描述
    if len(compact) >= 26:
        return True
    return False


def _merge_nutrition_rows(lines: list[str]) -> list[str]:
    """把「名称 / 数值 / NRV%」拆开的行合并成一行，尽量还原包装上的表格行。"""
    rows: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        compact = line.replace(" ", "")
        if _NUTRIENT_START_RE.match(compact) and not re.search(r"\d", compact):
            parts = [line]
            cursor = index + 1
            while cursor < len(lines) and len(parts) < 3 and _NUTRITION_VALUE_RE.match(lines[cursor].replace(" ", "")):
                parts.append(lines[cursor].strip())
                cursor += 1
            rows.append(" ".join(parts))
            index = cursor
            continue
        rows.append(line)
        index += 1
    return rows

# 这些词单独成行时只是表头或营养素项目名，不能当作「食品名称」推断
GENERIC_LABEL_WORDS = {
    "能量",
    "蛋白质",
    "脂肪",
    "碳水化合物",
    "钠",
    "糖",
    "水",
    "项目",
    "每份",
    "每袋",
    "每包",
    "每支",
    "净含量",
    "规格",
    "配料",
    "配料表",
    "营养成分表",
    "营养",
    "NRV",
    "营养素参考值",
    "保质期",
    "生产日期",
    "致敏原信息",
    "致敏物质提示",
    "贮存方法",
    "贮存条件",
    "食用方法",
    "温馨提示",
    "检验合格",
    "产品标准号",
    "执行标准",
}


def _norm_date(raw: str) -> str:
    text = re.sub(r"[^\d]", "-", raw.strip())
    parts = [p for p in text.split("-") if p]
    if len(parts) == 3:
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
        except ValueError:
            return raw.strip()
    if len(parts) == 1 and len(parts[0]) == 8:
        try:
            return date(int(parts[0][:4]), int(parts[0][4:6]), int(parts[0][6:])).isoformat()
        except ValueError:
            return raw.strip()
    return raw.strip()


class FieldParser:
    """输入 OCR 行，输出结构化字段 + 置信度 + 标记。"""

    def __init__(self, lines: list[tuple[str, float]]):
        self.lines = [(normalize(t), float(c)) for t, c in lines if t and t.strip()]
        self.text = "\n".join(t for t, _ in self.lines)
        self._line_scores = [c for _, c in self.lines]

    # ---------- 基础工具 ----------
    def _score_at(self, index: int) -> float:
        if 0 <= index < len(self._line_scores):
            return self._line_scores[index]
        return 0.0

    def _score_range(self, indexes: list[int]) -> float:
        scores = [self._score_at(i) for i in indexes if i >= 0]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 3)

    def _capture(self, pattern: str, *, stop: list[str] | None = None, max_len: int = 100):
        value, index = capture_after(self.text, pattern, stop_keywords=stop, max_len=max_len)
        return value, self._score_at(index), index

    # ---------- 各字段 ----------
    def _food_name(self):
        value, score, _ = self._capture(_NAME_PATTERN, stop=_STOP_GENERAL, max_len=40)
        if value:
            return value, score, None
        # 回退：取首个「像名称」的行，并明确标记为推断
        skip = (
            "配料",
            "原料",
            "营养成分",
            "营养",
            "项目",
            "每份",
            "每100",
            "每 100",
            "NRV",
            "营养素参考值",
            "净含量",
            "生产日期",
            "保质期",
            "贮存",
            "储存",
            "生产者",
            "生产商",
            "地址",
            "电话",
            "标准号",
            "执行标准",
            "致敏",
            "过敏",
            "食用方法",
            "检验合格",
            "温馨提示",
            "注意事项",
            "规格",
        )
        for line, score in self.lines[:8]:
            if any(word in line for word in skip):
                continue
            if re.search(r"\d{3,}", line):
                continue
            if line.strip(" :：·-—_") in GENERIC_LABEL_WORDS:
                continue
            # 纯数字/单位/百分比行不是名称（例如表格里的「11%」「889干焦」）
            if not re.search(r"[A-Za-z\u4e00-\u9fff]", line):
                continue
            if len(re.findall(r"[\u4e00-\u9fff]", line)) < 2:
                continue
            if re.search(r"\d", line):
                continue
            if is_probably_text(line, min_len=2) and len(line) <= 30:
                return (
                    line,
                    round(score * 0.55, 3),
                    "未识别到「食品名称」标注文字，暂取图片首行文字，请人工确认",
                )
        return "", 0.0, None

    # ---------- 段落推断（关键词被 OCR 识别坏时的兜底） ----------
    _NUTRIENT_LINE_PREFIXES = (
        "营养成分",
        "营养",
        "项目",
        "NRV",
        "能量",
        "蛋白质",
        "脂肪",
        "碳水化合物",
        "钠",
        "糖",
        "膳食纤维",
        "饱和脂肪",
        "反式脂肪",
        "胆固醇",
        "钙",
        "铁",
        "锌",
        "保质期",
        "生产日期",
        "贮存",
        "储存",
        "生产者",
        "生产商",
        "地址",
        "电话",
        "标准号",
        "执行标准",
        "致敏",
        "过敏",
    )

    def _looks_like_nutrient_line(self, line: str) -> bool:
        compact = line.replace(" ", "")
        if compact.startswith(self._NUTRIENT_LINE_PREFIXES):
            return True
        return any(token in compact for token in ("NRV", "营养素参考值", "每100", "每 100"))

    def _separator_score(self, line: str) -> int:
        compact = line.replace(" ", "")
        return sum(compact.count(ch) for ch in "、,，;；")

    def _guess_ingredient_block(self):
        """没有识别到「配料」字样时，按分隔符密度推测配料段落。"""
        candidates = []
        for index, (line, score) in enumerate(self.lines):
            compact = line.replace(" ", "")
            if self._looks_like_nutrient_line(compact):
                continue
            separators = self._separator_score(compact)
            if separators >= 3 and len(compact) >= 12:
                candidates.append((separators, len(compact), index, line, score))
        if not candidates:
            return "", [], None
        candidates.sort(key=lambda item: (-item[0], -item[1]))
        separators, length, index, line, score = candidates[0]
        parts = [line.strip()]
        used = [index]
        for cursor in range(index + 1, min(index + 4, len(self.lines))):
            next_line = self.lines[cursor][0]
            if any(next_line.startswith(word) for word in _STOP_INGREDIENT):
                break
            if self._looks_like_nutrient_line(next_line):
                break
            if self._separator_score(next_line) >= 1 and len(next_line.strip()) >= 6:
                parts.append(next_line.strip())
                used.append(cursor)
            else:
                break
        return (
            "\n".join(parts),
            used,
            "未识别到「配料」字样，已按分隔符密度推测该段为配料表，请人工核对",
        )

    def _guess_nutrition_block(self):
        """没有识别到「营养成分表」标题时，按营养素关键词推测表格段落。"""
        core_words = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠")
        start_index = -1
        for index, (line, _score) in enumerate(self.lines):
            compact = line.replace(" ", "")
            hits = sum(1 for word in core_words if word in compact)
            # 以营养素名开头（「能量」「 -饱和脂肪酸」等）即可作为表格起点
            if _NUTRIENT_START_RE.match(compact) or hits >= 2 or (hits == 1 and re.search(r"\d", compact)):
                start_index = index
                break
        if start_index < 0:
            return "", [], None
        parts = [self.lines[start_index][0].strip()]
        used = [start_index]
        for cursor in range(start_index + 1, min(start_index + 30, len(self.lines))):
            line = self.lines[cursor][0]
            if any(line.startswith(word) for word in ("配料", "生产日期", "保质期", "贮存", "生产者", "致敏")):
                break
            parts.append(line.strip())
            used.append(cursor)
        text = "\n".join(parts)
        if sum(1 for word in core_words if word in text) < 2:
            return "", [], None
        return text, used, "未识别到「营养成分表」标题，已按营养素关键词推测表格范围，请人工核对"

    def _ingredients(self):
        text, used = extract_section(
            self.text,
            r"配\s*[料枓科](?:\s*表)?\s*[:：]?",
            stop_keywords=_STOP_INGREDIENT,
            max_lines=16,
        )
        note = None
        if not text:
            # 关键词可能被识别坏（如「配科」「配枓」），或干脆没有标题
            text, used = extract_section(
                self.text,
                r"(?:原料|原材料|配方|成分)\s*[:：]?",
                stop_keywords=_STOP_INGREDIENT,
                max_lines=16,
            )
        if not text:
            text, used, note = self._guess_ingredient_block()
        if not text:
            return "", 0.0, used, None
        # 去掉紧邻的「原料：」重复前缀
        text = re.sub(r"^(?:原料|原材料|配方|成分)\s*[:：]?", "", text).strip()
        text = self._clean_ingredient_text(text)
        if not text:
            return "", 0.0, used, None
        if len(text) < 4 and not note:
            note = "配料段落过短，可能识别不完整"
        return text, self._score_range(used), used, note

    def _nutrition(self):
        text, used = extract_section(
            self.text,
            r"营养成分表|营养成分|營養成分|营养成份|nutrition",
            stop_keywords=_STOP_NUTRITION,
            max_lines=44,
        )
        note = None
        if not text:
            text, used, note = self._guess_nutrition_block()
        if not text:
            return "", 0.0, used, None
        text = self._clean_nutrition_text(text)
        if not text:
            return "", 0.0, used, None
        if not re.search(r"\d", text) and not note:
            note = "营养成分段落中未找到任何数值"
        return text, self._score_range(used), used, note

    # ---------- 双列排版分离：只留属于本段落的行 ----------
    def _clean_ingredient_text(self, text: str) -> str:
        """配料段落里剔除营养成分表的行（两列并排时常见串行）。"""
        cleaned: list[str] = []
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if any(word in line for word in _STOP_INGREDIENT_TEXT):
                break
            compact = line.replace(" ", "")
            if len(compact) <= 1:
                continue
            # 营养素名称行 / 纯数值行 / 表头行：不属于配料
            if _is_nutrition_line(line) and not re.search(r"[、,，;；]", compact):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    def _clean_nutrition_text(self, text: str) -> str:
        """营养成分段落里只保留营养素行，并还原成「名称 数值 NRV%」的表格行。"""
        kept: list[str] = []
        header_kept = False
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            compact = line.replace(" ", "")
            if _looks_like_ingredient_fragment(line):
                continue
            if _NUTRITION_HEADER_RE.match(compact):
                # 只保留能说明计量基准的第一行（每100g / 每份），并规范成简短写法
                if not header_kept and re.search(r"每\s*(100|份|袋|包|支)", compact):
                    basis = re.search(r"每\s*100\s*(g|克|ml|毫升)", compact, re.I)
                    if basis:
                        unit = basis.group(1).lower()
                        kept.append("每100mL" if unit in ("ml", "毫升") else "每100g")
                    else:
                        serving = re.search(r"每\s*(份|袋|包|支)", compact)
                        kept.append(f"每{serving.group(1)}" if serving else line)
                    header_kept = True
                continue
            if not _is_nutrition_line(line):
                continue
            kept.append(line)
        if not any(re.search(r"\d", line) for line in kept):
            return ""
        return "\n".join(_merge_nutrition_rows(kept)).strip()

    def _date(self, pattern: str):
        value, score, _ = self._capture(pattern, stop=_STOP_GENERAL, max_len=24)
        if not value:
            return "", 0.0, None
        normalized = _norm_date(value)
        note = None
        if parse_cn_date(normalized) is None:
            note = "日期无法解析为标准年-月-日格式，请人工校正"
        return normalized, score, note

    def _shelf_life(self):
        value, score, _ = self._capture(
            r"(?:保质期|保质期限|保质期至|保质至)\s*[:：]?\s*" + _SHELF_VALUE, stop=_STOP_GENERAL, max_len=24
        )
        if value:
            return value.replace(" ", ""), score, None
        return "", 0.0, None

    def _expiry_date(self):
        value, score, _ = self._capture(
            r"(?:保质期至|保质至|到期日期|有效期至|此日期前食用最佳|bestbefore)\s*[:：]?\s*" + _DATE_VALUE,
            stop=_STOP_GENERAL,
            max_len=24,
        )
        if not value:
            return "", 0.0, None
        return _norm_date(value), score, None

    def _net_content(self):
        value, score, _ = self._capture(_NET_PATTERN + _NET_VALUE, stop=_STOP_GENERAL, max_len=24)
        if not value:
            value, score, _ = self._capture(_NET_PATTERN, stop=_STOP_GENERAL, max_len=24)
        if not value:
            return "", 0.0, None
        value = value.replace(" ", "")
        note = None
        if not re.search(r"(kg|g|ml|mL|L|克|千克|毫升|升)$", value):
            note = "净含量缺少可识别的单位"
        return value, score, note

    def _storage(self):
        value, score, _ = self._capture(
            _STORAGE_PATTERN, stop=["生产日期", "保质期", "生产者", "地址", "电话", "产品标准", "致敏", "配料"], max_len=70
        )
        if value and value in {"条件", "说明"}:
            return "", score, None
        return value, score, None

    def _producer(self):
        value, score, _ = self._capture(
            _PRODUCER_PATTERN, stop=["地址", "电话", "服务热线", "生产日期", "保质期", "产品标准", "致敏", "净含量"], max_len=70
        )
        return value, score, None

    def _standard_no(self):
        value, score, _ = self._capture(_STANDARD_PATTERN, stop=["生产日期", "保质期", "地址", "电话", "配料"], max_len=40)
        if not value:
            return "", 0.0, None
        match = re.search(r"([A-Z]{1,4}\s*/?\s*[A-Z]{0,3}\s*[\d][\d.\-—]{1,18})", value.upper())
        note = None
        if not match:
            note = "标准号格式不符合常见写法，请人工确认"
            return value, round(score * 0.7, 3), note
        cleaned = re.sub(r"\s+", "", match.group(1)).replace("—", "-")
        if not re.match(r"^(GB|GB/T|GB/Z|Q/|SB/T|NY/T|NY|DB\d|T/|JJF|ISO)", cleaned.upper()):
            note = "标准号前缀不是常见标准代号，请人工确认"
        return cleaned, score, note

    def _allergen(self):
        value, score, _ = self._capture(
            _ALLERGEN_PATTERN, stop=["生产日期", "保质期", "贮存", "储存", "生产者", "地址", "电话", "产品标准"], max_len=90
        )
        return value, score, None

    # ---------- 汇总 ----------
    def parse(self) -> dict:
        fields: dict[str, str] = {}
        confidence: dict[str, float] = {}
        flags: dict[str, dict] = {}
        missing: list[str] = []
        low: list[str] = []

        food_name, name_score, name_note = self._food_name()
        fields["food_name"] = food_name
        confidence["food_name"] = name_score
        flags["food_name"] = {"status": "inferred" if name_note else "ok", "note": name_note}

        ingredients, ing_score, ing_used, ing_note = self._ingredients()
        fields["ingredients_text"] = ingredients
        confidence["ingredients_text"] = ing_score
        flags["ingredients_text"] = {"status": "low" if ing_note else "ok", "note": ing_note, "lines": ing_used}

        nutrition, nut_score, nut_used, nut_note = self._nutrition()
        fields["nutrition_text"] = nutrition
        confidence["nutrition_text"] = nut_score
        flags["nutrition_text"] = {"status": "low" if nut_note else "ok", "note": nut_note, "lines": nut_used}

        net, net_score, net_note = self._net_content()
        fields["net_content"] = net
        confidence["net_content"] = net_score
        flags["net_content"] = {"status": "format_suspect" if net_note else "ok", "note": net_note}

        prod, prod_score, prod_note = self._date(
            r"(?:生产日期|制造日期|生产日|灌装日期|包装日期)\s*[:：]?\s*" + _DATE_VALUE
        )
        fields["production_date"] = prod
        confidence["production_date"] = prod_score
        flags["production_date"] = {"status": "format_suspect" if prod_note else "ok", "note": prod_note}

        shelf, shelf_score, shelf_note = self._shelf_life()
        fields["shelf_life"] = shelf
        confidence["shelf_life"] = shelf_score
        flags["shelf_life"] = {"status": "low" if shelf_note else "ok", "note": shelf_note}

        expiry, exp_score, exp_note = self._expiry_date()
        fields["expiry_date"] = expiry
        confidence["expiry_date"] = exp_score
        flags["expiry_date"] = {"status": "format_suspect" if exp_note else "ok", "note": exp_note}

        storage, st_score, st_note = self._storage()
        fields["storage"] = storage
        confidence["storage"] = st_score
        flags["storage"] = {"status": "low" if st_note else "ok", "note": st_note}

        producer, pr_score, pr_note = self._producer()
        fields["producer"] = producer
        confidence["producer"] = pr_score
        flags["producer"] = {"status": "low" if pr_note else "ok", "note": pr_note}

        standard, sd_score, sd_note = self._standard_no()
        fields["standard_no"] = standard
        confidence["standard_no"] = sd_score
        flags["standard_no"] = {"status": "format_suspect" if sd_note else "ok", "note": sd_note}

        allergen, al_score, al_note = self._allergen()
        fields["allergen"] = allergen
        confidence["allergen"] = al_score
        flags["allergen"] = {"status": "low" if al_note else "ok", "note": al_note}

        for key in FIELD_ORDER:
            value = fields.get(key, "")
            conf = confidence.get(key, 0.0)
            if not str(value).strip():
                missing.append(key)
                flags[key] = {"status": "missing", "note": (flags.get(key) or {}).get("note")}
                confidence[key] = 0.0
            elif conf < LOW_CONFIDENCE_THRESHOLD:
                low.append(key)
                flags.setdefault(key, {"status": "ok", "note": None})
                if flags[key].get("status") in {"ok", None}:
                    flags[key]["status"] = "low"
        return {
            "fields": fields,
            "confidence": confidence,
            "flags": flags,
            "missing": missing,
            "low_confidence": low,
        }


def parse_fields(lines: list[tuple[str, float]]) -> dict:
    return FieldParser(lines).parse()


def merge_provider_fields(parsed: dict, provider_fields: dict | None) -> dict:
    """把视觉模型直接返回的结构化字段合并进解析结果。

    视觉模型往往能直接给出字段值（而不只是文字行），优先采用其结构化结果，
    但仍保留每条字段的置信度与标记，便于用户核对。
    """
    if not provider_fields:
        return parsed
    fields = parsed.setdefault("fields", {})
    confidence = parsed.setdefault("confidence", {})
    flags = parsed.setdefault("flags", {})
    missing = parsed.setdefault("missing", [])
    low = parsed.setdefault("low_confidence", [])
    for key, raw_value in provider_fields.items():
        if key not in fields:
            continue
        value = str(raw_value or "").strip()
        if not value:
            continue
        fields[key] = value
        confidence[key] = max(float(confidence.get(key) or 0), 0.9)
        flags[key] = {"status": "ok", "note": "视觉模型结构化输出"}
        if key in missing:
            missing.remove(key)
        if key in low:
            low.remove(key)
    return parsed


def build_corrected_text(fields: dict[str, str]) -> str:
    """把校正后的字段拼成人类可读的标签全文（供入库与报告展示）。"""
    labels = {
        "food_name": "食品名称",
        "net_content": "净含量",
        "ingredients_text": "配料表",
        "nutrition_text": "营养成分表",
        "production_date": "生产日期",
        "shelf_life": "保质期",
        "expiry_date": "到期日期",
        "storage": "贮存条件",
        "producer": "生产者",
        "standard_no": "产品标准号",
        "allergen": "致敏物质提示",
    }
    parts = []
    for key, label in labels.items():
        value = (fields.get(key) or "").strip()
        if value:
            parts.append(f"{label}：{value}")
    return "\n".join(parts)


__all__ = [
    "FIELD_ORDER",
    "FieldParser",
    "parse_fields",
    "merge_provider_fields",
    "build_corrected_text",
    "LOW_CONFIDENCE_THRESHOLD",
]
