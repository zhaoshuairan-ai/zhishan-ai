# 测试说明与实测结果

> 本文档记录**实际执行过**的测试与结果。凡未执行的项目都在最后一节明确列出，不虚构“全部通过”。

- 测试时间：2026-10-17
- 环境：Windows 10/11 · Python 3.12.14 · Node 24.21.0 · Chromium（Playwright 内置）
- 后端依赖：Flask 3.1.3 / SQLAlchemy 2.1.5 / Pydantic 2.14.1 / rapidocr-onnxruntime 1.4.4 / waitress 3.x
- 前端依赖：Vue 3.5.44 / Vite 5.4.21 / Element Plus 2.14.7 / ECharts 5.6.0 / TypeScript 5.6.3

---

## 一、测试策略

| 层级 | 工具 | 覆盖内容 |
| --- | --- | --- |
| 单元测试 | pytest | 字段解析、配料解析、营养解析、日期推算、规则引擎判定 |
| 接口测试 | pytest + Flask test client | 鉴权、上传校验、OCR 成功/失败、分析降级、记录增删查、报告权限、知识库检索 |
| 集成测试 | pytest（真实 OCR 引擎） | 生成中文标签图片 → 上传 → OCR → 字段正确性 |
| 端到端冒烟 | requests 脚本 | 对运行中的服务跑完整业务流程，自动清理数据 |
| 生产冒烟 | requests 脚本 | 静态托管、PWA 资源、同源 API、受保护图片与报告 |
| 前端静态检查 | vue-tsc | 类型错误（0 容忍） |
| 前端构建 | vite build | 生产构建是否成功 |
| 响应式检查 | Playwright | 7 种宽度 × 11 个路由的横向溢出与整页截图 |

---

## 二、后端 pytest（238 项）

先安装测试依赖（`requirements-dev.txt` 已包含 requirements.txt）：

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

运行：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

**实际输出**

```
........................................................................ [ 79%]
...................                                                      [100%]
238 passed in 134.99s
```

