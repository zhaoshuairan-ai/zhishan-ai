"""文本归一化与关键词截取工具（供字段解析、配料解析、营养解析共用）。"""
from __future__ import annotations

import re
import unicodedata

# 配料/营养段落结束的标志性关键词（出现即认为进入下一个字段）
SECTION_STOP = [
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
    "委托方",
    "地址",
    "电话",
    "服务热线",
    "产品标准",
    "执行标准",
    "标准号",
    "致敏",
    "过敏",
    "温馨提示",
    "食用方法",
    "注意事项",
    "规格",
    "净重",
]

DATE_LIKE = re.compile(r"(19|20)\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}")


def normalize(text: str) -> str:
    """全角转半角、统一换行、压缩多余空白（保留换行）。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def compact(text: str) -> str:
    """去除所有空白，用于「跨行/无空格」的关键词匹配。"""
    return re.sub(r"\s+", "", normalize(text))


def split_lines(text: str) -> list[str]:
    return [line for line in normalize(text).split("\n") if line]


def capture_after(
    text: str,
    keyword_pattern: str,
    *,
    stop_keywords: list[str] | None = None,
    max_len: int = 80,
) -> tuple[str, int]:
    """在文本中定位关键词，返回其后的内容与关键词所在行号（0 起）。

    优先使用正则的第 1 个捕获组作为取值（例如「生产日期：(2025-09-12)」），
    没有捕获组或捕获组为空时，才把关键词后面的剩余文本作为取值。
    这样既能处理「关键词:值」同行的写法，也支持值被 OCR 折到下一行的情况。
    截断规则：遇到换行或下一个字段关键词即停止，避免把相邻字段吞进来。
    """
    lines = split_lines(text)
    pattern = re.compile(keyword_pattern, re.I)
    stops = stop_keywords if stop_keywords is not None else SECTION_STOP
    for idx, line in enumerate(lines):
        match = pattern.search(line)
        if not match:
            continue
        if pattern.groups:
            captured = (match.group(1) or "").strip()
            if captured:
                return captured[:max_len], idx
        remainder = line[match.end():]
        remainder = re.sub(r"^[\s:：\-—]+", "", remainder)
        # 同一行后面的字段关键词
        for stop in stops:
            pos = remainder.find(stop)
            if pos > 0:
                remainder = remainder[:pos]
        remainder = remainder.strip(" ，,;；、")
        if remainder:
            return remainder[:max_len], idx
        # 值可能被 OCR 折到下一行
        if idx + 1 < len(lines):
            nxt = lines[idx + 1].strip()
            if nxt and not any(nxt.startswith(stop) for stop in SECTION_STOP):
                return nxt[:max_len], idx + 1
        return "", idx
    return "", -1


def extract_section(
    text: str,
    start_pattern: str,
    *,
    stop_keywords: list[str] | None = None,
    max_lines: int = 14,
) -> tuple[str, list[int]]:
    """抽取一个段落（如配料表、营养成分表），返回段落文本与行号列表。"""
    lines = split_lines(text)
    stops = stop_keywords if stop_keywords is not None else SECTION_STOP
    pattern = re.compile(start_pattern, re.I)
    for idx, line in enumerate(lines):
        match = pattern.search(line)
        if not match:
            continue
        collected: list[str] = []
        used: list[int] = [idx]
        remainder = line[match.end():]
        remainder = re.sub(r"^[\s:：\-—]+", "", remainder)
        remainder = re.sub(r"^\d{1,2}\s*[%％]\s*", "", remainder)
        if remainder.strip():
            collected.append(remainder.strip())
        for j in range(idx + 1, min(idx + 1 + max_lines, len(lines))):
            nxt = lines[j]
            if any(nxt.startswith(stop) for stop in stops) or DATE_LIKE.match(nxt):
                break
            collected.append(nxt)
            used.append(j)
        return "\n".join(collected).strip(), used
    return "", []


def is_probably_text(value: str, *, min_len: int = 2) -> bool:
    clean = re.sub(r"[\s:：\-—*※]", "", value or "")
    return len(clean) >= min_len
