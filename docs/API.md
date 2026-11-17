# API 文档

- Base URL（开发）：`http://127.0.0.1:5000/api`
- Base URL（生产同源）：`https://你的域名/api`
- 数据格式：`application/json; charset=utf-8`（`/api/upload` 等文件上传接口为 `multipart/form-data`；`/api/analyze` 前端主流程使用 Base64 JSON）
- 鉴权：`Authorization: Bearer <token>`（登录接口返回）
- 交互式验证：`python scripts/api_smoke_test.py --base-url http://127.0.0.1:5000`

---

## 一、统一响应格式

成功：

```json
{
  "success": true,
  "code": 0,
  "message": "ok",
  "data": { },
  "details": null,
  "request_id": "22e428d4cc05"
}
```

失败：

```json
{
  "success": false,
  "code": 40100,
  "message": "请先登录后再使用该功能",
  "data": null,
  "details": { "id": 12 },
  "request_id": "9159d421ef70"
}
```

**HTTP 状态码与业务码**

| HTTP | code | 含义 |
| --- | --- | --- |
| 200 | 0 | 成功 |
| 201 | 0 | 创建成功（注册、上传） |
| 400 | 40000 | 参数校验失败 |
| 401 | 40100 | 未登录 / 令牌无效或过期 |
| 403 | 40300 | 无权限 |
| 404 | 40400 | 资源不存在或无权限访问（统一返回，避免探测） |
| 409 | 40900 | 状态冲突（如用户已存在、记录未分析却请求报告） |
| 413 | 41300 | 上传文件超过 `MAX_CONTENT_LENGTH` |
| 415 | 41500 | 媒体类型不支持 |
| 429 | 42900 | 请求过于频繁（登录限流） |
| 500 | 50000 | 服务器内部错误 |
| 502 | 50200 | 外部服务（OCR/LLM）失败 |
| 503 | 50300 | 服务不可用（如 OCR 引擎未安装） |
| 504 | 50400 | 上游超时 |

响应头包含 `X-Request-ID`（便于对照日志）与 `X-Response-Time`。

---

## 二、健康检查

### `GET /api/health`

无需鉴权。返回数据库、存储、OCR、AI 的状态。

```json
{
  "success": true,
  "data": {
    "status": "ok",
    "app": "智膳 AI",
    "version": "1.0.0",
    "env": "production",
    "uptime_seconds": 128,
    "server_time": "2026-10-17T13:20:11.000Z",
    "checks": {
      "database": { "status": "ok", "engine": "sqlite" },
      "storage": { "status": "ok", "file_count": 12 },
      "ocr": { "status": "ok", "provider": "local" },
      "ai": { "status": "unconfigured", "mode": "rule" }
    }
  }
}
```

数据库不可用时返回 `503` 且 `data.status = "degraded"`。

---

## 三、账号

### `POST /api/auth/register`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| username | string | 是 | 3-20 位中文/字母/数字/下划线 |
| password | string | 是 | ≥8 位，需同时包含字母与数字 |
| display_name | string | 否 | 昵称，默认同用户名 |
| email | string | 否 | 格式校验 |

```json
{ "username": "alice", "password": "Alice12345", "display_name": "小艾" }
```

响应 `201`：`{ "token": "...", "expires_at": "...", "user": { "id": 2, "username": "alice", ... } }`
错误：用户名已存在 → `409`；弱密码 → `400`。

### `POST /api/auth/login`

```json
{ "username": "demo", "password": "demo123456", "captcha_id": "...", "captcha_code": 8 }
```

成功返回 token 与 `is_demo_account`。密码错误 `401`；连续失败 6 次后 `429`（5 分钟窗口）。
登录默认要求验证码（`LOGIN_CAPTCHA=1`）；验证码错误或过期返回 `400`，需重新获取。

### `GET /api/captcha`

获取登录验证码（公开接口，无需登录）：

```json
{ "captcha_id": "…", "image": "data:image/svg+xml;base64,…", "question": "3 + 5 = ?", "expires_in": 300 }
```

- `question` 仅用于无障碍提示与自动化测试，答案不返回；
- 验证码一次性使用，默认 5 分钟过期；响应设置 `Cache-Control: no-store`；
- 生产环境可用 `LOGIN_CAPTCHA=0` 临时关闭（不建议）。

### `POST /api/auth/change-password`（需登录）

```json
{ "old_password": "旧密码", "new_password": "新密码（≥8 位，含字母和数字）" }
```

校验原密码后重设，注销该账号全部旧会话并返回新令牌；原密码错误、弱密码或新旧相同返回 400。

### `POST /api/auth/logout`（需登录）

使当前令牌失效，返回 `{ "logged_out": true }`。

### `GET /api/auth/me`（需登录）

返回当前用户、记录数量与演示账号提示。

---

## 四、仪表盘

### `GET /api/dashboard`（需登录）

