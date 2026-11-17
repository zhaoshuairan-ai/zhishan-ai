"""食品安全知识库种子数据。

写作原则：
1. 只写公认的、可追溯的概述性内容，不编造文献、条款与原文；
2. 来源只写到「标准名称 / 官方机构网站」级别，不虚构具体条款编号；
3. verification_status 如实标注：verified（可复算或定义性事实）/ pending（需以官方原文为准）；
4. 对添加剂只解释用途与监管逻辑，不下「有毒/不安全」结论。
"""
from __future__ import annotations

WIKI_OFFICIAL = "https://openstd.samr.gov.cn/bzgk/gb/"
NHC = "http://www.nhc.gov.cn/"
CFSA = "https://www.cfsa.net.cn/"
WHO = "https://www.who.int/"

STANDARD_7718 = "GB 7718《食品安全国家标准 预包装食品标签通则》（名称引用）"
STANDARD_28050 = "GB 28050《食品安全国家标准 预包装食品营养标签通则》（名称引用）"
STANDARD_2760 = "GB 2760《食品安全国家标准 食品添加剂使用标准》（名称引用）"

PENDING_NOTE = "要点为概述性科普，标准原文未在系统内收录；具体条款、限量与适用范围请查阅官方发布的现行文本。"
VERIFIED_NOTE = "该条目为定义性或可复算的事实，可直接用于理解标签；涉及法规的判定仍以官方文本为准。"