| 文件 | 数量 | 覆盖点 |
| --- | --- | --- |
| `test_pantry.py` | 41 | 食材 CRUD/归属校验、临期与过期提醒、健康画像、规则食谱（临期优先/过敏排除/高血压提示/采购清单）、AI 规划、AI 非法/含过敏原降级、历史方案；语音/小票解析、批量导入、保质期/条码查询、SSE 单次推送、模拟邮件通知、临期拯救、AI 被规则引擎否决后重新生成、品牌包装食品保质期命中、警告聚合、服务端条码解码、ShowAPI 查询与缓存、Open Food Facts 公开库映射、本地公开条码兜底、偏心/旋转条码分块识别、保质期置信度/快捷选项/未估算留空 |
| `test_health_score.py` | 6 | 健康分边界（高糖/高钠/高反式脂肪、优质产品、数据不足不评分）、添加剂合规「待核实」、免责声明、详情/报告包含健康评估 |
| `test_health.py` | 6 | 健康检查、请求 ID、未知接口 404、未登录拦截、设置页不泄露密钥、规则集接口 |
| `test_auth.py` | 9 | 注册/登录/退出、弱密码、重复用户名、错误密码、令牌失效、密码哈希非明文 |
| `test_upload.py` | 11 | PNG/JPEG/WEBP 上传、伪造图片、GIF 拒绝、缺文件、超大小 413、未登录、文件名清洗、唯一记录 |
| `test_ocr.py` | 8 | OCR 成功字段、记录不存在、跨用户 404、引擎失败 502（可重试）、校正保存、未知字段拒绝、未识别先校正 |
| `test_analysis.py` | 10 | 完整结果结构、必须先 OCR、空内容拒绝、**AI 失败自动降级规则模式**、**规则模式营养解读**、重新分析、越权、营养缺失标记、名称/营养手工完善、饮用水提示与营销名回退 |
| `test_ai_mode.py` | 7 | **大模型模式全链路**（模拟服务）、幻觉配料过滤、虚构引用过滤、非法 JSON 重试后降级、500 降级、强制规则模式、**视觉模型 OCR**、视觉模型无 Key 回退演示 |
| `test_records.py` | 10 | 空列表、分页、状态筛选、关键词搜索、详情、删除并清理文件、**食谱收藏与排期、详情抽屉扣库存与营养兜底、一键清空、跨用户隔离**、图片鉴权、仪表盘统计 |
| `test_reports.py` | 6 | 报告完整性、未分析返回 409、越权 404、未登录 401、报告编号幂等、重新分析后编号变化 |
| `test_auth_security.py` | 6 | 验证码题目/答案/一次性校验、登录必须验证码、管理员登录验证码、修改密码（旧密码错误/弱密码/新旧相同/成功后旧令牌失效）、未登录改密、停用用户改密 |
| `test_admin.py` | 25 | 未登录 401、普通用户 403、管理员登录/限流/退出、停用用户立即失效、密码重置、记录备注与删除、知识库 CRUD 与发布约束、规则版本追溯、审计日志、监控不泄露密钥、反馈处理 |
| `test_family.py` | 1 | 家庭邀请码加入、家庭库存共享、胃炎用户辛辣食品提醒 |
| `test_knowledge.py` | 10 | 列表与分类、关键词搜索、分类过滤、非法分类、详情、404、来源 URL 合法性、种子规模与唯一性、导入模板合法性 |
| `test_assistant.py` | 38 | 检索命中/别名加权/拒答阈值、回答附带来源、未收录不编造、会话归属与删除、AI 改写逐句依据校验（剔除无依据句）、AI 失败自动退回检索直答、未直接命中时 AI 在候选条目中选一条、AI 判断无法回答时拒答 |
| `test_vision_endpoint.py` | 5 | 地址规范化、`/v1` 404 自动回退、双地址全 404 的报错、环境变量行内注释清洗 |
| `test_init_db.py` | 4 | 初始化幂等性、10 张表齐备、列级升级为空操作、新列已登记迁移 |
| `test_parsers.py` | 32 | 字段截取（同行/换行）、11 字段解析、不编造缺失值、复合配料展开、百分比、营养解析（NRV 折行、**逐格表格**、单位错字、kcal 换算、缺失标记）、配料软换行与括号不配对、食品名称不误取表头、保质期推算、闰年、规则引擎（过期/未来日期/缺失/数值异常/高钠提示/演示披露） |
| `test_ocr_real_engine.py` | 1 | **真实本地 OCR**：上传中文标签图片 → 识别 → 配料/营养/日期/净含量全部正确 |

其中真实 OCR 测试默认参与执行；若环境未安装 `rapidocr-onnxruntime` 会自动 skip 而不是失败：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ocr_real_engine.py -v
# tests/test_ocr_real_engine.py::test_local_ocr_recognizes_chinese_label PASSED [100%]
# 1 passed in 7.13s
```

### 大模型与视觉模型链路是怎么测的？

测试启动一个**本地 OpenAI 兼容模拟服务**（`scripts/mock_llm_server.py`），把后端的
`AI_BASE_URL` / `OCR_VISION_BASE_URL` 指向它，从而在**没有任何真实 Key、不消耗额度**的情况下验证：

| 测试 | 注入的行为 | 验证点 |
| --- | --- | --- |
| 成功链路 | 返回合法 JSON（按提示词中的配料逐项生成解释） | `analysis_mode=ai`、模型名落库、引用有效、前端显示「大模型分析」 |
| 幻觉过滤 | 额外返回一个不存在的配料「火星矿石粉」 | 该配料不出现在结果中，被记入 `unknown_items` 与「待确认事项」 |
| 引用过滤 | 额外返回知识库 ID 999999 | 虚构引用被丢弃，并在待确认事项中说明 |
| 非法 JSON | 返回普通文本 | 自动重试一次 → 仍失败则降级规则模式，并记录原因 |
| 上游 500 | 返回 HTTP 500 | 降级规则模式，结果中提示「大模型调用失败」 |
| 强制规则 | `AI_PROVIDER=rule` | 即使配置了 Key 也不发起请求 |
| 视觉 OCR | 请求带 image_url 时返回标签字段 | `provider=vision_llm`、字段正确、`is_demo=False` |
| 视觉无 Key | `OCR_PROVIDER=vision` 且 Key 为空 | 自动回退到演示驱动，并返回 `demo_warning` |

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\test_ai_mode.py -v
# 7 passed in 8.30s
```