```json
{
  "totals": {
    "records": 3, "analyzed": 3, "demo_records": 2, "real_records": 1,
    "demo_analyzed": 2, "real_analyzed": 1,
    "ingredients_explained": 20, "ingredients_real": 6,
    "knowledge_citations": 18, "suspected": 0, "needs_review": 3, "none_found": 0
  },
  "status_distribution": [{ "key": "analyzed", "name": "分析完成", "value": 3 }],
  "check_distribution": [{ "key": "needs_review", "name": "需要进一步核实", "value": 3 }],
  "level_counts": { "pass": 62, "info": 3, "review": 6, "suspected": 0, "skip": 5 },
  "trend": [{ "date": "2026-10-04", "label": "10-04", "count": 0 }, "…14 天"],
  "top_ingredients": [{ "name": "水", "value": 1 }],
  "recent_records": [ "同 /api/records 的 item 结构" ],
  "featured_knowledge": [ "知识条目摘要" ],
  "knowledge_stats": { "total": 60, "verified": 15, "pending": 45, "categories": 5 },
  "service_status": { "ocr_provider": "local", "ocr_label": "本地 OCR 引擎（RapidOCR，离线）", "ai_mode": "rule", "ai_configured": false, "ai_model": null },
  "onboarding": { "is_first_visit": false, "steps": [{ "title": "...", "description": "..." }] }
}
```

> `demo_records` 与 `real_records` 分开统计，前端会明确标注，不把演示数据当作真实统计数据。

---

## 五、上传

### `POST /api/upload`（需登录）

`multipart/form-data`，字段名 **`file`**。

| 限制 | 值 |
| --- | --- |
| 格式 | JPG / JPEG / PNG / WEBP（以 Pillow 真实解码为准） |
| 大小 | ≤ `MAX_CONTENT_LENGTH_MB`（默认 10MB） |
| 最小尺寸 | 40×40 px |

```json
{
  "record": { "id": 12, "status": "uploaded", "image_url": "/api/records/12/image", ... },
  "image": {
    "id": 10, "original_name": "label.jpg", "ext": "jpg", "mime": "image/jpeg",
    "size_bytes": 842133, "width": 3024, "height": 4032, "url": "/api/records/12/image"
  },
  "limits": { "max_mb": 10, "allowed": "JPG / JPEG / PNG / WEBP" }
}
```

错误：未选文件 `400`；伪造图片（扩展名是图片但内容不是）`400`；超过大小 `413`。

---

## 六、OCR 识别与校正

### `POST /api/ocr`（需登录）

```json
{ "record_id": 12 }
```

响应：

```json
{
  "record": { "id": 12, "status": "ocr_done", ... },
  "ocr": {
    "provider": "local_rapidocr",
    "provider_label": "本地 OCR 引擎（RapidOCR，离线）",
    "engine_version": "rapidocr-onnxruntime 1.4.4",
    "is_demo": false,
    "status": "success",
    "raw_text": "乐脆牌 原味苏打饼干\n净含量：200g\n…",
    "corrected_text": "食品名称：…\n配料表：…",
    "fields": {
      "food_name": "乐脆牌 原味苏打饼干", "ingredients_text": "小麦粉、植物油、…",
      "nutrition_text": "能量 1980kJ 24% …", "net_content": "200g",
      "production_date": "2026-09-12", "shelf_life": "12个月", "expiry_date": "",
      "storage": "置于阴凉干燥处", "producer": "乐脆食品有限公司",
      "standard_no": "GB/T20980", "allergen": "含有小麦、乳制品"
    },
    "field_confidence": { "food_name": 0.42, "ingredients_text": 0.97, … },
    "field_flags": { "food_name": { "status": "inferred", "note": "未识别到名称标注…" }, … },
    "low_confidence_fields": ["food_name"],
    "missing_fields": ["expiry_date"],
    "field_labels": { "food_name": "食品名称", … },
    "duration_ms": 5210
  },
  "fields": { "…同 ocr.fields…" },
  "provider": { "key": "local_rapidocr", "label": "…", "is_demo": false, "duration_ms": 5210 },
  "demo_warning": null
}
```

错误：记录不存在/不属于你 `404`；OCR 引擎异常 `502`（`details.retryable=true`，可直接重试）；
引擎未安装 `503`（提示安装依赖或改用演示/视觉模型）。

### `PUT /api/records/{id}/ocr`（需登录）

保存人工校正结果，**不覆盖原始 OCR 文本**。

```json
{ "fields": { "food_name": "原味苏打饼干", "ingredients_text": "小麦粉、植物油、白砂糖" }, "note": "手动补全配料表" }
```

- 只允许 11 个已知字段，出现未知字段返回 `400`
- 改动字段的置信度置为 `1.0`，并重建 `corrected_text`
- 响应返回更新后的 `ocr` 对象

---

## 七、分析

### `POST /api/analyze`（需登录）

支持三种请求体：

#### 1. JSON Base64：拍照/拖拽上传 + 模式（前端主流程）

```http
POST /api/analyze
Content-Type: application/json

{
  "image_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "mode": "packaging"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `image_base64` | 是 | 图片的 Base64 data URL，保留 `data:image/jpeg;base64,` 前缀；后端负责剥离 |
| `mode` | 是 | `packaging`（识包装）或 `dish`（识饭菜） |

- `packaging`：服务端剥离前缀、Base64 解码并用 Pillow 校验图片，保存图片、创建记录并执行 OCR，返回 `record`、`ocr`、`fields`、`provider`，前端进入“核对校正”步骤；后续仍用下面的 JSON 方式提交校正后的正式分析。
- `dish`：保存图片、创建记录并直接完成识饭菜分析，返回 `result.dish`、`detail` 和
  `stream_url`（如 `/analyze/dish/20/stream`），前端用 `fetch` + `ReadableStream` 读取 SSE。
- `image_base64` 为空、不是合法 Base64、不是图片，或 `mode` 缺失/非法返回 `400`。
- 图片大小受 `MAX_CONTENT_LENGTH_MB` 限制。
- Base64 图片上传**不需要 `record_id`**：服务端先检查 `image_base64`，命中后直接创建新记录。
  如果仍返回“缺少参数 record_id”，说明请求体没有带 `image_base64`，或运行的仍是旧后端代码。

#### 2. multipart：旧客户端兼容

```http
POST /api/analyze
Content-Type: multipart/form-data