KNOWLEDGE_ENTRIES: list[dict] = [
    # ================= 食品添加剂 =================
    {
        "slug": "potassium-sorbate",
        "title": "山梨酸钾",
        "aliases": "山梨酸钾,防腐剂,山梨酸",
        "category": "additive",
        "keywords": "防腐 霉菌 酵母 饮料 酱料",
        "summary": "常见的食品防腐剂，用于抑制霉菌、酵母菌和部分细菌的生长，延长食品保质期。",
        "content": (
            "山梨酸钾是山梨酸的钾盐，属于有机酸类防腐剂。它在酸性到中性偏酸的环境中抑菌效果较好，"
            "常出现在饮料、果酱、蜜饯、酱料、烘焙食品等配料表中。它在 GB 2760 规定的食品类别和用量范围内使用是允许的；"
            "「配料表里出现山梨酸钾」本身并不代表食品不安全，是否合规取决于使用范围与用量是否符合标准。"
        ),
        "usage_note": "看到它时，可以理解为厂家在做防霉保鲜，无需直接与「有害」划等号。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 10,
    },
    {
        "slug": "sodium-benzoate",
        "title": "苯甲酸钠",
        "aliases": "苯甲酸钠,苯甲酸,防腐剂",
        "category": "additive",
        "keywords": "防腐 酸性 饮料 酱油",
        "summary": "酸性条件下效果较好的防腐剂，常见于碳酸饮料、酱油、酱菜等。",
        "content": (
            "苯甲酸钠是苯甲酸的钠盐，在酸性环境中抑菌能力较强，因此多用于 pH 较低的食品。"
            "它在允许的食品类别和限量内使用是合规的。消费者需要注意的是：防腐剂的合规性取决于"
            "「是否在允许范围内使用」，而不是「是否出现在配料表」。若对某种添加剂有持续顾虑，"
            "可以减少高加工食品的摄入频率，这是更实际的饮食策略。"
        ),
        "usage_note": "配料表出现防腐剂说明厂家在做保质期管理，不等于超标或违规。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": False,
        "sort_order": 11,
    },
    {
        "slug": "sodium-nitrite",
        "title": "亚硝酸钠",
        "aliases": "亚硝酸钠,硝酸钠,亚硝酸盐,护色剂",
        "category": "additive",
        "keywords": "肉制品 腌腊 护色 防腐 肉毒",
        "summary": "用于腌腊肉制品的护色剂兼防腐剂，可抑制肉毒梭菌，使用范围和残留量受到严格管理。",
        "content": (
            "亚硝酸钠在肉制品中主要起两方面作用：一是与肌红蛋白结合形成稳定的腌制红色；"
            "二是抑制肉毒梭菌等厌氧菌的繁殖，这对腌腊肉制品的安全性很重要。"
            "同时，亚硝酸盐在体内可转化为亚硝胺类物质，长期大量摄入与健康风险相关，"
            "因此其允许使用的食品类别、最大使用量与残留量都有明确规定。"
            "需要强调：仅凭配料表无法判断实际残留量是否合规，这需要检测数据。"
        ),
        "usage_note": "它属于风险与功能并存的添加剂；合规使用与超量使用是两回事，不能仅凭名称判定。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 12,
    },
    {
        "slug": "monosodium-glutamate",
        "title": "谷氨酸钠（味精）",
        "aliases": "谷氨酸钠,味精,增味剂,MSG",
        "category": "additive",
        "keywords": "增味 鲜味 调味",
        "summary": "常用增味剂，提供鲜味，是味精的主要成分。",
        "content": (
            "谷氨酸钠是谷氨酸的钠盐，属于增味剂。谷氨酸本身是天然存在于番茄、海带、奶酪、肉类等食物中的氨基酸。"
            "国际与国内的食品安全机构多次评估其安全性，在正常食用量下未发现对一般人群的健康风险；"
            "部分人一次性大量摄入后可能出现短暂不适，但这属于个体反应，不等于食品不安全。"
        ),
        "usage_note": "对味道敏感的人可以留意摄入量，但无需把「含味精」当成安全警报。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 13,
    },
    {
        "slug": "aspartame",
        "title": "阿斯巴甜",
        "aliases": "阿斯巴甜,甜味剂,代糖,天冬酰苯丙氨酸甲酯",
        "category": "additive",
        "keywords": "甜味剂 无糖 零度 饮料",
        "summary": "高倍甜味剂，甜度约为蔗糖的 200 倍，代谢会产生苯丙氨酸；苯丙酮尿症患者需避免。",
        "content": (
            "阿斯巴甜由天门冬氨酸和苯丙氨酸构成，甜度高、热量低，常用于无糖饮料、口香糖等。"
            "它进入人体后会释放苯丙氨酸，因此苯丙酮尿症（PKU）患者应避免摄入，相关产品通常会有提示。"
            "对一般人群而言，在允许使用范围和摄入量内使用是被允许的；国际机构会持续评估并更新结论，"
            "建议关注权威机构的最新评估，而不是依据单一网络传言判断。"
        ),
        "usage_note": "PKU 患者需要特别留意；一般人群按正常饮食摄入无需过度担心。",
        "source_name": STANDARD_2760 + "；JECFA/EFSA 风险评估结论（概念性参考）",
        "source_url": CFSA,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 14,
    },
    {
        "slug": "sucralose",
        "title": "三氯蔗糖",
        "aliases": "三氯蔗糖,蔗糖素,甜味剂,代糖",
        "category": "additive",
        "keywords": "甜味剂 无糖 饮料 稳定",
        "summary": "以蔗糖为原料制得的高倍甜味剂，甜度约为蔗糖的 600 倍，稳定性好。",
        "content": (
            "三氯蔗糖甜度高、用量小，在饮料、烘焙、乳制品中较常见，常与安赛蜜、阿斯巴甜等复配以获得更接近蔗糖的口感。"
            "在允许的食品类别和用量范围内使用是合规的；其风味特点是在部分食品中可能略有后味，这属于感官差异，不是安全问题。"
        ),
        "usage_note": "「无糖」产品常用它提供甜味，可结合营养成分表一起看。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 15,
    },
    {
        "slug": "acesulfame-k",
        "title": "安赛蜜（乙酰磺胺酸钾）",
        "aliases": "安赛蜜,乙酰磺胺酸钾,AK糖,甜味剂",
        "category": "additive",
        "keywords": "甜味剂 无糖 复配",
        "summary": "高倍甜味剂，性质稳定，常与其他甜味剂复配使用。",
        "content": (
            "安赛蜜在高温和酸性条件下较稳定，因此常用于需要加热或酸性配方的无糖食品。"
            "它单独使用时甜味特征与蔗糖有差异，因此厂家常复配多种甜味剂来校正口感。"
            "合规使用是其安全性的前提，超出允许范围的添加属于违规，但这需要检测确认。"
        ),
        "usage_note": "配料表中多种甜味剂同时出现是常见的复配做法，不代表叠加超标。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 16,
    },
    {
        "slug": "carrageenan",
        "title": "卡拉胶",
        "aliases": "卡拉胶,增稠剂,稳定剂,红藻多糖",
        "category": "additive",
        "keywords": "增稠 稳定 悬浮 乳制品 果冻",
        "summary": "从红藻中提取的多糖，起增稠、稳定、悬浮作用，常见于乳饮料、果冻、肉制品。",
        "content": (
            "卡拉胶属于亲水性胶体，能让液体保持均匀、改善口感、防止分层。"
            "食品级卡拉胶在允许范围内使用是合规的。需要区分的是："
            "食品级卡拉胶与「降解卡拉胶」是不同物质，后者不被允许作为食品配料使用，"
            "把两者混为一谈是网络上常见的误解。"
        ),
        "usage_note": "看到卡拉胶时，可以理解为「让口感更稳定」，无需联想到工业胶水。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 17,
    },
    {
        "slug": "xanthan-gum",
        "title": "黄原胶",
        "aliases": "黄原胶,增稠剂,稳定剂",
        "category": "additive",
        "keywords": "增稠 稳定 沙拉酱 饮料",
        "summary": "由微生物发酵产生的多糖，增稠与稳定能力强，少量使用即可显著改变流动性。",
        "content": (
            "黄原胶在低浓度下就能显著提高黏度，常用于沙拉酱、酱汁、饮料、无麸质烘焙等。"
            "它属于食品胶体，在允许范围内使用是合规的；同时它也是膳食纤维的一种来源，"
            "但这并不意味着可以把它当作保健品，其添加量通常很小。"
        ),
        "usage_note": "它让酱汁不容易分层，是常见的工艺助剂。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 18,
    },
    {
        "slug": "citric-acid",
        "title": "柠檬酸",
        "aliases": "柠檬酸,酸度调节剂,柠檬酸钠",
        "category": "additive",
        "keywords": "酸度 调节 酸味 饮料",
        "summary": "最常用的酸度调节剂之一，提供酸味并帮助调节 pH，也是人体代谢的中间产物。",
        "content": (
            "柠檬酸用于调节酸度、增强风味，也常与柠檬酸钠配合作为缓冲体系。"
            "它天然存在于柑橘类水果中，也是三羧酸循环的中间产物，因此在允许范围内使用通常被认为安全性较高。"
            "对牙齿而言，长期频繁接触酸性饮料仍可能增加酸蚀风险，这属于饮用习惯问题。"
        ),
        "usage_note": "它主要影响口味与 pH，不必因为「化学名」而担心。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 19,
    },
    {
        "slug": "sodium-bicarbonate",
        "title": "碳酸氢钠（小苏打）",
        "aliases": "碳酸氢钠,小苏打,膨松剂,酸度调节剂",
        "category": "additive",
        "keywords": "膨松 饼干 蛋糕 酸碱",
        "summary": "常见膨松剂与酸度调节剂，受热或遇酸产生二氧化碳使面团膨胀。",
        "content": (
            "碳酸氢钠在烘焙中与酸性物质反应或受热分解，释放二氧化碳形成气孔，使饼干、蛋糕等口感疏松。"
            "它本身是弱碱性物质，在允许范围内使用是合规的；由于含钠，"
            "对需要控钠的人群，碳酸氢钠也是钠的一个来源，可在营养成分表的钠含量中一并考虑。"
        ),
        "usage_note": "饼干类产品常见，注意它的钠贡献。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 20,
    },
    {
        "slug": "caramel-color",
        "title": "焦糖色",
        "aliases": "焦糖色,着色剂,色素,糖色",
        "category": "additive",
        "keywords": "着色 酱油 饮料 颜色",
        "summary": "糖类加热反应生成的着色剂，按生产工艺分为不同类型，适用食品范围不同。",
        "content": (
            "焦糖色是通过糖类在特定条件下加热（可加入催化剂）制得的褐色着色剂，常见于酱油、可乐、"
            "烘焙食品等。按生产工艺可分为普通法、苛性硫酸盐法、氨法、亚硫酸铵法等类别，"
            "不同类别允许使用的食品范围不同，其中部分类别在使用上有更严格的限制。"
            "在允许范围内使用是合规的，仅凭配料表中的「焦糖色」无法判断具体类别。"
        ),
        "usage_note": "它主要提供颜色，具体类别信息通常不会标在标签上。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 21,
    },
    {
        "slug": "silicon-dioxide",
        "title": "二氧化硅",
        "aliases": "二氧化硅,抗结剂,硅酸钙",
        "category": "additive",
        "keywords": "抗结 粉末 结块 食盐 奶粉",
        "summary": "抗结剂，防止粉末状食品吸潮结块，添加量通常很小。",
        "content": (
            "二氧化硅以极细颗粒形式分散在粉末中，阻隔颗粒之间的粘连，从而保持流动性。"
            "它在允许范围内使用是合规的，且通常用量很低。它与「石英/结晶二氧化硅粉尘」的职业健康问题不是同一场景，"
            "不应直接套用工业粉尘的风险结论。"
        ),
        "usage_note": "看到它多说明产品是粉末状且需要防潮。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 22,
    },
    {
        "slug": "ascorbic-acid",
        "title": "抗坏血酸（维生素 C）",
        "aliases": "抗坏血酸,维生素C,抗氧化剂,营养强化剂",
        "category": "additive",
        "keywords": "抗氧化 维生素 护色",
        "summary": "兼具抗氧化剂与营养强化剂功能，可防止油脂氧化变色，也是维生素 C 本身。",
        "content": (
            "抗坏血酸能消耗氧气、抑制氧化褐变，因此常用于果汁、肉制品、果蔬罐头等。"
            "它既是食品添加剂（抗氧化剂），也是营养素（维生素 C），在营养强化剂类别下也有使用。"
            "维生素 C 本身不耐热，加工与贮存会造成损失，标签中的含量通常以出厂或标示值为准。"
        ),
        "usage_note": "配料表出现它，通常意味着「防氧化」，同时也是营养素。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 23,
    },
    {
        "slug": "flavoring",
        "title": "食用香精 / 食用香料",
        "aliases": "食用香精,食用香料,香精,香料,香兰素",
        "category": "additive",
        "keywords": "香味 风味 香精",
        "summary": "用于提供或补充香气的香料混合物，用量很小，标签上通常只标示类别名称。",
        "content": (
            "食用香精通常由多种香料物质调配而成，属于食品用香料的管理范畴。"
            "由于配方复杂且属于商业信息，标签上一般只标示「食用香精」或「食用香料」，不会列出全部成分。"
            "其在允许范围内使用是合规的；对极少数人而言，某些香气成分可能引起个体不适，这需要结合自身情况判断。"
        ),
        "usage_note": "标签只写「香精」是行业惯例，不代表隐瞒违规成分。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 24,
    },
    {
        "slug": "sulfites",
        "title": "二氧化硫及亚硫酸盐",
        "aliases": "二氧化硫,亚硫酸钠,焦亚硫酸钠,亚硫酸盐,漂白剂",
        "category": "additive",
        "keywords": "漂白 防腐 抗氧化 果干 葡萄酒",
        "summary": "兼具漂白、防腐与抗氧化作用，部分哮喘人群对其较敏感。",
        "content": (
            "二氧化硫及亚硫酸盐类常用于果干、蜜饯、葡萄酒、淀粉制品等，可抑制褐变和微生物生长。"
            "在允许范围内使用是合规的，但部分哮喘患者对亚硫酸盐较敏感，可能出现呼吸道不适，"
            "这类人群可留意标签中的相关标示并避免摄入。这是个体敏感性，不等同于对所有人的健康风险。"
        ),
        "usage_note": "哮喘人群需要特别关注；一般人群按正常摄入无需过度担心。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 25,
    },
    {
        "slug": "phosphates",
        "title": "磷酸盐类（水分保持剂）",
        "aliases": "磷酸盐,三聚磷酸钠,六偏磷酸钠,焦磷酸钠,水分保持剂",
        "category": "additive",
        "keywords": "水分 保水 肉制品 海产品",
        "summary": "用于保持水分、改善质构，常见于肉制品与冷冻水产。",
        "content": (
            "磷酸盐类能提高蛋白质的持水能力，使肉制品更嫩、减少解冻损失。"
            "在允许的食品类别和用量范围内使用是合规的。膳食中磷的总体摄入与钙磷平衡有关，"
            "这也是营养学关注点之一，但对单件食品而言，判断仍需结合整体饮食结构。"
        ),
        "usage_note": "它主要影响口感与出品率，标签上通常写成具体磷酸盐名称。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 26,
    },
    {
        "slug": "glycerol-monostearate",
        "title": "单硬脂酸甘油酯",
        "aliases": "单硬脂酸甘油酯,乳化剂,单甘酯",
        "category": "additive",
        "keywords": "乳化 稳定 面包 冰淇淋",
        "summary": "常用乳化剂，帮助油水混合稳定，改善面团与冰淇淋的组织结构。",
        "content": (
            "单硬脂酸甘油酯是甘油与硬脂酸形成的酯，属于乳化剂，能让互不相溶的油和水形成稳定体系。"
            "它常出现在面包、饼干、冰淇淋、植物蛋白饮料中，在允许范围内使用是合规的。"
            "其本身也是脂肪类物质，会被计入产品的脂肪含量。"
        ),
        "usage_note": "看到乳化剂时，可以理解为「让口感更细腻、结构更稳定」。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 27,
    },
    {
        "slug": "cmc",
        "title": "羧甲基纤维素钠（CMC）",
        "aliases": "羧甲基纤维素钠,CMC,增稠剂,稳定剂",
        "category": "additive",
        "keywords": "增稠 稳定 冰淇淋 饮料",
        "summary": "纤维素衍生物类增稠剂，用于改善黏度与稳定性，不被人体消化吸收。",
        "content": (
            "羧甲基纤维素钠由纤维素改性得到，属于水溶性增稠剂，常用于冰淇淋、乳饮料、烘焙食品等。"
            "它在允许范围内使用是合规的，人体缺乏分解它的酶，因此大部分随粪便排出，"
            "这也是它热量很低的原因。"
        ),
        "usage_note": "它属于「膳食纤维类」增稠剂，主要影响口感。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 28,
    },
    {
        "slug": "steviol-glycosides",
        "title": "甜菊糖苷",
        "aliases": "甜菊糖苷,甜菊糖,甜叶菊,甜味剂",
        "category": "additive",
        "keywords": "甜味剂 天然 零卡",
        "summary": "从甜叶菊中提取的天然来源高倍甜味剂，甜度高、热量低。",
        "content": (
            "甜菊糖苷来自甜叶菊的叶片，甜度远高于蔗糖，常与赤藓糖醇等配合用于「零糖」饮料。"
            "在允许范围内使用是合规的。「天然来源」不等于「可以无限量食用」，"
            "它仍然属于食品添加剂，需要按标准使用。"
        ),
        "usage_note": "天然来源也需要合规使用，不必迷信「天然」标签。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 29,
    },
    {
        "slug": "beta-carotene",
        "title": "β-胡萝卜素",
        "aliases": "β-胡萝卜素,β胡萝卜素,胡萝卜素,着色剂,维生素A",
        "category": "additive",
        "keywords": "着色 维生素A 脂溶性",
        "summary": "兼具着色与维生素 A 前体功能，脂溶性、对光热敏感。",
        "content": (
            "β-胡萝卜素能赋予食品橙黄色，同时可在体内转化为维生素 A，因此也被用作营养强化剂。"
            "它是脂溶性的，在含油脂的食品中更稳定；在允许范围内使用是合规的。"
            "大量摄入富含胡萝卜素的食物可能使皮肤暂时偏黄，这通常是无害的，减少摄入后可恢复。"
        ),
        "usage_note": "它既是色素也是营养素，属于比较「温和」的添加剂。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 30,
    },
    # ================= 常见配料 =================
    {
        "slug": "wheat-flour",
        "title": "小麦粉",
        "aliases": "小麦粉,面粉,麸质,面筋",
        "category": "ingredient",
        "keywords": "面粉 麸质 致敏 饼干 面包",
        "summary": "烘焙与面制品的基础原料，含有麸质蛋白，属于常见致敏原。",
        "content": (
            "小麦粉是小麦研磨后的产品，其中的面筋蛋白（麸质）决定了面团的弹性与延展性。"
            "对乳糜泻患者而言，麸质需要严格避免；对小麦过敏人群则需避免小麦蛋白。"
            "这两类情况不同，但都需要认真看配料表与致敏物质提示。"
        ),
        "usage_note": "麸质敏感人群应把小麦粉视为关键信息。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 40,
    },
    {
        "slug": "white-sugar",
        "title": "白砂糖",
        "aliases": "白砂糖,砂糖,蔗糖,添加糖,糖",
        "category": "ingredient",
        "keywords": "糖 甜味 能量 龋齿",
        "summary": "常见的添加糖来源，提供甜味与能量，摄入过多与龋齿和能量过剩相关。",
        "content": (
            "白砂糖主要成分是蔗糖，属于添加糖。它提供能量但几乎不含其他营养素。"
            "配料表中糖出现的位置越靠前，通常意味着用量越大（配料表一般按加入量递减排列）。"
            "营养成分表中「糖」是否单独列出取决于标签设计，没有单列不代表产品不含糖。"
        ),
        "usage_note": "看糖含量时，可结合配料表排序与碳水化合物数值一起判断。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": WHO,
        "source_type": "textbook",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 41,
    },
    {
        "slug": "vegetable-oil",
        "title": "植物油",
        "aliases": "植物油,大豆油,棕榈油,菜籽油,葵花籽油,食用植物油",
        "category": "ingredient",
        "keywords": "油脂 脂肪 氢化 反式脂肪",
        "summary": "泛指精炼植物油，是脂肪的主要来源；若标注「氢化」需关注反式脂肪酸。",
        "content": (
            "「植物油」是标签上常见的概括性写法，具体品种可能不标明。植物油是脂肪的主要来源，"
            "不同油种的脂肪酸组成差异较大。若配料表中出现「氢化植物油」「部分氢化植物油」，"
            "则可能含有反式脂肪酸，应结合营养成分表中的反式脂肪酸一项理解；"
            "标示为「0」时也要注意标准对「可标示为 0」的界限值规定。"
        ),
        "usage_note": "关注油脂时，比「有没有油」更重要的是总量与是否含氢化油。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 42,
    },
    {
        "slug": "edible-salt",
        "title": "食用盐",
        "aliases": "食用盐,食盐,盐,氯化钠",
        "category": "ingredient",
        "keywords": "钠 咸味 调味",
        "summary": "钠的主要来源，1 克食盐约含 393 毫克钠。",
        "content": (
            "食用盐的主要成分是氯化钠。按化学计量，1 克食盐约含 393 毫克钠"
            "（钠在氯化钠中的质量分数约 39.3%）。营养标签中的「钠」以毫克计，"
            "两者可以互相换算：钠（mg）÷ 393 ≈ 食盐（g）。"
            "加工食品中的钠还来自其他配料与添加剂，因此标签钠含量通常高于单纯加盐的估算。"
        ),
        "usage_note": "控盐时看营养成分表的钠更直接，因为钠有多种来源。",
        "source_name": "氯化钠化学计量换算（Na 22.99 / NaCl 58.44）",
        "source_url": WHO,
        "source_type": "editorial",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 43,
    },
    {
        "slug": "whole-milk-powder",
        "title": "全脂乳粉",
        "aliases": "全脂乳粉,奶粉,乳粉,乳制品,乳糖",
        "category": "ingredient",
        "keywords": "乳制品 乳糖 致敏 钙",
        "summary": "乳制品原料，含乳蛋白与乳糖，是钙的来源，也属于常见致敏原。",
        "content": (
            "全脂乳粉由牛乳浓缩干燥制成，保留乳脂肪、乳蛋白与乳糖。"
            "牛奶蛋白过敏人群需要避免乳制品；乳糖不耐受人群则可能因乳糖出现胀气、腹泻，"
            "这属于消化酶不足，与过敏机制不同。判断产品是否含乳成分，可查看配料表与致敏物质提示。"
        ),
        "usage_note": "乳糖不耐受与牛奶过敏是两回事，处理方式不同。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 44,
    },
    {
        "slug": "water",
        "title": "水 / 饮用水",
        "aliases": "水,饮用水,纯净水",
        "category": "ingredient",
        "keywords": "水 配料表 饮料",
        "summary": "饮料类产品中常作为第一位的配料，此时通常代表它是含量最高的成分。",
        "content": (
            "在饮料、汤料等产品中，「水」常出现在配料表的第一位。按配料表一般按加入量递减排列的惯例，"
            "这通常意味着水是含量最高的成分，但这不等于产品营养价值的判断依据。"
            "对浓缩还原类产品，水分来源与工艺也会影响标签的标示方式。"
        ),
        "usage_note": "水排第一是饮料的常态，不必据此判断产品好坏。",
        "source_name": STANDARD_7718,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 45,
    },
    # ================= 营养术语 =================
    {
        "slug": "nrv",
        "title": "NRV（营养素参考值）与 NRV%",
        "aliases": "NRV,营养素参考值,NRV%",
        "category": "nutrition",
        "keywords": "营养 参考值 每日 百分比",
        "summary": "NRV 是营养素每日参考值的基准，NRV% 表示一份或 100g 食品中某营养素占该基准的比例。",
        "content": (
            "NRV（Nutrient Reference Values）是用于营养标签的每日参考值基准。"
            "NRV% 的计算方式是：某营养素含量 ÷ 对应 NRV × 100%。"
            "它帮助消费者快速判断「吃一份能获得多少」。需要注意：NRV% 高只说明该营养素含量占比高，"
            "不代表食品不安全，也不代表越多越好（例如钠的 NRV% 高通常不是好事）。"
            "具体 NRV 数值请以现行标准附录为准。"
        ),
        "usage_note": "NRV% 是相对值，跨产品比较时要先统一计量基准（每 100g 还是每份）。",
        "source_name": STANDARD_28050,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 50,
    },
    {
        "slug": "energy-unit",
        "title": "能量单位：千焦与千卡换算",
        "aliases": "能量,千焦,千卡,大卡,kJ,kcal,热量",
        "category": "nutrition",
        "keywords": "能量 换算 卡路里",
        "summary": "1 千卡（kcal）= 4.184 千焦（kJ）；国内标签通常以 kJ 标示，可能并列 kcal。",
        "content": (
            "能量标示常用两个单位：千焦（kJ）和千卡（kcal，也称大卡）。"
            "换算是严格的物理关系：1 kcal = 4.184 kJ，1 kJ ≈ 0.239 kcal。"
            "例如标示 1000 kJ，约等于 239 kcal。"
            "很多产品只标 kJ，如果想换算成日常熟悉的「大卡」，除以 4.184 即可。"
        ),
        "usage_note": "换算属于定义性关系，可直接用于计算。",
        "source_name": "国际单位制定义：1 cal = 4.184 J（定义性换算）",
        "source_url": None,
        "source_type": "editorial",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 51,
    },
    {
        "slug": "trans-fat",
        "title": "反式脂肪酸",
        "aliases": "反式脂肪酸,反式脂肪,氢化油",
        "category": "nutrition",
        "keywords": "反式 脂肪 氢化 心血管",
        "summary": "部分氢化油脂与高温精炼过程中可能产生，摄入过多与心血管风险相关。",
        "content": (
            "反式脂肪酸主要来自部分氢化植物油，也可能在高温精炼过程中少量产生。"
            "多项研究显示，过量摄入反式脂肪酸与心血管疾病风险升高相关，因此营养标签通常要求标示。"
            "标示为「0」时需注意：标准允许在低于规定界限值时标示为 0，"
            "具体界限值请查阅现行标准文本。看到「氢化植物油」时，可重点看这一项。"
        ),
        "usage_note": "关注反式脂肪时，优先看配料表是否含氢化油，再看营养表数值。",
        "source_name": STANDARD_28050 + "；WHO 反式脂肪相关建议（概念性参考）",
        "source_url": WHO,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 52,
    },
    {
        "slug": "sodium-salt",
        "title": "钠与食盐：如何换算",
        "aliases": "钠,食盐换算,盐",
        "category": "nutrition",
        "keywords": "钠 盐 高血压 换算",
        "summary": "钠（mg）÷ 393 ≈ 食盐（g）；钠摄入过多与血压升高相关。",
        "content": (
            "营养标签中的钠以毫克计。由于 1 克食盐约含 393 毫克钠，"
            "可以用「钠（mg）÷ 393」估算相当于多少克食盐。"
            "例如每 100g 含钠 800mg，约相当于 2g 食盐。"
            "世界卫生组织建议成人每日食盐摄入量低于 5 克（约 2000mg 钠），"
            "加工食品是钠的重要来源，阅读标签是控制钠摄入的有效方法。"
        ),
        "usage_note": "换成食盐更直观，但注意其他配料也会贡献钠。",
        "source_name": "WHO《成人和儿童钠摄入量指南》（名称引用）",
        "source_url": WHO,
        "source_type": "public_health",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 53,
    },
    {
        "slug": "carbohydrate-sugar",
        "title": "碳水化合物与糖的关系",
        "aliases": "碳水化合物,糖,淀粉,膳食纤维",
        "category": "nutrition",
        "keywords": "碳水 糖 淀粉 纤维",
        "summary": "碳水化合物包括糖、淀粉和膳食纤维等，营养标签上的「碳水化合物」通常是一个总量概念。",
        "content": (
            "碳水化合物是一个大类，包括单糖、双糖（如蔗糖）、多糖（如淀粉）以及膳食纤维。"
            "不同标准对碳水化合物的计算口径略有差异（是否包含膳食纤维等），"
            "因此跨国比较标签数值时需要留意。标签上若单独列出「糖」，通常指单糖与双糖之和。"
        ),
        "usage_note": "总量高不等于全是添加糖，需结合配料表与「糖」项判断。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 54,
    },
    {
        "slug": "per-100g-vs-serving",
        "title": "每 100g 与每份：计量基准",
        "aliases": "每100g,每份,计量基准,份量",
        "category": "nutrition",
        "keywords": "基准 比较 份量",
        "summary": "比较不同食品的营养数值前，必须统一计量基准，否则容易得出错误结论。",
        "content": (
            "营养成分表通常按「每 100g（或每 100mL）」标示，也有的产品按「每份」标示。"
            "按每份标示时，必须知道一份是多少克才能比较；若标签未明确一份的重量，"
            "跨产品比较就会失真。此外，「每份」常小于 100g，看起来数值更低，但换算后可能并不低。"
        ),
        "usage_note": "比较前先看表头是「每 100g」还是「每份」。",
        "source_name": STANDARD_28050,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 55,
    },
    # ================= 标签与核查规则 =================
    {
        "slug": "ingredient-order",
        "title": "配料表为什么按顺序排列",
        "aliases": "配料表顺序,递减顺序,配料排序",
        "category": "label_rule",
        "keywords": "配料 顺序 递减 含量",
        "summary": "配料表一般按加入量从高到低排列，因此排序本身就是重要信息。",
        "content": (
            "预包装食品的配料表通常按各种配料加入量的递减顺序排列，"
            "加入量不超过一定比例的配料可以不按此顺序。"
            "因此，如果「白砂糖」排在前三位，通常意味着含糖量不低；"
            "如果水排第一，说明它是含量最高的成分。"
            "需要注意：复合配料的括号内子配料、以及可豁免排序的情形，会让简单推断出现偏差。"
        ),
        "usage_note": "排序是判断含量的有用线索，但不是精确的定量数据。",
        "source_name": STANDARD_7718,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 60,
    },
    {
        "slug": "date-marking",
        "title": "生产日期与保质期怎么看",
        "aliases": "生产日期,保质期,到期日期,喷码",
        "category": "label_rule",
        "keywords": "日期 保质期 喷码 到期",
        "summary": "生产日期与保质期（或到期日期）应清晰标示；到期日期 = 生产日期 + 保质期。",
        "content": (
            "标签通常需要标示生产日期与保质期，或者直接标示到期日期。"
            "保质期是在标注的贮存条件下保持品质的期限，因此贮存条件不满足时，保质期不能简单套用。"
            "计算到期日期时注意：按月计算通常按日历月推算，可能与厂家的实际计算口径略有差异，"
            "以包装上直接印制的到期日期为准。"
        ),
        "usage_note": "日期字迹模糊时不要猜测，可向商家或厂家核实。",
        "source_name": STANDARD_7718,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 61,
    },
    {
        "slug": "allergen-labeling",
        "title": "致敏物质提示",
        "aliases": "致敏物质,致敏原,过敏原,过敏提示",
        "category": "label_rule",
        "keywords": "过敏 致敏 提示 麸质 乳 坚果",
        "summary": "含常见致敏物质的食品通常以提示语方式告知，过敏人群应优先查看该项。",
        "content": (
            "常见致敏物质包括含麸质的谷物、甲壳类、鱼类、蛋类、花生、大豆、乳、坚果等。"
            "标签常以「含有……」「可能含有……」「致敏物质提示：……」等方式标注。"
            "不同地区对致敏物质标示的要求与强制程度不同，具体以现行法规与标准为准。"
            "对过敏人群而言，除看提示外，还应核对配料表，必要时直接联系厂家确认生产线情况。"
        ),
        "usage_note": "「可能含有」通常与共用生产线有关，过敏人群需谨慎对待。",
        "source_name": "预包装食品标签致敏物质标示相关要求（名称引用）",
        "source_url": NHC,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 62,
    },
    {
        "slug": "additive-labeling",
        "title": "食品添加剂在配料表中怎么标示",
        "aliases": "食品添加剂标示,添加剂,配料表添加剂",
        "category": "label_rule",
        "keywords": "添加剂 标示 名称 括号",
        "summary": "食品添加剂通常以「食品添加剂」字样引导并在括号中列出，或直接标示其通用名称。",
        "content": (
            "标签上常见的写法有两种：一是先写「食品添加剂」，再在其后括号内列出具体品种；"
            "二是直接在配料表中列出具体名称。使用的应当是标准中规定的通用名称。"
            "因此，配料表里出现「碳酸氢钠」「山梨酸钾」这样的名称是正常的标示方式，"
            "并不意味着厂家隐瞒了什么。复合配料中的添加剂标示方式另有规定，具体以标准文本为准。"
        ),
        "usage_note": "看到具体化学名称是规范标示的结果，不必因此紧张。",
        "source_name": STANDARD_7718,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 63,
    },
    {
        "slug": "product-standard-no",
        "title": "产品标准号是什么",
        "aliases": "产品标准号,执行标准,标准号,GB/T",
        "category": "label_rule",
        "keywords": "标准号 GB Q 执行标准",
        "summary": "标准号表示产品执行的标准，可用于进一步查询标准文本。",
        "content": (
            "产品标准号常见形式有国家标准（GB、GB/T）、行业标准（如 SB/T、NY/T）、"
            "地方标准（DB…）和企业标准（Q/…）。它说明产品声称执行的技术要求。"
            "如果想了解具体指标，可以到国家标准全文公开系统等官方平台查询标准文本。"
            "注意：标准号的存在不代表产品一定符合标准，符合性需要检验。"
        ),
        "usage_note": "标准号是查询的入口，不是质量合格的证明。",
        "source_name": STANDARD_7718 + "；国家标准全文公开系统",
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 64,
    },
    {
        "slug": "nutrition-label-basics",
        "title": "营养成分表的基本结构",
        "aliases": "营养成分表,营养标签,项目 每100g NRV%",
        "category": "label_rule",
        "keywords": "营养标签 表格 核心营养素",
        "summary": "营养成分表通常包含项目、每 100g（或每份）含量、NRV% 三列，核心项目是能量与四大营养素。",
        "content": (
            "营养标签以表格形式呈现，一般包括「项目」「每 100g（或每份）」「NRV%」三列。"
            "核心项目通常包括能量、蛋白质、脂肪、碳水化合物和钠。"
            "部分产品还会标示糖、膳食纤维、饱和脂肪、反式脂肪酸、钙等。"
            "没有标示的项目不等于含量为零，可能是未标示或低于标示阈值。"
        ),
        "usage_note": "「未标示」和「0」不是一回事，这一点在解读时很重要。",
        "source_name": STANDARD_28050,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 65,
    },
    # ================= 食品安全常识 =================
    {
        "slug": "additive-safety",
        "title": "食品添加剂 ≠ 不安全",
        "aliases": "食品添加剂安全,ADI,添加剂",
        "category": "safety",
        "keywords": "添加剂 安全 ADI 每日允许摄入量",
        "summary": "食品添加剂的安全性建立在「品种、范围、用量」三重管理之上，合规使用不等于有害。",
        "content": (
            "食品添加剂的使用遵循允许使用的品种、允许使用的食品类别、最大使用量或残留量三重管理。"
            "评估中常用「每日允许摄入量（ADI）」等指标，通常还会留出安全系数。"
            "真正需要警惕的是超范围、超限量使用以及非法添加物，而这些无法仅凭配料表判断。"
            "因此，「配料表里有添加剂」与「食品不安全」之间不能划等号。"
        ),
        "usage_note": "看到添加剂时，先问「是什么用途」，而不是直接问「有没有毒」。",
        "source_name": STANDARD_2760 + "；食品安全风险评估通用概念",
        "source_url": CFSA,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 70,
    },
    {
        "slug": "ocr-vs-lab-test",
        "title": "标签识别不能替代实验室检测",
        "aliases": "检测,实验室,微生物,农药残留,重金属,局限性",
        "category": "safety",
        "keywords": "检测 局限 微生物 农残 重金属 非法添加",
        "summary": "图片识别只能读取标签文字，无法发现微生物超标、农药残留、重金属或非法添加。",
        "content": (
            "本平台只能识别包装上的可见文字，并对文字的完整性与逻辑一致性做辅助核查。"
            "食品安全涉及的微生物污染、农药残留、重金属、真菌毒素、非法添加物等指标，"
            "必须通过实验室检测才能确认。此外，标签内容是否与实物一致，也需要实际核查。"
            "因此，本平台的分析结果不能作为食品是否安全或是否合规的判定依据。"
        ),
        "usage_note": "把这套工具当作「看懂标签的助手」，而不是「食品安全检测仪」。",
        "source_name": "平台功能边界说明（工程性说明）",
        "source_url": None,
        "source_type": "editorial",
        "verification_status": "verified",
        "version": "1.1",
        "is_featured": True,
        "sort_order": 71,
    },
    {
        "slug": "shelf-life-storage",
        "title": "保质期与贮存条件的关系",
        "aliases": "保质期,贮存条件,冷藏,冷冻,保存",
        "category": "safety",
        "keywords": "保质期 贮存 冷藏 冷冻 温度",
        "summary": "保质期是在指定贮存条件下的期限，条件不满足时保质期不再适用。",
        "content": (
            "食品的保质期与贮存条件绑定：标注「0-4℃ 冷藏」的产品，如果在常温下放置，"
            "其保质期不能直接套用。开封后的食品，其可食用期限通常也会缩短，"
            "并以产品说明为准。购买时除了看日期，还应确认销售环境的温度是否符合标注要求。"
        ),
        "usage_note": "日期没问题，但贮存条件不满足，同样会影响食品安全。",
        "source_name": "食品安全通用常识（教材级）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 72,
    },
    {
        "slug": "near-expiry-food",
        "title": "临期食品能不能吃",
        "aliases": "临期食品,临近保质期,打折食品",
        "category": "safety",
        "keywords": "临期 保质期 打折",
        "summary": "在保质期内且贮存条件符合要求时，临期食品通常可以正常食用。",
        "content": (
            "「临期」指的是接近但尚未超过保质期。在保质期内、且全程贮存条件符合标签要求的食品，"
            "通常可以正常食用，风味或口感可能略有变化。"
            "需要注意的是：如果贮存条件被破坏（如冷链中断），即使在保质期内也存在风险。"
            "购买临期食品时应检查包装是否完好、有无胀袋、霉变、异味等异常。"
        ),
        "usage_note": "价格优惠不等于质量有问题，但贮存条件必须达标。",
        "source_name": "食品安全通用常识（教材级）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 73,
    },
    {
        "slug": "label-photo-tips",
        "title": "怎样拍出能识别的食品标签照片",
        "aliases": "拍照技巧,识别失败,图片模糊,光线",
        "category": "safety",
        "keywords": "拍摄 清晰 光线 反光 角度",
        "summary": "正面平拍、光线均匀、避开反光、文字占画面主要区域，识别成功率最高。",
        "content": (
            "拍摄建议：1）让包装表面尽量平整，避免曲面导致文字变形；"
            "2）光线均匀，避免包装膜强反光；3）文字在画面中占较大比例，"
            "不要拍得过远；4）分别拍摄正面（名称、净含量）、配料表、营养成分表、"
            "日期喷码四个区域，识别更准确；5）使用手机原相机而非社交软件的压缩图。"
        ),
        "usage_note": "一张照片通常只能覆盖包装的一个面，多拍几张再逐张识别效果更好。",
        "source_name": "平台使用经验总结（工程性说明）",
        "source_url": None,
        "source_type": "editorial",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": True,
        "sort_order": 74,
    },
    # ================= 补充：常见配料（用于覆盖演示样例中的成分） =================
    {
        "slug": "erythritol",
        "title": "赤藓糖醇",
        "aliases": "赤藓糖醇,代糖,糖醇,甜味剂",
        "category": "additive",
        "keywords": "甜味剂 糖醇 零糖 饮料 甜度",
        "summary": "糖醇类甜味剂，甜度约为蔗糖的 60%–70%，能量系数很低，常见于「零糖」饮料。",
        "content": (
            "赤藓糖醇属于糖醇类甜味剂，甜度约为蔗糖的 60%–70%，入口有清凉感，常用于无糖饮料、"
            "口香糖与代糖产品。它在营养标签中的能量折算系数很低（通常按 0 kJ/g 处理，具体以现行标准为准），"
            "因此常被用于「0 糖 0 能量」配方。糖醇类一次大量摄入时，部分人可能出现腹胀或轻度腹泻，"
            "这属于渗透性反应，与「有毒」无关，控制份量即可。"
        ),
        "usage_note": "看到它说明产品用糖醇替代了蔗糖；对糖醇敏感的人注意一次不要吃太多。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 31,
    },
    {
        "slug": "calcium-carbonate",
        "title": "碳酸钙",
        "aliases": "碳酸钙,钙强化剂,膨松剂,酸度调节剂",
        "category": "additive",
        "keywords": "钙 强化 膨松 酸度 稳定",
        "summary": "兼具钙营养强化剂、膨松剂与酸度调节剂功能，在饼干、乳制品中较常见。",
        "content": (
            "碳酸钙是常见的钙盐，可作为营养强化剂补充钙，也可作为膨松剂或酸度调节剂使用。"
            "它在允许的食品类别和用量范围内使用是合规的。需要注意：配料表中出现碳酸钙，"
            "并不代表产品达到了「高钙」等营养声称的条件——那类声称需要满足标准规定的含量要求，"
            "应以营养成分表与标准原文为准。"
        ),
        "usage_note": "它既可能是补钙的强化剂，也可能是工艺用的膨松剂，具体看产品类型。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 32,
    },
    {
        "slug": "maltodextrin",
        "title": "麦芽糊精",
        "aliases": "麦芽糊精,糊精,填充剂,载体",
        "category": "ingredient",
        "keywords": "淀粉 水解 载体 增稠 升糖",
        "summary": "淀粉水解得到的产物，常作填充剂、载体与增稠剂，消化吸收较快。",
        "content": (
            "麦芽糊精由淀粉部分水解得到，易溶于水、口感温和，常作为粉末食品的填充剂与风味载体，"
            "也用于增加体积与改善冲调性。它的升糖速度较快，属于高升糖指数食物原料，"
            "需要控制血糖的人群在计入碳水化合物总量时应留意其占比。"
        ),
        "usage_note": "它本质上仍是碳水化合物，配料表出现并不等于「无糖」。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 46,
    },
    {
        "slug": "carbon-dioxide",
        "title": "二氧化碳",
        "aliases": "二氧化碳,碳酸气,气泡,碳酸",
        "category": "ingredient",
        "keywords": "气泡 碳酸 饮料 抑菌",
        "summary": "碳酸饮料中的气泡来源，溶于水形成碳酸，并有助于抑制部分需氧微生物。",
        "content": (
            "二氧化碳用于碳酸饮料、气泡水，提供气泡口感；溶解后形成碳酸，使产品呈弱酸性。"
            "它同时能降低包装内的氧气含量，对部分需氧微生物有抑制作用，"
            "因此常与防腐工艺配合使用。作为食品添加剂或加工助剂使用时需符合相应的使用要求。"
        ),
        "usage_note": "它带来「刺激感」，对牙齿酸蚀的影响主要与饮用频率有关。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 47,
    },
    {
        "slug": "yeast",
        "title": "酵母",
        "aliases": "酵母,酿酒酵母,活性干酵母,发酵剂",
        "category": "ingredient",
        "keywords": "发酵 膨松 烘焙 面团",
        "summary": "生物膨松剂，通过发酵产生二氧化碳使面团膨松，并带来特有的发酵风味。",
        "content": (
            "烘焙中使用的酵母通常是酿酒酵母，它消耗糖类产生二氧化碳与少量酒精，"
            "使面团膨胀、形成气孔。与化学膨松剂（如碳酸氢钠）相比，酵母发酵还产生风味物质。"
            "酵母本身富含蛋白质与 B 族维生素，但在成品中的实际贡献取决于用量与工艺。"
        ),
        "usage_note": "它属于「生物发酵」，与化学膨松剂不是一回事。",
        "source_name": "食品工艺学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 48,
    },
    {
        "slug": "raw-milk",
        "title": "生牛乳",
        "aliases": "生牛乳,牛乳,鲜牛奶,原料乳",
        "category": "ingredient",
        "keywords": "乳制品 乳蛋白 乳糖 钙 致敏",
        "summary": "以牛乳为原料的乳制品配料，含乳蛋白与乳糖，属于常见致敏原。",
        "content": (
            "生牛乳指未经加工或仅经初步处理的牛乳，作为配料出现在需要后续杀菌/发酵工艺的产品中"
            "（如巴氏杀菌乳、酸奶）。它提供乳蛋白、乳脂肪、乳糖与钙。"
            "牛奶蛋白过敏人群需要严格避免；乳糖不耐受人群可能出现胀气、腹泻，两者机制不同。"
            "产品标签上的贮存条件（如 2–6℃ 冷藏）与保质期需要一并留意。"
        ),
        "usage_note": "乳糖不耐受与牛奶过敏不同，前者可考虑低乳糖产品，后者需避免乳蛋白。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 49,
    },
    {
        "slug": "whey-protein",
        "title": "乳清蛋白粉",
        "aliases": "乳清蛋白粉,乳清蛋白,浓缩乳清蛋白,分离乳清蛋白",
        "category": "ingredient",
        "keywords": "乳制品 蛋白质 乳糖 健身 致敏",
        "summary": "乳制品来源的高蛋白配料，常用于酸奶、蛋白棒与运动营养食品。",
        "content": (
            "乳清蛋白是牛乳蛋白中的可溶性部分，含有人体所需的必需氨基酸，吸收速度较快。"
            "分离乳清蛋白的乳糖含量更低，适合部分乳糖不耐受人群，但乳蛋白过敏者仍需避免。"
            "配料表中的乳清蛋白粉会显著提高蛋白质含量，可结合营养成分表查看实际贡献。"
        ),
        "usage_note": "它属于乳制品来源，乳蛋白过敏者仍需回避。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 50,
    },
    {
        "slug": "lactic-acid-bacteria",
        "title": "乳酸菌（发酵菌种）",
        "aliases": "乳酸菌,保加利亚乳杆菌,嗜热链球菌,发酵菌,益生菌",
        "category": "ingredient",
        "keywords": "发酵 酸奶 菌种 活菌 乳糖",
        "summary": "酸奶发酵使用的菌种，把乳糖转化为乳酸，使乳凝固并产生酸味。",
        "content": (
            "保加利亚乳杆菌与嗜热链球菌是酸奶发酵的经典菌种组合：它们将乳糖发酵为乳酸，"
            "使乳蛋白凝固、形成细腻质地，并带来酸味。发酵还会降低部分乳糖含量，"
            "对轻度乳糖不耐受者更友好。活菌数量会随贮存温度与时间下降，"
            "因此低温贮存与保质期对这类产品尤其重要。"
        ),
        "usage_note": "「活菌型」产品需要冷链；常温酸奶通常经过杀菌，活菌已不再增殖。",
        "source_name": "食品微生物学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 51,
    },
    # ================= 补充：膨化食品/饮料标签里的高频配料 =================
    {
        "slug": "potato",
        "title": "马铃薯（土豆）",
        "aliases": "马铃薯,土豆,马铃薯片,马铃薯粉",
        "category": "ingredient",
        "keywords": "薯片 淀粉 钾 维生素C 油炸",
        "summary": "薯片、薯条等产品的主要原料，提供淀粉与钾；经油炸或膨化后脂肪含量会明显上升。",
        "content": (
            "马铃薯本身富含淀粉、钾和维生素 C，是常见的薯类主食原料。"
            "在薯片等膨化食品中，切片后通常经过油炸或热风膨化，脂肪与能量会显著上升，"
            "具体数值以营养成分表为准。发芽或变绿的马铃薯龙葵素含量升高，应避免食用。"
        ),
        "usage_note": "配料表出现「马铃薯」说明是薯类原料；关注脂肪与钠请看营养成分表。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 52,
    },
    {
        "slug": "whey-powder",
        "title": "乳清粉",
        "aliases": "乳清粉,乳清,甜乳清粉,乳清蛋白",
        "category": "ingredient",
        "keywords": "乳制品 乳糖 乳蛋白 奶香 致敏",
        "summary": "乳制品来源的配料，提供乳糖、乳蛋白与奶香味，属于常见致敏原。",
        "content": (
            "乳清粉是牛乳制取奶酪或酪蛋白后剩余的乳清经浓缩干燥得到，主要成分是乳糖与乳清蛋白。"
            "它常用于饼干、饮料、乳制品与烘焙食品，能提供奶香与部分蛋白质。"
            "牛奶蛋白过敏人群需要避免；乳糖不耐受人群可能因其中的乳糖出现腹胀。"
        ),
        "usage_note": "看到「乳清粉」说明含乳成分，乳蛋白过敏者需谨慎。",
        "source_name": "营养与食品卫生学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 53,
    },
    {
        "slug": "disodium-ribonucleotide",
        "title": "5'-呈味核苷酸二钠",
        "aliases": "5'-呈味核苷酸二钠,呈味核苷酸二钠,核苷酸二钠,肌苷酸二钠,鸟苷酸二钠,I+G",
        "category": "additive",
        "keywords": "增味剂 鲜味 协同 味精",
        "summary": "增味剂，与谷氨酸钠（味精）协同放大鲜味，用量通常很小。",
        "content": (
            "5'-呈味核苷酸二钠由肌苷酸二钠与鸟苷酸二钠组成，本身就有鲜味，"
            "与谷氨酸钠一起使用时能显著增强鲜味（常说的「I+G」）。它在允许的食品类别和用量范围内使用是合规的，"
            "在配料表中位置靠后通常说明用量很小。"
        ),
        "usage_note": "它和味精常一起出现，属于增鲜组合，不用因为名字长就担心。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 33,
    },
    {
        "slug": "neotame",
        "title": "纽甜",
        "aliases": "纽甜,甜味剂,高倍甜味剂",
        "category": "additive",
        "keywords": "甜味剂 高倍 用量极低 无糖",
        "summary": "高倍甜味剂，甜度约为蔗糖的数千倍，因此实际用量极低。",
        "content": (
            "纽甜是在阿斯巴甜结构基础上开发的甜味剂，甜度非常高、用量极小，"
            "常用于饮料、乳制品与蜜饯等需要甜味但控制能量的产品。"
            "在允许的食品类别和用量范围内使用是合规的；由于用量极低，它在配料表中通常排在最后几位。"
        ),
        "usage_note": "甜度极高意味着添加量很少，不必按「配料表顺序」推断它的绝对量。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 34,
    },
    {
        "slug": "carmine",
        "title": "胭脂虫红",
        "aliases": "胭脂虫红,胭脂红酸,天然色素,着色剂",
        "category": "additive",
        "keywords": "着色剂 天然色素 红色 素食 过敏",
        "summary": "从胭脂虫中提取的天然红色素，属于动物来源着色剂，极少数人可能过敏。",
        "content": (
            "胭脂虫红是从胭脂虫（一种介壳虫）中提取的红色色素，常用于饮料、糖果、肉制品等。"
            "它属于动物来源的着色剂，严格素食者可能需要留意；极少数人可能对其过敏，"
            "这属于个体反应。在允许的食品类别和用量范围内使用是合规的。"
        ),
        "usage_note": "「天然色素」不等于「植物来源」；素食人群可以关注这一条。",
        "source_name": STANDARD_2760,
        "source_url": WIKI_OFFICIAL,
        "source_type": "standard_name",
        "verification_status": "pending",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 35,
    },
    {
        "slug": "brewed-soy-sauce",
        "title": "酿造酱油",
        "aliases": "酿造酱油,酱油,生抽,老抽,酱油粉",
        "category": "ingredient",
        "keywords": "调味 发酵 钠 小麦 大豆 致敏",
        "summary": "大豆与小麦发酵制成的调味料，提供咸味、鲜味与色泽，是钠和小麦/大豆致敏原的来源。",
        "content": (
            "酿造酱油以大豆（或脱脂大豆）和小麦为主要原料，经微生物发酵制成，"
            "含有氨基酸、肽类与食盐，能提供咸味与鲜味。它既是钠的重要来源，"
            "也可能带入小麦与大豆致敏原，过敏人群需要留意配料表与致敏提示。"
        ),
        "usage_note": "复合调味料里的「酱油粉」同样是钠与致敏原的来源。",
        "source_name": "食品工艺学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 54,
    },
    {
        "slug": "chili-powder",
        "title": "辣椒粉",
        "aliases": "辣椒粉,辣椒,香辛料,红辣椒粉",
        "category": "ingredient",
        "keywords": "香辛料 辣味 调味",
        "summary": "天然香辛料，提供辣味与香气，属于「香辛料」类配料。",
        "content": (
            "辣椒粉由辣椒干燥研磨而成，主要提供辣味与香气，属于天然香辛料。"
            "它本身热量贡献很小，通常用量不大；对辣味敏感或胃肠道敏感的人群按自身情况调整即可。"
        ),
        "usage_note": "香辛料通常用量很少，看配料表时不必过度关注它的排名。",
        "source_name": "食品工艺学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 55,
    },
    {
        "slug": "onion-powder",
        "title": "洋葱粉",
        "aliases": "洋葱粉,洋葱,脱水洋葱,香辛料",
        "category": "ingredient",
        "keywords": "香辛料 调味 甜味 葱香",
        "summary": "脱水洋葱研磨制成的调味料，提供葱香与甜味。",
        "content": (
            "洋葱粉是洋葱经脱水、研磨得到的粉末，常用于调味料、膨化食品与汤料，"
            "提供葱香和轻微甜味。它属于天然香辛料/蔬菜类配料，用量通常较小。"
        ),
        "usage_note": "它常与辣椒粉、香辛料一起出现在复合调味料里。",
        "source_name": "食品工艺学通用知识（教材级常识）",
        "source_url": None,
        "source_type": "textbook",
        "verification_status": "verified",
        "version": "1.0",
        "is_featured": False,
        "sort_order": 56,
    },
]


# ===== 第二批扩展条目（见 knowledge_seed_extra.py）=====
from .knowledge_seed_extra import EXTRA_KNOWLEDGE_ENTRIES

KNOWLEDGE_ENTRIES.extend(EXTRA_KNOWLEDGE_ENTRIES)
