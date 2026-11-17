"""新手菜谱回答：内置少量家常菜 + 大模型兜底，输出分步骤教学。"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from ..seed.recipe_catalog import RECIPE_EXAMPLES
from . import household_service

SAFETY_MARKERS = (
    "安全",
    "中毒",
    "致癌",
    "亚硝酸",
    "细菌",
    "保存",
    "隔夜",
    "过敏",
    "孕妇",
    "糖尿病",
    "高血压",
    "能不能吃",
    "可以吃吗",
    "能吃吗",
)
COOKING_PATTERNS = (
    "怎么做",
    "如何做",
    "怎样做",
    "做法",
    "教程",
    "怎么炒",
    "怎么煮",
    "怎么蒸",
    "怎么炖",
    "怎么烤",
    "怎么煎",
    "怎么凉拌",
    "烹饪步骤",
)
CLEAN_WORDS = (
    "请问",
    "麻烦",
    "教教我",
    "教我",
    "那",
    "具体",
    "然后",
    "还有",
    "这道菜",
    "它",
    "新手",
    "零基础",
    "家常",
    "简单",
    "好吃",
    "才好吃",
    "一点",
    "一下",
    "的",
    "能",
    "吗",
    "呢",
    "？",
    "?",
    "，",
    ",",
    "。",
    ".",
)
GENERIC_STEPS = [
    "先把所有食材洗净、切好，调料提前放在手边；新手不要边炒边找调料。",
    "锅烧热后再放油，油面开始轻微晃动时下葱姜蒜等香料，小火炒香 10–20 秒，别炒焦。",
    "转中大火下主料，快速翻炒；难熟的食材先下，易熟的后下，避免一起下锅导致生熟不均。",
    "沿锅边淋少量料酒或清水，盖上锅盖焖 1–2 分钟，帮助食材熟透；具体时间按食材厚度调整。",
    "加盐、生抽等基础调料，先少放，尝味后再补；不要一开始就放很咸。",
    "食材完全熟透、中心不再发白或带血水后出锅；盛盘趁热吃，剩菜及时冷藏。",
]


NUTRITION_FIELDS = {
    "energy_kcal": "energy",
    "protein_g": "protein",
    "fat_g": "fat",
    "carbs_g": "carbs",
    "sodium_mg": "sodium",
    "sugar_g": "sugar",
}


def _ingredient_grams(text: str, name: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|千克|g|克|ml|毫升|斤)", text or "", re.I)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit in {"kg", "千克"}:
            value *= 1000
        elif unit == "斤":
            value *= 500
        return value
    if "油" in name:
        return 10.0
    if any(word in name for word in ("盐", "生抽", "老抽", "酱油", "蚝油")):
        return 15.0
    if any(word in name for word in ("糖", "冰糖")):
        return 10.0
    if any(word in name for word in ("葱", "姜", "蒜", "淀粉", "胡椒", "花椒")):
        return 5.0
    return 200.0


def _estimate_nutrition(ingredients: list[str]) -> dict:
    from .recipe_agent_service import NUTRITION

    total = {key: 0.0 for key in NUTRITION_FIELDS}
    named = [str(item) for item in ingredients or []]
    for line in named:
        text = str(line).strip()
        if not text:
            continue
        name = re.split(r"[：:]", text, maxsplit=1)[-1].strip()
        amount_text = text
        if "：" in text or ":" in text:
            amount_text = text
        grams = _ingredient_grams(amount_text, name)
        if "油" in name:
            kind = "oil"
        elif any(word in name for word in ("五花肉", "猪肉", "排骨", "肉末", "肉")):
            kind = "pork"
        elif "鸡" in name:
            kind = "chicken"
        elif "牛" in name:
            kind = "beef"
        elif any(word in name for word in ("鱼", "鲈鱼", "鲤鱼")):
            kind = "fish"
        elif "虾" in name:
            kind = "shrimp"
        elif any(word in name for word in ("豆腐", "豆干", "豆皮")):
            kind = "tofu"
        elif "蛋" in name:
            kind = "egg"
        elif any(word in name for word in ("米", "饭")):
            kind = "rice"
        elif "面" in name:
            kind = "noodle"
        elif any(word in name for word in ("盐", "生抽", "老抽", "酱油", "蚝油")):
            kind = "salt"
        elif any(word in name for word in ("糖", "冰糖")):
            kind = "sugar"
        else:
            kind = "vegetable"
        factor = grams / 100
        if kind == "sugar":
            total["energy_kcal"] += 400 * factor
            total["carbs_g"] += 100 * factor
            total["sugar_g"] += 95 * factor
            continue
        table = NUTRITION.get(kind, NUTRITION["vegetable"])
        total["energy_kcal"] += table["energy"] * factor
        total["protein_g"] += table["protein"] * factor
        total["fat_g"] += table["fat"] * factor
        total["carbs_g"] += table["carbs"] * factor
        total["sodium_mg"] += table["sodium"] * factor
        total["sugar_g"] += table["sugar"] * factor
    return {key: round(value, 1) for key, value in total.items()}


def _ensure_recipe_quality(recipe: dict) -> dict:
    versions = recipe.get("versions") if isinstance(recipe.get("versions"), dict) else _normalize_versions(recipe)
    for key in ("novice", "chef"):
        version = versions.setdefault(key, {"steps": [], "tips": []})
        steps = [str(item).strip() for item in version.get("steps") or [] if str(item).strip()]
        # 模型偶尔只给两步；用通用阶段补齐到可操作的新手教程，至少 6 步
        if len(steps) < 6:
            for generic in GENERIC_STEPS:
                if len(steps) >= 6:
                    break
                if generic not in steps:
                    steps.append(generic)
        version["steps"] = steps[:20]
    recipe["versions"] = versions
    if not recipe.get("steps"):
        recipe["steps"] = versions["novice"]["steps"]
    nutrition = recipe.get("nutrition") if isinstance(recipe.get("nutrition"), dict) else {}
    values = [float(nutrition.get(key) or 0) for key in NUTRITION_FIELDS]
    if not values or not any(value > 0 for value in values):
        recipe["nutrition"] = _estimate_nutrition([str(item) for item in recipe.get("ingredients") or []])
    return recipe


class RecipeVersionModel(BaseModel):
    steps: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


class RecipeVersionsModel(BaseModel):
    novice: RecipeVersionModel
    chef: RecipeVersionModel


class AiRecipeModel(BaseModel):
    title: str
    intro: str = ""
    ingredients: list[str] = Field(default_factory=list, min_length=1)
    steps: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    safety: list[str] = Field(default_factory=list)
    nutrition: dict = Field(default_factory=dict)
    versions: RecipeVersionsModel | None = None


class RecipeOptionModel(BaseModel):
    title: str
    time: str = ""
    difficulty: str = "新手"
    main_ingredients: list[str] = Field(default_factory=list)
    safety: str = ""


class AiRecipeOptionsModel(BaseModel):
    subject: str = ""
    options: list[RecipeOptionModel] = Field(default_factory=list, min_length=2)


def _normalize(text: str) -> str:
    return re.sub(r"[\s*·,，。.、：:；;（）()\-—]+", "", text or "")


def lookup_recipe(dish: str) -> dict | None:
    target = _normalize(dish)
    if not target:
        return None
    for recipe in RECIPE_EXAMPLES:
        names = [recipe["title"], *recipe.get("aliases", [])]
        for name in names:
            normalized = _normalize(name)
            if normalized and (normalized == target or normalized in target or target in normalized):
                return recipe
    return None


def _clean_dish(text: str) -> str:
    value = text
    for word in CLEAN_WORDS:
        value = value.replace(word, "")
    return value.strip(" ：:，,。.、")


DISH_WORDS = (
    "豆腐", "鱼", "鸡", "鸭", "鹅", "肉", "排骨", "牛", "羊", "猪", "虾", "蟹", "蛋",
    "菜", "瓜", "土豆", "番茄", "西红柿", "茄子", "豆角", "藕", "蘑菇", "菌", "面", "饭", "汤",
)
DISH_STOP_WORDS = ("推荐", "怎么", "什么", "为什么", "安全", "过期", "营养", "热量", "可以", "能不能", "吗", "呢", "做法")


def _looks_like_dish_name(text: str) -> bool:
    value = (text or "").strip()
    if not (2 <= len(value) <= 14):
        return False
    if any(word in value for word in DISH_STOP_WORDS):
        return False
    return any(word in value for word in DISH_WORDS)


def extract_dish(question: str) -> str:
    text = question.strip()
    bought = re.search(r"(?:我买了|买了|家里有|冰箱里有)(?:一[条只个块斤]?|一些|点)?([^\s，,。.？?！!]{1,14})", text)
    if bought:
        dish = _clean_dish(bought.group(1))
        if dish:
            return dish
    selected = re.search(r"我选[：: ]*([^\s，,。.？?！!]{1,20})", text)
    if selected:
        dish = _clean_dish(selected.group(1))
        if dish:
            return dish
    patterns = [
        r"(.+?)(?:怎么做|如何做|怎样做|的做法|做法|教程|烹饪步骤|步骤)",
        r"(?:怎么做|如何做|怎样做|怎么炒|怎么煮|怎么蒸|怎么炖|怎么烤|怎么煎|怎么凉拌)(?:一道|一个|一份)?(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            dish = _clean_dish(match.group(1))
            if dish and len(dish) <= 20:
                return dish
    for recipe in RECIPE_EXAMPLES:
        for name in [recipe["title"], *recipe.get("aliases", [])]:
            if name and name in text:
                return recipe["title"]
    if _looks_like_dish_name(text):
        return _clean_dish(text)
    return ""


def is_cooking_question(question: str) -> bool:
    text = question.strip()
    if not text:
        return False
    if any(marker in text for marker in SAFETY_MARKERS):
        return False
    if any(pattern in text for pattern in COOKING_PATTERNS):
        return True
    # 只输入具体菜名（如“麻婆豆腐”）也直接进入食谱卡片
    return (lookup_recipe(text) is not None and len(text) <= 20) or _looks_like_dish_name(text)


CHEF_EXTRA_STEPS = [
    "大厨技巧：锅先烧到微微冒烟，再下冷油润锅，形成不粘面后再下主料。",
    "大厨技巧：主料下锅后先静置定型，不要立刻频繁翻动，避免出水、粘锅。",
    "大厨技巧：出锅前转大火收汁或勾薄芡，让酱汁均匀挂在食材上，再淋少量明油提亮。",
]


def _normalize_versions(recipe: dict) -> dict:
    raw = recipe.get("versions")
    if isinstance(raw, dict):
        novice = raw.get("novice") if isinstance(raw.get("novice"), dict) else {}
        chef = raw.get("chef") if isinstance(raw.get("chef"), dict) else {}
        novice_steps = [str(item) for item in novice.get("steps") or [] if str(item).strip()]
        chef_steps = [str(item) for item in chef.get("steps") or [] if str(item).strip()]
        if novice_steps and chef_steps:
            return {
                "novice": {
                    "steps": novice_steps,
                    "tips": [str(item) for item in novice.get("tips") or [] if str(item).strip()],
                },
                "chef": {
                    "steps": chef_steps,
                    "tips": [str(item) for item in chef.get("tips") or [] if str(item).strip()],
                },
            }
    base_steps = [str(item) for item in recipe.get("steps") or [] if str(item).strip()] or list(GENERIC_STEPS)
    tips = [str(item) for item in recipe.get("tips") or [] if str(item).strip()]
    chef_steps = base_steps + CHEF_EXTRA_STEPS
    return {
        "novice": {"steps": base_steps, "tips": tips},
        "chef": {
            "steps": chef_steps,
            "tips": tips + ["大厨版补充：所有“适量”都要先少放，尝味后再补；装盘前用干净布擦净盘边。"],
        },
    }


def _with_versions(recipe: dict) -> dict:
    result = dict(recipe)
    result["versions"] = _normalize_versions(result)
    if not result.get("steps"):
        result["steps"] = result["versions"]["novice"]["steps"]
    if not result.get("tips"):
        result["tips"] = result["versions"]["novice"]["tips"]
    return result


def _sections(recipe: dict, *, source_label: str) -> tuple[list[dict], str]:
    ingredients = "\n".join(f"· {household_service.enrich_ingredient_line(item)}" for item in recipe.get("ingredients", []))
    versions = _normalize_versions(recipe)
    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(versions["novice"]["steps"], start=1))
    tips = "\n".join(f"· {item}" for item in versions["novice"]["tips"])
    safety = "\n".join(f"· {item}" for item in recipe.get("safety", []))
    sections = []
    if recipe.get("intro"):
        sections.append({"key": "intro", "label": "份量与难度", "text": recipe["intro"]})
    if ingredients:
        sections.append({"key": "ingredients", "label": "食材与调料", "text": ingredients})
    if steps:
        sections.append({"key": "steps", "label": "新手分步做法", "text": steps})
    if tips:
        sections.append({"key": "tips", "label": "新手易错点", "text": tips})
    if safety:
        sections.append({"key": "safety", "label": "食品安全提醒", "text": safety})
    sections.append({"key": "source", "label": "说明", "text": source_label})
    content = "\n\n".join(f"{item['label']}：\n{item['text']}" for item in sections)
    return sections, content


def is_recipe_recommendation(question: str) -> bool:
    text = question or ""
    return ("推荐" in text and ("做法" in text or "吃法" in text or "怎么" in text)) or "有什么做法" in text


def _option_fallback(dish: str) -> list[dict]:
    subject = dish or "这道食材"
    if "鱼" in subject or "虾" in subject or "蟹" in subject:
        titles = [("红烧", "30分钟"), ("清蒸", "20分钟"), ("糖醋", "35分钟")]
    elif any(word in subject for word in ("肉", "鸡", "鸭", "牛", "羊", "排")):
        titles = [("红烧", "40分钟"), ("清炒", "20分钟"), ("炖汤", "50分钟")]
    elif any(word in subject for word in ("蛋",)):
        titles = [("番茄炒", "15分钟"), ("蒸", "15分钟"), ("做汤", "10分钟")]
    elif any(word in subject for word in ("菜", "瓜", "豆", "菌", "菇", "笋")):
        titles = [("清炒", "10分钟"), ("蒜蓉", "10分钟"), ("凉拌", "8分钟")]
    else:
        titles = [("清炒", "15分钟"), ("红烧", "30分钟"), ("做汤", "25分钟")]
    options = []
    for prefix, duration in titles:
        title = f"{prefix}{subject}" if prefix != "做汤" else f"{subject}汤"
        options.append(
            {
                "title": title,
                "time": duration,
                "difficulty": "新手",
                "main_ingredients": [subject, "姜", "葱"],
                "safety": "食材彻底加热，生熟分开；鱼类去鳞去内脏，肉类中心熟透。",
            }
        )
    return options


def _recommend_options(question: str, dish: str) -> tuple[str, list[dict], str | None]:
    subject = dish or "这道食材"
    ai_error = None
    try:
        from .assistant_service import _chat

        raw = _chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是家庭菜谱教练。用户有一种食材，想知道可以怎么做。"
                        "只返回 JSON：{subject, options[{title,time,difficulty,main_ingredients,safety}]}；"
                        "options 必须 2-3 个，只是做法选项，不要展开完整步骤；"
                        "每个选项给菜名、预计耗时、难度、主要食材和一句核心安全提醒。不得编造品牌或标准。"
                    ),
                },
                {"role": "user", "content": f"食材：{subject}\n用户问题：{question}\n请给我 2-3 个家常做法选择。"},
            ]
        )
        text = raw.strip()
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        if match:
            text = match.group(1).strip()
        data = AiRecipeOptionsModel.model_validate(json.loads(text))
        options = [item.model_dump() for item in data.options[:3]]
        if len(options) >= 2:
            return data.subject or subject, options, None
        ai_error = "AI 返回的选项少于 2 个"
    except PydanticValidationError as exc:
        ai_error = f"AI 选项格式不合法：{exc.__class__.__name__}"
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        ai_error = f"AI 选项解析失败：{exc.__class__.__name__}"
    except Exception as exc:  # noqa: BLE001
        ai_error = f"AI 选项生成失败：{exc.__class__.__name__}"
    return subject, _option_fallback(subject), ai_error


def _recipe_summary(recipe: dict) -> dict:
    intro = str(recipe.get("intro") or "")
    steps_text = " ".join(str(item) for item in recipe.get("steps") or [])
    total = re.search(r"(?:总耗时|总时间|全程|总共|大约|约)[^\d]{0,8}(\d+)\s*分钟", intro)
    all_minutes = [int(value) for value in re.findall(r"(\d+)\s*分钟", intro + " " + steps_text)]
    all_minutes = [value for value in all_minutes if 0 < value <= 180]
    if total:
        minutes = f"约{total.group(1)}分钟"
    elif all_minutes:
        minutes = f"约{max(all_minutes)}分钟"
    else:
        minutes = "约30分钟"
    names = []
    for line in recipe.get("ingredients") or []:
        name = re.split(r"[\s：:（(]", str(line).strip("· "), maxsplit=1)[0]
        if name and name not in names:
            names.append(name)
    return {
        "title": str(recipe.get("title") or ""),
        "time": minutes,
        "difficulty": "新手" if "新手" in intro or "简单" in intro else "家常",
        "main_ingredients": names[:4],
        "safety": " ".join(str(item) for item in (recipe.get("safety") or [])[:2])[:180],
    }


def _ai_recipe(dish: str, history: str) -> tuple[dict | None, str | None]:
    try:
        from .assistant_service import _chat
    except Exception:
        return None, "大模型不可用"
    system = (
        "你是面向完全不会做饭的新手的家常菜教练。根据菜名给出可执行的做法，"
        "必须写清楚份量、火候、时间和判断熟没熟的视觉标准；不要编造品牌、标准号或营养数据。"
        "只输出 JSON：{title,intro,ingredients[],safety[],nutrition{energy_kcal,protein_g,fat_g,carbs_g,sodium_mg,sugar_g},versions:{novice:{steps[],tips[]},chef:{steps[],tips[]}}}。"
        "必须同时给新手版和大厨版两套步骤：novice 用最稳、最不容易翻车的做法；chef 用专业技巧（火候、锅气、收汁/勾芡、静置等），两套步骤都要能独立照着做。"
        "ingredients 必须同时包含主料和辅料，不能只写主料；适用时列出葱、姜、蒜、冰糖、老抽、料酒、食用油等调料，用 2 人份、必须优先用中国家庭厨房单位并在括号附克数：调料「1小勺（约3g）」「半汤勺（约8ml）」，主食「一小碗（约150g）」或「一杯（电饭煲量杯，约133g）」，蛋/肉/菜「2个（约100g）」「1个掌心大小（约100g）」「一小把（约100g）」；严禁茶匙、汤匙、盎司等西式单位；"
        "每套步骤必须至少 8 步（绝不能少于 5 步），步骤正文合计不少于 180 个汉字，严禁偷懒简写或只给 2 步；必须依次覆盖备料、腌制/焯水、起锅烧油、炒香/炒糖色、下主料、加入核心调料、火候控制（如小火炖煮40分钟）、大火收汁和熟度判断，要像真正的新手教程，每一步写清动作、时间、火候和视觉状态；"
        "nutrition 必须根据食材和调料真实属性估算，五花肉、生抽、盐等不能给出 0；六个字段都要有合理数值，不得全部为 0；"
        "novice.tips 写新手易错点；chef.tips 写专业提升点；safety 写生熟分开、彻底加热、过敏原等。"
        "nutrition 是估算值，不要声称治疗作用；数值要符合常见食材常识（例如五花肉 300g 的蛋白质和脂肪不可能为 0）。"
    )
    user = f"菜名：{dish}\n"
    if history:
        user += f"对话上文（仅供理解指代）：\n{history}\n"
    user += "请同时给新手版和大厨版两套完整步骤。"
    try:
        raw = _chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        text = raw.strip()
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        if match:
            text = match.group(1).strip()
        data = json.loads(text)
        recipe = AiRecipeModel.model_validate(data)
        return recipe.model_dump(), None
    except (PydanticValidationError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return None, f"AI 菜谱格式不合法：{exc.__class__.__name__}"
    except Exception as exc:  # 网络/模型失败
        return None, f"AI 菜谱生成失败：{exc.__class__.__name__}"


def maybe_answer(question: str, history_text: str = "") -> dict | None:
    if not is_cooking_question(question):
        return None
    dish = extract_dish(question)
    context_used = False
    if not dish and history_text:
        # “那具体怎么做？”：从上一轮对话里找最近提到的菜名
        for recipe in RECIPE_EXAMPLES:
            for name in [recipe["title"], *recipe.get("aliases", [])]:
                if name and name in history_text:
                    dish = recipe["title"]
                    context_used = True
                    break
            if dish:
                break
    if not dish:
        dish = "这道菜"
    if is_recipe_recommendation(question):
        subject, options, options_error = _recommend_options(question, dish if dish != "这道菜" else "")
        return {
            "mode": "recipe_options",
            "title": f"{subject}的推荐做法",
            "answer": f"用{subject}可以做 {len(options)} 种家常做法，先选一个，我再展开详细步骤。",
            "options": options,
            "subject": subject,
            "sections": [],
            "source_label": "AI/规则生成的候选做法",
            "context_used": context_used,
            "ai_error": options_error,
        }

    curated = lookup_recipe(dish)
    if curated:
        curated = _with_versions(curated)
        sections, content = _sections(curated, source_label="本站家常菜谱整理（新手版/大厨版），不是权威菜谱或食品安全结论")
        return {
            "mode": "recipe",
            "title": curated["title"],
            "answer": content,
            "sections": sections,
            "source_label": "本站家常菜谱整理（新手版/大厨版）",
            "recipe": curated,
            "versions": curated["versions"],
            "context_used": context_used,
            "ai_error": None,
        }
    ai_recipe, ai_error = _ai_recipe(dish, history_text)
    if ai_recipe:
        ai_recipe = _with_versions(ai_recipe)
        sections, content = _sections(
            ai_recipe,
            source_label="AI 按常见家常做法生成，未引用本站知识库；请结合食材实际调整",
        )
        return {
            "mode": "recipe_ai",
            "title": ai_recipe.get("title") or dish,
            "answer": content,
            "sections": sections,
            "source_label": "AI 烹饪步骤（新手版/大厨版）",
            "recipe": ai_recipe,
            "versions": ai_recipe["versions"],
            "context_used": context_used,
            "ai_error": None,
        }
    generic = {
        "title": f"{dish}：新手通用做法框架",
        "intro": "AI 暂时不可用，先给你一套不会翻车的新手框架；具体食材和调味可以再问我。",
        "ingredients": [
            "主料：按菜名准备，肉类约 150–200g/人，蔬菜约 200–250g/人",
            "基础调料：食用油、盐、生抽；葱姜蒜按口味准备",
        ],
        "steps": GENERIC_STEPS,
        "tips": [
            "所有食材先切好、调料先打开，再开火。",
            "不确定熟没熟时，切开最厚的一块看中心是否变色、是否还有血水。",
            "先少放盐，尝味后再补，避免一次做咸。",
        ],
        "safety": [
            "生肉、生蛋和熟食分开处理，案板刀具用后洗净。",
            "肉类、蛋类必须彻底加热；剩菜及时冷藏并热透。",
        ],
    }
    generic = _with_versions(generic)
    sections, content = _sections(generic, source_label="通用新手/大厨框架；AI 不可用时生成，未针对具体菜谱")
    return {
        "mode": "recipe",
        "title": generic["title"],
        "answer": content,
        "sections": sections,
        "source_label": "通用新手/大厨框架",
        "recipe": generic,
        "versions": generic["versions"],
        "context_used": context_used,
        "ai_error": ai_error,
    }


__all__ = ["maybe_answer", "is_cooking_question", "extract_dish", "lookup_recipe"]