file=<图片文件>
mode=packaging   # 或 dish
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | JPG / PNG / WEBP 图片 |
| `mode` | 是 | `packaging`（识包装）或 `dish`（识饭菜） |

前端已改为 Base64 JSON 上传；multipart 仅保留给旧客户端/测试兼容。

#### 3. JSON：校正文字后的正式分析（原有流程）

```json
{ "record_id": 12, "type": "package" }
```

`type` 可选，默认 `package`：

| 值 | 场景 | 处理方式 |
| --- | --- | --- |
| `package` | 识包装 | OCR 配料表/营养成分表 → AI 配料解读 → 国标与健康画像核查 |
| `dish` | 识饭菜 | 跳过包装 OCR；视觉模型只识别菜名与可食用重量，再检索菜品营养库并按克数精准换算 |

响应（节选）：

```json
{
  "result": {
    "record_id": 12, "status": "analyzed", "analysis_mode": "rule",
    "overall": "needs_review", "counts": { "pass": 20, "review": 3, "info": 2, "skip": 1, "suspected": 0 },
    "ingredient_count": 8, "errors": [],
    "dish": {
      "slug": "dish-001", "dish_name": "西红柿炒鸡蛋",
      "estimated_weight_g": 200,
      "totals": { "weight_g": 200, "calories": 172, "protein_g": 9, "fat_g": 10.4, "carbs_g": 11.6 }
    }
  },
  "record": { "…记录摘要…" },
  "detail": { "record": {}, "ocr": {}, "ingredient": {}, "nutrition": {}, "check": {}, "meta": {} }
}
```

- 配料表与营养成分表都为空 → `400`
- 未完成 OCR → `404`，提示先识别（`type = "dish"` 不要求先 OCR）
- 大模型失败会自动降级规则模式：`result.analysis_mode = "rule"`，`result.errors` 含原因，
  `detail.ingredient.unconfirmed` 中也会提示
- `type = "dish"` 时若未配置视觉模型（`OCR_VISION_API_KEY` / `OCR_VISION_BASE_URL`），返回 `503`
- 识饭菜的 System Prompt 为：`你是营养师，请识别图片中的菜品，估算其重量、热量及三大营养素，并给出饮食建议。返回JSON格式。`
- 视觉模型返回的菜名/别名会在 `backend/app/data/dish_database.json` 中检索；识别到西红柿炒鸡蛋 200g 时，按 86 大卡/100g 计算为 172 大卡
- 菜品库未收录时返回 `422`，不会用包装标签规则硬套

### `GET /api/analyze/dish/{record_id}/stream`（需登录，SSE）

把已完成的识饭菜结果按字符流返回，前端用 `fetch` 读取 `text/event-stream`：

```text
data: {"text":"识"}

data: {"text":"别"}

event: done
data: {"done": true}
```

### `GET /api/dishes`（无需登录）

常见菜品营养库，供知识库“常见菜品”Tab 查询。

| 查询参数 | 说明 |
| --- | --- |
| query | 菜名/别名关键词 |
| category | 菜品分类，默认 `all` |
| page / per_page | 分页，默认 12 条 |

### `GET /api/dishes/{slug}`

返回单个菜品详情与同类推荐。字段包括：

`dish_name`、`aliases`、`category`、`calories_per_100g`、`protein_per_100g`、`fat_per_100g`、`carbs_per_100g`、`typical_portion_g`、`health_tip`。

### `POST /api/records/{id}/reanalyze`（需登录）

用当前校正数据重新跑一遍分析（响应同上）。

---

## 八、记录

### `GET /api/records`（需登录）

| 查询参数 | 说明 |
| --- | --- |
| page | 页码，默认 1 |
| per_page | 每页条数，默认 8（最大 50） |
| query | 按食品名称模糊搜索 |
| status | `all` / `uploaded` / `ocr_done` / `corrected` / `analyzed` / `failed` |

```json
{
  "items": [{
    "id": 12, "food_name": "乐脆牌 原味苏打饼干（演示）", "status": "analyzed", "status_label": "分析完成",
    "data_source": "demo", "analysis_mode": "rule", "is_demo": true,
    "ocr_provider": "demo", "overall_check": "needs_review", "summary": "需要进一步核实｜待核实 2 项、提示 1 项、通过 22 项",
    "created_at": "2026-10-17T13:10:00Z", "updated_at": "…", "analyzed_at": "…",
    "image_url": "/api/records/12/image", "ingredient_count": 8, "issue_count": 2, "has_report": true
  }],
  "total": 3, "page": 1, "per_page": 8, "pages": 1,
  "stats": { "total": 3, "analyzed": 3, "suspected": 0, "demo": 2 },
  "filters": { "query": "", "status": "all" }
}
```

