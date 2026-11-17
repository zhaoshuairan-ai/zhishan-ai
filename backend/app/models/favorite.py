"""用户收藏食谱。"""
from __future__ import annotations

from sqlalchemy import UniqueConstraint

from ..extensions import db
from .user import utcnow


class UserFavoriteRecipe(db.Model):
    __tablename__ = "user_favorite_recipes"
    __table_args__ = (
        UniqueConstraint("user_id", "recipe_name", name="uq_favorite_user_recipe"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipe_name = db.Column(db.String(120), nullable=False)
    recipe_data = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "recipe_name": self.recipe_name,
            "recipe_data": self.recipe_data or {},
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
