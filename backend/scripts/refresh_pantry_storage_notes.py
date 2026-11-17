"""把库存中旧的“预计送达/保质期估算”备注，刷新为简短来源 + AI 科学存储建议。

运行：backend/.venv/Scripts/python.exe scripts/refresh_pantry_storage_notes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import PantryItem  # noqa: E402
from app.services import storage_advice_service  # noqa: E402


def main() -> None:
    app = create_app()
    with app.app_context():
        items = [
            item for item in PantryItem.query.all()
            if item.note and any(word in item.note for word in ("同城急送", "常规发货", "预计", "保质期 AI 估算"))
        ]
        if not items:
            print("没有需要刷新的旧备注")
            return
        advice = storage_advice_service.generate(
            [{"name": item.name, "category": item.category} for item in items]
        )
        changed = 0
        for item in items:
            text = advice.get(item.name) or storage_advice_service.fallback_advice(item.name, item.category)
            source = "常规发货（已送达）" if item.category in {"staple", "condiment"} else "同城急送（已送达）"
            item.note = f"{source}；AI科学存储建议：{text}"
            changed += 1
        db.session.commit()
        print(f"updated={changed}")


if __name__ == "__main__":
    main()
