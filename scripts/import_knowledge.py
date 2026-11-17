"""导入外部知识条目（JSON / CSV），用于把权威资料批量接进知识库。

适用场景：拿到 GB 2760 添加剂名录、辟谣平台导出、机构科普清单等结构化数据后，
转换成约定字段即可批量导入；已存在的 slug 会被更新（幂等），不会产生重复条目。

用法：
    python scripts/import_knowledge.py docs/knowledge-import-template.json --dry-run
    python scripts/import_knowledge.py data/additives.json
    python scripts/import_knowledge.py data/additives.csv --csv

字段（JSON 数组 / CSV 表头）：
    slug*        唯一标识，小写字母数字与短横线，如 sodium-benzoate
    title*       条目标题
    category*    additive / ingredient / nutrition / label_rule / safety
    summary*     一句话概述
    content      详细说明
    aliases      逗号分隔的别名
    keywords     空格分隔的检索关键词
    usage_note   一句话使用提示
    source_name* 来源名称
    source_url   来源链接
    source_type  standard_name / textbook / public_health / official_website / editorial
    verification_status  verified / pending（默认 pending）
    version      版本号（默认 1.0）
    is_featured  true/false
    sort_order   排序数字

注意：脚本不会替你「核实」内容。导入前请确认资料本身可公开引用，
并以 verification_status 如实标注是否逐条核对过原文。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from app.models.knowledge import CATEGORIES, SOURCE_TYPES, VERIFICATION  # noqa: E402
from app.services import knowledge_service  # noqa: E402

REQUIRED = ("slug", "title", "category", "summary", "source_name")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")

BOOL_TRUE = {"1", "true", "yes", "y", "是"}


def _normalize_row(row: dict, index: int) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    data = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
    for key in REQUIRED:
        if not data.get(key):
            errors.append(f"第 {index} 行缺少必填字段 {key}")
    if errors:
        return None, errors
    if not SLUG_RE.match(str(data["slug"])):
        errors.append(f"第 {index} 行 slug 不合法：{data['slug']}（小写字母/数字/短横线）")
    if data["category"] not in CATEGORIES:
        errors.append(f"第 {index} 行 category 不合法：{data['category']}（可选：{'、'.join(CATEGORIES)}）")
    source_type = data.get("source_type") or "editorial"
    if source_type not in SOURCE_TYPES:
        errors.append(f"第 {index} 行 source_type 不合法：{source_type}")
    status = data.get("verification_status") or "pending"
    if status not in VERIFICATION:
        errors.append(f"第 {index} 行 verification_status 不合法：{status}")
    if errors:
        return None, errors

    entry = {
        "slug": str(data["slug"]).lower(),
        "title": data["title"],
        "category": data["category"],
        "summary": data["summary"],
        "content": data.get("content") or "",
        "aliases": data.get("aliases") or "",
        "keywords": data.get("keywords") or "",
        "usage_note": data.get("usage_note") or "",
        "source_name": data["source_name"],
        "source_url": data.get("source_url") or None,
        "source_type": source_type,
        "verification_status": status,
        "version": str(data.get("version") or "1.0"),
        "is_featured": str(data.get("is_featured", "")).lower() in BOOL_TRUE,
        "sort_order": int(data["sort_order"]) if str(data.get("sort_order", "")).isdigit() else 900,
    }
    return entry, []


def load_rows(path: Path, as_csv: bool) -> tuple[list[dict], list[str]]:
    if as_csv or path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return rows, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"JSON 解析失败：{exc}"]
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        payload = payload["entries"]
    if not isinstance(payload, list):
        return [], ["JSON 顶层必须是数组（或包含 entries 数组的对象）"]
    return [row for row in payload if isinstance(row, dict)], []


def main() -> int:
    parser = argparse.ArgumentParser(description="把外部知识条目导入本站知识库")
    parser.add_argument("file", help="JSON 或 CSV 文件路径")
    parser.add_argument("--csv", action="store_true", help="强制按 CSV 解析")
    parser.add_argument("--dry-run", action="store_true", help="只校验，不写数据库")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"[错误] 文件不存在：{path}")
        return 2

    rows, errors = load_rows(path, args.csv)
    if errors:
        for item in errors:
            print("[错误]", item)
        return 2

    entries: list[dict] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        entry, row_errors = _normalize_row(row, index)
        if row_errors:
            errors.extend(row_errors)
            continue
        assert entry is not None
        if entry["slug"] in seen:
            errors.append(f"第 {index} 行 slug 重复：{entry['slug']}")
            continue
        seen.add(entry["slug"])
        entries.append(entry)

    print(f"读取 {len(rows)} 行，通过校验 {len(entries)} 条，问题 {len(errors)} 条")
    for item in errors:
        print("[校验失败]", item)
    if errors:
        return 2
    if args.dry_run:
        print("dry-run：未写入数据库。")
        return 0

    app = create_app()
    with app.app_context():
        result = knowledge_service.upsert_seed(entries)
    print(
        f"导入完成：新增 {result['created']} 条，更新 {result['updated']} 条，"
        f"知识库现有 {result['total']} 条。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
