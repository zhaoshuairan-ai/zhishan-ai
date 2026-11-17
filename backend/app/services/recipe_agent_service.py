"""食谱推荐 Agent：优先消耗临期食材，结合健康画像生成营养方案。

两种模式：
- ai：调用 OpenAI 兼容大模型，要求返回结构化 JSON，服务端再做过敏原/库存校验；
- rule：本地规则引擎（无 Key 或模型失败时自动降级），同样给出决策轨迹。

无论哪种模式，营养数值均为估算，不构成医学处方或治疗建议。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

import requests
from typing import Any

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError, field_validator

from flask import current_app
from sqlalchemy.orm.attributes import flag_modified

from ..extensions import db
from ..models import ChatMessage, ChatSession, CookLog, HealthProfile, PantryItem, RecipePlan
from ..utils.errors import NotFoundError, ValidationError
from . import household_service, ingredient_rules, pantry_service

MODEL_VERSION = "recipe-agent-1.0"
DISCLAIMER = (
    "食谱与营养数值由程序按常见食材估算，不是医学处方或营养师方案；"
    "高血压、糖尿病、肾病等慢性病人群请遵医嘱，过敏原请自行再次核对。"
)

EMPTY_INVENTORY_TRACE = "检测到当前库存为空，正根据用户口味偏好生成标准食谱。已为您自动生成全套采购清单。"
TEST_TRACE_MARKERS = ("追加助手菜谱", "已从收藏加入今日排期")


def _clean_agent_trace(trace: list, *, empty_inventory: bool) -> list[str]:
    lines = []
    for item in trace or []:
        text = str(item).strip()
        if not text or any(marker in text for marker in TEST_TRACE_MARKERS):
            continue
        if empty_inventory and any(word in text for word in ("消耗库存", "使用 0 项库存", "读取库存 0 项", "库存充足")):
            continue
        lines.append(text)
    if empty_inventory:
        lines = [line for line in lines if line != EMPTY_INVENTORY_TRACE]
        return [EMPTY_INVENTORY_TRACE, *lines]
    return lines


MEAL_TYPE_LABELS = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}

MEAL_TYPES = {
    2: ["午餐", "晚餐"],
    3: ["早餐", "午餐", "晚餐"],
    4: ["早餐", "午餐", "加餐", "晚餐"],
    5: ["早餐", "午餐", "加餐", "晚餐", "夜宵"],
    6: ["早餐", "上午加餐", "午餐", "下午加餐", "晚餐", "夜宵"],
}

# 每 100g 可食部分的粗略营养（用于估算，不用于标签判定）
NUTRITION = {
    "rice": {"energy": 116, "protein": 2.6, "fat": 0.3, "carbs": 25.9, "sodium": 2, "sugar": 0.1},
    "oats": {"energy": 380, "protein": 13.0, "fat": 6.5, "carbs": 66.0, "sodium": 4, "sugar": 1.0},
    "noodle": {"energy": 138, "protein": 4.5, "fat": 0.7, "carbs": 28.0, "sodium": 120, "sugar": 0.5},
    "egg": {"energy": 143, "protein": 13.0, "fat": 9.5, "carbs": 1.1, "sodium": 131, "sugar": 1.1},
    "chicken": {"energy": 133, "protein": 19.4, "fat": 5.0, "carbs": 0, "sodium": 63, "sugar": 0},
    "pork": {"energy": 395, "protein": 13.2, "fat": 37.0, "carbs": 0, "sodium": 56, "sugar": 0},
    "beef": {"energy": 125, "protein": 19.9, "fat": 4.2, "carbs": 0, "sodium": 84, "sugar": 0},
    "fish": {"energy": 100, "protein": 18.0, "fat": 3.0, "carbs": 0, "sodium": 60, "sugar": 0},
    "shrimp": {"energy": 93, "protein": 18.6, "fat": 0.8, "carbs": 2.8, "sodium": 165, "sugar": 0},
    "tofu": {"energy": 76, "protein": 8.1, "fat": 3.7, "carbs": 4.2, "sodium": 7, "sugar": 0.5},
    "vegetable": {"energy": 25, "protein": 1.5, "fat": 0.3, "carbs": 4.0, "sodium": 30, "sugar": 2.0},
    "fruit": {"energy": 52, "protein": 0.5, "fat": 0.2, "carbs": 13.0, "sodium": 2, "sugar": 10.0},
    "milk": {"energy": 54, "protein": 3.0, "fat": 3.2, "carbs": 3.4, "sodium": 37, "sugar": 3.4},
    "oil": {"energy": 899, "protein": 0, "fat": 99.9, "carbs": 0, "sodium": 0, "sugar": 0},
    "salt": {"energy": 0, "protein": 0, "fat": 0, "carbs": 0, "sodium": 39300, "sugar": 0},
}

PROTEIN_WORDS = ("鸡胸", "鸡腿", "鸡肉", "牛肉", "猪肉", "羊肉", "鱼", "虾", "蛋", "豆腐", "豆干", "瘦肉", "排骨")
STAPLE_WORDS = ("米", "面", "馒头", "燕麦", "红薯", "土豆", "玉米", "全麦", "粥", "粉")
VEG_WORDS = ("菜", "菠菜", "西兰花", "番茄", "西红柿", "黄瓜", "胡萝卜", "洋葱", "蘑菇", "菌", "青椒", "茄子", "豆角", "南瓜")
FRUIT_WORDS = ("苹果", "香蕉", "橙", "梨", "葡萄", "草莓", "蓝莓", "桃")
DAIRY_WORDS = ("牛奶", "酸奶", "奶酪")
ALLERGEN_INGREDIENT_TERMS = {
    "粗粮": (
        "燕麦", "即食燕麦片", "燕麦片", "糙米", "糙米饭", "小米", "小米粥",
        "玉米", "玉米面", "全麦", "杂粮", "荞麦", "大麦", "黑米", "紫米",
        "藜麦", "高粱", "八宝粥", "杂粮饭", "粗粮",
    ),
    "面粉": (
        "面粉", "小麦", "面条", "面包", "馒头", "包子", "饺子", "面筋",
        "饼干", "蛋糕", "吐司", "挂面", "意面", "面饼", "小麦粉",
    ),
    "小麦": (
        "面粉", "小麦", "面条", "面包", "馒头", "包子", "饺子", "面筋",
        "饼干", "蛋糕", "吐司", "挂面", "意面", "面饼", "小麦粉",
    ),
    "麸质": (
        "面粉", "小麦", "面条", "面包", "馒头", "包子", "饺子", "面筋",
        "饼干", "蛋糕", "吐司", "挂面", "意面", "面饼", "小麦粉",
    ),
    "牛奶": (
        "牛奶", "低脂牛奶", "脱脂牛奶", "酸奶", "奶酪", "乳制品", "黄油",
        "奶油", "炼乳", "奶粉", "乳清", "乳酪",
    ),
    "花生": ("花生", "花生酱", "花生油", "花生米"),
    "海鲜": (
        "海鲜", "鱼", "虾", "蟹", "贝", "蛤蜊", "牡蛎", "鱿鱼", "章鱼",
        "海参", "海带", "紫菜",
    ),
}

FATTY_MEAT_TERMS = (
    "五花肉", "带皮五花肉", "肥肉", "猪油", "培根", "腊肉", "香肠", "梅菜扣肉",
)

FORBIDDEN_BY_CONDITION = {
    "hypertension": ("腌", "咸菜", "腊肉", "火腿", "咸鱼", "酱菜", "榨菜"),
    "gout": ("内脏", "肝", "腰", "海鲜", "虾", "蟹", "贝", "浓汤", "沙丁"),
    "diabetes": ("白糖", "冰糖", "蜂蜜", "果葡糖浆", "糖浆", "蛋糕", "糖果"),
    "pregnancy": ("刺身", "生鱼片", "醉虾", "醉蟹", "酒", "金枪鱼", "鲨鱼", "剑鱼", "未巴氏", "生奶", "溏心"),
    "kidney": ("咸菜", "腌", "加工肉", "浓汤"),
}


class RecipeIngredientModel(BaseModel):
    name: str
    amount: str = ""
    from_pantry: bool = True
    expiring: bool = False
    role: str = ""  # main | auxiliary


class RecipeMealModel(BaseModel):
    meal_type: str
    name: str
    ingredients: list[RecipeIngredientModel] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    nutrition: dict = Field(default_factory=dict)
    suitability: dict = Field(default_factory=dict)
    tips: str = ""


class RecipePlanModel(BaseModel):
    summary: str
    meals: list[RecipeMealModel] = Field(default_factory=list)
    shopping_list: list[str] = Field(default_factory=list)
    agent_trace: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("shopping_list", "agent_trace", "warnings", mode="before")
    @classmethod
    def _stringify_list(cls, value: Any) -> list[str]:
        """模型可能把补购项写成对象，这里统一转成可读字符串。"""
        if value is None:
            return []
        if not isinstance(value, list):
            return [str(value)]
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("item") or item.get("title") or ""
                amount = item.get("amount") or item.get("quantity") or ""
                reason = item.get("reason") or item.get("note") or ""
                text = " ".join(part for part in (str(name), str(amount)) if part).strip()
                if reason:
                    text = f"{text}（{reason}）" if text else str(reason)
                result.append(text or json.dumps(item, ensure_ascii=False))
            else:
                result.append(str(item))
        return result


def _dedupe_warnings(items: list) -> list[str]:
    result: list[str] = []
    for item in items:
        text = str(item or '').strip()
        if not text:
            continue
        if text in result:
            continue
        if '估算' in text and any('估算' in existing for existing in result):
            continue
        result.append(text)
    return result[:4]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


def _kind(item: PantryItem) -> str:
    name = item.name
    category = item.category
    if category in {"meat", "seafood", "egg_dairy", "bean"}:
        if "蛋" in name or category == "egg_dairy":
            return "egg" if "蛋" in name else "milk"
        if category == "bean" or "豆腐" in name:
            return "tofu"
        if category == "seafood":
            return "shrimp" if "虾" in name else "fish"
        if "牛" in name:
            return "beef"
        if "猪" in name or "排骨" in name:
            return "pork"
        return "chicken"
    if category == "staple" or any(word in name for word in STAPLE_WORDS):
        if "燕麦" in name:
            return "oats"
        if "面" in name:
            return "noodle"
        return "rice"
    if category == "fruit" or any(word in name for word in FRUIT_WORDS):
        return "fruit"
    if category == "condiment":
        if "盐" in name:
            return "salt"
        if any(word in name for word in ("油", "花生油", "菜籽油", "橄榄油")):
            return "oil"
        return "vegetable"
    return "vegetable"


def _role(item: PantryItem) -> str:
    if item.category in {"meat", "seafood", "egg_dairy", "bean"}:
        return "protein"
    if item.category == "staple":
        return "staple"
    if item.category == "vegetable":
        return "vegetable"
    if item.category == "fruit":
        return "fruit"
    if item.category == "condiment":
        return "condiment"
    kind = _kind(item)
    if kind in {"egg", "tofu", "chicken", "pork", "beef", "fish", "shrimp"}:
        return "protein"
    if kind in {"rice", "oats", "noodle"}:
        return "staple"
    if kind == "fruit":
        return "fruit"
    return "vegetable"


def _allergen_terms(allergies: list[str]) -> list[tuple[str, str]]:
    """把用户填写的大类忌口展开为容易漏掉的隐性食材。"""
    terms: list[tuple[str, str]] = []
    for allergy in allergies:
        clean = str(allergy or "").strip()
        if not clean:
            continue
        for term in ALLERGEN_INGREDIENT_TERMS.get(clean, ()):
            terms.append((clean, term))
        terms.append((clean, clean))
    return terms


def _has_weight_loss(goals: list[str]) -> bool:
    return any(
        goal in {"weight_loss", "fat_loss", "减脂", "减重"}
        for goal in goals
    )


def _excluded(
    item: PantryItem,
    *,
    conditions: list[str],
    allergies: list[str],
    goals: list[str] | None = None,
) -> str | None:
    name = item.name
    for allergy, term in _allergen_terms(allergies):
        if term and term in name:
            return f"过敏原/忌口「{allergy}」的隐性食材「{term}」"
    if ("gastritis" in conditions or _has_weight_loss(goals or [])) and any(
        term in name for term in FATTY_MEAT_TERMS
    ):
        return "胃炎/减脂画像下应避开高脂难消化的肥肉"
    for condition in conditions:
        for word in FORBIDDEN_BY_CONDITION.get(condition, ()):
            if word in name:
                return f"{condition} 画像下建议避开「{word}」"
    if "vegetarian" in conditions and item.category in {"meat", "seafood"}:
        return "素食画像"
    return None


def _amounts(grams: int) -> str:
    return f"约 {grams}g"


def _scale_grams(base: int, servings: int) -> int:
    return max(1, round(base * max(1, servings) / 2))


def _estimate(parts: list[tuple[str, int]]) -> dict:
    total = {"energy_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carbs_g": 0.0, "sodium_mg": 0.0, "sugar_g": 0.0}
    for kind, grams in parts:
        table = NUTRITION.get(kind, NUTRITION["vegetable"])
        factor = grams / 100
        total["energy_kcal"] += table["energy"] * factor
        total["protein_g"] += table["protein"] * factor
        total["fat_g"] += table["fat"] * factor
        total["carbs_g"] += table["carbs"] * factor
        total["sodium_mg"] += table["sodium"] * factor
        total["sugar_g"] += table["sugar"] * factor
    return {key: round(value, 1) for key, value in total.items()}


def _pick(items: list[PantryItem], role: str, used: set[int]) -> PantryItem | None:
    candidates = [
        item for item in items
        if _role(item) == role
        and item.id not in used
        and not (role == "vegetable" and ingredient_rules.is_aromatic(item.name, item.category))
    ]
    if not candidates:
        return None
    # 临期优先，其次按分类稳定排序
    candidates.sort(key=lambda item: (item.expires_at or date.max, item.id))
    return candidates[0]


def _common_dish_name(protein: PantryItem, vegetable: PantryItem | None) -> str:
    kind = _kind(protein)
    if vegetable is None:
        return f"清蒸{protein.name}"
    if kind == "fish":
        return f"清蒸{protein.name}"
    if kind == "tofu":
        return f"{vegetable.name}烧{protein.name}"
    return f"{vegetable.name}炒{protein.name}"


def _recipe_for(
    meal_type: str,
    items: list[PantryItem],
    used: set[int],
    *,
    profile: dict,
    focus: PantryItem | None = None,
    servings: int = 2,
) -> dict:
    conditions = profile.get("conditions") or []
    preferred = [focus] if focus is not None and focus.id not in used else []
    protein = _pick(preferred + items, "protein", used)
    vegetable = _pick(preferred + items, "vegetable", used)
    staple = _pick(preferred + items, "staple", used)
    fruit = _pick(preferred + items, "fruit", used) if meal_type in {"早餐", "加餐", "上午加餐", "下午加餐"} else None

    if not any([protein, vegetable, staple, fruit]):
        # 没有可用食材时给一个明确的“需要采购”方案
        return {
            "meal_type": meal_type,
            "name": "库存不足，建议先补购食材",
            "ingredients": [],
            "steps": ["录入至少一种蔬菜、蛋白质或主食后再生成食谱。"],
            "nutrition": _estimate([]),
            "suitability": {},
            "tips": "可以在食材管家中补充库存。",
            "_parts": [],
        }

    used_ids: list[int] = []
    ingredients: list[dict] = []
    parts: list[tuple[str, int]] = []
    steps: list[str] = []

    if meal_type == "早餐":
        name = "营养早餐组合"
        if staple:
            used_ids.append(staple.id)
            grams = _scale_grams(60, servings)
            ingredients.append({"name": staple.name, "amount": _amounts(grams), "from_pantry": True, "expiring": staple.status()[0] == "expiring"})
            parts.append((_kind(staple), grams))
        if protein:
            used_ids.append(protein.id)
            kind = _kind(protein)
            amount = _scale_grams(50 if kind == "egg" else 100, servings)
            ingredients.append({"name": protein.name, "amount": _amounts(amount), "from_pantry": True, "expiring": protein.status()[0] == "expiring"})
            parts.append((kind, amount))
        if fruit:
            used_ids.append(fruit.id)
            grams = _scale_grams(100, servings)
            ingredients.append({"name": fruit.name, "amount": _amounts(grams), "from_pantry": True, "expiring": fruit.status()[0] == "expiring"})
            parts.append(("fruit", grams))
        steps = [
            "主食煮熟或冲泡，鸡蛋/蛋白质食材煮熟或煎熟（少油）。",
            "搭配水果，尽量不额外加糖。",
            "如有牛奶/无糖酸奶可搭配一份，补充蛋白质与钙。",
        ]
    else:
        name = "家常营养餐"
        if protein and vegetable:
            name = _common_dish_name(protein, vegetable)
            used_ids.extend([protein.id, vegetable.id])
            p_kind, v_kind = _kind(protein), _kind(vegetable)
            p_grams, v_grams = _scale_grams(120, servings), _scale_grams(200, servings)
            ingredients.append({"name": protein.name, "amount": _amounts(p_grams), "from_pantry": True, "expiring": protein.status()[0] == "expiring"})
            ingredients.append({"name": vegetable.name, "amount": _amounts(v_grams), "from_pantry": True, "expiring": vegetable.status()[0] == "expiring"})
            parts.extend([(p_kind, p_grams), (v_kind, v_grams)])
            steps = [
                "蛋白质食材洗净切好，蔬菜洗净切段。",
                "少油热锅，先炒蛋白质食材至变色，再加入蔬菜翻炒。",
                "出锅前用少量盐调味，避免额外使用高钠酱料。",
            ]
        elif protein:
            name = f"清蒸{protein.name}"
            used_ids.append(protein.id)
            grams = _scale_grams(120, servings)
            ingredients.append({"name": protein.name, "amount": _amounts(grams), "from_pantry": True, "expiring": protein.status()[0] == "expiring"})
            parts.append((_kind(protein), grams))
            steps = ["蛋白质食材洗净，加姜片清蒸至熟透。", "出锅后用少量盐或葱蒜调味。"]
        elif vegetable:
            name = f"清炒{vegetable.name}"
            used_ids.append(vegetable.id)
            grams = _scale_grams(250, servings)
            ingredients.append({"name": vegetable.name, "amount": _amounts(grams), "from_pantry": True, "expiring": vegetable.status()[0] == "expiring"})
            parts.append((_kind(vegetable), grams))
            steps = ["蔬菜洗净切好，少油快炒。", "出锅前少量盐调味。"]
        if staple:
            used_ids.append(staple.id)
            grams = _scale_grams(80, servings)
            ingredients.append({"name": staple.name, "amount": _amounts(grams), "from_pantry": True, "expiring": staple.status()[0] == "expiring"})
            parts.append((_kind(staple), grams))
            steps.append(f"{staple.name}按份量煮熟，作为主食。")
        if not steps:
            steps = ["按现有食材简单烹调，注意少油少盐。"]

    for ingredient in ingredients:
        ingredient["role"] = ingredient_rules.classify_role(str(ingredient.get("name") or ""))
    used.update(used_ids)
    suitability = {}
    if "hypertension" in conditions:
        suitability["高血压"] = "采用少盐做法，避免腌制食材；具体钠摄入请遵医嘱。"
    if "diabetes" in conditions:
        suitability["糖尿病"] = "控制主食份量，搭配蔬菜与蛋白质，避免加糖。"
    if "hyperlipidemia" in conditions:
        suitability["高血脂"] = "少油烹调，优先蒸、煮、炖。"
    if "gout" in conditions:
        suitability["痛风"] = "避免海鲜/内脏/浓汤，多饮水。"
    tips = "营养数值为估算；如有慢性病或过敏，请结合医生/营养师建议。"

    return {
        "meal_type": meal_type,
        "name": name,
        "ingredients": ingredients,
        "steps": steps,
        "nutrition": _estimate(parts),
        "suitability": suitability,
        "tips": tips,
        "_parts": parts,
    }


def _rule_plan(
    items: list[PantryItem],
    profile: dict,
    *,
    meals: int,
    max_minutes: int,
    focus: PantryItem | None = None,
    preference: str = "",
    servings: int = 2,
) -> dict:
    conditions = profile.get("conditions") or []
    allergies = profile.get("allergies") or []
    meal_types = MEAL_TYPES.get(meals, MEAL_TYPES[3])
    trace: list[str] = []
    usable: list[PantryItem] = []
    excluded: list[str] = []
    for item in items:
        reason = _excluded(
            item,
            conditions=conditions,
            allergies=allergies,
            goals=profile.get("goals") or [],
        )
        if reason:
            excluded.append(f"{item.name}（{reason}）")
        else:
            usable.append(item)
    if preference:
        trace.append(f"口味偏好：{preference[:40]}；规则引擎优先选择少油、易消化的做法。")
    trace.append(f"读取库存 {len(items)} 项，可用 {len(usable)} 项。")
    if excluded:
        trace.append("已排除：" + "、".join(excluded[:4]))
    expiring = [item for item in usable if item.status()[0] == "expiring"]
    if expiring:
        trace.append("优先使用临期食材：" + "、".join(item.name for item in expiring[:4]))
    if conditions:
        labels = [{"hypertension": "高血压", "diabetes": "糖尿病", "hyperlipidemia": "高血脂", "gout": "痛风", "kidney": "肾功能不全", "pregnancy": "孕期", "lactation": "哺乳期", "vegetarian": "素食"}.get(item, item) for item in conditions]
        trace.append("已应用健康画像：" + "、".join(labels))

    used: set[int] = set()
    recipes = [_recipe_for(meal_type, usable, used, profile=profile, focus=focus, servings=servings) for meal_type in meal_types]
    recipes.sort(key=lambda item: MEAL_ORDER.get(str(item.get("meal_type") or ""), 9))
    for recipe in recipes:
        for ingredient in recipe.get("ingredients") or []:
            ingredient["role"] = ingredient_rules.classify_role(str(ingredient.get("name") or ""))
        recipe["main_ingredients"] = [item for item in recipe.get("ingredients") or [] if item.get("role") != "auxiliary"]
        recipe["auxiliary_ingredients"] = [item for item in recipe.get("ingredients") or [] if item.get("role") == "auxiliary"]
    focus_used = any(
        focus is not None and any(ingredient.get("name") == focus.name for ingredient in recipe["ingredients"])
        for recipe in recipes
    )
    if focus is not None and not focus_used:
        kind = _kind(focus)
        recipes.insert(
            0,
            {
                "meal_type": "临期拯救",
                "name": f"{focus.name}快手消耗",
                "ingredients": [
                    {"name": focus.name, "amount": _amounts(_scale_grams(150, servings)), "from_pantry": True, "expiring": True}
                ],
                "steps": ["将食材洗净处理好，尽量采用清炒、煮汤或凉拌等少油做法。", "尽快食用，避免继续存放。"],
                "nutrition": _estimate([(kind, 150)]),
                "suitability": {},
                "tips": "这是临期食材优先消耗建议，具体做法可按口味调整。",
            },
        )
        trace.append(f"加入临期拯救菜：{focus.name}")
    # 去掉内部字段，并给克数补生活化换算
    for recipe in recipes:
        recipe.pop("_parts", None)
        household_service.enrich_ingredients(recipe.get("ingredients") or [])
    shopping: list[str] = []
    if not any(item.category == "condiment" and "油" in item.name for item in usable):
        shopping.append("食用油（少量）")
    if not any(item.category == "condiment" and "盐" in item.name for item in usable):
        shopping.append("食盐（少量）")
    if not any(_role(item) == "protein" for item in usable):
        shopping.append("蛋白质食材（鸡蛋/豆腐/鸡胸肉等）")
    if not any(_role(item) == "vegetable" for item in usable):
        shopping.append("蔬菜（绿叶菜/番茄/菌菇等）")
    if not any(_role(item) == "staple" for item in usable):
        shopping.append("主食（米/面/燕麦/红薯等）")
    # 把基础调味料分配到具体餐次，方便“只想做午餐”时直接看到缺什么
    for recipe in recipes:
        missing = []
        if recipe.get("ingredients"):
            if any("食用油" in item for item in shopping):
                missing.append({"name": "食用油", "amount": "少量", "reason": "基础调味料，库存没有"})
            if any("食盐" in item for item in shopping):
                missing.append({"name": "食盐", "amount": "少量", "reason": "基础调味料，库存没有"})
        else:
            missing = [{"name": item, "amount": "", "reason": "库存不足"} for item in shopping]
        recipe["missing"] = missing

    totals = {
        "energy_kcal": round(sum(recipe["nutrition"]["energy_kcal"] for recipe in recipes), 1),
        "protein_g": round(sum(recipe["nutrition"]["protein_g"] for recipe in recipes), 1),
        "sodium_mg": round(sum(recipe["nutrition"]["sodium_mg"] for recipe in recipes), 1),
        "sugar_g": round(sum(recipe["nutrition"]["sugar_g"] for recipe in recipes), 1),
    }
    warnings = [DISCLAIMER]
    if "hypertension" in conditions and totals["sodium_mg"] > 2000:
        warnings.append("本次食谱估算钠超过 2000mg/天，高血压人群建议进一步减少盐和酱料。")
    if "diabetes" in conditions and totals["sugar_g"] > 25:
        warnings.append("本次食谱估算糖超过 25g/天，糖尿病人群建议减少水果/主食份量并监测血糖。")
    trace.append(f"生成 {len(recipes)} 餐，使用 {len(used)} 项库存食材，需补购 {len(shopping)} 项。")

    return {
        "mode": "rule",
        "mode_label": "规则引擎食谱规划",
        "model": None,
        "summary": f"基于 {len(usable)} 项可用食材，为 {len(recipes)} 餐做了搭配，优先消耗临期食材。",
        "meals": recipes,
        "shopping_list": shopping,
        "agent_trace": trace,
        "warnings": warnings,
        "nutrition_totals": totals,
    }


def _config() -> dict:
    config = current_app.config
    base = str(config.get("AI_BASE_URL") or "").rstrip("/")
    key = str(config.get("AI_API_KEY") or "")
    mode = str(config.get("RECIPE_AGENT_MODE") or "auto").lower()
    return {
        "base": base,
        "key": key,
        "model": config.get("AI_MODEL") or "deepseek-chat",
        "timeout": int(config.get("AI_TIMEOUT") or 60),
        "mode": mode,
    }


def _allow_ai() -> bool:
    cfg = _config()
    if cfg["mode"] == "rule":
        return False
    return bool(cfg["key"] and cfg["base"])


def _strip_fence(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return match.group(1).strip() if match else text


def _call_llm(messages: list[dict]) -> str:
    cfg = _config()
    url = cfg["base"] if cfg["base"].endswith("/chat/completions") else cfg["base"] + "/chat/completions"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
        json={"model": cfg["model"], "temperature": 0.4, "messages": messages},
        timeout=cfg["timeout"],
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:160]}")
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content or "").strip()


def _ai_prompt(
    items: list[PantryItem],
    profile: dict,
    *,
    meals: int,
    max_minutes: int,
    focus: PantryItem | None = None,
    feedback: str = "",
    preference: str = "",
    servings: int = 2,
    budget: int = 0,
    weather: dict | None = None,
) -> list[dict]:
    inventory = [
        {
            "name": item.name,
            "category": item.category,
            "quantity": item.quantity,
            "unit": item.unit,
            "days_left": item.to_public()["days_left"],
            "status": item.status()[0],
        }
        for item in items
    ]
    payload = {
        "inventory": inventory,
        "health_profile": {
            "conditions": profile.get("conditions") or [],
            "goals": profile.get("goals") or [],
            "allergies": profile.get("allergies") or [],
            "notes": profile.get("notes") or "",
        },
        "meals": meals,
        "max_minutes_per_meal": max_minutes,
        "servings": servings,
        "budget_per_meal": budget or None,
        "weather": weather or None,
        "focus_item": focus.name if focus else None,
        "preference": preference,
        "user_request": preference,
    }
    system = (
        "你是家庭营养食谱规划 Agent。用户需求和口味偏好优先于库存，不要被库存限制住："
        "用户明确想吃的菜必须优先安排；库存只用于减少浪费和判断哪些食材已有，缺少的食材标记 from_pantry=false 并加入 shopping_list。"
        "只有用户没有提出需求时，才优先根据库存、临期食材和健康画像自由搭配家常菜。"
        "严格避开过敏原；高血压少盐、糖尿病控糖控主食；"
        "孕妇忌酒/生食/高汞鱼，痛风忌海鲜内脏浓汤，肾病遵医嘱；规则引擎会逐条检查并对违规方案一票否决。"
        "必须严格执行大类忌口过滤，不能只看菜名，必须逐项检查 ingredients 中的隐性食材："
        "allergies 含「粗粮」时，严禁出现燕麦、即食燕麦片、燕麦片、糙米、糙米饭、小米、小米粥、玉米、玉米面、全麦、杂粮、荞麦、大麦、黑米、紫米、藜麦、高粱等任何粗粮及其制品；"
        "allergies 含「面粉/小麦/麸质」时，严禁面粉、面条、面包、馒头、包子、饺子、面筋、饼干、蛋糕、吐司、挂面、意面、小麦粉；"
        "allergies 含「牛奶」时，严禁牛奶、低脂牛奶、脱脂牛奶、酸奶、奶酪、黄油、奶油、奶粉、乳清等乳制品，早餐必须把牛奶替换为无糖豆浆或燕麦奶（仅当大豆、燕麦未被忌口时）。"
        "医学常识冲突拦截：conditions 含 gastritis 或 goals 含 weight_loss/fat_loss 时，严禁五花肉、带皮五花肉、肥肉、猪油、培根、腊肉、香肠等高脂难消化肉类；"
        "正餐主菜的肉类只能推荐鸡胸肉、瘦牛肉、去皮鸡腿肉或鱼虾（且不得是过敏原）。"
        "如果库存中确实有五花肉，只能建议少量分餐、作为配菜或焯水去油后少量使用，绝对不能作为正餐主菜，也不能写进早餐/午餐主菜。"
        "以上规则优先于库存消耗；违反任意一条，规则引擎会一票否决并要求重新生成。"
        "meals 数组必须严格按照时间顺序输出（2 餐午餐→晚餐，3 餐早餐→午餐→晚餐，4 餐早餐→午餐→加餐→晚餐，5 餐早餐→午餐→加餐→晚餐→夜宵，6 餐早餐→上午加餐→午餐→下午加餐→晚餐→夜宵），不得打乱。"
        "请给出符合常识的食材重量：一条完整的鱼通常约 500g（不要写 120g 这种明显偏小的整鱼重量），整鸡/整鸭通常约 1000–1500g，单个鸡蛋约 50g。"
        "如果给出 focus_item，第一餐必须包含它，用于消耗临期食材；但 focus_item 不代表只能用它。所有食材用量与营养估算必须按 servings 人份计算，不能只按 1 人份。"
        "budget_per_meal 是单餐预算（人民币元）；大于 0 时必须控制食材成本，优先选择当季蔬菜、鸡蛋、豆腐、鸡胸肉等性价比高的食材，减少高价海鲜和牛肉，并在 agent_trace 中说明如何满足预算。"
        "weather 是当前天气环境。只要 weather 非空，最终 summary 必须显式说明天气如何影响本方案，必须包含城市、温度和天气现象，且天气现象必须原样使用 weather.description，例如「今日唐山市5℃霾，已为您安排暖胃热汤和炖菜」；严禁把霾改写成晴天、雨天等其他天气，严禁自行编造天气。如果天气为 rain/storm/snow，或 description 含雨、雪、霾、降温，或温度较低，必须优先安排热汤、炖菜、暖胃菜。请客观描述天气对食谱的影响，严禁臆造用户原本想吃但并未提及的食物；不要声称把用户没有提到的沙拉、冷饮等替换成了其他食物，除非用户明确提过。agent_trace 中必须有一条以「天气与环境感知：」开头的步骤，且内容必须引用本次 weather 数据。"
        "preference 是用户的原始要求（例如「今晚想吃红烧肉，少辣」），必须认真满足并在 agent_trace 中说明如何满足；"
        "如果 inventory 为空，summary 必须明确说明「当前库存为空，已按用户口味生成标准食谱并自动生成采购清单」，"
        "agent_trace 第一条必须写「检测到当前库存为空，正根据用户口味偏好生成标准食谱。已为您自动生成全套采购清单。」；"
        "绝对不要写「消耗库存」「使用库存」等与空库存矛盾的内容；"
        "即使库存没有对应主料，也要生成标准家常做法，把缺少的主料和辅料放进 shopping_list。"
        "每个 meal.ingredients 的每一项必须带 role：主料 role=main，辅料 role=auxiliary。葱、姜、蒜、辣椒、花椒等只能做辅料，严禁作为主料生成菜名；"
        "有鲤鱼时优先给「红烧鲤鱼」「清蒸鲤鱼」，有豆腐时优先给「葱烧豆腐」「家常豆腐」等符合中华家常常识的菜名。"
        "为了符合烹饪常识，允许额外补购 1–2 样配菜（如麻婆豆腐的肉末），这类食材标记 from_pantry=false，并加入 shopping_list，不要因此否决整份方案。"
        "每个食材的 amount 必须优先使用中国家庭厨房单位，并在括号里附克数/毫升：调料用「1小勺（约3g）」「半汤勺（约8ml）」，"
        "主食「一小碗（约150g）」或「一杯（电饭煲量杯，约133g）」，蛋/肉/菜用「2个（约100g）」「1个掌心大小（约100g）」「一小把（约100g）」。"
        "严禁使用茶匙、汤匙、盎司、oz、tsp 等西式单位；确保用户不用厨房秤也能操作。"
        "返回 JSON（不要 Markdown），字段：summary, meals[{meal_type,name,ingredients[{name,amount,from_pantry,expiring}],"
        "steps[],nutrition{energy_kcal,protein_g,fat_g,carbs_g,sodium_mg,sugar_g},suitability{},tips}],"
        "shopping_list[], agent_trace[], warnings[]。营养值是估算，不要声称治疗作用。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    if feedback:
        messages.append({"role": "user", "content": feedback})
    return messages


MEAL_ORDER = {"早餐": 0, "上午加餐": 1, "午餐": 2, "加餐": 3, "下午加餐": 3, "晚餐": 4, "夜宵": 5}


def _meals_with_missing(plan_obj: RecipePlanModel) -> list[dict]:
    meals = []
    for meal in plan_obj.meals:
        data = meal.model_dump()
        household_service.enrich_ingredients(data.get("ingredients") or [])
        for ingredient in data.get("ingredients") or []:
            name = str(ingredient.get("name") or "")
            ingredient["role"] = ingredient_rules.classify_role(name)
        data["main_ingredients"] = [
            item for item in data.get("ingredients") or [] if item.get("role") != "auxiliary"
        ]
        data["auxiliary_ingredients"] = [
            item for item in data.get("ingredients") or [] if item.get("role") == "auxiliary"
        ]
        data["missing"] = [
            {"name": ingredient.get("name"), "amount": ingredient.get("amount"), "reason": "库存没有该食材"}
            for ingredient in data.get("ingredients") or []
            if ingredient.get("from_pantry") is False
            and not ingredient_rules.is_non_purchase(str(ingredient.get("name") or ""))
        ]
        meals.append(data)
    meals.sort(key=lambda item: MEAL_ORDER.get(str(item.get("meal_type") or ""), 9))
    return meals


def _safe_ai_meal_name(meal: RecipeMealModel) -> str:
    name = str(meal.name or "").strip()
    if not name:
        return name
    allowed_prefixes = ("葱烧", "葱油", "姜母", "蒜蓉", "蒜香")
    if not any(name.startswith(prefix) for prefix in allowed_prefixes):
        if any(name.startswith(word) for word in ("大葱", "小葱", "香葱", "葱", "生姜", "姜", "大蒜", "蒜", "辣椒", "小米椒")):
            main_names = [
                str(ingredient.name or "").strip()
                for ingredient in meal.ingredients
                if ingredient_rules.classify_role(str(ingredient.name or "")) == "main"
            ]
            cleaned = []
            for main_name in main_names:
                clean = re.split(r"\s+\d", main_name)[0].strip()
                if clean and clean not in cleaned:
                    cleaned.append(clean)
            if cleaned:
                main = cleaned[0]
                if "鱼" in main or "虾" in main:
                    return f"清蒸{main}"
                if "豆腐" in main:
                    return f"家常{main}"
                return f"{main}家常做法"
    return name


def _validate_ai_plan(raw: str, items: list[PantryItem], profile: dict) -> tuple[RecipePlanModel | None, str | None]:
    try:
        data = json.loads(_strip_fence(raw))
        plan = RecipePlanModel.model_validate(data)
    except (json.JSONDecodeError, PydanticValidationError, TypeError) as exc:
        return None, f"模型返回格式无法解析：{exc.__class__.__name__}"
    if not plan.meals:
        return None, "模型没有生成任何食谱"
    names = [item.name for item in items]
    for meal in plan.meals:
        key = str(meal.meal_type or "").strip().lower()
        meal.meal_type = MEAL_TYPE_LABELS.get(key, meal.meal_type)
        for ingredient in meal.ingredients:
            if ingredient.name not in names:
                ingredient.from_pantry = False
            if not ingredient.role:
                ingredient.role = ingredient_rules.classify_role(str(ingredient.name or ""))
        meal.name = _safe_ai_meal_name(meal)
    return plan, None


CONDITION_LABELS = {
    "hypertension": "高血压",
    "diabetes": "糖尿病",
    "hyperlipidemia": "高血脂",
    "gout": "痛风",
    "kidney": "肾功能不全",
    "pregnancy": "孕期",
    "lactation": "哺乳期",
    "vegetarian": "素食",
}


def _meal_contains_focus(meals: list[dict], focus_name: str) -> bool:
    target = (focus_name or "").strip()
    if not target:
        return False
    for meal in meals:
        for ingredient in meal.get("ingredients") or []:
            name = str(ingredient.get("name") or "").strip()
            if name and (target in name or name in target):
                return True
    return False


def _plan_vetoes(
    plan: RecipePlanModel,
    profile: dict,
    *,
    focus: PantryItem | None = None,
    items: list[PantryItem] | None = None,
) -> list[str]:
    """AI 方案需修正：过敏原、疾病禁忌、素食、指定临期食材未使用。"""
    conditions = profile.get("conditions") or []
    allergies = profile.get("allergies") or []
    vetoes: list[str] = []
    focus_used = False
    item_by_name = {item.name: item for item in (items or [])}
    for meal in plan.meals:
        for ingredient in meal.ingredients:
            name = ingredient.name or ""
            if focus is not None and focus.name in name:
                focus_used = True
            for allergy, term in _allergen_terms(allergies):
                if term and term in name:
                    vetoes.append(
                        f"「{meal.name}」含忌口「{allergy}」的隐性食材「{term}」（{name}）"
                    )
            if (
                "gastritis" in conditions
                or _has_weight_loss(profile.get("goals") or [])
            ) and any(term in name for term in FATTY_MEAT_TERMS):
                vetoes.append(
                    f"「{meal.name}」含高脂难消化的肥肉「{name}」，不适合胃炎/减脂画像"
                )
            for condition in conditions:
                for word in FORBIDDEN_BY_CONDITION.get(condition, ()):
                    if word in name:
                        vetoes.append(
                            f"「{meal.name}」含「{word}」，与{CONDITION_LABELS.get(condition, condition)}画像冲突（{name}）"
                        )
                        break
            pantry_item = item_by_name.get(name)
            if "vegetarian" in conditions and pantry_item is not None and pantry_item.category in {"meat", "seafood"}:
                vetoes.append(f"「{meal.name}」含肉类/水产「{name}」，与素食画像冲突")
    if focus is not None and not focus_used:
        vetoes.append(f"未优先使用指定的临期食材「{focus.name}」")
    # 去重并限制长度
    unique: list[str] = []
    for item in vetoes:
        if item not in unique:
            unique.append(item)
    return unique[:6]


def plan_recipes(
    user_id: int,
    *,
    meals: int = 3,
    max_minutes: int = 30,
    focus_item_id: int | None = None,
    preference: str = "",
    force_rule: bool = False,
    servings: int = 2,
    budget: int = 0,
    weather: dict | None = None,
) -> dict:
    items = PantryItem.query.filter_by(user_id=user_id).all()
    if not items and not _allow_ai():
        raise ValidationError("食材库为空，请先录入购买的食材，或配置大模型后按口味生成")
    if not items and not preference:
        preference = "请根据健康画像和家常菜常识，自由推荐适合的一日三餐"
    focus: PantryItem | None = None
    if focus_item_id:
        focus = PantryItem.query.filter_by(id=int(focus_item_id), user_id=user_id).first()
        if focus is None:
            raise NotFoundError("指定食材不存在")
    profile_obj = HealthProfile.query.filter_by(user_id=user_id).first()
    profile = profile_obj.to_public() if profile_obj else {"conditions": [], "goals": [], "allergies": []}
    meals = max(2, min(6, int(meals or 3)))
    max_minutes = max(10, min(90, int(max_minutes or 30)))
    servings = max(1, min(6, int(servings or 2)))
    budget = max(0, min(200, int(budget or 0)))
    weather = weather if isinstance(weather, dict) else {}
    # 临期食材放前面，便于规则引擎和 prompt 都优先使用
    ordered_items = ([focus] + [item for item in items if focus is None or item.id != focus.id]) if focus else items

    ai_error: str | None = None
    veto_history: list[str] = []
    plan: dict | None = None
    if _allow_ai() and not force_rule:
        feedback = ""
        for attempt in range(2):
            try:
                raw = _call_llm(
                    _ai_prompt(
                        ordered_items,
                        profile,
                        meals=meals,
                        max_minutes=max_minutes,
                        focus=focus,
                        feedback=feedback,
                        preference=preference,
                        servings=servings,
                        budget=budget,
                        weather=weather,
                    )
                )
            except Exception as exc:  # 网络失败直接降级
                ai_error = f"{exc.__class__.__name__}: {str(exc)[:160]}"
                break
            plan_obj, error = _validate_ai_plan(raw, items, profile)
            if plan_obj is None:
                ai_error = error
                feedback = "上一轮输出格式不合法，请只返回合法 JSON，且必须包含 meals 数组。"
                continue
            vetoes = _plan_vetoes(plan_obj, profile, focus=focus, items=items)
            if vetoes:
                veto_history.extend(item for item in vetoes if item not in veto_history)
                ai_error = "AI 方案需修正：" + "；".join(vetoes[:3])
                feedback = (
                    "规则引擎否决了上一版方案："
                    + "；".join(vetoes)
                    + "。请重新生成，严格避开这些食材与禁忌，并优先使用临期食材。"
                )
                continue
            plan = {
                "mode": "ai",
                "mode_label": "AI Agent 食谱规划",
                "model": _config()["model"],
                "summary": plan_obj.summary,
                "meals": _meals_with_missing(plan_obj),
                "shopping_list": plan_obj.shopping_list,
                "agent_trace": [
                    "规则引擎复核：未发现过敏原、疾病禁忌或指定食材冲突。",
                    *([f"AI 智能修正：已自动修正并重新生成（第 {attempt + 1} 次通过）。"] if veto_history else []),
                    *(plan_obj.agent_trace or ["AI Agent 根据库存与健康画像生成食谱。"]),
                ],
                "warnings": _dedupe_warnings(
                    [
                        DISCLAIMER,
                        *(["AI 智能修正：已自动修正并重新生成。"] if veto_history else []),
                        *plan_obj.warnings,
                    ]
                ),
                "rule_vetoes": veto_history,
                "nutrition_totals": {
                    "energy_kcal": round(sum(float(meal.nutrition.get("energy_kcal") or 0) for meal in plan_obj.meals), 1),
                    "protein_g": round(sum(float(meal.nutrition.get("protein_g") or 0) for meal in plan_obj.meals), 1),
                    "sodium_mg": round(sum(float(meal.nutrition.get("sodium_mg") or 0) for meal in plan_obj.meals), 1),
                    "sugar_g": round(sum(float(meal.nutrition.get("sugar_g") or 0) for meal in plan_obj.meals), 1),
                },
            }
            ai_error = None
            break

    if plan is None:
        plan = _rule_plan(ordered_items, profile, meals=meals, max_minutes=max_minutes, focus=focus, preference=preference, servings=servings)
        plan["rule_vetoes"] = veto_history
        if ai_error:
            prefix = "AI 智能修正" if veto_history else "AI 生成失败"
            plan["warnings"].append(f"{prefix}，已使用规则引擎：{ai_error}")

    if budget:
        trace_lines = plan.setdefault("agent_trace", [])
        if not any("预算" in str(line) for line in trace_lines):
            trace_lines.append(
                f"预算控制：按单餐 ¥{budget} 内的目标，优先选择当季蔬菜、鸡蛋、豆腐等性价比高的食材。"
            )
    if weather:
        trace_lines = plan.setdefault("agent_trace", [])
        city = str(weather.get("city") or "").strip()
        temp = weather.get("temperature")
        status = str(weather.get("description") or weather.get("condition") or "").strip()
        if temp is not None:
            weather_step = f"天气与环境感知：检测到今日{city}{temp}℃"
            if status:
                weather_step += f"，当前天气{status}"
            weather_step += "，偏好安排温热菜谱以御寒。"
        else:
            weather_step = f"天气与环境感知：检测到今日{city}天气变化"
            if status:
                weather_step += f"（{status}）"
            weather_step += "，偏好安排温热菜谱以御寒。"

        # 天气步骤必须以本次前端传来的实时天气为准，移除模型自行编造的天气步骤
        trace_lines = [
            line for line in trace_lines
            if not str(line).startswith("天气与环境感知")
            and not str(line).startswith("天气联动")
        ]
        trace_lines.insert(0, weather_step)
        plan["agent_trace"] = trace_lines
    plan["budget"] = budget
    plan["weather"] = weather or None
    if weather:
        city = str(weather.get("city") or "").strip()
        temp = weather.get("temperature")
        description = str(weather.get("description") or "").strip()
        summary_text = str(plan.get("summary") or "").strip()
        if city and temp is not None and (
            city not in summary_text
            or str(temp) not in summary_text
            or (description and description not in summary_text)
        ):
            weather_summary = f"今日{city}{temp}℃"
            if description:
                weather_summary += f"（{description}）"
            weather_summary += "，已开启天气联动，优先安排暖胃热汤/炖菜。"
            plan["summary"] = f"{weather_summary} {summary_text}".strip()

    focus_name = focus.name if focus else ""
    plan["focus_in_final"] = _meal_contains_focus(plan.get("meals") or [], focus_name)
    plan["requested_meals"] = meals
    plan["actual_meals"] = len(plan.get("meals") or [])
    if focus:
        vetoes = list(plan.get("rule_vetoes") or [])
        if plan["focus_in_final"]:
            vetoes = [
                item for item in vetoes
                if "未优先使用指定的临期食材" not in item and focus_name not in item
            ]
        elif not any("未优先使用指定的临期食材" in item for item in vetoes):
            vetoes.append(f"未优先使用指定的临期食材「{focus_name}」")
        plan["rule_vetoes"] = vetoes
    # 旧文案统一改成“AI 智能修正”，不在 UI 出现“规则引擎一票否决”
    if focus_name and plan["focus_in_final"]:
        plan["warnings"] = [
            warning
            for warning in (plan.get("warnings") or [])
            if "未优先使用指定的临期食材" not in str(warning)
        ]
    plan["warnings"] = [
        (
            f"⚠️ AI 智能修正：已优先为您安排消耗临期食材（{focus_name}）。"
            if focus_name and plan["focus_in_final"]
            else "AI 方案已自动修正，最终结果以当前展示为准。"
        )
        if "一票否决" in str(warning) or "规则引擎拦截" in str(warning)
        else warning
        for warning in (plan.get("warnings") or [])
    ]
    plan["agent_trace"] = [
        str(item).replace("规则引擎一票否决", "AI 智能修正").replace("规则引擎拦截", "AI 智能修正")
        for item in (plan.get("agent_trace") or [])
    ]
    if ai_error:
        ai_error = (
            f"AI 智能修正：已优先为您安排消耗临期食材（{focus_name}）。"
            if focus_name and plan["focus_in_final"]
            else ai_error.replace("规则引擎一票否决", "AI 方案需修正").replace("规则引擎拦截", "AI 方案需修正")
        )
    # 把实际缺料并入补购清单（允许 AI 为家常常识补 1–2 样配菜）
    existing_shopping = [str(item) for item in plan.get("shopping_list") or []]
    seen_shopping = set(existing_shopping)
    for meal in plan.get("meals") or []:
        for item in meal.get("missing") or []:
            label = f"{item.get('name')} {item.get('amount')}".strip()
            if label and label not in seen_shopping:
                seen_shopping.add(label)
                existing_shopping.append(label)
    plan["shopping_list"] = existing_shopping
    plan["agent_trace"] = _clean_agent_trace(plan.get("agent_trace") or [], empty_inventory=not items)
    if not items:
        preference_text = f"：{preference[:50]}" if preference else ""
        plan["summary"] = f"检测到当前库存为空，已根据用户口味偏好生成标准食谱{preference_text}。已为您自动生成全套采购清单。"
    plan["warnings"] = _dedupe_warnings(plan.get("warnings") or [DISCLAIMER])
    plan.update(
        {
            "model_version": MODEL_VERSION,
            "generated_at": _now(),
            "request": {"meals": meals, "max_minutes": max_minutes, "focus_item_id": focus_item_id, "preference": preference, "servings": servings},
            "focus_item": focus.to_public() if focus else None,
            "pantry_count": len(items),
            "preference": preference,
            "servings": servings,
            "profile": profile,
            "ai_error": ai_error,
            "disclaimer": DISCLAIMER,
        }
    )
    record = RecipePlan(
        user_id=user_id,
        mode=plan["mode"],
        model=plan.get("model"),
        request=plan["request"],
        result=plan,
    )
    db.session.add(record)
    db.session.commit()
    plan["plan_id"] = record.id
    return plan


MASS_UNITS = {"g": 1.0, "克": 1.0, "kg": 1000.0, "千克": 1000.0}
VOLUME_UNITS = {"ml": 1.0, "毫升": 1.0, "l": 1000.0, "升": 1000.0}


def _parse_amount(text: str, item_unit: str = "") -> tuple[float | None, str]:
    value_text = text or ""
    # 先找括号里的克数/毫升：如「1小勺（约3g）」「半汤勺（约8ml）」
    paren = re.search(r"[（(]\s*约?\s*(\d+(?:\.\d+)?)\s*(kg|g|克|千克|ml|毫升|升|l)", value_text, re.I)
    # 再找开头的家庭计数：如「3个」「2把」
    lead = re.match(r"^(\d+(?:\.\d+)?)\s*(个|只|把|块|盒|片|份)", value_text.strip())
    unit = (item_unit or "").strip().lower()
    if lead and (lead.group(2) == unit or (unit in {"份", "块"} and lead.group(2) in {"个", "只"})):
        return float(lead.group(1)), lead.group(2)
    if paren:
        return float(paren.group(1)), paren.group(2).lower()
    if lead:
        return float(lead.group(1)), lead.group(2)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|克|千克|ml|毫升|升|l|个|只|把|块|盒|片|份)?", value_text, re.I)
    if not match:
        return None, ""
    return float(match.group(1)), (match.group(2) or "").lower()


def _match_pantry(items: list[PantryItem], name: str) -> PantryItem | None:
    target = re.sub(r"[\s（）()]", "", name or "")
    if not target:
        return None
    exact = [item for item in items if re.sub(r"[\s（）()]", "", item.name) == target]
    if exact:
        return sorted(exact, key=lambda item: item.expires_at or date.max)[0]
    partial = [
        item
        for item in items
        if target in re.sub(r"[\s（）()]", "", item.name) or re.sub(r"[\s（）()]", "", item.name) in target
    ]
    return sorted(partial, key=lambda item: item.expires_at or date.max)[0] if partial else None


def _convert_amount(amount: float, amount_unit: str, item: PantryItem) -> float | None:
    item_unit = (item.unit or "份").strip().lower()
    if not amount_unit:
        return amount
    if amount_unit in MASS_UNITS and item_unit in MASS_UNITS:
        return amount * MASS_UNITS[amount_unit] / MASS_UNITS[item_unit]
    if amount_unit in VOLUME_UNITS and item_unit in VOLUME_UNITS:
        return amount * VOLUME_UNITS[amount_unit] / VOLUME_UNITS[item_unit]
    if amount_unit == item_unit:
        return amount
    if item_unit in {"份", "块", "包"} and amount_unit not in MASS_UNITS | VOLUME_UNITS:
        return amount
    return None


def complete_meal(user_id: int, plan_id: int, meal_index: int) -> dict:
    """完成一道菜：按配料用量扣减库存，幂等并记录 CookLog。"""
    plan = RecipePlan.query.filter_by(id=plan_id, user_id=user_id).first()
    if plan is None:
        raise NotFoundError("食谱方案不存在")
    meals = (plan.result or {}).get("meals") or []
    if meal_index < 0 or meal_index >= len(meals):
        raise ValidationError("菜品序号不合法")
    meal = meals[meal_index]
    existing = CookLog.query.filter_by(plan_id=plan_id, meal_index=meal_index).first()
    if existing:
        return {
            "completed": True,
            "already_done": True,
            "plan_id": plan_id,
            "meal_index": meal_index,
            "recipe_name": meal.get("name") or "",
            "consumed": existing.consumed or [],
            "missing": existing.missing or [],
            "message": "这道菜已经完成过，库存不会重复扣减",
        }

    items = PantryItem.query.filter_by(user_id=user_id).all()
    consumed: list[dict] = []
    missing: list[dict] = []
    skipped: list[dict] = []
    staples: list[dict] = []
    for ingredient in meal.get("ingredients") or []:
        name = str(ingredient.get("name") or "").strip()
        amount_text = str(ingredient.get("amount") or "")
        if not name:
            continue
        if ingredient_rules.is_staple(name):
            staples.append({"name": name, "amount": amount_text, "reason": "常备调料，视为无限库存"})
            continue
        if ingredient_rules.is_non_purchase(name):
            continue
        if ingredient.get("from_pantry") is False:
            missing.append({"name": name, "amount": amount_text, "reason": "库存中没有该食材"})
            continue
        item = _match_pantry(items, name)
        if item is None:
            missing.append({"name": name, "amount": amount_text, "reason": "库存中没有该食材"})
            continue
        amount, amount_unit = _parse_amount(amount_text, item.unit)
        if amount is None or amount <= 0:
            skipped.append({"name": item.name, "amount": amount_text, "reason": "用量不明确，未自动扣减"})
            continue
        deduct = _convert_amount(amount, amount_unit, item)
        estimated = False
        if deduct is None:
            # 单位和库存单位无法换算（例如“150g”对“1块”），按 1 个库存单位估算
            deduct = 1.0
            estimated = True
        before = float(item.quantity)
        after = max(0.0, before - deduct)
        item.quantity = round(after, 2)
        consumed.append(
            {
                "name": item.name,
                "amount": amount_text,
                "deducted": round(min(deduct, before), 2),
                "unit": item.unit,
                "remaining": round(after, 2),
                "estimated": estimated,
            }
        )
        if after <= 0:
            db.session.delete(item)
    log = CookLog(
        user_id=user_id,
        plan_id=plan_id,
        meal_index=meal_index,
        recipe_name=str(meal.get("name") or "")[:160],
        consumed=consumed,
        missing=missing,
    )
    db.session.add(log)
    db.session.commit()
    return {
        "completed": True,
        "already_done": False,
        "plan_id": plan_id,
        "meal_index": meal_index,
        "recipe_name": meal.get("name") or "",
        "consumed": consumed,
        "missing": missing,
        "skipped": skipped,
        "staples": staples,
        "shopping_list": (plan.result or {}).get("shopping_list") or [],
        "message": f"已扣减 {len(consumed)} 项库存" + (f"，{len(missing)} 项缺少" if missing else ""),
    }


def _split_recipe_ingredient(line: str) -> tuple[str, str]:
    text = re.sub(r"^[·\-\s]+", "", str(line or "")).strip()
    match = re.match(r"^(.+?)\s+(.+)$", text)
    if match:
        name = match.group(1).strip(" ：:")
        amount = match.group(2).strip()
    else:
        name, amount = text, "1份"
    return (name[:60] or "食材", amount[:80] or "1份")


def save_assistant_recipe(user_id: int, message_id: int, version: str = "novice") -> dict:
    """把助手菜谱保存为一条食谱方案，方便在食谱规划里查看/扣库存。"""
    message = (
        ChatMessage.query.join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .filter(ChatMessage.id == message_id, ChatSession.user_id == user_id)
        .first()
    )
    if message is None:
        raise NotFoundError("菜谱消息不存在")
    payload = message.payload or {}
    recipe = payload.get("recipe_data") if isinstance(payload, dict) else None
    if not isinstance(recipe, dict) or not recipe.get("title") or not recipe.get("ingredients"):
        raise ValidationError("这条回答里没有可加入食谱的菜谱数据")
    versions = recipe.get("versions") if isinstance(recipe.get("versions"), dict) else {}
    if not versions.get("novice") or not versions.get("chef"):
        base_steps = [str(step)[:500] for step in recipe.get("steps") or []][:15]
        base_tips = [str(tip)[:120] for tip in recipe.get("tips") or []]
        versions = {
            "novice": {"steps": base_steps, "tips": base_tips},
            "chef": {"steps": base_steps, "tips": base_tips},
        }
    selected_version = version if version in {"novice", "chef"} else "novice"
    selected = versions[selected_version]

    pantry_items = PantryItem.query.filter_by(user_id=user_id).all()
    ingredients = []
    missing = []
    for line in recipe.get("ingredients") or []:
        name, amount = _split_recipe_ingredient(str(line))
        matched = _match_pantry(pantry_items, name)
        ingredients.append(
            {
                "name": name,
                "amount": amount,
                "from_pantry": matched is not None,
                "expiring": bool(matched and matched.status()[0] == "expiring"),
            }
        )
        if matched is None:
            missing.append({"name": name, "amount": amount, "reason": "库存没有该食材"})
    for ingredient in ingredients:
        ingredient["role"] = ingredient_rules.classify_role(str(ingredient.get("name") or ""))
    meal = {
        "meal_type": "自定义菜谱",
        "name": str(recipe.get("title"))[:80],
        "ingredients": ingredients,
        "main_ingredients": [item for item in ingredients if item.get("role") != "auxiliary"],
        "auxiliary_ingredients": [item for item in ingredients if item.get("role") == "auxiliary"],
        "steps": [str(step)[:500] for step in selected.get("steps") or []][:20],
        "tips": "；".join(str(item)[:120] for item in selected.get("tips") or [])[:400],
        "version": selected_version,
        "versions": versions,
        "nutrition": {"energy_kcal": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0, "sodium_mg": 0, "sugar_g": 0},
        "suitability": {},
        "missing": missing,
    }

    existing_plans = (
        RecipePlan.query.filter_by(user_id=user_id, mode="assistant_recipe")
        .order_by(RecipePlan.id.desc())
        .limit(20)
        .all()
    )
    for existing_plan in existing_plans:
        request = existing_plan.request or {}
        ids = set(request.get("message_ids") or [])
        if request.get("message_id"):
            ids.add(request.get("message_id"))
        if message_id in ids:
            result = dict(existing_plan.result or {})
            meals = list(result.get("meals") or [])
            target = next((item for item in meals if item.get("name") == meal["name"]), None)
            if target is not None and target.get("version") != selected_version:
                target.update(
                    {
                        "steps": meal["steps"],
                        "tips": meal["tips"],
                        "version": selected_version,
                        "versions": versions,
                    }
                )
                result["meals"] = meals
                existing_plan.result = result
                flag_modified(existing_plan, "result")
                db.session.commit()
            result["plan_id"] = existing_plan.id
            return result

    latest = RecipePlan.query.filter_by(user_id=user_id).order_by(RecipePlan.id.desc()).first()
    if latest is not None:
        base = dict(latest.result or {})
        meals = list(base.get("meals") or [])
        # 只追加到当前方案；不再把历史上其他助手方案里的菜全部倒进来，
        # 否则用户每点一次“加入食谱”，界面就会凭空多出好几道没点过的菜。
        same_meal = next((item for item in meals if item.get("name") == meal["name"]), None)
        if same_meal is None:
            meals.append(meal)
        else:
            same_meal.update(
                {
                    "steps": meal["steps"],
                    "tips": meal["tips"],
                    "version": selected_version,
                    "versions": versions,
                }
            )
        shopping = []
        seen_shopping = set()
        for label in (latest.result or {}).get("shopping_list") or []:
            if label not in seen_shopping:
                seen_shopping.add(label)
                shopping.append(label)
        for item in meals:
            for item_missing in item.get("missing") or []:
                label = f"{item_missing.get('name')} {item_missing.get('amount')}".strip()
                if label and label not in seen_shopping:
                    seen_shopping.add(label)
                    shopping.append(label)
        base["meals"] = meals
        base["shopping_list"] = shopping
        base["pantry_count"] = len(pantry_items)
        base["summary"] = f"🍄 为您生成了 {len(meals)} 道菜的方案，记得按时吃饭哦~"
        trace = list(base.get("agent_trace") or [])
        base["agent_trace"] = trace[-12:]
        base["plan_id"] = latest.id
        latest.result = base
        flag_modified(latest, "result")
        request = dict(latest.request or {})
        ids = set(request.get("message_ids") or [])
        if request.get("message_id"):
            ids.add(request.get("message_id"))
        ids.add(message_id)
        request["source"] = request.get("source") or "assistant"
        request["message_ids"] = sorted(ids)
        latest.request = request
        flag_modified(latest, "request")
        db.session.commit()
        return base

    result = {
        "mode": "assistant_recipe",
        "mode_label": "助手菜谱加入",
        "model": None,
        "summary": f"来自助手的菜谱「{recipe.get('title')}」，已整理进食谱规划，可查看缺料并完成扣减库存。",
        "servings": 2,
        "meals": [meal],
        "shopping_list": [f"{item['name']} {item['amount']}" for item in missing],
        "agent_trace": [
            "从科普助手的做菜回答中加入食谱。",
            f"读取库存 {len(pantry_items)} 项，缺少 {len(missing)} 项。",
            "可在食谱规划中查看，完成后扣减库存。",
        ],
        "warnings": [DISCLAIMER],
        "nutrition_totals": {"energy_kcal": 0, "protein_g": 0, "sodium_mg": 0, "sugar_g": 0},
        "pantry_count": len(pantry_items),
        "request": {"source": "assistant", "message_id": message_id, "message_ids": [message_id], "title": recipe.get("title")},
    }
    plan = RecipePlan(
        user_id=user_id,
        mode="assistant_recipe",
        model=None,
        request=result["request"],
        result=result,
    )
    db.session.add(plan)
    db.session.flush()
    result["plan_id"] = plan.id
    plan.result = dict(result)
    flag_modified(plan, "result")
    db.session.commit()
    return result


def remove_meal(user_id: int, plan_id: int, meal_index: int) -> dict:
    """从当前方案里移除一道菜；全部移除后删除方案。"""
    plan = RecipePlan.query.filter_by(id=plan_id, user_id=user_id).first()
    if plan is None:
        raise NotFoundError("食谱方案不存在")
    result = dict(plan.result or {})
    meals = list(result.get("meals") or [])
    if meal_index < 0 or meal_index >= len(meals):
        raise ValidationError("菜品序号不合法")
    removed = dict(meals[meal_index])
    remaining = [meal for index, meal in enumerate(meals) if index != meal_index]

    # 保留已完成记录：删除被移除那道菜的记录，后面的序号前移。
    # 先挪到临时序号，避开 (plan_id, meal_index) 唯一约束。
    logs = CookLog.query.filter_by(plan_id=plan_id).order_by(CookLog.meal_index.asc()).all()
    shifted = []
    for log in logs:
        if log.meal_index == meal_index:
            db.session.delete(log)
        elif log.meal_index > meal_index:
            shifted.append((log, log.meal_index))
            log.meal_index = -100000 - log.id
    db.session.flush()
    for log, old_index in shifted:
        log.meal_index = old_index - 1
    db.session.flush()

    if not remaining:
        db.session.delete(plan)
        db.session.commit()
        return {"deleted_plan": True, "plan_id": plan_id, "result": None, "message": "方案已清空"}

    removed_names = {
        str(item.get("name") or "").strip()
        for item in removed.get("ingredients") or []
        if str(item.get("name") or "").strip()
    }
    remaining_names = {
        str(item.get("name") or "").strip()
        for meal in remaining
        for item in meal.get("ingredients") or []
        if str(item.get("name") or "").strip()
    }
    shopping = []
    for label in result.get("shopping_list") or []:
        if any(name in label and name not in remaining_names for name in removed_names):
            continue
        shopping.append(label)
    result["meals"] = remaining
    result["shopping_list"] = shopping
    result["summary"] = f"🍄 方案已更新为 {len(remaining)} 道菜，记得按时吃饭哦~"
    trace = list(result.get("agent_trace") or [])
    trace.append(f"移除菜谱「{removed.get('name') or '未命名'}」。")
    result["agent_trace"] = trace[-12:]
    result["plan_id"] = plan.id
    plan.result = result
    flag_modified(plan, "result")
    db.session.commit()
    return {"deleted_plan": False, "plan_id": plan.id, "result": result, "message": "已从方案中移除"}


def history(user_id: int, *, limit: int = 10) -> list[dict]:
    rows = (
        RecipePlan.query.filter_by(user_id=user_id)
        .order_by(RecipePlan.id.desc())
        .limit(max(1, min(30, limit)))
        .all()
    )
    items = []
    for row in rows:
        public = row.to_public()
        result = dict(public.get("result") or {})
        result["plan_id"] = row.id
        public["result"] = result
        items.append(public)
    return items


__all__ = ["plan_recipes", "history", "MODEL_VERSION", "DISCLAIMER"]
