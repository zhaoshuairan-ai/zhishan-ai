# 数据库设计说明

- 数据库：**SQLite**（文件默认 `data/food_safety.db`，可用 `DATABASE_URL` 修改）
- ORM：**SQLAlchemy 2.x** + Flask-SQLAlchemy 3.x（`Mapped` / `mapped_column` 风格）
- 时间字段统一存 **UTC**（`created_at` / `updated_at` / `analyzed_at` 等），前端按本地时区展示

---

## 一、实体关系

```
users 1 ──── n auth_sessions
  │
  └── 1 ──── n analysis_records
                    │
                    ├── 1 ──── 1 uploaded_images      （图片元数据，文件在 uploads/）
                    ├── 1 ──── 1 ocr_results          （原始 OCR + 校正文本 + 置信度）
                    ├── 1 ──── 1 ingredient_analyses  （配料解读：AI 或规则）
                    ├── 1 ──── 1 nutrition_facts      （营养成分与警告）
                    ├── 1 ──── 1 label_checks         （核查条目与整体结论）
                    └── 1 ──── 1 report_meta          （报告编号与生成时间）

knowledge_entries  （独立表：知识库条目，被 ingredient_analyses.citations 以 ID 引用）
```

一次分析 = 一条 `analysis_records`，其下 6 张表严格 1:1（`record_id` 唯一索引），
删除记录时由数据库级联删除全部关联行，并同步删除磁盘图片。

---

## 二、表结构

### 1. `users`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增主键 |
| username | VARCHAR(40) UNIQUE INDEX | 登录名（3-20 位） |
| display_name | VARCHAR(60) | 昵称 |
| email | VARCHAR(160) NULL | 可选 |
| password_hash | VARCHAR(255) | **scrypt 哈希**（含随机 salt），绝不存明文 |
| is_demo | BOOLEAN | 是否为演示账号 |
| is_active | BOOLEAN | 是否启用 |
| created_at / last_login_at | DATETIME | UTC |

### 2. `auth_sessions`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| token_hash | VARCHAR(64) UNIQUE INDEX | 令牌的 SHA-256（原始令牌只返回给客户端） |
| user_id | FK users.id ON DELETE CASCADE | |
| created_at / expires_at | DATETIME | 默认 30 天（`SESSION_DAYS`） |
| user_agent | TEXT | 预留 |

### 3. `analysis_records`（核心表）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| user_id | FK users.id CASCADE INDEX | 归属账号 |
| food_name | VARCHAR(120) | 食品名称（OCR/校正后回填） |
| brand | VARCHAR(120) NULL | 预留 |
| status | VARCHAR(20) INDEX | `uploaded` → `ocr_done` → `corrected` → `analyzed`；失败为 `failed` |
| data_source | VARCHAR(12) | `real` / `demo` |
| analysis_mode | VARCHAR(12) NULL | `ai` / `rule` |
| ocr_provider | VARCHAR(32) NULL | `local_rapidocr` / `vision_llm` / `demo` |
| overall_check | VARCHAR(20) INDEX | `none_found` / `needs_review` / `suspected` |
| summary | TEXT | 给列表展示的一句话结论 |
| note | TEXT | 备注（演示记录会写 `[演示] ...`） |
| is_demo | BOOLEAN | 是否含演示数据（OCR 或分析使用样例） |
| created_at / updated_at / analyzed_at | DATETIME | |

### 4. `uploaded_images`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| record_id | FK analysis_records.id CASCADE **UNIQUE** | 1:1 |
| user_id | FK users.id CASCADE INDEX | 便于审计 |
| stored_name | VARCHAR(80) | **服务端生成的 UUID 文件名**，不使用用户原始名 |
| original_name | VARCHAR(200) | 仅展示用（已清洗路径分隔符） |
| ext / mime | VARCHAR | 由 Pillow 真实解码结果决定 |
| size_bytes / width / height | INTEGER | |
| sha256 | VARCHAR(64) | 可按内容去重/审计 |
| created_at | DATETIME | |

> 磁盘布局：`uploads/{uuid}.{ext}`（原图）+ `uploads/display_{uuid}.jpg`（长边 ≤2200 的展示图/OCR 输入）。

### 5. `ocr_results`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| record_id | FK CASCADE **UNIQUE** | |
| provider / provider_label / engine_version | VARCHAR | 驱动标识与版本 |
| is_demo | BOOLEAN | 演示样例标记 |
| status | VARCHAR(20) | `success` / `partial` / `failed` |
| raw_text | TEXT | **原始 OCR 文本（永不覆盖）** |
| corrected_text | TEXT | 由校正后字段重建的标签全文 |
| fields | JSON | 11 个字段：food_name / ingredients_text / nutrition_text / net_content / production_date / shelf_life / expiry_date / storage / producer / standard_no / allergen |
| field_confidence | JSON | 每个字段 0-1 置信度 |
| field_flags | JSON | 每字段状态：ok / low / missing / inferred / format_suspect + 说明 |
| low_confidence_fields / missing_fields | JSON | 便于前端高亮 |
| raw_payload | JSON | 驱动原始输出（文本行、耗时、警告） |
| duration_ms | INTEGER | |
| corrected_at | DATETIME NULL | 用户最后一次校正时间 |

