"""修复历史记录中「食品名称」与 OCR 原文不一致的数据。

只做名称同步，不修改营养成分、配料或核查逻辑。
运行：backend/.venv/Scripts/python.exe scripts/sync_ocr_food_names.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm.attributes import flag_modified

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AnalysisRecord  # noqa: E402


def _variants(name: str) -> list[str]:
    values = {name}
    cleaned = re.sub(r"[（(]演示[^）)]*[）)]", "", name).strip()
    values.add(cleaned)
    values.add(cleaned.replace("(", "（").replace(")", "）"))
    return [value for value in values if value]


def main() -> None:
    app = create_app()
    with app.app_context():
        changed = 0
        for record in AnalysisRecord.query.all():
            if record.ocr is None:
                continue
            fields = dict(record.ocr.fields or {})
            old_name = str(fields.get("food_name") or "").strip()
            new_name = str(record.food_name or "").strip()
            if not old_name or not new_name or old_name == new_name:
                continue
            for variant in _variants(old_name):
                record.ocr.raw_text = (record.ocr.raw_text or "").replace(variant, new_name)
                record.ocr.corrected_text = (record.ocr.corrected_text or "").replace(variant, new_name)
            fields["food_name"] = new_name
            record.ocr.fields = fields
            flag_modified(record.ocr, "fields")
            changed += 1
        db.session.commit()
        print(f"synced={changed}")


if __name__ == "__main__":
    main()