### `GET /api/records/{id}`（需登录）

响应中新增 `health`：`score`（0–100，数据不足时为 `null`）、`grade`、`dimensions`、`findings`（反式脂肪 / 糖与减脂 / 钠 / 脂肪 / 添加剂）、`additives`（合规状态固定为「待核实」）、`score_note` 与 `disclaimer`。健康分是自建参考模型，**不是国家标准、医学诊断或合规判定**；反式脂肪只与 WHO 供能建议比较，不使用「超标」结论。

返回 `record / ocr / ingredient / nutrition / check / health / report / meta` 等部分

- `meta.disclaimer`：平台边界声明
- `meta.demo_notice`：本次使用演示数据时的说明
- `meta.mode_notice`：规则模式说明

### `GET /api/records/{id}/image`（需登录）

返回图片二进制（默认展示图；`?original=1` 取原图）。`Content-Type` 为 `image/jpeg` 或 `image/png`。
前端使用带 Authorization 头的请求获取后转为 blob 显示。

### `DELETE /api/records/{id}`（需登录）

删除记录、关联数据与磁盘图片。

```json
{ "deleted_id": 12, "deleted_files": ["a1b2.png", "display_a1b2.jpg"] }
```

---

## 九、报告

### `GET /api/reports/{id}`（需登录）

响应包含与记录详情同一份 `health` 对象，报告页会展示健康分与逐项说明。

```json
{
  "report": { "report_no": "FS-20261017-0012-7A3C", "version": "1.0", "generated_at": "2026-10-17T13:20:00Z", "generated_count": 1 },
  "record": { }, "ocr": { }, "ingredient": { }, "nutrition": { }, "check": { }, "health": { },
  "check_overall_label": "需要进一步核实",
  "coverage": "direct",
  "sources": [{ "id": 6, "title": "三氯蔗糖", "source_name": "GB 2760…（名称引用）", "source_url": "…", "verification_status": "pending", "version": "1.0" }],
  "rule_sources": [{ "name": "GB 7718…（名称引用）", "type": "standard_name", "note": "…", "rule_ids": ["FIELD_INGREDIENTS"] }],
  "ruleset": { "version": "2025.11", "updated_at": "2025-11-01", "disclaimer": "…" },
  "meta": { "app_name": "智膳 AI", "app_version": "1.0.0", "disclaimer": "…", "is_demo": false, "public_site_url": null }
}
```

记录未分析 → `409`（提示「尚未完成分析」）。

---

## 十、知识库（无需登录）

### `GET /api/knowledge`

| 参数 | 说明 |
| --- | --- |
| query | 关键词（标题/别名/关键词/摘要/正文） |
| category | `all` / `additive` / `ingredient` / `nutrition` / `label_rule` / `safety` |
| page / per_page | 分页，默认 12 |
| featured | `1` 只取首页推荐 |

```json
{
  "items": [{ "id": 6, "slug": "sucralose", "title": "三氯蔗糖", "category": "additive",
    "category_label": "食品添加剂", "summary": "…", "source_name": "GB 2760…",
    "source_url": "…", "source_type": "standard_name", "source_type_label": "标准/法规名称（未收录原文）",
    "verification_status": "pending", "verification_label": "待核验（仅作参考，请以官方原文为准）",
    "version": "1.0", "updated_at": "…", "is_featured": false }],
  "total": 60, "page": 1, "per_page": 12, "pages": 5,
  "categories": [{ "value": "all", "label": "全部", "count": 52 }, { "value": "additive", "label": "食品添加剂", "count": 22 }],
  "verification_labels": { "verified": "已核对来源名称与要点", "pending": "待核验…" }
}
```

### `GET /api/knowledge/{id}`

返回 `entry`（含 `content` 与 `usage_note`）与 `related`（同分类 4 条）。不存在 → `404`。

---

## 十一、食安科普助手（RAG）

当用户说“用我的食材推荐几道清淡的菜/根据库存推荐”时，助手会调用食材管家，返回 `coverage=pantry_recipe`、`pantry_plan_id`、`pantry_dishes`、`pantry_shopping` 与决策轨迹；每道菜带「去做」「已完成」按钮，完成后调用 `/api/recipes/complete` 扣减库存。

食谱中的 `amount` 必须优先使用中国家庭单位并在括号附克数，例如 `大米 一杯半（电饭煲量杯，约200g）`、`食用油 1小勺（约5ml）`、`食盐 1小勺（约3g）`；严禁茶匙、汤匙、盎司等西式单位，服务端会对规则/AI 生成的用量做二次补全。

食谱规划与助手推荐都支持 `servings`（1–6 人份）：规则食谱按人数缩放食材克数与营养估算，AI 提示词要求按人数出量；助手会从“3人份”这类话里自动解析人数，默认 2 人份。

涉及库存、冰箱、临期/过期、能不能吃/喝的问题，会先读取当前用户库存并拼进 Prompt，返回 `coverage=inventory`、`action=jump_to_inventory`、`action_label=管理我的冰箱库存`、`inventory_items` 与 `used_items`；前端据此在回答下方渲染跳转按钮到 `/inventory`。