> 说明：这套测试验证的是**协议、校验与降级链路**，不代表某家厂商模型的真实输出质量。
> 真实厂商 API 需要配置自己的 Key 后人工验证（见第八节）。

---

### 真实用户图片回归（发现并修复的解析缺陷）

用手机实拍的零食/饮料标签（RapidOCR 输出为「逐格表格」而不是整行）做回归，发现 5 个真实缺陷并已修复：

| # | 缺陷 | 现象 | 修复 |
| --- | --- | --- | --- |
| 1 | 营养成分段落被截断 | `max_lines=16`，表格拆行后只取到前 5 项 | 上限提高到 44 行 |
| 2 | 名称/数值/NRV% 各占一行 | 所有营养项都被判为「未识别」 | 新增「逻辑行合并」：名称行 + 数值行 + 百分比行拼回一行 |
| 3 | OCR 把「千焦」识别成「干焦」 | 能量单位缺失 → 标记为待确认 | 单位归一化表补充 `干焦 → kJ` |
| 4 | 配料行内折行被当成分隔符 | 出现「聚甘油脂」「肪酸酯」两个错误配料 | 换行按软换行拼接，由 `、,，;；/` 决定切分 |
| 5 | 括号不配对（OCR 多了一个「（」） | 后续 19 种配料被吞进同一个 token | 括号深度上限设为 1，闭合后恢复正常切分 |
| 6 | 食品名称被推断成表头/百分比 | 名称变成「11%」「每份食用量…」 | 增加通用词与纯数字过滤；识别不到就如实返回「未识别」 |

修复前后（同一条真实记录，仅重新解析、未改用户数据）：

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 营养项（有数值） | 0 项 | 7 项（能量 889kJ / 蛋白质 2.3g / 脂肪 13.3g / 饱和脂肪酸 6.6g / 碳水 20.6g / 膳食纤维 1.0g / 钠 323mg） |
| 配料项 | 1 个（被括号吞并） | 20 项 |
| 食品名称 | 「11%」 | 未识别（图片确实没拍到名称，如实为空） |

这些回归用例已固化为单元测试（`tests/test_parsers.py` 中 4 条新增用例），防止后续改动再退化。
用户已有的分析记录不会被自动改写，可在结果页点击「重新分析」应用修复后的解析。

---

### 科普助手（RAG）验证

| 验证 | 方法 | 结果 |
| --- | --- | --- |
| 命中示例问题 | `隔夜菜到底能不能吃？` / `西瓜和桃子一起吃会中毒吗？` | ✅ 分别命中 `leftover-food` / `food-incompatibility` |
| 未收录问题 | `量子水能养生吗` / `今天股市怎么样` | ✅ `matched=false`，不返回来源，给出相近条目 |
| 回答带来源 | 接口断言 `sources` 非空、每条有名称与机构 | ✅ 通过 |
| 引用链路 | AI 回答中的 `[K1]` 只指向最相关条目，来源清单为该条目的文档 | ✅ 通过 |
| 幻觉句过滤 | 模拟服务返回一句无关内容 | ✅ 被逐句校验剔除（`dropped_sentences ≥ 1`） |
| 大模型失败 | 把 `AI_BASE_URL` 指向不可达端口 | ✅ 自动退回检索直答并注明 |
| 会话隔离 | 他人会话读取/删除 | ✅ 均返回 404 |
| 浏览器检查 | Playwright 1366 / 390 提问并断言 | ✅ 10/10：来源、依据摘要、引用角标、无溢出、0 控制台错误 |

