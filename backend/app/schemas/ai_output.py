"""大模型输出的 JSON 校验模型（Pydantic v2）。

模型返回的内容一律先经过这里的校验，不合规的字段会被丢弃或标记，
避免把幻觉内容直接写进数据库。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

CONFIDENCE = Literal["high", "medium", "low"]
EVIDENCE = Literal["knowledge_base", "general_knowledge", "unverified"]


class CitationModel(BaseModel):
    knowledge_id: int | None = None
    title: str = Field(default="", max_length=120)
    source_name: str = Field(default="", max_length=200)
    claim: str = Field(default="", max_length=300)


class FavoriteTagModel(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    value: str = Field(default="", max_length=40)
    status: Literal["high", "medium", "low", "good", "neutral"] = "neutral"
    label: str = Field(default="", max_length=20)


class IngredientExplainModel(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    category: str = Field(default="未分类", max_length=40)
    role: str = Field(default="", max_length=40)
    purpose: str = Field(default="", max_length=300)
    simple_desc: str = Field(default="", max_length=120)
    explanation: str = Field(default="", max_length=500)
    confidence: CONFIDENCE = "low"
    evidence: EVIDENCE = "unverified"
    is_ai_generated: bool = False
    source_refs: list[str] = Field(default_factory=list, max_length=5)
    caution: str | None = Field(default=None, max_length=300)

    @field_validator("purpose", "simple_desc", "explanation", "role", mode="before")
    @classmethod
    def _stringify(cls, value):
        return "" if value is None else str(value).strip()


class PersonalizationModel(BaseModel):
    level: Literal["danger", "warning", "info", "none"] = "none"
    title: str = Field(default="", max_length=80)
    message: str = Field(default="", max_length=300)
    reasons: list[str] = Field(default_factory=list, max_length=5)


class IngredientAnalysisModel(BaseModel):
    summary: str = Field(default="", max_length=200)
    tags: list[FavoriteTagModel] = Field(default_factory=list, max_length=3)
    personalization: PersonalizationModel | None = None
    ingredients: list[IngredientExplainModel] = Field(default_factory=list)
    nutrition_notes: list[str] = Field(default_factory=list)
    unknown_items: list[str] = Field(default_factory=list)
    unconfirmed: list[str] = Field(default_factory=list)
    citations: list[CitationModel] = Field(default_factory=list)
    safety_note: str = Field(default="", max_length=600)

    @field_validator("nutrition_notes", mode="before")
    @classmethod
    def _clean_notes(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()[:200]] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip()[:200] for item in value if str(item).strip()][:6]
        return []

    @field_validator("unknown_items", "unconfirmed", mode="before")
    @classmethod
    def _clean_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(v).strip()[:80] for v in value if str(v).strip()][:20]
        return []


class OcrFieldModel(BaseModel):
    food_name: str = ""
    ingredients_text: str = ""
    nutrition_text: str = ""
    net_content: str = ""
    production_date: str = ""
    shelf_life: str = ""
    expiry_date: str = ""
    storage: str = ""
    producer: str = ""
    standard_no: str = ""
    allergen: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _to_str(cls, value):
        return "" if value is None else str(value).strip()


AI_OUTPUT_JSON_SCHEMA = IngredientAnalysisModel.model_json_schema()


__all__ = [
    "IngredientAnalysisModel",
    "IngredientExplainModel",
    "FavoriteTagModel",
    "PersonalizationModel",
    "CitationModel",
    "OcrFieldModel",
    "AI_OUTPUT_JSON_SCHEMA",
]