营养、添加剂、食物相克问题会先过意图门禁，跳过食谱/库存分支，强制走 RAG 检索并附来源；输入具体菜名（如“麻婆豆腐”）或明确“怎么做”时直接进入 `coverage=recipe`，返回 `recipe_versions={novice:{steps,tips},chef:{steps,tips}}`，前端渲染摘要卡+版本 Tabs，不再展示大段科普正文。

推荐类问题（如“我买了一条鲤鱼，有什么推荐的做法吗”）先返回 `coverage=recipe_options` 和 2–3 个 `recipe_options`；用户选定后返回 `coverage=recipe`、`recipe_summary`（菜名/耗时/主要食材/安全提醒）与完整 `sections`，前端用摘要卡+详情抽屉展示。

做菜类问题（如“番茄炒蛋怎么做？”）会进入菜谱模式：`coverage=recipe`、`mode=recipe`（内置菜谱）或 `recipe_ai`（AI 生成），`sections` 返回份量、食材、分步做法、新手易错点和食品安全提醒；菜谱不作为本站知识库核验结论。

同一会话（传 `session_id`）内支持多轮追问：服务端读取最近消息，对“为什么/那这个呢/还能吃吗”等追问用上一轮主题补全检索，并把对话历史交给大模型仅用于理解指代（不得作为事实依据）。响应中的 `context_used` 表示本轮是否使用了上文，`retrieval_query` 为实际检索词。例如先问“有什么蘑菇”，再问“能和酒一起吃吗”，检索词会自动补全为“蘑菇和酒能一起吃吗”，而不是匹配到药物条目。

### `GET /api/assistant/overview`（无需登录）

返回收录规模、分类、热门问题与免责声明：

```json
{
  "success": true, "code": 0,
  "data": {
    "stats": {
      "entries": 59, "verified": 44, "pending": 15,
      "categories": [{ "key": "myth", "label": "食物相克与常见谣言" }],
      "mode": "ai", "mode_label": "RAG 知识提炼（基于权威知识库，已溯源防幻觉）"
    },
    "featured": [{ "slug": "leftover-food", "title": "隔夜菜到底能不能吃？", "question": "隔夜菜", "category_label": "储存、保鲜与剩菜" }],
    "disclaimer": "回答仅基于本站收录的公开资料整理…"
  }
}
```

### `POST /api/assistant/ask`（需登录）

请求：`{ "question": "隔夜菜到底能不能吃？", "session_id": 12 }`（`session_id` 可省略，表示新建会话）。

```json
{
  "session_id": 12, "message_id": 34, "matched": true,
  "mode": "ai", "mode_label": "RAG 知识提炼（基于权威知识库，已溯源防幻觉）",
  "mode_note": null,
  "answer": "隔夜菜能不能吃，关键看储存和加热条件…[K1]",
  "sections": [],
  "evidence": "《中国居民膳食指南（2022）》建议食物及时冷藏…",
  "sources": [
    { "id": "K1", "name": "《中国居民膳食指南（2022）》", "publisher": "中国营养学会",
      "year": "2022", "url": "https://www.cnsoc.org/", "kind": "guideline",
      "kind_label": "膳食指南 / 营养共识", "verified": true }
  ],
  "entry": { "slug": "leftover-food", "title": "隔夜菜到底能不能吃？", "verification_label": "已核对来源与要点" },
  "related": [{ "slug": "overnight-water", "title": "隔夜水、隔夜茶能喝吗？", "category_label": "储存、保鲜与剩菜" }],
  "disclaimer": "回答仅基于本站收录的公开资料整理…",
  "ai_check": { "kept_sentences": 3, "dropped_sentences": 1, "citations": 1 }
}
```

- `retrieval` 模式返回 `sections`（结论 / 为什么 / 依据 / 注意事项），`answer` 与之一致；
- `ai` 模式返回 `answer`（含 `[K#]` 引用）与 `ai_check`（保留/剔除句子数），`sections` 为空；
- `coverage` 取值：`direct` 直接命中 / `related` AI 从相近条目中选一条 / `general` AI 补充回答 / `none` 未收录；
- 检索不到时 `matched=false`、`sources=[]`、`answer` 明确说明「未收录」，并给出 `related` 候选；
- 若配置了 `ASSISTANT_GENERAL_ANSWER=1`，未收录的问题会由通用大模型补充回答，前端标注「AI 补充」；
  `mode_note` 只保留安全提示「涉及用药、中毒、过敏请务必咨询医生或药师」，页脚注明内容由 AI 结合通用知识生成；
- 频率限制：每用户每分钟 20 次，超出返回 `429`。

### `GET /api/assistant/sessions`（需登录）

返回当前账号的会话列表（按更新时间倒序），含 `message_count`。

### `GET /api/assistant/sessions/{id}`（需登录）

返回会话详情与全部消息（`role` / `content` / `mode` / `sources` / `payload`）。他人会话返回 `404`。

### `DELETE /api/assistant/sessions/{id}`（需登录）

删除会话及其消息。他人会话返回 `404`。

### `GET /api/assistant/entries/{slug}`（无需登录）

返回单条目的完整内容（结论/原因/依据/注意/来源），用于「查看依据条目」。

---

## 十一、运行状态

### `GET /api/settings/status`（无需登录）

用于前端「设置与帮助」页展示**状态**（不返回任何密钥内容）：