---

## 三、端到端接口冒烟（33 项）

```powershell
backend\.venv\Scripts\python.exe scripts\api_smoke_test.py
```

覆盖：健康检查 → 未登录拦截 → 登录 → 仪表盘/记录/知识库/设置/我的 → 上传 → OCR（真实本地引擎）
→ 校正 → 分析 → 记录详情/分页 → 报告 → 图片读取 → 不存在记录 404 → 删除 → 删除后 404。

**实际输出（节选）**

```
  [PASS] GET /api/health 返回 200 — HTTP 200
  [PASS] 未登录访问 /api/records 被拒绝 — HTTP 401
  [PASS] 登录成功 — HTTP 200
  [PASS] POST /api/upload — 图片上传成功，可以开始文字识别
    记录 ID = 3
  [PASS] POST /api/ocr — 文字识别完成，请核对识别结果
    OCR 驱动：本地 OCR 引擎（RapidOCR，离线）（演示模式=False，耗时 5813ms）
    配料表：生牛乳、白砂糖、乳清蛋白粉、保加利亚乳杆菌、嗜热链球菌
  [PASS] PUT /api/records/<id>/ocr 保存校正 — 识别结果已保存
  [PASS] POST /api/analyze — 分析完成
    分析模式：rule，整体核查：suspected，配料数：5
  [PASS] GET /api/reports/<id> — ok
  [PASS] 报告包含核查依据来源 — 16 个来源
  [PASS] DELETE /api/records/<id>
结果：通过 33 项，失败 0 项
```

> 本次运行的整体核查为 `suspected`，因为测试图片故意使用了已过期的生产日期（2026-01-15 + 21 天），
> 说明「日期逻辑核查」规则确实在工作，而不是永远返回“没问题”。

---

## 四、生产模式冒烟（13 项）

```powershell
# 先以单服务模式启动
$env:SERVE_FRONTEND="1"; python backend\wsgi.py   # 或 start_prod.bat
backend\.venv\Scripts\python.exe scripts\prod_smoke_test.py --base-url http://127.0.0.1:8000
```

**实际输出**

```
[PASS] GET / 返回前端页面 — HTTP 200
[PASS] 首页引用构建后的 JS
[PASS] GET /api/health
[PASS] PWA manifest 可访问且合法 — application/manifest+json
[PASS] PWA 图标全部可访问 — 3 个图标
[PASS] Service Worker 可访问
[PASS] SPA 路由回退到 index.html
[PASS] 离线提示页可访问
[PASS] 未知 API 返回统一 JSON 404
[PASS] 同源登录成功 — HTTP 200
[PASS] 记录列表可读 — 2 条
[PASS] 受保护的图片接口
[PASS] 报告接口
结果：通过 13 项，失败 0 项
```

---

## 五、PWA / 离线 / 打印 / 局域网（6 项）

```powershell
# 需先以生产模式启动：SERVE_FRONTEND=1，端口 8000
backend\.venv\Scripts\python.exe scripts\pwa_check.py
```

**实际输出**

```
[PASS] Service Worker 已注册并激活 — http://127.0.0.1:8000/sw.js
[PASS] 缓存中没有 /api 数据 — 11 个缓存项，0 个 API 项
[PASS] 应用外壳（JS/CSS）已预缓存 — fsai-v2-html、fsai-v2-static
[PASS] 断网后可打开缓存页面并提示离线 — 页面已渲染并提示离线
[PASS] 报告可打印为 PDF — 703 KB -> report.pdf
[PASS] 可通过局域网 IP 访问生产服务 — http://<局域网IP>:8000
通过 6 / 6 项
```

