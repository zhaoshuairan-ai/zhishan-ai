"""知识库扩展条目（第二批）。

与 knowledge_seed.py 保持同样的写作原则：
- 只写公认的、可追溯的概述性内容，不编造文献、条款与原文；
- 来源只写到「标准名称 / 官方机构」级别；
- 添加剂只解释用途与监管逻辑，不下「有毒 / 不安全」结论；
- verification_status 如实标注。
"""
from __future__ import annotations

from .knowledge_seed import (
    CFSA,
    NHC,
    STANDARD_2760,
    STANDARD_7718,
    STANDARD_28050,
    WIKI_OFFICIAL,
    WHO,
)

TEXTBOOK = "食品工艺学与营养学通用知识（教材级常识）"
GUIDE = "《中国居民膳食指南（2022）》（来源名称引用）"
CNSOC = "https://www.cnsoc.org/"
CFSA_URL = CFSA

EXTRA_KNOWLEDGE_ENTRIES: list[dict] = [
    # ================= 食品添加剂（续） =================
    {
        "slug": "nisin",
        "title": "乳酸链球菌素（Nisin）",
        "aliases": "乳酸链球菌素,Nisin,天然防腐剂",
        "category": "additive",
        "keywords": "防腐 天然 乳制品 罐头 肉制品",
        "summary": "由乳酸乳球菌发酵产生的天然防腐剂，主要抑制革兰氏阳性菌，常用于乳制品、肉制品与罐头。",
        "content": (
            "乳酸链球菌素是一种多肽类防腐剂，能被人体消化酶分解，安全性评估较为充分。"
            "它在 GB 2760 规定的食品类别和用量范围内使用是允许的，常与热处理配合延长保质期。"
        ),
        "usage_note": "属于「微生物来源」的防腐剂，看到它不必紧张，关注用量与适用类别即可。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 110,
    },
    {
        "slug": "natamycin",
        "title": "纳他霉素",
        "aliases": "纳他霉素,游霉素,防霉剂",
        "category": "additive",
        "keywords": "防霉 真菌 奶酪 肉制品 表面处理",
        "summary": "抗真菌防腐剂，主要抑制霉菌和酵母，常用于奶酪、肉制品表面防霉。",
        "content": (
            "纳他霉素对霉菌、酵母有效，对细菌作用弱，因此多用于「表面防霉」。"
            "它在 GB 2760 允许的类别与用量下使用是合规的，通常以喷洒或浸泡方式处理食品表面。"
        ),
        "usage_note": "糕点、奶酪表面偶尔能看到它，属于防霉用途。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 111,
    },
    {
        "slug": "dehydroacetate",
        "title": "脱氢乙酸钠",
        "aliases": "脱氢乙酸钠,脱氢醋酸钠,防腐剂",
        "category": "additive",
        "keywords": "防腐 霉菌 面包 糕点 腌菜",
        "summary": "广谱防腐剂，对霉菌和酵母效果较好，常见于糕点、腌菜等食品；使用范围以现行 GB 2760 为准。",
        "content": (
            "脱氢乙酸钠通过抑制微生物细胞代谢起到防腐作用，过去在面包糕点中使用较多。"
            "GB 2760 会随风险评估结果修订使用范围，选购时可以对照现行标准或产品标签判断。"
        ),
        "usage_note": "标准版本会更新，看到它时以现行 GB 2760 与该产品执行标准为准。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 112,
    },
    {
        "slug": "calcium-propionate",
        "title": "丙酸钙",
        "aliases": "丙酸钙,丙酸钠,防霉剂",
        "category": "additive",
        "keywords": "防霉 面包 糕点 丙酸",
        "summary": "常用的防霉剂，对霉菌抑制效果好，多用于面包、糕点延长货架期。",
        "content": (
            "丙酸钙在酸性条件下释放丙酸，抑制霉菌生长；它对酵母影响较小，因此适合面包发酵。"
            "在 GB 2760 允许的食品类别和用量范围内使用是合规的。"
        ),
        "usage_note": "面包配料表里比较常见，主要作用是防霉。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 113,
    },
    {
        "slug": "sodium-diacetate",
        "title": "双乙酸钠",
        "aliases": "双乙酸钠,二醋酸钠,防腐剂",
        "category": "additive",
        "keywords": "防腐 防霉 酸度 粮食 糕点",
        "summary": "兼具防腐与酸度调节作用的添加剂，常用于粮食制品、糕点与调味料防霉。",
        "content": (
            "双乙酸钠在食品中释放乙酸，抑制霉菌和部分细菌；它也可作为酸度调节剂使用。"
            "按 GB 2760 规定的类别和用量使用是允许的。"
        ),
        "usage_note": "看到它时可按「防霉 + 调酸」理解。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 114,
    },
    {
        "slug": "lactic-acid",
        "title": "乳酸",
        "aliases": "乳酸,酸度调节剂,发酵酸",
        "category": "additive",
        "keywords": "酸味 酸度调节 发酵 乳制品 饮料",
        "summary": "常见的酸度调节剂，提供温和酸味，也是乳酸菌发酵的天然产物。",
        "content": (
            "乳酸广泛存在于酸奶等发酵食品中，添加用途主要是调酸、调味与辅助防腐。"
            "它属于 GB 2760 允许的酸度调节剂，按生产需要适量使用。"
        ),
        "usage_note": "酸奶、饮料里的乳酸既是风味来源，也是合法的酸度调节剂。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 115,
    },
    {
        "slug": "malic-acid",
        "title": "苹果酸",
        "aliases": "苹果酸,DL-苹果酸,L-苹果酸",
        "category": "additive",
        "keywords": "酸味 酸度调节 饮料 糖果",
        "summary": "常用酸味剂，酸味比柠檬酸更持久，常用于饮料、糖果与果冻。",
        "content": (
            "苹果酸天然存在于苹果等水果中，作为酸度调节剂可增强风味、平衡甜味。"
            "在 GB 2760 允许范围内使用是合规的。"
        ),
        "usage_note": "与柠檬酸常一起出现，作用是让酸味更有层次。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 116,
    },
    {
        "slug": "hexametaphosphate",
        "title": "六偏磷酸钠",
        "aliases": "六偏磷酸钠,磷酸盐,水分保持剂",
        "category": "additive",
        "keywords": "水分保持 品质改良 肉制品 饮料 磷酸盐",
        "summary": "磷酸盐类水分保持剂，用于肉制品保水、饮料稳定与品质改良。",
        "content": (
            "六偏磷酸钠能螯合金属离子、帮助蛋白质保水，常与三聚磷酸钠等复配使用。"
            "磷酸盐在 GB 2760 中有明确的类别与限量要求，复合使用时需要合并计算。"
        ),
        "usage_note": "肉制品、海鲜制品里常见，属于「保水嫩化」用途。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 117,
    },
    {
        "slug": "sodium-tripolyphosphate",
        "title": "三聚磷酸钠",
        "aliases": "三聚磷酸钠,磷酸盐,保水剂",
        "category": "additive",
        "keywords": "保水 嫩化 肉制品 水产 磷酸盐",
        "summary": "常见磷酸盐类水分保持剂，帮助肉制品与水产保水、改善口感。",
        "content": (
            "三聚磷酸钠通过调节蛋白质电荷状态提高持水性，常与焦磷酸钠、六偏磷酸钠复配。"
            "磷酸盐的使用有类别与总量限制，具体以 GB 2760 为准。"
        ),
        "usage_note": "火腿、鱼丸等产品常见，属于工艺需要的保水剂。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 118,
    },
    {
        "slug": "sodium-alginate",
        "title": "海藻酸钠",
        "aliases": "海藻酸钠,褐藻胶,增稠剂",
        "category": "additive",
        "keywords": "增稠 稳定 凝胶 海藻 膳食纤维",
        "summary": "从褐藻中提取的天然增稠剂，遇钙离子可形成凝胶，常用于饮料、果冻与仿生食品。",
        "content": (
            "海藻酸钠属于水溶性膳食纤维类多糖，能增稠、稳定，并与钙离子交联成凝胶。"
            "它安全性较高，在 GB 2760 中按生产需要适量使用。"
        ),
        "usage_note": "名字里有「海藻」，本质是从海带等褐藻提取的多糖。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 119,
    },
    {
        "slug": "gellan-gum",
        "title": "结冷胶",
        "aliases": "结冷胶,高酰基结冷胶,增稠剂",
        "category": "additive",
        "keywords": "增稠 悬浮 饮料 稳定 凝胶",
        "summary": "微生物发酵产生的多糖增稠剂，悬浮能力强，常用于饮料防止分层沉淀。",
        "content": (
            "结冷胶由少动鞘氨醇单胞菌发酵产生，用量很低就能形成稳定悬浮体系。"
            "在 GB 2760 允许范围内使用是合规的。"
        ),
        "usage_note": "饮料里出现它，多半是为了让果粒或成分不沉淀。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 120,
    },
    {
        "slug": "guar-gum",
        "title": "瓜尔胶",
        "aliases": "瓜尔胶,瓜尔豆胶,增稠剂",
        "category": "additive",
        "keywords": "增稠 稳定 植物来源 饮料 冰淇淋",
        "summary": "从瓜尔豆中提取的天然增稠剂，增稠效率高，常用于饮料、冰淇淋与酱料。",
        "content": (
            "瓜尔胶主要成分是半乳甘露聚糖，属于水溶性膳食纤维，能显著提高黏度。"
            "它在 GB 2760 中按生产需要适量使用，安全性较高。"
        ),
        "usage_note": "植物来源增稠剂，看到它说明产品在控制口感与稳定性。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 121,
    },
    {
        "slug": "locust-bean-gum",
        "title": "刺槐豆胶",
        "aliases": "刺槐豆胶,槐豆胶,角豆胶",
        "category": "additive",
        "keywords": "增稠 稳定 协同 冰淇淋 酱料",
        "summary": "从刺槐豆中提取的天然增稠剂，与卡拉胶等复配时能形成更好的凝胶与口感。",
        "content": (
            "刺槐豆胶也是半乳甘露聚糖，单独增稠效果温和，但与黄原胶、卡拉胶协同作用明显。"
            "在 GB 2760 允许范围内使用是合规的。"
        ),
        "usage_note": "常和卡拉胶一起出现在冰淇淋、果冻配料表中。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 122,
    },
    {
        "slug": "acacia-gum",
        "title": "阿拉伯胶",
        "aliases": "阿拉伯胶,金合欢胶,乳化剂",
        "category": "additive",
        "keywords": "乳化 增稠 稳定 饮料 糖果",
        "summary": "从金合欢树分泌的天然胶体，兼具乳化与增稠作用，常用于饮料、糖果与香精载体。",
        "content": (
            "阿拉伯胶是历史悠久的天然食品胶，能稳定油水乳化体系、改善口感。"
            "在 GB 2760 中按生产需要适量使用，安全性较高。"
        ),
        "usage_note": "饮料、口香糖里常见，属于天然来源的乳化稳定剂。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 123,
    },
    {
        "slug": "gelatin",
        "title": "明胶",
        "aliases": "明胶,动物胶,吉利丁",
        "category": "additive",
        "keywords": "凝胶 增稠 动物来源 软糖 酸奶",
        "summary": "动物来源的蛋白质胶体，加热溶解、冷却成胶，常用于软糖、酸奶与慕斯。",
        "content": (
            "明胶由动物胶原蛋白部分水解制得，属于蛋白质而非碳水化合物胶体。"
            "它是素食者需要留意的成分，在 GB 2760 中按生产需要适量使用。"
        ),
        "usage_note": "素食人群注意：明胶是动物来源；同名「吉利丁」也是它。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 124,
    },
    {
        "slug": "modified-starch",
        "title": "变性淀粉",
        "aliases": "变性淀粉,乙酰化淀粉,羟丙基淀粉",
        "category": "additive",
        "keywords": "增稠 稳定 淀粉 耐热 耐酸",
        "summary": "经过物理或化学改性的淀粉，耐热、耐酸、抗剪切，比原淀粉更适合工业加工。",
        "content": (
            "变性淀粉通过交联、酯化等方式改变淀粉性质，使酱料、饮料在高温或酸性条件下保持稳定。"
            "它属于 GB 2760 允许的增稠剂，安全性评估充分；配料表可能写成具体名称（如乙酰化二淀粉磷酸酯）。"
        ),
        "usage_note": "看到「××淀粉」多为变性淀粉，作用类似增稠剂与稳定剂。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 125,
    },
    {
        "slug": "ethyl-maltol",
        "title": "乙基麦芽酚",
        "aliases": "乙基麦芽酚,增香剂,麦芽酚",
        "category": "additive",
        "keywords": "增香 甜香 焦糖香 用量低",
        "summary": "增香剂，少量使用即可增强甜香、焦糖香，常见于饮料、烘焙与肉制品。",
        "content": (
            "乙基麦芽酚本身有甜香和焦糖香，能提升整体香气、掩盖异味，用量通常很低。"
            "在 GB 2760 允许的类别和用量内使用是合规的。"
        ),
        "usage_note": "配料表末尾出现、用量很小，属于增香用途。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 126,
    },
    {
        "slug": "vanillin",
        "title": "香兰素",
        "aliases": "香兰素,香草醛,香草香精",
        "category": "additive",
        "keywords": "香草 增香 烘焙 冰淇淋 巧克力",
        "summary": "赋予香草风味的增香剂，天然存在于香草豆中，也可人工合成，广泛用于烘焙与冷饮。",
        "content": (
            "香兰素是最常见的增香剂之一，合成香兰素与天然提取物在风味物质上一致。"
            "在 GB 2760 允许范围内使用是合规的；「香草味」产品未必含天然香草提取物。"
        ),
        "usage_note": "配料表写「香兰素」不等于劣质，它是最常用的香草风味来源之一。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 127,
    },
    {
        "slug": "paprika-red",
        "title": "辣椒红",
        "aliases": "辣椒红,辣椒红色素,天然色素",
        "category": "additive",
        "keywords": "着色 天然色素 红色 辣椒 提取",
        "summary": "从辣椒中提取的天然红色素，用于食品着色，部分产品也带有轻微辣味。",
        "content": (
            "辣椒红属于天然着色剂，主要显色成分是辣椒红素，常用于肉制品、调味料与休闲食品。"
            "在 GB 2760 允许的类别和用量内使用是合规的。"
        ),
        "usage_note": "「天然色素」不等于完全无添加，仍是按标准使用的着色剂。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 128,
    },
    {
        "slug": "monascus-red",
        "title": "红曲红",
        "aliases": "红曲红,红曲米,红曲色素",
        "category": "additive",
        "keywords": "着色 红曲 发酵 腐乳 肉制品",
        "summary": "由红曲霉发酵产生的天然红色素，常用于腐乳、肉制品与糕点着色。",
        "content": (
            "红曲红是红曲霉发酵产物，属于微生物来源的天然色素，也可视为传统发酵食品的一部分。"
            "在 GB 2760 允许范围内使用是合规的；红曲本身也与他汀类物质相关，但食品着色用量很低。"
        ),
        "usage_note": "红腐乳的颜色常来自红曲，属于发酵来源色素。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 129,
    },
    {
        "slug": "tartrazine",
        "title": "柠檬黄",
        "aliases": "柠檬黄,酒石黄,合成色素",
        "category": "additive",
        "keywords": "着色 合成色素 黄色 饮料 糖果",
        "summary": "常见的合成黄色素，色泽稳定、成本低，在 GB 2760 允许的类别与限量内使用。",
        "content": (
            "柠檬黄属于合成着色剂，常用于饮料、糖果、蜜饯等。"
            "部分国家对合成色素有额外标识要求；我国按 GB 2760 管理，合规使用是允许的。"
        ),
        "usage_note": "颜色特别鲜艳的糖果、饮料常见；对色素敏感的人群可留意。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 130,
    },
    {
        "slug": "titanium-dioxide",
        "title": "二氧化钛",
        "aliases": "二氧化钛,钛白粉,白色着色剂",
        "category": "additive",
        "keywords": "着色 白色 不透明 糖果 口香糖",
        "summary": "白色着色剂，用于让食品呈现不透明的白色，常见于糖果、口香糖与糖衣。",
        "content": (
            "二氧化钛是白色颜料，在食品中作为着色剂使用，能让产品更白、更不透明。"
            "各国对其管理不同，我国按 GB 2760 的类别与限量管理；相关风险评估仍在持续更新。"
        ),
        "usage_note": "白色糖衣、口香糖里可能见到；关注最新标准动态即可。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 131,
    },
    {
        "slug": "tbhq",
        "title": "特丁基对苯二酚（TBHQ）",
        "aliases": "TBHQ,特丁基对苯二酚,抗氧化剂",
        "category": "additive",
        "keywords": "抗氧化 油脂 哈喇味 油炸食品",
        "summary": "油脂抗氧化剂，能延缓油脂氧化酸败，常用于油炸食品与含油食品。",
        "content": (
            "TBHQ 通过捕获自由基延缓油脂氧化，防止产生哈喇味；用量通常很低。"
            "在 GB 2760 规定的类别与限量内使用是合规的。"
        ),
        "usage_note": "方便面、油炸零食配料表末尾偶见，作用是防止油脂变哈喇。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 132,
    },
    {
        "slug": "glucono-delta-lactone",
        "title": "葡萄糖酸-δ-内酯",
        "aliases": "葡萄糖酸内酯,GDL,豆腐王",
        "category": "additive",
        "keywords": "凝固剂 酸度调节 豆腐脑 内酯",
        "summary": "温和的酸度调节剂与凝固剂，遇水缓慢水解成葡萄糖酸，常用于内酯豆腐与豆腐脑。",
        "content": (
            "葡萄糖酸-δ-内酯在水中缓慢释放酸，使大豆蛋白温和凝固，因此做出的豆腐更嫩。"
            "它属于 GB 2760 允许的酸度调节剂，按生产需要适量使用。"
        ),
        "usage_note": "「内酯豆腐」的嫩滑口感就来自它。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 133,
    },
    {
        "slug": "baking-powder",
        "title": "泡打粉（复合膨松剂）",
        "aliases": "泡打粉,膨松剂,复合膨松剂,无铝泡打粉",
        "category": "additive",
        "keywords": "膨松 烘焙 蛋糕 饼干 铝",
        "summary": "由碳酸氢钠与酸性盐组成的复合膨松剂，遇热或遇水产气使面点蓬松；选购时可选「无铝」配方。",
        "content": (
            "泡打粉受热释放二氧化碳，让蛋糕、饼干膨松；传统配方可能含铝盐，现行产品多有无铝配方。"
            "铝的摄入有每周耐受量，正规产品按标准使用是安全的，家庭烘焙可优先选无铝泡打粉。"
        ),
        "usage_note": "看配料表是否有「硫酸铝钾/铵」可判断含铝配方。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 134,
    },
    {
        "slug": "meat-tenderizer",
        "title": "嫩肉粉",
        "aliases": "嫩肉粉,木瓜蛋白酶,蛋白酶",
        "category": "additive",
        "keywords": "嫩化 酶 肉类 烹饪 蛋白酶",
        "summary": "以蛋白酶为主要成分的嫩化剂，分解肌肉蛋白让肉更嫩，常用于餐饮与家庭烹饪。",
        "content": (
            "嫩肉粉中的蛋白酶（如木瓜蛋白酶）能切断部分蛋白质肽键，使肉质变嫩。"
            "它属于加工助剂或酶制剂范畴，按说明使用即可；过量使用会让肉质发软发糊。"
        ),
        "usage_note": "腌肉时少量使用即可，过量反而影响口感。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 135,
    },
    # ================= 常见配料（续） =================
    {
        "slug": "rice",
        "title": "大米",
        "aliases": "大米,粳米,籼米,糯米",
        "category": "ingredient",
        "keywords": "主食 淀粉 碳水 谷物",
        "summary": "主要主食原料，以淀粉为主，提供碳水化合物与部分蛋白质；不同品种口感与直链淀粉比例不同。",
        "content": (
            "大米的主要成分是淀粉，蛋白质含量约 7% 左右，脂肪很低。"
            "糯米支链淀粉比例高、黏性强；籼米直链淀粉多、颗粒分明。搭配杂粮与豆类能提高膳食多样性。"
        ),
        "usage_note": "配料表靠前说明用量大，主食类产品尤其明显。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 140,
    },
    {
        "slug": "corn",
        "title": "玉米",
        "aliases": "玉米,玉米粒,甜玉米,玉米糁",
        "category": "ingredient",
        "keywords": "谷物 淀粉 膳食纤维 叶黄素",
        "summary": "常见谷物原料，提供淀粉、膳食纤维与叶黄素等，可做成玉米糁、玉米面与膨化食品。",
        "content": (
            "玉米以淀粉为主，含一定膳食纤维和类胡萝卜素；玉米胚芽含较多脂肪，玉米油即来自胚芽。"
            "膨化玉米制品通常油盐较高，需结合营养成分表判断。"
        ),
        "usage_note": "「玉米糁」「玉米淀粉」与「玉米」不是同一种配料，看名称区分。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 141,
    },
    {
        "slug": "oats",
        "title": "燕麦",
        "aliases": "燕麦,燕麦片,裸燕麦,莜麦",
        "category": "ingredient",
        "keywords": "谷物 膳食纤维 β-葡聚糖 早餐",
        "summary": "富含 β-葡聚糖等可溶性膳食纤维的谷物，常用于早餐麦片与代餐。",
        "content": (
            "燕麦的 β-葡聚糖有助于增加饱腹感、改善血脂，是公认的健康谷物之一。"
            "即食燕麦片升糖速度通常快于整粒燕麦，选择时看配料表是否额外加糖。"
        ),
        "usage_note": "「风味麦片」常加糖与植脂末，纯燕麦片配料通常只有燕麦。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 142,
    },
    {
        "slug": "corn-starch",
        "title": "玉米淀粉",
        "aliases": "玉米淀粉,生粉,粟粉",
        "category": "ingredient",
        "keywords": "淀粉 增稠 勾芡 油炸",
        "summary": "从玉米提取的淀粉，常用于勾芡、上浆与油炸挂糊，提供稠度与酥脆口感。",
        "content": (
            "玉米淀粉糊化后透明度较低、凝胶性强，适合勾芡和挂糊。"
            "它本质是碳水化合物，本身几乎不含蛋白质与脂肪。"
        ),
        "usage_note": "配料表里的「淀粉」若未注明来源，需要结合产品判断。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 143,
    },
    {
        "slug": "soybean",
        "title": "大豆",
        "aliases": "大豆,黄豆,青豆,黑豆",
        "category": "ingredient",
        "keywords": "植物蛋白 豆制品 致敏 大豆油",
        "summary": "优质植物蛋白来源，可制成豆腐、豆浆、酱油等；属于常见致敏原。",
        "content": (
            "大豆蛋白质含量高、氨基酸组成较均衡，是植物蛋白的重要来源。"
            "大豆及其制品是常见致敏原，标签通常会在致敏物质提示中标注「含有大豆」。"
        ),
        "usage_note": "对大豆过敏的人群需要同时留意酱油、豆粉等「隐形大豆」。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 144,
    },
    {
        "slug": "soy-protein-isolate",
        "title": "大豆分离蛋白",
        "aliases": "大豆分离蛋白,分离蛋白,植物蛋白",
        "category": "ingredient",
        "keywords": "植物蛋白 蛋白粉 肉制品 增重",
        "summary": "蛋白质含量很高的大豆制品，常用于肉制品、素肉与蛋白粉，属于大豆致敏原。",
        "content": (
            "大豆分离蛋白去除了大部分脂肪和碳水化合物，蛋白质含量通常在 90% 左右（以干基计）。"
            "它常被用于提升产品蛋白含量或改善质构，对大豆过敏者需回避。"
        ),
        "usage_note": "火腿、素鸡、蛋白棒里常见，是「提高蛋白含量」的原料。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 145,
    },
    {
        "slug": "peanut",
        "title": "花生",
        "aliases": "花生,花生仁,花生酱,落花生",
        "category": "ingredient",
        "keywords": "坚果 致敏 脂肪 黄曲霉毒素",
        "summary": "高脂肪坚果类配料，蛋白质与不饱和脂肪丰富；属于常见致敏原，储存不当有黄曲霉毒素风险。",
        "content": (
            "花生脂肪含量约 45%–50%，以不饱和脂肪酸为主，同时含有蛋白质与维生素 E。"
            "花生是重要致敏原，严重过敏可危及生命；受潮发霉的花生可能产生黄曲霉毒素，应避免食用。"
        ),
        "usage_note": "对花生过敏者要留意「可能含有花生」的交叉污染提示。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 146,
    },
    {
        "slug": "sesame",
        "title": "芝麻",
        "aliases": "芝麻,白芝麻,黑芝麻,芝麻酱",
        "category": "ingredient",
        "keywords": "坚果籽类 致敏 脂肪 钙",
        "summary": "高脂肪籽类配料，含钙与维生素 E，常用于糕点、调味酱；属于需要标注的致敏原之一。",
        "content": (
            "芝麻脂肪含量高，富含亚油酸、钙和维生素 E，磨碎后更易吸收。"
            "芝麻是常见致敏原，部分国家标准要求对含芝麻产品进行致敏提示。"
        ),
        "usage_note": "芝麻酱、烧饼、调味料里常见，过敏人群需留意。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 147,
    },
    {
        "slug": "honey",
        "title": "蜂蜜",
        "aliases": "蜂蜜,百花蜜,洋槐蜜,椴树蜜",
        "category": "ingredient",
        "keywords": "糖 果糖 葡萄糖 婴儿肉毒",
        "summary": "以果糖和葡萄糖为主的天然糖类，属于添加糖来源；1 岁以内婴儿不建议食用。",
        "content": (
            "蜂蜜主要成分是糖（果糖、葡萄糖为主）和水分，风味来自少量挥发性物质。"
            "蜂蜜可能含肉毒杆菌芽孢，1 岁以内婴儿肠道菌群未成熟，存在婴儿肉毒中毒风险。"
        ),
        "usage_note": "蜂蜜仍属于糖，控制添加糖摄入时也要计入。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 148,
    },
    {
        "slug": "high-fructose-corn-syrup",
        "title": "果葡糖浆",
        "aliases": "果葡糖浆,高果糖浆,F55,HFS",
        "category": "ingredient",
        "keywords": "添加糖 果糖 饮料 甜味",
        "summary": "由玉米淀粉制得的液体糖，含果糖与葡萄糖，甜度高、成本低，常用于饮料与烘焙。",
        "content": (
            "果葡糖浆通过淀粉水解与异构化制得，常见 F42、F55 等规格，数字代表果糖比例。"
            "它属于添加糖，过量摄入与能量过剩、龋齿相关；看营养成分表的「糖」含量更有意义。"
        ),
        "usage_note": "碳酸饮料、果汁饮料里很常见，是「隐形糖」的主要来源之一。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 149,
    },
    {
        "slug": "palm-oil",
        "title": "棕榈油",
        "aliases": "棕榈油,棕榈液油,起酥油原料",
        "category": "ingredient",
        "keywords": "油脂 饱和脂肪 烘焙 油炸",
        "summary": "饱和脂肪含量较高的植物油，稳定性好、耐高温，常用于油炸与烘焙。",
        "content": (
            "棕榈油富含棕榈酸等饱和脂肪酸，常温呈半固态，适合需要起酥与耐炸的产品。"
            "饱和脂肪摄入过多与血脂异常相关，看营养成分表的脂肪与饱和脂肪含量更直观。"
        ),
        "usage_note": "「植物油」未注明种类时，可能包含棕榈油，具体以配料表展开为准。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 150,
    },
    {
        "slug": "olive-oil",
        "title": "橄榄油",
        "aliases": "橄榄油,特级初榨橄榄油,初榨橄榄油",
        "category": "ingredient",
        "keywords": "油脂 单不饱和脂肪 地中海饮食",
        "summary": "以单不饱和脂肪酸为主的植物油，特级初榨橄榄油适合凉拌与低温烹调。",
        "content": (
            "橄榄油油酸含量高，是地中海饮食的代表油脂；特级初榨橄榄油保留更多多酚类物质。"
            "初榨橄榄油烟点相对较低，高温油炸并非最佳用途，但日常炒菜仍可使用。"
        ),
        "usage_note": "「特级初榨」与「精炼」是不同等级，风味和耐热性不同。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 151,
    },
    {
        "slug": "butter",
        "title": "黄油",
        "aliases": "黄油,牛油,动物黄油",
        "category": "ingredient",
        "keywords": "乳制品 脂肪 饱和脂肪 烘焙",
        "summary": "从牛乳中提取的乳脂肪，风味浓郁，饱和脂肪含量较高，常用于烘焙与西餐。",
        "content": (
            "黄油约含 80% 乳脂肪，其余是水和少量乳蛋白，赋予产品酥松口感与奶香。"
            "它含乳成分，乳蛋白过敏者需回避；饱和脂肪较高，适量使用即可。"
        ),
        "usage_note": "与「人造黄油/植物黄油」不同，后者可能含氢化油。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 152,
    },
    {
        "slug": "cocoa-butter-substitute",
        "title": "代可可脂",
        "aliases": "代可可脂,类可可脂,非可可脂",
        "category": "ingredient",
        "keywords": "巧克力 油脂 反式脂肪 成本",
        "summary": "替代可可脂的油脂原料，成本更低，口感与可可脂不同；部分产品可能含反式脂肪。",
        "content": (
            "代可可脂常用棕榈油等分提或氢化油脂制成，用于降低巧克力成本。"
            "使用代可可脂的产品需按规定标示；若工艺涉及部分氢化，可能带入反式脂肪。"
        ),
        "usage_note": "配料表写「代可可脂」说明不是纯可可脂巧克力。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 153,
    },
    {
        "slug": "oyster-sauce",
        "title": "蚝油",
        "aliases": "蚝油,牡蛎油,蚝汁",
        "category": "ingredient",
        "keywords": "调味料 钠 鲜味 海鲜 致敏",
        "summary": "以牡蛎汁或蚝汁为原料的复合调味料，鲜味强、钠含量高，部分产品含小麦与海鲜成分。",
        "content": (
            "蚝油通常由蚝汁、糖、盐、淀粉与增味剂调配而成，钠含量往往不低。"
            "对海鲜或小麦过敏的人群需要查看致敏提示；控盐人群应减少用量。"
        ),
        "usage_note": "炒菜放蚝油后要相应减少食盐与酱油。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 154,
    },
    # ================= 营养术语（续） =================
    {
        "slug": "saturated-fat",
        "title": "饱和脂肪酸",
        "aliases": "饱和脂肪酸,饱和脂肪,饱和脂肪含量",
        "category": "nutrition",
        "keywords": "脂肪 血脂 心血管 营养标签",
        "summary": "脂肪酸的一类，摄入过多与血脂异常相关；营养标签中通常单独列出饱和脂肪含量。",
        "content": (
            "饱和脂肪酸主要来自动物脂肪、棕榈油与椰子油，室温下多为固态。"
            "《中国居民膳食指南（2022）》建议控制饱和脂肪摄入，用不饱和脂肪替代部分饱和脂肪。"
        ),
        "usage_note": "看营养成分表的「饱和脂肪」一栏，比只看总脂肪更有参考价值。",
        "source_name": GUIDE,
        "source_url": CNSOC,
        "source_type": "public_health",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 160,
    },
    {
        "slug": "added-sugar",
        "title": "添加糖",
        "aliases": "添加糖,游离糖,精制糖,加糖",
        "category": "nutrition",
        "keywords": "糖 能量 龋齿 膳食指南",
        "summary": "在加工中额外加入的糖与糖浆，不包括水果和牛奶中天然存在的糖；建议每天不超过 50 克，最好控制在 25 克以内。",
        "content": (
            "添加糖包括白砂糖、果葡糖浆、蜂蜜、浓缩果汁等，摄入过多与龋齿、超重相关。"
            "《中国居民膳食指南（2022）》建议添加糖每天不超过 50 克，最好少于 25 克。"
        ),
        "usage_note": "「无蔗糖」不等于无添加糖，可能用了果葡糖浆或浓缩果汁。",
        "source_name": GUIDE,
        "source_url": CNSOC,
        "source_type": "public_health",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 161,
    },
    {
        "slug": "glycemic-index",
        "title": "血糖生成指数（GI）",
        "aliases": "GI,升糖指数,血糖生成指数,低GI",
        "category": "nutrition",
        "keywords": "血糖 碳水 主食 低GI 糖尿病",
        "summary": "衡量含碳水化合物食物升高血糖速度的指标；GI 低于 55 通常称为低 GI 食物。",
        "content": (
            "GI 反映食物中碳水化合物被消化吸收后升血糖的相对速度，受加工精度、膳食纤维、烹调方式影响。"
            "低 GI 不等于低热量，控制总量仍然重要；糖尿病人群应结合血糖监测与医生建议。"
        ),
        "usage_note": "「低 GI」是营养宣称，需有检测依据，不能只看包装字样。",
        "source_name": TEXTBOOK,
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 162,
    },
    {
        "slug": "potassium",
        "title": "钾",
        "aliases": "钾,钾含量,高钾",
        "category": "nutrition",
        "keywords": "矿物质 血压 电解质 肾功能",
        "summary": "维持电解质平衡与正常血压的重要矿物质，蔬果、豆类、薯类含量丰富；肾功能不全者需限钾。",
        "content": (
            "钾参与神经传导、肌肉收缩与血压调节，多数人通过蔬果即可满足需要。"
            "肾功能不全或服用某些降压药的人群可能需要限制钾摄入，应遵医嘱。"
        ),
        "usage_note": "营养标签目前不强制标钾，特殊人群需按医生建议计算。",
        "source_name": GUIDE,
        "source_url": CNSOC,
        "source_type": "public_health",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 163,
    },
    {
        "slug": "vitamin-d",
        "title": "维生素 D",
        "aliases": "维生素D,维D,VD,钙吸收",
        "category": "nutrition",
        "keywords": "脂溶性维生素 钙吸收 骨骼 日照",
        "summary": "促进钙吸收、维持骨骼健康的脂溶性维生素，主要靠日照合成，食物来源有限。",
        "content": (
            "维生素 D 能促进肠道吸收钙磷，缺乏与佝偻病、骨软化相关。"
            "深海鱼、蛋黄、强化奶是主要食物来源，日照不足人群可在医生指导下补充。"
        ),
        "usage_note": "强化维生素 D 的牛奶、麦片会在营养成分表或配料表中标注。",
        "source_name": GUIDE,
        "source_url": CNSOC,
        "source_type": "public_health",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 164,
    },
    {
        "slug": "calcium",
        "title": "钙",
        "aliases": "钙,钙含量,高钙",
        "category": "nutrition",
        "keywords": "矿物质 骨骼 乳制品 强化",
        "summary": "构成骨骼与牙齿的主要矿物质，乳制品、豆制品、深绿色蔬菜是良好来源。",
        "content": (
            "钙的吸收受维生素 D、植酸、草酸等因素影响；乳制品中的钙吸收率通常较高。"
            "「高钙」属于营养声称，需达到标准规定的含量条件，不能只看包装字样。"
        ),
        "usage_note": "补钙优先靠饮食，是否需要补充剂应咨询医生。",
        "source_name": GUIDE,
        "source_url": CNSOC,
        "source_type": "public_health",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 165,
    },
    {
        "slug": "zero-sugar-claim",
        "title": "「无糖」声称的条件",
        "aliases": "无糖,0糖,零糖,无糖声称",
        "category": "nutrition",
        "keywords": "营养声称 糖 标签 代糖",
        "summary": "「无糖/0 糖」需满足营养标签标准规定的糖含量条件，通常指每 100g 或 100mL 中糖含量低于规定界限值。",
        "content": (
            "「无糖」是营养声称，不是「完全不含糖」的绝对表述；产品仍可能含代糖或天然糖醇。"
            "具体界限值以 GB 28050 为准，判断时应看营养成分表的糖含量与实际配料。"
        ),
        "usage_note": "无糖饮料也可能有能量，注意看能量与碳水化合物。",
        "source_name": STANDARD_28050,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 166,
    },
    {
        "slug": "high-protein-claim",
        "title": "「高蛋白」声称的条件",
        "aliases": "高蛋白,蛋白质声称,富含蛋白",
        "category": "nutrition",
        "keywords": "营养声称 蛋白质 标签 蛋白粉",
        "summary": "「高蛋白/富含蛋白质」需达到标准规定的蛋白质含量条件，并同时满足能量占比要求。",
        "content": (
            "高蛋白声称不仅看蛋白质绝对值，还要看蛋白质供能占总能量的比例。"
            "具体条件以 GB 28050 为准；配料表中蛋白粉、乳清蛋白排位靠前通常说明用量较大。"
        ),
        "usage_note": "「高蛋白」不等于适合所有人，肾病人群需遵医嘱控制蛋白摄入。",
        "source_name": STANDARD_28050,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 167,
    },
    # ================= 标签规则（续） =================
    {
        "slug": "compound-ingredient",
        "title": "复合配料怎么标示",
        "aliases": "复合配料,复配,括号内配料,复合调味料",
        "category": "label_rule",
        "keywords": "配料表 复合配料 括号 展开 标示",
        "summary": "复合配料（如调味料、裹粉）通常先写名称，再在括号内按用量递减列出原始配料；添加剂的标示方式另有规定。",
        "content": (
            "当复合配料在终产品中起作用时，需要标示其名称并在括号内展开原始配料（有相应标准条件）。"
            "读标签时，括号内越靠前的成分用量越大；看不懂的名词可以回到知识库逐项查。"
        ),
        "usage_note": "括号很长不代表有问题，说明厂家把复合配料展开标注了。",
        "source_name": STANDARD_7718,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 170,
    },
    {
        "slug": "net-content",
        "title": "净含量怎么看",
        "aliases": "净含量,规格,含量,克数",
        "category": "label_rule",
        "keywords": "标签 净含量 规格 计量",
        "summary": "净含量指去除包装后食品的实际含量，通常与食品名称在同一展示版面标示。",
        "content": (
            "净含量是判断「一份」到底有多少的关键：营养成分表若按每份标示，需要结合净含量换算。"
            "组合包装会分别标示各件净含量与总净含量。"
        ),
        "usage_note": "比较两款产品时，先统一到每 100g 或每份再比。",
        "source_name": STANDARD_7718,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 171,
    },
    {
        "slug": "sc-license",
        "title": "食品生产许可证编号（SC）",
        "aliases": "SC,生产许可证,食品生产许可,SC编号",
        "category": "label_rule",
        "keywords": "标签 许可证 SC 监管 追溯",
        "summary": "国产预包装食品标签通常标示「SC」开头的食品生产许可证编号，可用于追溯生产企业。",
        "content": (
            "SC 编号由「SC」加 14 位阿拉伯数字组成，对应生产者与食品类别。"
            "它是判断产品是否来自合法生产企业的线索之一；买到无 SC 的预包装食品应谨慎。"
        ),
        "usage_note": "可在国家市场监督管理总局政务服务平台查询编号对应的企业信息。",
        "source_name": STANDARD_7718,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 172,
    },
    {
        "slug": "storage-condition",
        "title": "贮存条件怎么看",
        "aliases": "贮存条件,储存条件,保存方法,常温保存",
        "category": "label_rule",
        "keywords": "标签 贮存 冷藏 冷冻 保质期",
        "summary": "贮存条件说明产品在什么温度与环境下保存，直接影响保质期是否成立。",
        "content": (
            "「常温」「阴凉干燥处」「冷藏 2–6℃」「冷冻 -18℃」都是贮存条件；"
            "如果实际保存条件与标签不符，保质期承诺就不再适用。"
        ),
        "usage_note": "买回家后按标签条件存放，开封后通常需要冷藏并尽快吃完。",
        "source_name": STANDARD_7718,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 173,
    },
    {
        "slug": "nutrition-claim",
        "title": "营养声称（低脂、高钙等）",
        "aliases": "营养声称,低脂,高钙,低钠,富含",
        "category": "label_rule",
        "keywords": "标签 营养声称 低脂 高钙 标准条件",
        "summary": "「低脂」「高钙」「低钠」等属于营养声称，必须满足标准规定的含量条件，不能随意标注。",
        "content": (
            "营养声称分为含量声称与比较声称，每种都有对应的数值条件；"
            "产品标注「低脂」时，营养成分表的脂肪含量必须达到规定界限以下。"
        ),
        "usage_note": "看到声称时，用营养成分表验证一下，比看正面广告更可靠。",
        "source_name": STANDARD_28050,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 174,
    },
    # ================= 食品安全常识（续） =================
    {
        "slug": "cross-contamination",
        "title": "生熟分开与交叉污染",
        "aliases": "生熟分开,交叉污染,砧板,抹布",
        "category": "safety",
        "keywords": "厨房 生熟 砧板 细菌 食品安全五要点",
        "summary": "生肉、海鲜的汁液会把致病菌带到熟食上，厨房应做到生熟分开、工具专用、及时清洗。",
        "content": (
            "交叉污染是家庭食物中毒的常见原因：同一块砧板先切生鸡再切熟食，就可能把沙门氏菌带到即食食品。"
            "建议准备两块砧板、两把刀，或用「先熟后生」的顺序并彻底清洗消毒。"
        ),
        "usage_note": "冰箱里也要分层：生肉放下层，熟食与即食食品放上层并密封。",
        "source_name": "世界卫生组织：食品安全五要点",
        "source_url": WHO,
        "source_type": "official_website",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 180,
    },
    {
        "slug": "cooking-temperature",
        "title": "彻底加热：中心温度与剩菜复热",
        "aliases": "中心温度,彻底加热,复热,70度",
        "category": "safety",
        "keywords": "加热 中心温度 复热 剩菜 微生物",
        "summary": "食物中心温度达到 70℃ 以上并保持一段时间，能有效杀灭多数致病菌；剩菜复热要热透而不只是表面热。",
        "content": (
            "大块肉、带骨肉、肉馅制品最容易「外热内冷」，可用食品温度计确认中心温度。"
            "微波炉复热容易出现冷点，中途翻动、加盖能让受热更均匀。"
        ),
        "usage_note": "汤类要煮沸，肉块要切开确认内部不再发红。",
        "source_name": "世界卫生组织：食品安全五要点",
        "source_url": WHO,
        "source_type": "official_website",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 181,
    },
    {
        "slug": "aflatoxin",
        "title": "黄曲霉毒素",
        "aliases": "黄曲霉毒素,发霉花生,发霉玉米,霉变",
        "category": "safety",
        "keywords": "霉菌 毒素 花生 玉米 肝癌",
        "summary": "由黄曲霉等产生的强致癌物，常见于受潮发霉的花生、玉米与坚果；发霉食物应整份丢弃。",
        "content": (
            "黄曲霉毒素耐高温，普通烹调难以破坏，长期摄入与肝癌风险相关。"
            "花生、玉米、棉籽等易受污染，家庭储存应干燥、密封、避光，发霉后不要「挖掉霉点继续吃」。"
        ),
        "usage_note": "小作坊自榨花生油若原料霉变，风险更高，建议选正规产品。",
        "source_name": "国家食品安全风险评估中心：真菌毒素科普",
        "source_url": CFSA_URL,
        "source_type": "official_website",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 182,
    },
    {
        "slug": "bongkrekic-acid",
        "title": "米酵菌酸（发酵米面制品的风险）",
        "aliases": "米酵菌酸,椰毒假单胞菌,酸汤子,发酵玉米面",
        "category": "safety",
        "keywords": "发酵米面 木耳 银耳 中毒 毒素",
        "summary": "由椰毒假单胞菌产生的剧毒毒素，常见于变质发酵米面制品与泡发过久的木耳银耳；无特效解毒药，重在预防。",
        "content": (
            "米酵菌酸耐热、毒性强，被污染的食物外观可能没有明显异常。"
            "自制发酵米面、长时间室温泡发的木耳银耳风险较高，应冷藏泡发、及时食用，出现异味立即丢弃。"
        ),
        "usage_note": "泡木耳建议冷藏、4 小时内用完，不要室温泡一整晚。",
        "source_name": "国家卫生健康委员会：食品安全风险提示",
        "source_url": NHC,
        "source_type": "official_website",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 183,
    },
    {
        "slug": "listeria",
        "title": "李斯特菌：冰箱里的「隐形风险」",
        "aliases": "李斯特菌,冰箱细菌,即食食品,孕妇",
        "category": "safety",
        "keywords": "冷藏 即食 孕妇 免疫力 细菌",
        "summary": "李斯特菌在冷藏温度下仍能缓慢生长，常见于即食冷切肉、软奶酪、烟熏水产；孕妇与免疫力低下者风险更高。",
        "content": (
            "李斯特菌病潜伏期长，孕妇感染可能影响胎儿，因此孕期通常建议避免生食与高风险即食冷藏食品。"
            "冰箱不是保险箱：即食食品应尽快吃完，剩菜复热要彻底。"
        ),
        "usage_note": "孕妇、老人、免疫力低下者尤其要注意冷藏即食食品的食用期限。",
        "source_name": "世界卫生组织：食源性疾病",
        "source_url": WHO,
        "source_type": "official_website",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 184,
    },
    {
        "slug": "wild-mushroom",
        "title": "野生蘑菇不要采食",
        "aliases": "毒蘑菇,野生蘑菇,采蘑菇,菌子",
        "category": "safety",
        "keywords": "毒蘑菇 野生 中毒 鉴别 急救",
        "summary": "野生毒蘑菇与可食蘑菇外形相似，靠颜色、大蒜、银针等「土办法」无法鉴别，最安全的做法是不采、不买、不吃。",
        "content": (
            "我国毒蘑菇种类多，部分品种致死率高，且没有特效解毒药。"
            "不要轻信「颜色鲜艳才有毒」「虫子咬过就无毒」等说法；误食后应尽快就医并保留剩余蘑菇样本。"
        ),
        "usage_note": "不认识的野生菌一律不采食；市场购买也要选正规渠道。",
        "source_name": "国家卫生健康委员会：预防毒蘑菇中毒提示",
        "source_url": NHC,
        "source_type": "official_website",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 185,
    },
    {
        "slug": "methanol",
        "title": "甲醇与「假酒」风险",
        "aliases": "甲醇,假酒,工业酒精,中毒",
        "category": "safety",
        "keywords": "甲醇 假酒 失明 中毒 散装酒",
        "summary": "工业酒精含甲醇，误饮可导致失明甚至死亡；来源不明的散装酒、自酿酒存在风险。",
        "content": (
            "甲醇代谢产物毒性强，少量即可造成视神经损伤。"
            "正规酒类产品有生产许可与检验，来源不明的「内部酒」「纯粮散酒」风险高，不要购买。"
        ),
        "usage_note": "喝酒后出现视力模糊、头痛剧烈应立刻就医并说明饮酒情况。",
        "source_name": "国家市场监督管理总局：酒类消费提示",
        "source_url": "https://www.samr.gov.cn/",
        "source_type": "official_website",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 186,
    },
    {
        "slug": "pufferfish",
        "title": "河豚毒素与河豚鱼",
        "aliases": "河豚,河豚毒素,河鲀,拼死吃河豚",
        "category": "safety",
        "keywords": "河豚 毒素 神经毒素 禁止 加工",
        "summary": "河豚体内含河豚毒素，毒性极强且耐热，国家仅允许符合条件的养殖河豚经专业加工后销售，个人不得随意加工食用。",
        "content": (
            "河豚毒素是神经毒素，普通烹调无法破坏，中毒后进展快。"
            "我国对养殖河豚的品种、加工与销售有专门规定，野生河豚与来源不明的河豚制品都不应食用。"
        ),
        "usage_note": "不要自行处理河豚；正规河豚产品需来自备案加工企业。",
        "source_name": "国家卫生健康委员会：河豚毒素风险提示",
        "source_url": NHC,
        "source_type": "official_website",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 187,
    },
    {
        "slug": "norovirus",
        "title": "诺如病毒与生食贝类",
        "aliases": "诺如病毒,生蚝,贝类,呕吐腹泻",
        "category": "safety",
        "keywords": "病毒 贝类 生食 腹泻 呕吐 冬季",
        "summary": "诺如病毒传染性强，常通过受污染的水与生食贝类传播，冬季高发；贝类应彻底加热。",
        "content": (
            "诺如病毒感染剂量低、传播快，常引起呕吐与腹泻，学校与集体食堂易暴发。"
            "生蚝等滤食性贝类可能富集病毒，加热至中心温度足够才能降低风险。"
        ),
        "usage_note": "处理呕吐物要戴手套并消毒；患者应隔离至症状消失后 48 小时。",
        "source_name": "中国疾病预防控制中心：诺如病毒科普",
        "source_url": "https://www.chinacdc.cn/",
        "source_type": "official_website",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 188,
    },
]