```json
{
  "app": { "name": "智膳 AI", "version": "1.0.0", "env": "production", "public_site_url": null },
  "ocr": {
    "configured_provider": "auto", "active_provider": "local",
    "active_label": "本地 OCR 引擎（RapidOCR，离线）",
    "providers": [{ "key": "local", "name": "本地 OCR 引擎（RapidOCR，离线）", "available": true, "is_demo": false }],
    "vision_base_url": "…", "vision_model": "qwen-vl-max", "vision_key": "未配置"
  },
  "ai": { "mode": "rule", "configured": false, "model": "deepseek-chat", "api_key": "未配置", "prompt_version": "ingredient-v2" },
  "storage": { "database": "SQLite 文件：food_safety.db", "file_count": 12, "total_bytes": 3948121, "max_upload_mb": 10, "allowed_formats": ["JPG","JPEG","PNG","WEBP"] },
  "security": { "password_hashing": "scrypt（werkzeug.security，含随机 salt）", "session_days": 30, "cors_origins": ["…"], "api_key_in_logs": false },
  "demo_account": { "exists": true, "username": "demo" },
  "ruleset": { "version": "2025.11", "updated_at": "2025-11-01", "rule_count": 24 },
  "limits": { "page_size": 8, "max_page_size": 50 },
  "runtime": { "python": "3.12.14", "flask": "3.1.3" }
}
```

### `GET /api/rules`（无需登录）

返回规则集：版本、更新时间、免责声明、阈值、按分类组织的 24 条规则（含依据、来源、待确认事项）。

---

## 十二、枚举值

| 字段 | 取值 |
| --- | --- |
| `record.status` | `uploaded` / `ocr_done` / `corrected` / `analyzed` / `failed` |
| `record.analysis_mode` | `ai` / `rule` |
| `record.data_source` | `real` / `demo` |
| `record.overall_check` | `none_found` / `needs_review` / `suspected`（未分析为 `null`） |
| `ocr.status` | `success` / `partial` / `failed` |
| `ocr.provider` | `local_rapidocr` / `vision_llm` / `demo` |
| `nutrition.basis` | `per_100g` / `per_100ml` / `per_serving` |
| `nutrition.items[].status` | `ok` / `missing` / `unit_inferred` / `duplicate` |
| `check.items[].level` | `pass` / `info` / `review` / `suspected` / `skip` |
| `ingredient.ingredients[].confidence` | `high` / `medium` / `low` |
| `ingredient.ingredients[].evidence` | `knowledge_base` / `general_knowledge` / `unverified` |
| `knowledge.category` | `additive` / `ingredient` / `nutrition` / `label_rule` / `safety` |
| `knowledge.verification_status` | `verified` / `pending` |

---

## 十三、接口测试

```powershell
# 完整业务流程（上传→OCR→校正→分析→报告→删除）
backend\.venv\Scripts\python.exe scripts\api_smoke_test.py

# 生产模式（静态托管 + PWA）
backend\.venv\Scripts\python.exe scripts\prod_smoke_test.py --base-url http://127.0.0.1:8000

# pytest 单元/接口测试（含权限与失败路径）
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

---

## 十二、管理员后台 API（/api/admin）

所有管理接口（除登录）都要求 `Authorization: Bearer <token>` 且账号 `role=admin`。
未登录返回 401，普通用户返回 403；登录失败按「用户名 + IP」限流（5 次 / 5 分钟 → 429）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/admin/auth/login` | 管理员登录（写审计日志，失败也记录） |
| POST | `/api/admin/auth/logout` | 退出并注销当前令牌 |
| GET | `/api/admin/auth/me` | 当前管理员信息 |
| GET | `/api/admin/meta` | 分类/状态/来源类型等枚举 |
| GET | `/api/admin/dashboard` | 用户数、任务数、成功率、失败数、知识库数、14 天趋势、最近审计 |
| GET | `/api/admin/users` | 用户列表（`q` / `status` / `role` / `page`） |
| PATCH | `/api/admin/users/<id>` | 停用/恢复（`is_active`）或调整角色（`role=user/admin`），不能停用自己或最后一个管理员 |
| DELETE | `/api/admin/users/<id>` | 删除用户及关联记录/会话/图片，不能删除自己或最后一个管理员 |
| POST | `/api/admin/users/<id>/reset-password` | 生成一次性临时密码并注销该用户全部会话 |
| GET | `/api/admin/records` | 分析记录列表（`q` / `status` / 分页） |
| GET | `/api/admin/records/<id>` | OCR / AI / 核查 / 复核备注 / 用户反馈 |
| POST | `/api/admin/records/<id>/notes` | 追加复核备注 |
| DELETE | `/api/admin/records/<id>` | 删除记录，请求体必须含 `{"confirm": true}` |
| GET | `/api/admin/feedback` | 用户反馈列表（`status=open/resolved`） |
| PATCH | `/api/admin/feedback/<id>` | 标记已处理并填写处理说明 |
| POST | `/api/feedback` | 普通用户提交反馈（登录后，非管理接口） |
| GET/POST | `/api/admin/knowledge` | 知识条目列表（含草稿）/ 新增 |
| PUT | `/api/admin/knowledge/<id>` | 更新条目 |
| POST | `/api/admin/knowledge/<id>/verify` | 审核通过 AI 生成词条，转为已核验并发布 |
| POST | `/api/admin/knowledge/<id>/publish` | 发布 / 下架 / 转草稿 |
| DELETE | `/api/admin/knowledge/<id>` | 删除条目 |
| GET/POST | `/api/admin/rules` | 核查规则列表 / 新增 |
| PUT | `/api/admin/rules/<rule_id>` | 修改规则（写入 before/after 版本快照） |
| POST | `/api/admin/rules/<rule_id>/toggle` | 启用 / 停用（同样留痕） |
| GET | `/api/admin/rules/<rule_id>/revisions` | 规则版本历史 |
| GET | `/api/admin/monitor` | OCR/AI/助手状态、请求与失败数、OCR 耗时、最近错误（不含任何 Key） |
| GET | `/api/admin/audit-logs` | 审计日志（`action` / `actor` / `result` / 分页） |
| GET | `/api/captcha` | 获取登录验证码（公开接口） |