- 生成的示例 PDF 由 `scripts/pwa_check.py` 在本地生成，不随仓库提交。
- Service Worker 的策略：`/api/**` 永不缓存（实测缓存项中 0 个 API 请求）；静态资源 stale-while-revalidate；
  安装阶段解析 `index.html` 预缓存带哈希的 JS/CSS，保证首次访问后断网也能启动应用外壳。
- **修复记录**：初版 SW 只预缓存了 `index.html`，断网后 `#app` 为空（JS 未缓存）。
  已改为安装时解析 index 并预缓存 `/assets/*.js|css`，断网后能正常渲染并显示离线横幅。

---

## 六、手机端完整流程（10 项）

```powershell
backend\.venv\Scripts\python.exe scripts\mobile_flow_check.py
```

在 **390×844、is_mobile + has_touch** 的移动端模拟环境中，通过真实 UI 走完整流程
（选择图片 → 自动上传与 OCR → 校正表单 → 保存并分析 → 结果页 → 历史记录），结束后自动删除测试记录。

**实际输出**

```
[PASS] 打开手机端上传页
[PASS] 自动完成上传与 OCR 并进入校正页
[PASS] 校正页已填入识别出的配料表 — 小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母
[PASS] 分析完成并跳转到结果页 — http://127.0.0.1:8000/result/3
[PASS] 结果页包含配料分析
[PASS] 结果页包含营养分析
[PASS] 结果页包含标签核查
[PASS] 结果页无横向溢出 — overflow=0px
[PASS] 历史记录中出现本次记录
[PASS] 清理测试记录 — #3
通过 10 / 10 项
```

截图：`docs/images/dashboard-mobile.jpg`、`docs/images/result-mobile.jpg`、`docs/images/analyze-mobile.jpg` 为当前界面。

---

## 七、前端类型检查与构建

```powershell
cd frontend
npm run type-check     # vue-tsc --noEmit
npm run build          # vue-tsc --noEmit && vite build
```

**实际结果**：类型检查 0 error；构建成功。产物（gzip）：

```
dist/assets/element-*.js   1,089.55 kB │ gzip: 342.09 kB
dist/assets/echarts-*.js     540.11 kB │ gzip: 181.56 kB
dist/assets/vue-*.js         113.93 kB │ gzip:  44.39 kB
dist/assets/index-*.js        75.17 kB │ gzip:  29.82 kB
dist/assets/index-*.css      374.34 kB │ gzip:  51.31 kB
✓ built in 11.03s
```

---

## 八、管理员后台端到端（38 项）

**入口可见性与免二次登录**（另用 Playwright 验证 9 + 3 项）：
- 管理员从普通登录页登录后，点击「管理后台」直接进入，不再要求输入密码；
- 普通用户（桌面头部与手机抽屉）看不到「管理后台」入口；直接访问 `/admin/dashboard` 回到首页，访问 `/admin/login` 也会被送回首页；
- 管理员在后台把某用户设为管理员后，该用户刷新/切换页面（或直接访问后台 URL）即可看到入口并进入，无需重新登录；
- 取消管理员后入口随之消失。

```powershell
python scripts/admin_check.py --base-url http://127.0.0.1:8000 --username <管理员> --password <密码>
```

覆盖：未登录访问后台被重定向、管理员登录、7 个后台页面标题与 JS 错误、1366 与 390 宽度无横向溢出、知识库新增草稿→删除、规则停用→版本记录→恢复、审计日志包含上述操作。

## 九、响应式与横向溢出检查（77 组合）

```powershell
backend\.venv\Scripts\python.exe scripts\responsive_check.py --screenshots logs/responsive-screens
```

- 宽度：**360 / 390 / 430 / 768 / 1024 / 1366 / 1920**
- 路由：`/login`、`/`、`/analyze`、`/history`、`/knowledge`、`/settings`、`/about`、`/result/:id`、`/report/:id`
- 判定：`document.scrollWidth - document.clientWidth > 2px` 视为横向溢出；并额外输出右边界越界的元素
- 手机模拟：`is_mobile=True`、`has_touch=True`

