"""集中管理的标签核查规则库。

设计原则：
1. 规则 = 元数据（可展示的依据）+ 判定函数（见 services/checker.py）；
2. 所有规则在此集中登记，新增/修改规则只需改这一处，版本号随规则集升级；
3. 依据一律使用"标准名称"级别的引用，不抄录条款编号与原文，避免误导；
4. 无法仅凭图片判断的事项，一律标记为"需要进一步核实"而非"发现问题"。
"""
from __future__ import annotations

RULESET = {
    "version": "2025.11",
    "updated_at": "2025-11-01",
    "name": "智膳·标签辅助核查规则集",
    "disclaimer": (
        "本规则集为工程化的辅助检查逻辑，依据名称仅用于指引用户查阅标准，"
        "系统未收录标准原文、不引用条款编号，也不构成合规判定。"
        "最终结论请以现行有效的标准文本与监管要求为准。"
    ),
}

_BASIS_NOTE = "依据名称引用，未收录原文；条款细节请查阅现行标准正式发布文本。"

RULES: list[dict] = [
    # ---------------- 字段完整性 ----------------
    {
        "id": "FIELD_FOOD_NAME",
        "title": "食品名称",
        "category": "字段完整性",
        "description": "检查本次识别范围（图片可见区域）内是否能读到食品名称。",
        "basis": "预包装食品标签通常应在醒目位置标示食品名称。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "若包装正面未拍入画面，请补拍正面主展示面后重新识别。",
    },
    {
        "id": "FIELD_INGREDIENTS",
        "title": "配料表",
        "category": "字段完整性",
        "description": "检查是否识别到配料表/配料说明文字。",
        "basis": "预包装食品标签通常应标示配料表。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "请确认配料表所在面已拍全；若确实无法辨认，可手动输入配料表继续分析。",
    },
    {
        "id": "FIELD_NUTRITION",
        "title": "营养成分表",
        "category": "字段完整性",
        "description": "检查是否识别到营养成分表及其数值。",
        "basis": "预包装食品营养标签通常以表格形式标示能量与核心营养素。",
        "source": {
            "name": "GB 28050《食品安全国家标准 预包装食品营养标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "请补拍营养成分表区域的清晰照片，或手动填写关键数值。",
    },
    {
        "id": "FIELD_PRODUCER",
        "title": "生产者信息",
        "category": "字段完整性",
        "description": "检查是否识别到生产者/制造商名称或地址信息。",
        "basis": "标签通常应标示生产者名称、地址和联系方式等信息。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "请检查包装上是否有生产者信息，并确认是否被漏拍。",
    },
    {
        "id": "FIELD_NET_CONTENT",
        "title": "净含量",
        "category": "字段完整性",
        "description": "检查是否识别到净含量及其单位。",
        "basis": "预包装食品标签通常应在显著位置标示净含量。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "请补拍含净含量标注的区域。",
    },
    {
        "id": "FIELD_DATE",
        "title": "生产日期与保质期",
        "category": "日期",
        "description": "检查生产日期与保质期是否可读，并做日期逻辑推算。",
        "basis": "标签通常应清晰标示生产日期与保质期（或到期日期）。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "请补拍日期喷码区域；日期字迹模糊时请以实物清晰度为准人工确认。",
    },
    {
        "id": "FIELD_STORAGE",
        "title": "贮存条件",
        "category": "字段完整性",
        "description": "检查是否识别到贮存条件说明。",
        "basis": "标签通常应标示贮存条件（尤其对需低温保存的食品）。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "请确认包装上是否标注贮存条件，或是否被漏拍。",
    },
    {
        "id": "FIELD_ALLERGEN",
        "title": "致敏物质提示",
        "category": "字段完整性",
        "description": "检查是否识别到致敏物质（过敏原）提示信息。",
        "basis": "含常见致敏物质的食品宜通过提示语等方式告知消费者。是否强制及具体形式以现行标准与法规为准。",
        "source": {
            "name": "预包装食品标签致敏物质标示相关要求（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "对过敏人群，请直接查看包装上是否含致敏物质提示，必要时联系厂家确认。",
    },
    {
        "id": "FIELD_STANDARD_NO",
        "title": "产品标准号",
        "category": "字段完整性",
        "description": "检查产品标准号是否存在，并做格式层面的粗检。",
        "basis": "标签通常应标示产品所执行的标准号。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "若标准号不清晰，可记录后可到标准信息公共服务平台人工查询。",
    },
    # ---------------- 日期逻辑 ----------------
    {
        "id": "DATE_FORMAT",
        "title": "日期格式可解析性",
        "category": "日期",
        "description": "尝试解析生产日期为年-月-日，无法解析时提示人工确认。",
        "basis": "日期应清晰可读、避免歧义；本系统仅做可解析性检查。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "请在识别校正页把日期改为「YYYY-MM-DD」格式后重新分析。",
    },
    {
        "id": "DATE_FUTURE",
        "title": "生产日期是否晚于今天",
        "category": "日期",
        "description": "若解析出的生产日期晚于当前日期，提示疑似问题。",
        "basis": "生产日期不应晚于购买/查看日期，晚于当前日期属于需要核实的异常。",
        "source": {
            "name": "平台核查逻辑（日期合理性推断）",
            "type": "editorial",
            "note": "该规则为通用逻辑推断，不引用具体标准条款。",
        },
        "todo": "请核对实物日期喷码，并确认手机系统日期是否正确。",
    },
    {
        "id": "DATE_EXPIRY",
        "title": "保质期推算",
        "category": "日期",
        "description": "用生产日期 + 保质期推算到期日期，并提示是否已过期或临近到期。",
        "basis": "到期日期 = 生产日期 + 保质期（按月/日/年换算）。",
        "source": {
            "name": "平台核查逻辑（日期算术推算）",
            "type": "editorial",
            "note": "按月推算时按日历月处理，可能与厂商实际计算口径存在差异。",
        },
        "todo": "若包装上直接印有到期日期，请以实物标注为准。",
    },
    {
        "id": "DATE_STORAGE_MATCH",
        "title": "贮存条件与保质期一致性提示",
        "category": "日期",
        "description": "若标注需冷藏/冷冻但图片中未见相关说明位置，提示人工核对。",
        "basis": "需低温贮存的食品，其贮存条件描述与销售环境应一致。",
        "source": {
            "name": "平台核查逻辑（条件匹配提示）",
            "type": "editorial",
            "note": "系统无法判断实际贮存环境，仅作提示。",
        },
        "todo": "请确认购买与存放环境的温度是否符合包装标注的贮存条件。",
    },
    # ---------------- 单位与数值 ----------------
    {
        "id": "NUTRI_UNIT",
        "title": "营养成分单位识别",
        "category": "单位与数值",
        "description": "检查营养素是否带有可识别的单位（能量 kJ/kcal，蛋白质/脂肪/碳水 g，钠 mg）。",
        "basis": "常见标示习惯：能量用 kJ（可并列 kcal），核心营养素用 g，钠用 mg。",
        "source": {
            "name": "GB 28050《食品安全国家标准 预包装食品营养标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "请在识别校正页补齐单位后重新分析。",
    },
    {
        "id": "NUTRI_RANGE",
        "title": "营养成分数值范围",
        "category": "单位与数值",
        "description": "检查数值是否为负、是否出现不可能的极大值（如每 100g 中单营养素 >100g）。",
        "basis": "每 100g 食品中单一营养素质量不应超过 100g。",
        "source": {
            "name": "平台核查逻辑（物理量合理性）",
            "type": "editorial",
            "note": "该规则仅用于发现明显的 OCR 误读，不评价食品本身。",
        },
        "todo": "若数值明显不合理，多为识别错误，请对照实物更正。",
    },
    {
        "id": "NUTRI_SUM",
        "title": "三大营养素合计",
        "category": "单位与数值",
        "description": "蛋白质 + 脂肪 + 碳水化合物合计是否超过 100g/100g。",
        "basis": "按每 100g 计时，三大营养素质量之和不应显著超过 100g。",
        "source": {
            "name": "平台核查逻辑（质量守恒）",
            "type": "editorial",
            "note": "允许一定误差，超过 105g 时才提示。",
        },
        "todo": "请确认各数值的单位与基准（每 100g / 每份）是否被正确识别。",
    },
    {
        "id": "NUTRI_ENERGY",
        "title": "能量与三大营养素折算一致性",
        "category": "单位与数值",
        "description": "用蛋白质×17 + 脂肪×37 + 碳水化合物×17 (kJ/g) 估算能量，与标示能量比较。",
        "basis": "食品能量主要由蛋白质、脂肪、碳水化合物折算而来（Atwater 系数：17/37/17 kJ/g）。",
        "source": {
            "name": "营养学通用能量折算系数（教材级常识）",
            "type": "textbook",
            "note": "不同食物成分的折算系数存在差异（如膳食纤维、酒精），偏差属正常现象。",
        },
        "todo": "若偏差较大，请核对能量单位是 kJ 还是 kcal，以及是否为「每份」数值。",
    },
    {
        "id": "NUTRI_NRV",
        "title": "营养素参考值占比",
        "category": "单位与数值",
        "description": "基于平台内置 NRV 参考值计算占比，并与标示 NRV% 做粗对比。",
        "basis": "NRV% 用于表达每份/每 100g 食品中营养素占每日参考值的比例。",
        "source": {
            "name": "GB 28050《食品安全国家标准 预包装食品营养标签通则》NRV 概念（名称引用）",
            "type": "standard_name",
            "note": "平台内置 NRV 数值仅供估算，请以标准附录的现行数值为准。",
        },
        "todo": "NRV% 以包装标示为准，本系统结果仅作理解辅助。",
    },
    {
        "id": "NUTRI_HIGH_SODIUM",
        "title": "钠含量提示",
        "category": "单位与数值",
        "description": "钠 ≥ 600mg/100g 时给出「钠含量较高」的饮食提示。",
        "basis": "该阈值为平台饮食提示阈值，用于帮助用户关注钠摄入，不代表食品不合格或不安全。",
        "source": {
            "name": "平台提示阈值（非法规判定）",
            "type": "editorial",
            "note": "阈值可由维护者在 rules/label_rules.py 中调整。",
        },
        "todo": "需要控制钠摄入的人群，请结合每日总摄入量自行判断。",
    },
    # ---------------- 配料表 ----------------
    {
        "id": "INGREDIENT_PARSE",
        "title": "配料表可拆分性",
        "category": "配料表",
        "description": "检查配料表能否被拆分为独立配料项。",
        "basis": "配料表通常以顿号、逗号等分隔各配料。",
        "source": {
            "name": "平台核查逻辑（文本结构）",
            "type": "editorial",
            "note": "复合配料内的括号内容不会被展开为独立配料。",
        },
        "todo": "若拆分明显错误，请在校正页补全分隔符（如「、」）后重新分析。",
    },
    {
        "id": "INGREDIENT_ORDER",
        "title": "配料标示顺序",
        "category": "配料表",
        "description": "当配料表带百分比时，检查是否按加入量从高到低排列。",
        "basis": "配料表通常按加入量递减顺序排列（加入量不超过 2% 的配料可不按此顺序）。",
        "source": {
            "name": "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）",
            "type": "standard_name",
            "note": _BASIS_NOTE,
        },
        "todo": "若顺序异常，请核对是否 OCR 打乱了行序，或该配料属于可豁免排序的情形。",
    },
    {
        "id": "INGREDIENT_ADDITIVE",
        "title": "食品添加剂识别与解释",
        "category": "配料表",
        "description": "识别常见食品添加剂并给出客观用途解释，不作安全性判定。",
        "basis": "食品添加剂在标准允许的品种、范围与用量内使用是允许的；本系统仅解释用途。",
        "source": {
            "name": "GB 2760《食品安全国家标准 食品添加剂使用标准》（名称引用）",
            "type": "standard_name",
            "note": "系统不收录允许使用范围与限量数据，相关结论请查阅标准现行文本。",
        },
        "todo": "对添加剂有顾虑时，可查阅知识库条目或咨询专业人士，不必因「添加剂」字样直接判断为不安全。",
    },
    # ---------------- 识别质量 ----------------
    {
        "id": "OCR_CONFIDENCE",
        "title": "识别置信度",
        "category": "识别质量",
        "description": "统计低置信度字段，提示人工复核。",
        "basis": "OCR 对模糊、反光、倾斜文字的字形相似度较低，易出现错字。",
        "source": {
            "name": "平台核查逻辑（OCR 质量）",
            "type": "editorial",
            "note": "置信度来自 OCR 引擎输出，不同引擎不可直接横向比较。",
        },
        "todo": "请在识别校正页逐字核对低置信度字段。",
    },
    {
        "id": "OCR_COVERAGE",
        "title": "字段覆盖度",
        "category": "识别质量",
        "description": "统计本次识别到的关键字段数量，覆盖度过低时建议重拍。",
        "basis": "单张照片通常只能拍到包装的一个面，字段不全是正常现象。",
        "source": {
            "name": "平台核查逻辑（拍摄覆盖度）",
            "type": "editorial",
            "note": "图片未拍到不等于包装上没有该信息。",
        },
        "todo": "可分别拍摄包装正面、配料表、营养表与喷码区后逐张识别。",
    },
    {
        "id": "MODE_DISCLOSURE",
        "title": "分析模式披露",
        "category": "识别质量",
        "description": "检查本次分析是真实 AI、规则模式还是演示数据，并在报告中明确标注。",
        "basis": "演示模式与规则模式的结果不应被误认为真实大模型分析。",
        "source": {
            "name": "平台透明性要求",
            "type": "editorial",
            "note": "该系统级规则用于保证结果可追溯。",
        },
        "todo": "比赛演示时如需展示真实 AI 能力，请在 .env 中配置 AI_API_KEY 后重新分析。",
    },
]

RULES_BY_ID = {rule["id"]: rule for rule in RULES}

# 平台饮食提示阈值（集中可调）
THRESHOLDS = {
    "sodium_high_mg_per_100g": 600.0,
    "nrv": {
        "energy_kj": 8400.0,
        "protein_g": 60.0,
        "fat_g": 60.0,
        "carbohydrate_g": 300.0,
        "sodium_mg": 2000.0,
        "dietary_fiber_g": 25.0,
        "calcium_mg": 800.0,
        "sugar_g": None,
    },
    "energy_factors_kj_per_g": {"protein": 17.0, "fat": 37.0, "carbohydrate": 17.0},
    "energy_deviation_tolerance": 0.35,
    "nutrient_sum_tolerance_g": 105.0,
    "expiry_warning_days": 7,
}


def ruleset_public() -> dict:
    """提供给前端/文档展示的规则集元数据。"""
    categories: dict[str, list] = {}
    for rule in RULES:
        categories.setdefault(rule["category"], []).append(
            {
                "id": rule["id"],
                "title": rule["title"],
                "description": rule["description"],
                "basis": rule["basis"],
                "source": rule["source"],
                "todo": rule["todo"],
            }
        )
    return {
        "version": RULESET["version"],
        "updated_at": RULESET["updated_at"],
        "name": RULESET["name"],
        "disclaimer": RULESET["disclaimer"],
        "rule_count": len(RULES),
        "thresholds": THRESHOLDS,
        "categories": [{"name": k, "rules": v} for k, v in categories.items()],
    }
