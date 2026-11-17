"""食材归类规则：常备调料 / 生鲜 / 无需采购。

调味料在业务上视为“常备物资”：做菜不扣库存、不产生过期提醒；
购物清单里单独归为“建议囤货”，不跟生鲜一起即时配送。
"""
from __future__ import annotations

AROMATIC_KEYWORDS = ("葱", "姜", "蒜", "辣椒", "花椒", "八角", "桂皮", "香叶", "香菜", "小米椒", "干辣椒")
STAPLE_KEYWORDS = (
    "油", "盐", "酱油", "生抽", "老抽", "蚝油", "醋", "料酒", "淀粉", "糖",
    "胡椒", "花椒", "八角", "桂皮", "香叶", "味精", "鸡精", "豆瓣酱", "番茄酱",
    "辣椒酱", "芝麻", "孜然", "咖喱", "五香粉", "十三香", "香油", "腐乳", "豆豉",
)
NON_PURCHASE_KEYWORDS = ("清水", "水")
FRESH_CATEGORIES = {"vegetable", "meat", "seafood", "fruit", "egg_dairy", "staple", "grain", "bean"}


def is_staple(name: str, category: str | None = None) -> bool:
    """油盐酱醋淀粉等常备调料。"""
    text = (name or "").strip()
    if not text:
        return False
    if category == "condiment":
        return True
    if category in FRESH_CATEGORIES:
        # “油麦菜”这类菜名不能被“油”误判
        return False
    return any(word in text for word in STAPLE_KEYWORDS)


def is_aromatic(name: str, category: str | None = None) -> bool:
    text = (name or "").strip()
    if category in {"vegetable", "meat", "seafood", "egg_dairy", "staple", "fruit"}:
        # “大葱”“生姜”仍是蔬菜/食材，但做主菜时按辅料处理
        pass
    return any(word in text for word in AROMATIC_KEYWORDS)


def classify_role(name: str, category: str | None = None) -> str:
    """main：主料；auxiliary：葱姜蒜/油盐酱醋等辅料。"""
    text = (name or "").strip()
    if is_aromatic(text, category) or is_staple(text, category) or is_non_purchase(text):
        return "auxiliary"
    return "main"


def is_non_purchase(name: str) -> bool:
    """清水这类不用买、也不应扣库存的项。"""
    text = (name or "").strip()
    return any(word in text for word in NON_PURCHASE_KEYWORDS)


__all__ = ["is_staple", "is_non_purchase", "is_aromatic", "classify_role"]