**实际结果**：`77 个页面/宽度组合，0 处横向溢出`；最大溢出值 `0`。
证据报告由 `scripts/responsive_check.py` 在本地生成，不随仓库提交；当前界面截图见 `docs/images/`。

修复记录（真实修过的两个移动端问题）：

1. 报告页 `.report-shell` 在 ≤768 时 `width:100%` + `margin:10px` 导致文档多出 10px 横向滚动 → 改为 `width:auto; margin:10px auto`。
2. 报告页配料表 6 列在 390px 下被压成逐字换行（页面高度 27,630px）→ 移动端改为卡片式布局，高度降至 10,173px，且无溢出。

---

## 十、手动/浏览器验证清单

| 项目 | 方式 | 结论 |
| --- | --- | --- |
| 电脑浏览器完整流程 | Chromium（Playwright 截图） | ✅ 通过 |
| 手机尺寸布局（360/390/430） | Playwright 移动端模拟 | ✅ 无溢出、底部导航可用 |
| 平板/桌面（768/1024/1366/1920） | Playwright | ✅ 无溢出 |
| 上传 → OCR → 校正 → 分析 → 报告 | 真实 HTTP（本地 OCR） | ✅ 通过 |
| 报告打印样式 | 浏览器打印 CSS（`@media print` 隐藏导航/阴影） | ✅ 样式已配置（未做实体打印机测试） |
| 跨设备共享 | 同一账号 + 同一后端数据库（API 层验证） | ✅ 逻辑成立；未用实体手机复核 |
| 删除记录与文件清理 | pytest + 冒烟（`deleted_files` 返回） | ✅ 通过 |
| 未登录访问受保护接口 | pytest + 冒烟 | ✅ 401 |
| 跨用户越权 | pytest（记录/图片/报告） | ✅ 404 |
| 大模型失败降级 | pytest（monkeypatch 抛错 + 模拟服务返回非法 JSON/500） | ✅ 降级为规则模式并在结果中提示 |
| 大模型成功链路（协议层） | 本地模拟 OpenAI 服务 + 真实 HTTP + Playwright 截图 | ✅ 界面显示「大模型分析 / mock-model」，无规则模式横幅 |
| 视觉模型 OCR（协议层） | 本地模拟视觉服务 | ✅ `provider=vision_llm`，字段正确，非演示数据 |
| 伪造图片 / 超大文件 / 非法字段 | pytest | ✅ 400 / 413 / 400 |
| 设置页密钥泄露 | pytest（断言只返回「已配置/未配置」） | ✅ 通过 |
| 前端控制台错误 | Playwright 监听 console/pageerror，遍历 8 个路由 | ✅ 0 个错误 |
| 「重新识别」按钮（真实照片回归） | Playwright 点击 + 确认弹窗 + 表单刷新 + 后续分析 | ✅ 5/5 通过（用真实上传图片的副本验证，未改动用户记录） |
| 营养解读（规则/AI） | 结果页断言「营养解读 / 食盐 / 模式标签」 | ✅ 通过 |
| 网络中断后的续做提示 | Playwright 拦截 `/api/analyze` 制造失败 | ✅ 提示「网络已中断…恢复后可继续」 |
| 窄屏弹窗与抽屉（360/390） | Playwright 测量 dialog/drawer 宽度与文档溢出 | ✅ 4/4 通过，无溢出 |
| 模糊图片识别 | 生成高斯模糊 2.2 的标签图，走完整上传→OCR→分析 | ✅ 17 行文字、10 项配料、5 项营养全部识别 |
| 原图 vs 展示图 OCR | 同图分别用原图与压缩展示图识别并对比 | ✅ 原图 40 行 / 展示图 39 行，原图略优，已改为默认用原图 |
| 图片放大 | Playwright 打开查看器 + 滚轮缩放（390 / 1366） | ✅ 6/6 通过，可放大到 2.7 倍以上 |
| 低分辨率图片提示 | 上传 210×462 小图，检查确认弹窗与页面提示 | ✅ 弹窗「图片分辨率偏低」+ 页面提示 210×462 |
| 只拍到包装正面的提示 | 上传仅含品牌名的高清图 | ✅ 提示「没有找到配料表/营养成分表」并给出「重新拍一张」 |
| 手机端相册/拍照入口 | Playwright 移动端 390/360 点击两个按钮 | ✅ 均能触发文件选择（`filechooser` 事件） |
| 底部导航遮挡检查 | 390px 下遍历 9 个路由滚到底部，测量元素与导航栏是否重叠 | ✅ 0 个元素被遮挡 |
| 科普助手输入框 | 390/360 下检查「提问」按钮位置与吸底效果 | ✅ 按钮位于导航栏上方 19px，顶部/中部/底部滚动时均可见 |
| HEIC 兼容 | 前端自动转 JPEG；服务端对无法解码的 HEIC 返回可操作提示 | ✅ 单元测试通过 |
| 两列排版（配料表+营养表并排） | 用真实「烧牛肉面」OCR 文本回归 | ✅ 营养表只留 5 行营养素，配料文字被剔除 |
| 营养成分表预览表 | Playwright 打开校正页检查 | ✅ 5 行、单位 kJ/mg、无配料文字、390/1366 无溢出 |

