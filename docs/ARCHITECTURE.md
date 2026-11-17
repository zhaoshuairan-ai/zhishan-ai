# 系统架构说明

## 一、总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│  浏览器（电脑 / 安卓 / iPhone）                                    │
│  Vue 3 SPA（Element Plus + Pinia + ECharts + PWA）                │
│  · 页面路由与登录守卫                                              │
│  · 图片通过带 Authorization 的请求取回并转 blob 显示                │
└───────────────┬──────────────────────────────────────────────────┘
                │ HTTPS · JSON（统一响应结构）· Bearer Token
                │ 开发时：Vite 代理 /api → 127.0.0.1:5000
                │ 生产时：同源（Flask 托管 dist）或独立域名 + CORS
┌───────────────▼──────────────────────────────────────────────────┐
│  Flask 后端（分层架构）                                            │
│  api/       路由层：参数校验、鉴权、统一响应                        │
│  services/  业务层：OCR、AI 解读、解析、核查、知识库、存储           │
│  rules/     规则库（集中维护，带版本/依据/来源）                    │
│  models/    持久化层：SQLAlchemy 模型                              │
│  schemas/   Pydantic 校验模型（大模型 JSON 输出）                   │
└───────┬───────────────────┬───────────────────┬──────────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
  SQLite 数据库         uploads/ 目录       外部服务（均可配置/可降级）
  data/*.db            UUID 文件名          · 本地 RapidOCR（ONNX）
  （记录/知识/账号）    原图 + 展示图         · OpenAI 兼容视觉模型
                                              · OpenAI 兼容大语言模型
```

**核心原则**

1. 前端不直接连接数据库，所有数据通过 HTTP API 读写。
2. 所有外部能力（OCR / LLM）都可配置，并且在不可用时**明确降级**，不伪装结果。
3. 每条 AI 解释与每条核查结论都必须能追溯到知识库条目或规则定义。

---

## 二、技术选型

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 前端框架 | Vue 3 + TypeScript + Vite | 组合式 API 便于拆分逻辑，Vite 启动快，TS 保证接口字段一致 |
| UI | Element Plus | 组件齐全、中文文档完善、移动端可用 |
| 状态 | Pinia | 只存登录态与全局设置；业务数据一律来自后端 |
| 图表 | ECharts（按需引入） | 条形图/折线图/饼图足够表达营养与统计 |
| 后端 | Flask + SQLAlchemy | 轻量、易读，适合比赛与教学；SQLAlchemy 保证模型清晰 |
| 校验 | Pydantic v2 | 校验大模型 JSON 输出，字段类型与取值范围一次性约束 |
| 存储 | SQLite + 受控文件目录 | 单机零配置；结构上可平滑替换 PostgreSQL |
| OCR | RapidOCR（ONNX） | 离线、无需 Key、中文识别效果好；同时支持视觉模型 |
| 部署 | waitress / Docker | Windows 友好；Linux 可换 gunicorn |

---

## 三、后端模块职责

```
backend/app/
├── __init__.py            # 应用工厂：配置、扩展、CORS、错误处理、前端托管、CLI
├── config.py              # 环境变量集中读取（含 TestConfig）
├── extensions.py          # db / cors 实例
├── api/
│   ├── common.py          # JSON 入参、分页参数校验
│   ├── health.py          # GET /api/health（数据库/存储/OCR/AI 状态）
│   ├── auth.py            # 注册/登录/退出/当前用户 + 登录限流
│   ├── dashboard.py       # 首页统计（真实/演示数据分开统计）
│   ├── uploads.py         # 图片上传（类型、大小、文件名校验）
│   ├── ocr.py             # 触发 OCR 并保存原始/校正基线
│   ├── analyze.py         # 触发完整分析流水线
│   ├── records.py         # 列表/详情/校正/删除/图片/重新分析
│   ├── reports.py         # 报告聚合（含来源与规则依据）
│   └── settings_api.py    # 运行状态（密钥仅显示是否配置）
├── services/
│   ├── ocr/               # 驱动抽象：base / local_rapidocr / vision_llm / demo / service
│   ├── field_parser.py    # OCR 文本 → 11 个结构化字段 + 置信度 + 标记
│   ├── text_utils.py      # 文本归一化、段落截取（跨行/无空格容错）
│   ├── nutrition_parser.py# 营养成分表 → 项目/数值/单位/NRV%
│   ├── ingredient_parser.py# 配料文本 → 有序配料项（含复合配料展开）
│   ├── knowledge_service.py# 检索、匹配、上下文组织、种子导入
│   ├── ai_service.py      # 大模型调用 + 校验 + 幻觉过滤 + 规则模式兜底
│   ├── checker.py         # 规则引擎（24 条规则，三档结论）
│   ├── storage.py         # 图片落盘、展示图生成、安全读取与删除
│   └── analysis_service.py# 编排：解析 → 知识匹配 → AI/规则 → 核查 → 入库
├── models/                # 9 张表（见 DATABASE.md）
├── rules/label_rules.py   # 规则元数据（标题/依据/来源/待确认/版本）
├── schemas/ai_output.py   # 大模型输出结构（Pydantic）
└── seed/                  # 知识库种子、演示数据、初始化与列级升级
```

**设计要点**

- 路由层只做参数校验与权限判断，业务逻辑全部在 `services/`。
- `analysis_service.analyze()` 是唯一的分析入口，保证网页、重新分析、演示数据三条路径行为一致。
- 规则与知识分离：规则判断「逻辑是否一致」，知识解释「成分是什么」，两者不互相污染。

---

## 四、前端结构

```
frontend/src/
├── api/            # client.ts（Axios 封装/错误/鉴权）、index.ts（接口集合）、types.ts（类型）
├── stores/         # auth（登录态）、app（网络状态/运行状态/安装引导）
├── router/         # 路由表 + 登录守卫 + 标题
├── layouts/        # AppLayout：桌面侧栏、移动端顶栏+抽屉+底部导航
├── components/     # AuthImage、ChartCard、NutritionPanel、IngredientPanel、CheckPanel、StatCard…
├── views/          # 9 个页面
├── utils/          # 格式化、ECharts 主题、配料文本拆分
└── styles/         # 设计变量、响应式规则、打印样式
```

**响应式策略**

- 断点：`1200 / 1024 / 900 / 768 / 560 / 380`，同时用 `useBreakpoint()` 做**结构性切换**（表格 ↔ 卡片）。
- 布局：桌面侧栏 + 宽屏多列网格；≤1024 折叠为顶栏 + 抽屉；≤768 用底部导航，内容单列。
- 所有长文本 `overflow-wrap: anywhere`；表格外层 `overflow-x:auto`；图片 `object-fit: contain` 保证不拉伸。
- 报告页在 ≤768 时把宽表格换成卡片，并单独定义 `@media print` 隐藏导航、去掉阴影。

---

## 五、一次分析的完整时序

```
① 上传  POST /api/upload (multipart)
        → 校验 MIME/大小（Pillow 真实解码，不看扩展名）
        → 生成 UUID 文件名，写入 uploads/，生成展示图（长边 ≤2200，EXIF 方向校正）
        → 创建 analysis_records（status=uploaded）+ uploaded_images
        返回 record_id

② 识别  POST /api/ocr {record_id}
        → 按 OCR_PROVIDER 选择驱动：local（RapidOCR）→ vision（视觉模型）→ demo
        → 文本行 + 置信度
        → field_parser 解析 11 个字段（食品名称/配料表/营养成分表/净含量/生产日期/保质期/
          到期日期/贮存条件/生产者/产品标准号/致敏物质提示）
        → 保存 ocr_results（raw_text + fields + 置信度 + 缺失/低置信度 + provider）
        → 记录 status=ocr_done；若为演示驱动，记录 is_demo=True

③ 校正  PUT /api/records/{id}/ocr {fields}
        → 覆盖 fields，保留 raw_text；校正字段置信度置 1.0
        → 重建 corrected_text，status=corrected

④ 分析  POST /api/analyze {record_id, type: package|dish}
   识饭菜：视觉模型识别菜名/重量 → 菜品营养库检索 → 份量换算 → SSE 输出
        → ingredient_parser 拆分配料（括号感知、复合配料展开、百分比提取）
        → nutrition_parser 解析营养表（项目/数值/单位/NRV%，缺失标记 missing）
        → knowledge_service.match_names 匹配知识条目（精确 > 包含）
        → ai_service：
             · 有 Key → 大模型（知识库作为上下文）→ Pydantic 校验 → 丢弃幻觉配料与虚构引用
             · 无 Key / 调用失败 → 规则模式（知识库原文摘要 + 名称特征），记录降级原因
        → checker.run_checks：字段完整性、识别质量、日期逻辑、单位与数值、配料表、透明度
        → 落库：ingredient_analyses / nutrition_facts / label_checks
        → 更新 analysis_records（status=analyzed, analysis_mode, overall_check, summary）
        → 使旧报告失效（下次访问重新生成）

⑤ 展示  GET /api/records/{id}   → 结果页完整数据
⑥ 报告  GET /api/reports/{id}   → 报告编号 + 生成时间 + 全部 section + 来源 + 规则依据
```

**降级链路（任何一环失败都不产生假数据）**

```
OCR:    配置驱动 → 本地 RapidOCR → 视觉模型 → 演示样例（is_demo=True，页面顶部红色横幅）
AI:     OpenAI 兼容 LLM → 失败自动规则模式（结果里写明原因，unconfirmed 中提示）
解析:   字段缺失 → 标记 missing（不填默认值）；营养缺失 → 「未识别」
```

---

## 六、AI 输出的可信性控制

1. **提示词约束**：禁止判定安全性/合规性，禁止编造标准编号，不确定必须标 `unverified`。
2. **结构校验**：Pydantic 模型约束字段类型、长度、枚举（confidence / evidence）。
3. **幻觉过滤**：
   - 模型返回的配料名必须能在配料表中找到（否则丢弃并记入 `unconfirmed`）；
   - 引用必须能对应到本次检索到的知识库条目（否则丢弃并提示「引用无法对应」）。
4. **可追溯**：每条解释附带 `knowledge_refs`（知识库 ID/标题/来源/核验状态）。
5. **重试与降级**：格式错误重试一次；仍失败则降级规则模式，并把失败原因写入结果。

**离线可验证**：仓库提供 `scripts/mock_llm_server.py`，一个本地 OpenAI 兼容服务，
既可在没有 Key 时演示「大模型模式」界面，也被 `tests/test_ai_mode.py` 用来验证
「成功 / 幻觉 / 虚构引用 / 非法 JSON / 500 / 视觉 OCR」等路径。

---

## 六点五、食安科普助手（RAG）

目标：**答案不产生幻觉**，每句话都能落到已收录条目上。

```
用户问题
  ↓ 中文分词（字符二元组 + 英文词）
  ↓ BM25 检索（标题×4 / 别名×5 / 关键词×3 / 结论×2 / 正文×1）
  ↓ 别名命中 +8、标题命中 +6（口语化问法主要靠别名）
  ↓ 阈值判定：score ≥ 4 且（别名/标题命中 或 二元组覆盖率 ≥ 60%）
  ├─ 命中 → 取最相关 1 条
  │    ├─ retrieval 模式：把条目的「结论 / 为什么 / 依据 / 注意」原样组织成回答 + 来源清单
  │    └─ ai 模式：把条目作为唯一资料交给大模型改写
  │         ├─ 提示词限定：只能使用资料、必须标注 [K1]、资料没有就说“未提及”
  │         ├─ 引用白名单：不在 1..N 的 [K#] 直接删除
  │         ├─ 逐句依据校验：句子与资料的三元组重合度 < 20% 则丢弃
  │         └─ 保留句数不足或丢弃多于保留 → 自动退回 retrieval，并注明“已改为检索直答”
  └─ 未命中 → 若配置了 AI：让模型在候选条目里「选一条」（只做路由，不生成事实）
       ├─ 选中 → 用该条目原文作答，标注“未直接命中”、附来源
       └─ 未选中（NONE）→ 明确回复“未收录”，给出相近条目
```

数据表：

| 表 | 作用 |
| --- | --- |
| `assistant_entries` | 可引用的科普条目（结论/原因/依据/注意/来源 JSON/核验状态） |
| `chat_sessions` | 会话（按用户隔离，标题取首个问题） |
| `chat_messages` | 消息（含 `sources` 与 `payload` 快照，历史记录不受条目后续修改影响） |

引用链：`回答句子 → 条目 → 来源文档`。AI 模式只使用检索到的第一条目，避免 `[K2]` 指向未展示来源的条目。

## 七、权限模型

- 账号：密码 scrypt 哈希；会话令牌随机 32 字节，数据库仅存 SHA-256，30 天过期。
- 归属：`analysis_records.user_id` 决定可见性；查询一律带 `user_id` 过滤。
- 越权：`owned_or_404()` 对「不存在」和「不属于你」统一返回 404，避免探测他人记录。
- 图片：`GET /api/records/{id}/image` 需要登录且校验归属；前端用带头的请求取 blob。
- 删除：只删除自己的记录，并同步删除磁盘文件。

---

## 八、PWA 策略

| 资源 | 策略 |
| --- | --- |
| `/api/**` | **仅网络**，永不缓存（避免旧结果覆盖新结果、避免数据泄露） |
| 页面导航 | 网络优先，离线回退缓存的 `index.html` / `offline.html` |
| 静态资源（js/css/图片/字体） | stale-while-revalidate |
| 缓存版本 | `fsai-v2-*`，激活时清理旧版本缓存；安装阶段解析 index.html 预缓存带哈希的 JS/CSS |

Service Worker 只在**生产构建**注册（`import.meta.env.PROD`），避免开发时缓存干扰热更新。

**浏览器兼容性**

| 浏览器 | 安装到主屏幕 | 离线缓存 | 说明 |
| --- | --- | --- | --- |
| Chrome / Edge（安卓、桌面） | ✅ 支持（含自动安装提示） | ✅ | 完整 PWA 体验 |
| Safari（iOS / iPadOS） | ⚠️ 需「分享 → 添加到主屏幕」，无自动提示 | ✅ 首次访问后可用 | 不支持 `beforeinstallprompt` |
| 微信 / QQ 内置浏览器 | ❌ 一般不支持安装 | ⚠️ 部分受限 | 建议引导用户「在浏览器中打开」 |
| Firefox 桌面 | ⚠️ 支持有限 | ✅ | 不显示安装入口 |

应用内已做兼容处理：`beforeinstallprompt` 不可用时隐藏安装按钮；离线时顶部显示网络提示；
分析失败且为网络原因时，校正页显示「恢复网络后可继续」的提示，不会丢失已填写的校正内容。
manifest 提供 192/512/遮罩图标、standalone 显示模式、3 个快捷入口。

---

## 九、性能与容量

| 关注点 | 现状 | 说明 |
| --- | --- | --- |
| 图片大小 | 上传 ≤10MB；展示图长边 ≤2200px、JPEG q86 | 手机原图 5-8MB 也能正常展示 |
| OCR 耗时 | 首次约 5-8 秒（加载模型），之后 3-6 秒 | 取决于 CPU；已用单例复用引擎 |
| 前端体积 | element 342KB(gz) + echarts 182KB(gz) + vue 44KB(gz) | 按路由懒加载页面 |
| 数据库 | SQLite，单文件 | 记录列表按 8 条分页；统计只取最近 300 条 |
| 并发 | waitress 8 线程 | 比赛演示足够；正式多实例建议换 PostgreSQL + Redis |

---

## 十、可扩展点

- OCR 驱动：实现 `BaseOcrProvider` 并在 `PROVIDERS` 注册即可（如接入百度/腾讯 OCR）。
- AI 服务：`ai_service.run_ai_analysis` 是唯一入口，可替换为其他厂商协议。
- 知识库：`knowledge_service.upsert_seed()` 幂等导入，可扩展为后台管理或权威资料批量导入。
- 规则：在 `rules/label_rules.py` 登记元数据 + 在 `checker.py` 实现判定，版本号随规则集升级。
