"""一次性清理演示历史，换成更接近真实产品的两条示例记录。

运行：backend/.venv/Scripts/python.exe scripts/replace_history_samples.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AnalysisRecord, User  # noqa: E402
from app.seed.demo_data import _cracker_lines, _create_demo_record, _soda_lines  # noqa: E402
from app.services import storage  # noqa: E402


def main() -> None:
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username="demo").first()
        if user is None:
            print("demo 用户不存在")
            return
        removed = []
        for record in AnalysisRecord.query.filter_by(user_id=user.id).all():
            if record.is_demo or "演示" in (record.food_name or ""):
                removed.append(record)
        stored = [record.image.stored_name for record in removed if record.image]
        for record in removed:
            db.session.delete(record)
        db.session.commit()
        for name in stored:
            try:
                storage.delete_image(name)
            except Exception:
                pass

        samples = [
            (
                "元气森林 白桃味苏打气泡水",
                _soda_lines(),
                "示例记录：用常见苏打气泡水标签演示营养解读与标签核查。",
            ),
            (
                "奥利奥 巧克力夹心饼干",
                _cracker_lines(),
                "示例记录：用常见夹心饼干标签演示配料解读与营养分析。",
            ),
        ]
        created = 0
        for title, lines, note in samples:
            record = _create_demo_record(user, title=title, lines=lines, note=note)
            record.is_demo = False
            record.data_source = "real"
            record.note = note
            record.ocr_provider = None
            if record.ocr:
                record.ocr.is_demo = False
                record.ocr.provider = "sample"
                record.ocr.provider_label = "内置示例标签"
                record.ocr.warning = ""
                record.ocr.raw_payload = {**(record.ocr.raw_payload or {}), "sample": True}
            if record.image:
                db.session.delete(record.image)
                record.image = None
            created += 1
        db.session.commit()
        print(f"removed={len(removed)} created={created}")


if __name__ == "__main__":
    main()