**发布约束**：`source_type=editorial` 且 `verification_status=pending` 的条目不能直接发布，只能保存为草稿或先核验来源。

---

## 家庭共享

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/family` | 当前家庭、邀请码与成员列表 |
| POST | `/api/family/join` | 通过邀请码加入家庭，共享库存 |
| POST | `/api/family/leave` | 退出当前家庭 |
| DELETE | `/api/family/members/<id>` | 户主移除家庭成员 |
| GET | `/api/family/alert` | 家人辛辣食品与胃炎画像提醒 |


## 收藏定向缺料

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/favorites/<id>/missing` | 按单条收藏计算家庭库存缺料，供定向购物清单使用 |

## 十三、家庭食材管家与食谱 Agent

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/pantry` | 库存列表（`status=expired/expiring/fresh/no_expiry`、`query`） |
| POST | `/api/pantry` | 添加食材 |
| PUT | `/api/pantry/<id>` | 修改食材（仅本人） |
| DELETE | `/api/pantry/<id>` | 删除食材（仅本人） |
| POST | `/api/pantry/batch-delete` | 批量删除：`{ids:[1,2,3]}`；只删当前用户的行，返回 deleted/missing |
| POST | `/api/pantry/batch` | 批量导入（先全部校验，再一次性提交） |
| POST | `/api/pantry/import/text` | 语音/自然语言解析，返回预览，不直接入库 |
| POST | `/api/pantry/import/receipt` | 小票/商品图片 OCR 后解析，返回预览；图片识别后即删除 |
| GET | `/api/pantry/reminders` | 过期/临期（3 天内）食材、`urgent`（≤1 天）与提醒文案 |
| GET | `/api/pantry/stream` | **SSE** 实时提醒流（`text/event-stream`，`?once=1` 仅推一次，便于测试） |
| GET | `/api/pantry/lookup/shelf-life` | 按名称查常规保质期（内置表 + 可选 Tavily），返回 `confidence_percent` / `confidence_label` / `alternatives`；置信度是规则启发式，不是统计准确率 |
| POST | `/api/pantry/decode-barcode` | 上传条码照片，由服务端 zxing-cpp 解码出条码数字（浏览器不支持 BarcodeDetector 时兜底） |
| GET | `/api/pantry/lookup/barcode` | 商业条码商品查询：ShowAPI（`SHOWAPI_APP_KEY`）或自定义 `BARCODE_API_URL`；未配置时明确返回「未配置」 |
| GET/PUT | `/api/health-profile` | 健康画像（高血压/糖尿病/痛风/孕期/过敏原等） |
| POST | `/api/health-profile/tip` | 根据勾选的症状/目标生成一句 AI 饮食提示（失败自动规则兜底） |
| POST | `/api/recipes/plan` | 生成食谱，body 可带 `preference` 用户口味/菜品要求，库存为空也可由 AI 生成（meals 含 `main_ingredients/auxiliary_ingredients`；返回 `focus_in_final/requested_meals/actual_meals`，餐数不足时前端提示）（`meals=2..4`、`servings=1..6` 份量、`max_minutes`、可选 `focus_item_id`） |
| POST | `/api/recipes/rescue` | 临期拯救：指定 `item_id`，优先为它生成 2 餐 |
| POST | `/api/recipes/from-assistant` | 把助手做菜回答加入规划：`{message_id, version: "novice"|"chef"}`；按当前选中的版本保存步骤，并追加到当前方案 |
| POST | `/api/recipes/complete` | 完成一道菜并扣减库存：`{plan_id, meal_index}`；同一道菜幂等，不重复扣 |
| POST | `/api/pantry/consume` | 按食谱食材扣减库存（详情抽屉“烹饪完成”） |
| POST | `/api/pantry/shopping/checkout` | 购物结算：`{items: ["鸡蛋 1个", ...], include_staples: true}`；默认只送生鲜，`include_staples=true` 时调料走常规发货（次日达），返回 `fresh_count/staple_count` 与对应配送文案 |
| POST | `/api/recipes/remove-meal` | 从方案移除单道菜：`{plan_id, meal_index}`；移除最后一道时删除整个方案 |
| GET | `/api/recipes/history` | 最近生成的食谱方案 |
| POST | `/api/pantry/notify-test` | 生成并尝试发送今日摘要（无 SMTP/Webhook 时写模拟日志） |

### 多模态录入

`POST /api/pantry/import/text`：

```json
{ "text": "今天买了3个西红柿、2斤排骨，放冷藏", "source": "voice" }
```

返回 `mode`（ai/rule）、`items[]`（名称、数量、单位、分类、建议到期日、`shelf_life_confidence`/`shelf_life_confidence_label`/`shelf_life_alternatives`、保质期来源）、`warnings[]` 与 `count`。未收录的食材 `expires_at` 为空，前端要求用户手动选择；已知食材给出置信度与 3天/5天等快捷选项，用户可改。所有结果都是**预览**，需要再调用 `/api/pantry/batch` 确认导入。每个食材会返回 `shelf_life_confidence`（置信度百分比）、`shelf_life_confidence_label`、`shelf_life_alternatives`；未收录的食材 `expires_at` 为空，不自动填 7 天，由用户手动选择到期日。

`POST /api/pantry/import/receipt` 使用 `multipart/form-data` 的 `file` 字段；复用现有 OCR 驱动（本地/视觉/演示），OCR 文本交给大模型或规则解析。当前演示 OCR 会明确标注 `is_demo`。

### 商业条码库

支持三种接入方式，由 `BARCODE_PROVIDER` 控制（`auto` 默认优先 ShowAPI；没有商业 Key 时自动使用 Open Food Facts）：

1. **ShowAPI（万维易源）商品条码查询 66-22**：配置 `SHOWAPI_APP_KEY`，服务端 POST `https://route.showapi.com/66-22`，解析 `goodsName / trademark / spec / manuName / goodsType / gpc`；成功查询会计费，失败通常不扣费，具体以服务商账单为准；
2. **自定义商业库/代理**：配置 `BARCODE_API_URL`（`{barcode}` 占位）、`BARCODE_API_KEY`、`BARCODE_API_KEY_HEADER`，返回 JSON 至少包含 `name`，可选 `brand/spec/manufacturer/category`；
3. **Open Food Facts 免费公开库**：无需 Key，`auto` 在没有商业 Key 时自动启用；国内商品覆盖有限，未命中时只对少量已核对的条码使用本地公开缓存，并在 `provider_label` 中标注「非商业」。