### 6. `ingredient_analyses`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| record_id | FK CASCADE **UNIQUE** | |
| mode | VARCHAR(12) | `ai` / `rule` / `demo` |
| model | VARCHAR(80) NULL | 模型名（规则模式为空） |
| prompt_version | VARCHAR(20) | 提示词版本，便于复现 |
| summary | TEXT | 整体说明 |
| ingredients | JSON | 每项：name/category/role/purpose/explanation/confidence/evidence/source_refs/caution/knowledge_refs |
| unknown_items | JSON | 知识库未收录的成分 |
| unconfirmed | JSON | 待确认事项（含降级原因、被丢弃的幻觉项） |
| citations | JSON | 知识库引用（ID/标题/来源/是否已核验） |
| diff | JSON | 统计摘要（配料数/未知数/待确认数） |
| disclaimer / error | TEXT | 免责声明 / 降级错误信息 |
| raw_response | JSON | 调用元信息（不存完整模型原文，避免膨胀） |
| duration_ms | INTEGER | |

### 7. `nutrition_facts`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| record_id | FK CASCADE **UNIQUE** | |
| basis | VARCHAR(30) | `per_100g` / `per_100ml` / `per_serving` |
| source | VARCHAR(20) | `ocr` / `manual` |
| items | JSON | 每项：key/name/raw_name/value/unit/unit_inferred/nrv_percent/nrv_percent_estimated/status/note/raw/value_kj/… |
| warnings | JSON | 单位缺失、基准不明、数值异常等提示 |

> 缺失项**不会**被补默认值：`value=NULL`、`status="missing"`，前端显示「未识别」。

### 8. `label_checks`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| record_id | FK CASCADE **UNIQUE** | |
| ruleset_version | VARCHAR(20) | 规则集版本（如 `2025.11`） |
| overall | VARCHAR(20) | `none_found` / `needs_review` / `suspected` |
| items | JSON | 每条：rule_id/title/category/level/level_label/result/reason/basis/source/todo/rule_version/rule_updated_at |
| counts | JSON | pass/info/review/suspected/skip 计数 |
| coverage | JSON | 字段覆盖度、营养项数、配料数 |

### 9. `knowledge_entries`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| slug | VARCHAR(80) UNIQUE INDEX | 稳定标识（便于导入更新） |
| title | VARCHAR(160) INDEX | 条目标题 |
| aliases | VARCHAR(300) | 逗号分隔的别名（用于配料匹配） |
| keywords | VARCHAR(300) | 检索关键词 |
| category | VARCHAR(30) INDEX | additive / ingredient / nutrition / label_rule / safety |
| summary / content / usage_note | TEXT | 摘要 / 正文 / 使用提示 |
| source_name | VARCHAR(200) | 来源名称（标准名称/机构） |
| source_url | VARCHAR(300) NULL | 官方查询入口（不编造具体文献链接） |
| source_type | VARCHAR(30) | standard_name / textbook / public_health / official_website / editorial |
| verification_status | VARCHAR(20) | `verified` / `pending`（待核验） |
| version | VARCHAR(20) | 条目版本 |
| is_featured / sort_order | BOOLEAN / INTEGER | 首页推荐与排序 |

### 10. `report_meta`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| record_id | FK CASCADE **UNIQUE** | |
| report_no | VARCHAR(40) UNIQUE INDEX | 形如 `FS-20261017-0002-C9F5` |
| version | VARCHAR(20) | 报告模板版本 |
| generated_at | DATETIME | 生成时间 |
| generated_count | INTEGER | 生成次数 |
| snapshot_hash | VARCHAR(64) | 数据快照哈希（用于判断报告是否过期） |

> 报告正文**不存 JSON 快照**，而是每次按真实数据渲染，避免「报告与数据不一致」。
> 记录被重新分析时会删除 `report_meta`，下次访问重新生成新的报告编号。

---

## 二点五、科普助手相关表

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `assistant_entries` | `slug`(唯一)、`title`、`aliases`、`keywords`、`category`、`summary`、`detail`、`evidence`、`caveat`、`sources`(JSON)、`verification_status` | 科普/辟谣条目，按 `slug` 幂等 upsert |
| `chat_sessions` | `user_id`、`title`、`created_at`、`updated_at` | 会话，按用户隔离 |
| `chat_messages` | `session_id`、`role`、`content`、`mode`、`matched_slug`、`sources`(JSON)、`payload`(JSON) | 消息；`sources`/`payload` 保存当时快照 |

消息与会话为级联删除（`ondelete="CASCADE"` + ORM `cascade`），删除会话会一并清空消息。

## 三、索引与约束