---

## 十一、尚未验证的项目（如实说明）

| 项目 | 原因 | 如何自行验证 |
| --- | --- | --- |
| **真实公网 HTTPS 部署** | 当前环境无法注册云账号、绑定域名 | 按 [DEPLOYMENT.md](DEPLOYMENT.md) 阶段 C 部署后运行 `prod_smoke_test.py --base-url https://你的域名` |
| **实体安卓/iPhone 访问** | 无实体设备 | 手机与电脑同一 Wi-Fi，访问 `http://电脑IP:5173`；用 `responsive_check.py --base-url` 也可复测 |
| **真实厂商大模型 API** | 未配置 `AI_API_KEY`；已用本地模拟服务验证协议与降级链路 | 配置 Key 后重新分析一条记录，结果页应显示「大模型分析」与真实模型名 |
| **真实厂商视觉模型 OCR** | 未配置 `OCR_VISION_API_KEY`；已用本地模拟服务验证链路 | 设 `OCR_PROVIDER=vision` 并填 Key 后上传中文标签，检查 `provider=vision_llm` |
| **PWA 安装到主屏幕** | 需要真实浏览器/手机手动操作 | 生产构建后打开站点，Chrome/Edge 地址栏安装入口；iOS Safari「添加到主屏幕」 |
| **打印/另存 PDF 的实际输出** | 需要人工在打印对话框中操作 | 打开 `/report/:id` → 打印 → 另存为 PDF，检查分页与页眉页脚 |
| **微信内置浏览器** | 无法在此环境测试 | 用微信扫码打开，检查上传按钮与图片选择是否可用 |
| **并发/压测** | 超出比赛演示范围 | 可用 `wrk`/`locust` 对 `/api/health`、`/api/records` 压测 |

---

## 十一、如何重现全部测试

```powershell
# 0) 准备
cd D:\食品项目\food-safety-ai

# 1) 后端测试（102 项，含真实 OCR、模拟大模型/视觉模型、数据库初始化）
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..

# 2) 启动服务（开发模式）
.\start.bat
# 或手动： backend\.venv\Scripts\python.exe backend\wsgi.py
#         cd frontend; npm run dev

# 3) 接口冒烟（33 项）
backend\.venv\Scripts\python.exe scripts\api_smoke_test.py

# 4) 响应式检查（77 组合 + 截图）
backend\.venv\Scripts\python.exe scripts\responsive_check.py --screenshots logs/responsive-screens

# 5) 生产模式
.\start_prod.bat
backend\.venv\Scripts\python.exe scripts\prod_smoke_test.py --base-url http://127.0.0.1:8000

# 6) 前端类型检查与构建
cd frontend
npm run type-check
npm run build
```