查询成功后会写入 `barcode_cache` 表，**30 天内同一 GTIN 不再请求商业库**，避免重复扣费；非食品（如沐浴露）不会套用食品保质期，`shelf_life.days` 为 `null`，需按包装填写。公开库未命中时返回 `found=false` 与「未收录」提示，不编造商品；商业库配置后会优先走商业库。

配置可用交互脚本写入（Key 不回显）：`python scripts/configure_barcode.py`。

配置后可运行 `python scripts/check_barcode.py <条码>` 验证（只显示 Key 是否配置，不输出明文）：

```bash
python scripts/check_barcode.py 6954767410388
```

### 保质期与条码

前端优先用浏览器 `BarcodeDetector` 识别条码照片；不支持、条码不在画面中央或识别失败时，把图片上传到 `POST /api/pantry/decode-barcode`，服务端用 `zxing-cpp` 解码（已加入 `backend/requirements.txt`）：先全图，再灰度/增强，最后 2×2、3×3 重叠分块，条码在边角、旋转或尺寸较小时也能尝试识别。解码只解决「条码数字」问题，**商品名称仍需条码库**：未配置 `BARCODE_API_URL` 时明确返回「未接入」，前端引导手动补名称。

- 内置常识表覆盖常见蔬菜、肉禽、蛋奶、主食等；返回 `source=builtin`，不是食品安全标准；
- 配置 `TAVILY_API_KEY` 后，未收录食材会尝试联网检索，返回 `source=web` 与搜索链接/摘要；
- **未接入商业条码库**：`BARCODE_API_URL` 未配置时 `/lookup/barcode` 返回 `found=false` 与「未接入」，前端引导手动补充商品名称，不会编造商品信息。

### SSE 实时推送（非 WebSocket）

浏览器在食材管家页用 `fetch` + `Authorization` 读取 `/api/pantry/stream`，每条连接立即推送一次，之后约每 10 秒刷新，期间每秒发送心跳；离开食材管家后改为 60 秒轮询。同一用户只保留一条 SSE 连接，新连接会结束旧连接，避免刷新页面占满 waitress 线程；当前 WSGI 栈没有 WebSocket，因此使用 SSE 达到服务端主动推送效果，文档和页面文案都不会声称是 WebSocket。

### 每日 8:00 通知

```bash
python scripts/pantry_daily_notify.py --dry-run
python scripts/pantry_daily_notify.py            # 发一次
python scripts/pantry_daily_notify.py --loop     # 常驻每天 08:00
```

未配置 SMTP、`WECOM_WEBHOOK_URL`、`DINGTALK_WEBHOOK_URL` 时，摘要写入 `data/notifications/email-*.log`，接口返回 `simulated`，不会假装已发送。

### AI + 规则引擎复核（AI 智能修正）

AI 方案生成后，服务端逐条检查过敏原、高血压/糖尿病/痛风/孕期等禁忌和指定临期食材；命中则把否决原因回传模型要求重写，最多重试 1 次；仍不通过或格式错误时降级规则引擎。响应中的 `rule_vetoes`、`agent_trace` 与 `warnings` 会保留拦截记录。
