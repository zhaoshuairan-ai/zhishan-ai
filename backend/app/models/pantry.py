"""家庭食材管家：库存、健康画像与食谱规划记录。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .user import utcnow

PANTRY_CATEGORIES = {
    "vegetable": "蔬菜",
    "fruit": "水果",
    "meat": "肉禽",
    "seafood": "水产",
    "egg_dairy": "蛋奶",
    "staple": "主食",
    "bean": "豆制品",
    "condiment": "调味料",
    "other": "其他",
}

HEALTH_CONDITIONS = {
    "hypertension": "高血压",
    "diabetes": "糖尿病",
    "hyperlipidemia": "高血脂",
    "gout": "痛风/高尿酸",
    "kidney": "肾功能不全",
    "pregnancy": "孕期",
    "lactation": "哺乳期",
    "vegetarian": "素食",
    "gastritis": "胃炎/胃病",
}

HEALTH_GOALS = {
    "weight_loss": "减脂",
    "low_sodium": "控盐",
    "low_sugar": "控糖",
    "high_protein": "高蛋白",
    "balanced": "均衡饮食",
}


def _days_left(expires_at: date | None) -> int | None:
    if not expires_at:
        return None
    return (expires_at - date.today()).days


class PantryItem(db.Model):
    __tablename__ = "pantry_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="other", index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="份")
    purchased_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def status(self) -> tuple[str, str]:
        days = _days_left(self.expires_at)
        if days is None:
            return "no_expiry", "未设置保质期"
        if days < 0:
            return "expired", f"已过期 {abs(days)} 天"
        if days == 0:
            return "expiring", "今天到期"
        if days <= 3:
            return "expiring", f"还有 {days} 天到期"
        return "fresh", f"还有 {days} 天"

    def to_public(self) -> dict:
        status, status_text = self.status()
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "category_label": PANTRY_CATEGORIES.get(self.category, self.category),
            "quantity": self.quantity,
            "unit": self.unit,
            "purchased_at": self.purchased_at.isoformat() if self.purchased_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "days_left": _days_left(self.expires_at),
            "status": status,
            "status_text": status_text,
            "note": self.note,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class CookLog(db.Model):
    """一次“已完成”的做菜记录，用于幂等扣减库存。"""

    __tablename__ = "cook_logs"
    __table_args__ = (UniqueConstraint("plan_id", "meal_index", name="uq_cook_plan_meal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("recipe_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    meal_index: Mapped[int] = mapped_column(nullable=False, default=0)
    recipe_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    consumed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "meal_index": self.meal_index,
            "recipe_name": self.recipe_name,
            "consumed": self.consumed or [],
            "missing": self.missing or [],
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class BarcodeCache(db.Model):
    """商业条码库查询缓存：同一 GTIN 不重复扣费。"""

    __tablename__ = "barcode_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    spec: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    manufacturer: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="other")
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="showapi")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def to_public(self) -> dict:
        data = dict(self.payload or {})
        data.update(
            {
                "found": True,
                "barcode": self.barcode,
                "name": self.name,
                "brand": self.brand,
                "spec": self.spec,
                "manufacturer": self.manufacturer,
                "category": self.category,
                "source": self.source,
                "cached": True,
            }
        )
        return data


class HealthProfile(db.Model):
    __tablename__ = "health_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    goals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    allergies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def to_public(self) -> dict:
        return {
            "conditions": self.conditions or [],
            "condition_labels": [HEALTH_CONDITIONS.get(item, item) for item in (self.conditions or [])],
            "goals": self.goals or [],
            "goal_labels": [HEALTH_GOALS.get(item, item) for item in (self.goals or [])],
            "allergies": self.allergies or [],
            "notes": self.notes,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }


class RecipePlan(db.Model):
    __tablename__ = "recipe_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="rule")
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "mode": self.mode,
            "model": self.model,
            "request": self.request or {},
            "result": self.result or {},
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
