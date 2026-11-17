"""Import the existing static dish nutrition library into knowledge_entries.

This is additive only: it never deletes existing rows. Existing titles are
updated to published + verified and their nutrition fields are refreshed.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import KnowledgeEntry  # noqa: E402
from app.models.user import utcnow  # noqa: E402
from app.services import dish_library  # noqa: E402


def main() -> None:
    app = create_app()
    with app.app_context():
        dishes = dish_library.load_all()
        created = 0
        updated = 0

        for index, dish in enumerate(dishes, start=1):
            title = str(dish.get("dish_name") or "").strip()
            if not title:
                continue

            entry = KnowledgeEntry.query.filter_by(title=title).first()
            summary = str(dish.get("health_tip") or "").strip()
            if not summary:
                summary = (
                    f"{title}每 100g 约 {float(dish['calories_per_100g']):.0f} kcal，"
                    "营养数据按常见做法估算，实际数值会随用油与份量变化。"
                )
            content = (
                f"{title}属于{dish.get('category') or '常见菜品'}。"
                f"按每 100g 估算，能量约 {float(dish['calories_per_100g']):.0f} kcal，"
                f"蛋白质 {float(dish['protein_per_100g']):.1f} g，"
                f"脂肪 {float(dish['fat_per_100g']):.1f} g，"
                f"碳水化合物 {float(dish['carbs_per_100g']):.1f} g。"
                "数据用于饮食规划参考，不替代实验室检测或医疗建议。"
            )

            if entry is None:
                slug_suffix = dish.get("slug") or f"{index:03d}"
                entry = KnowledgeEntry(
                    slug=f"dish-library-{slug_suffix}",
                    title=title,
                    category="dish",
                    summary=summary,
                    content=content,
                    source_name=dish.get("source") or dish_library.DISH_SOURCE,
                    source_url="",
                    source_type="editorial",
                    aliases=",".join(str(x) for x in (dish.get("aliases") or [])),
                    keywords="",
                    verification_status="verified",
                    status="published",
                    scope="常见菜品营养参考",
                    version="1.0",
                    published_at=utcnow(),
                    created_by="菜品营养库导入",
                    updated_by="菜品营养库导入",
                    is_featured=False,
                    sort_order=200 + index,
                )
                db.session.add(entry)
                created += 1
            else:
                entry.category = "dish"
                entry.summary = summary
                entry.content = content
                entry.source_name = dish.get("source") or dish_library.DISH_SOURCE
                entry.verification_status = "verified"
                entry.status = "published"
                entry.published_at = entry.published_at or utcnow()
                entry.updated_by = "菜品营养库导入"
                updated += 1

            entry.calories_per_100g = float(dish["calories_per_100g"])
            entry.protein_per_100g = float(dish["protein_per_100g"])
            entry.fat_per_100g = float(dish["fat_per_100g"])
            entry.carbs_per_100g = float(dish["carbs_per_100g"])
            entry.typical_portion_g = int(dish["typical_portion_g"])

        db.session.commit()
        total = KnowledgeEntry.query.count()
        print(f"dish_library={len(dishes)} created={created} updated={updated} total={total}")


if __name__ == "__main__":
    main()
