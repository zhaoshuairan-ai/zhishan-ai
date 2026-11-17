-- 智膳 AI：知识库状态核对与批量恢复
-- 数据库：SQLite
-- 说明：只做 SELECT / UPDATE，不包含任何 DELETE。
-- 执行前建议先备份 data/food_safety.db。

-- ------------------------------------------------------------
-- 1. 核对当前状态分布
-- ------------------------------------------------------------
SELECT
    category,
    status,
    verification_status,
    COUNT(*) AS total
FROM knowledge_entries
GROUP BY category, status, verification_status
ORDER BY category, status, verification_status;

SELECT COUNT(*) AS total_entries
FROM knowledge_entries;

-- ------------------------------------------------------------
-- 2. 确认重点条目仍然存在
-- ------------------------------------------------------------
SELECT id, title, category, status, verification_status
FROM knowledge_entries
WHERE title LIKE '%反式脂肪酸%'
   OR title LIKE '%山梨酸钾%'
   OR title LIKE '%小麦粉%';

-- ------------------------------------------------------------
-- 3. 批量恢复：所有已有知识恢复为「已发布 + 已核验」
--    注意：数据库实际存储英文枚举值
--    status: published / draft / offline
--    verification_status: pending / verified
--    不要写成中文「已发布」「已核验」，否则不会命中。
-- ------------------------------------------------------------
BEGIN TRANSACTION;

UPDATE knowledge_entries
SET
    status = 'published',
    verification_status = 'verified',
    updated_at = CURRENT_TIMESTAMP
WHERE status <> 'published'
   OR verification_status <> 'verified';

COMMIT;

-- ------------------------------------------------------------
-- 4. 复核：C 端与后台「已发布」都应读取这个结果
-- ------------------------------------------------------------
SELECT
    category,
    COUNT(*) AS published_verified_total
FROM knowledge_entries
WHERE status = 'published'
  AND verification_status = 'verified'
GROUP BY category
ORDER BY category;

SELECT COUNT(*) AS published_verified_total
FROM knowledge_entries
WHERE status = 'published'
  AND verification_status = 'verified';