| 索引/约束 | 目的 |
| --- | --- |
| `users.username` UNIQUE | 用户名唯一（登录时大小写不敏感） |
| `auth_sessions.token_hash` UNIQUE | 令牌查询 |
| `analysis_records.user_id` / `created_at` / `status` / `overall_check` | 列表过滤与统计 |
| 各子表 `record_id` UNIQUE | 保证 1:1，重复写入会覆盖而非产生脏数据 |
| `knowledge_entries.slug` UNIQUE | 种子导入幂等 |
| `report_meta.report_no` UNIQUE | 报告编号唯一 |
| 外键 `ON DELETE CASCADE` | 删除记录时自动清理子表 |

---

## 四、初始化与表结构升级

```powershell
python backend\init_db.py            # 建表 + 知识库 + 演示账号 + 演示记录（幂等）
python backend\init_db.py --no-demo  # 不生成演示记录
```

`init_database()` 做三件事：

1. `db.create_all()`：创建缺失的表；
2. `_ensure_columns()`：**列级升级**——检查 `PRAGMA table_info`，只做「新增缺失列」的安全操作
   （例如给旧库补 `knowledge_entries.keywords`、`analysis_records.is_demo`），不删不改；
3. `knowledge_service.upsert_seed()`：按 `slug` 幂等写入/更新 123 条知识（分两批种子：`knowledge_seed.py` + `knowledge_seed_extra.py`）；
4. `ensure_demo_user()` + `seed_demo()`：创建演示账号与 2 条带 `is_demo` 标记的演示记录。

**正式版本化迁移建议**：引入 Alembic（`flask db init/migrate/upgrade`），
把 `COLUMN_MIGRATIONS` 换成真实的迁移脚本，支持回滚与多环境。

---

## 五、数据生命周期

| 事件 | 数据库 | 磁盘 |
| --- | --- | --- |
| 上传图片 | 新增 `analysis_records` + `uploaded_images` | 写入原图 + 展示图 |
| 触发 OCR | 新增/更新 `ocr_results` | — |
| 校正 | 更新 `ocr_results.fields / corrected_text` | — |
| 分析 | 新增/更新 `ingredient_analyses`、`nutrition_facts`、`label_checks`；删除旧 `report_meta` | — |
| 生成报告 | 新增 `report_meta` | — |
| 删除记录 | 级联删除 6 张子表 + 记录本身 | 删除原图与展示图（失败仅记录日志，不影响接口成功） |
| 更换图片 | 新上传创建新记录；旧记录保留在历史中（可删除） | 旧文件随记录删除 |

---

## 六、备份、迁移与容量

**备份**（服务运行中也可执行，SQLite 建议先停服务或用 `.backup`）：

```powershell
# 停止服务后最简单：复制数据库与图片目录
Copy-Item data\food_safety.db D:\backup\food_safety-2026-10-17.db
Copy-Item uploads D:\backup\uploads -Recurse
```

**迁移到 PostgreSQL**（结构兼容，需改动）：

1. `pip install psycopg[binary]`
2. `.env` 设置 `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/food`
3. `python backend/init_db.py`
4. 图片仍需放在持久化磁盘或对象存储（建议改用 S3/OSS，替换 `services/storage.py` 的实现）

**容量估算**

| 项目 | 单条约占 |
| --- | --- |
| 记录 + OCR + 分析 + 核查（JSON） | 30–80 KB |
| 原图（手机 8MP，压缩前） | 2–6 MB |
| 展示图（长边 2200，JPEG q86） | 200–600 KB |

> 比赛演示（数十条记录）SQLite 完全够用；若要长期运行，建议定期清理图片并迁移到对象存储。

---

## 管理员后台新增表（SQLAlchemy 自动建表 + 轻量列升级）

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| `users.role` | 角色 | `user` / `admin`（默认 user；只能通过 CLI 初始化为 admin） |
| `admin_audit_logs` | 操作审计 | `actor_username`、`action`、`target_type/id`、`detail`、`result`、`ip`、`created_at` |
| `check_rules` | 可后台维护的核查规则元数据 | `rule_id`、标题、分类、依据、来源、`scope`、`version`、`effective_date`、`enabled` |
| `rule_revisions` | 规则版本快照 | `rule_id`、`action`、`before` / `after` JSON、`changed_by`、`changed_at` |
| `record_notes` | 记录复核备注 | `record_id`、`admin_username`、`content`、`created_at` |
| `feedbacks` | 用户反馈 | `user_id`、`record_id`、`content`、`status`、`reply`、`handled_by` |
| `service_events` | 服务错误事件（监控页） | `kind`、`level`、`message`、`detail`、`created_at` |
| `knowledge_entries` 新列 | 发布流程 | `status`（published/draft/offline）、`scope`、`published_at`、`created_by`、`updated_by` |

迁移方式：`python backend/init_db.py` 会执行 `create_all()` 并对已有 SQLite 库补充缺失列（只加列，不删改），随后写入规则种子。
