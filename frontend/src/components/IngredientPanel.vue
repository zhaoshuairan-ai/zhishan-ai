<script setup lang="ts">
import { computed } from 'vue'
import type { IngredientAnalysis, IngredientExplain } from '@/api/types'
import { confidenceLabel, evidenceLabel } from '@/utils/format'
import { splitIngredientText } from '@/utils/ingredients'

const props = withDefaults(
  defineProps<{
    analysis: IngredientAnalysis | null
    ingredientsText?: string
    showCitations?: boolean
  }>(),
  { ingredientsText: '', showCitations: true }
)

const chips = computed(() => splitIngredientText(props.ingredientsText))
const items = computed<IngredientExplain[]>(() => props.analysis?.ingredients || [])
const isRuleMode = computed(() => props.analysis?.mode === 'rule')
const isAiMode = computed(() => props.analysis?.mode === 'ai')

function evidenceTag(evidence?: string) {
  if (evidence === 'knowledge_base') return 'chip-ok'
  if (evidence === 'general_knowledge') return 'chip-info'
  return 'chip-warn'
}

function confidenceTag(confidence?: string) {
  if (confidence === 'high') return 'chip-ok'
  if (confidence === 'medium') return 'chip-info'
  return 'chip-warn'
}
</script>

<template>
  <div class="ingredient-panel">
    <div v-if="!analysis" class="empty">
      <p>尚未进行配料分析。</p>
    </div>
    <template v-else>
      <div class="mode-row">
        <span class="chip" :class="isAiMode ? '' : 'chip-warn'">
          <el-icon><MagicStick v-if="isAiMode" /><SetUp v-else /></el-icon>
          {{ analysis.mode_label }}
        </span>
        <span v-if="analysis.model" class="chip chip-muted">模型：{{ analysis.model }}</span>
        <span class="chip chip-muted">提示词版本：{{ analysis.prompt_version }}</span>
        <span v-if="analysis.duration_ms" class="chip chip-muted">耗时 {{ analysis.duration_ms }} ms</span>
      </div>

      <div v-if="isRuleMode" class="notice notice-brand mode-notice">
        <el-icon><InfoFilled /></el-icon>
        <div>
          本次解读由本地规则引擎基于知识库条目生成，<strong>没有调用大模型</strong>，解释内容以知识库原文摘要为主。
          如需真实 AI 解读，请在 <code>.env</code> 中配置 <code>AI_API_KEY</code> 后重新分析。
        </div>
      </div>

      <p class="summary">{{ analysis.summary }}</p>

      <div v-if="chips.length" class="chip-block">
        <div class="block-label">校正后的配料表（{{ chips.length }} 项）</div>
        <div class="ingredient-chips">
          <span v-for="(chip, index) in chips" :key="`${chip}-${index}`" class="ingredient-chip">
            <span class="order">{{ index + 1 }}</span>{{ chip }}
          </span>
        </div>
      </div>

      <div class="explain-list">
        <article v-for="item in items" :key="item.name" class="explain-card">
          <header class="explain-head">
            <div class="explain-title">
              <span class="name">{{ item.name }}</span>
              <span class="chip chip-muted">{{ item.category }}</span>
              <span v-if="item.role && item.role !== item.category" class="role">{{ item.role }}</span>
            </div>
            <div class="explain-tags">
              <span class="chip" :class="confidenceTag(item.confidence)">{{ confidenceLabel(item.confidence) }}</span>
              <span class="chip" :class="evidenceTag(item.evidence)">{{ evidenceLabel(item.evidence) }}</span>
            </div>
          </header>
          <p v-if="item.purpose" class="purpose">{{ item.purpose }}</p>
          <p class="explanation">{{ item.explanation || '暂无解释内容。' }}</p>
          <p v-if="item.caution" class="caution">
            <el-icon><Warning /></el-icon>
            {{ item.caution }}
          </p>
          <div v-if="item.knowledge_refs?.length" class="refs">
            <span class="refs-label">知识库来源：</span>
            <a
              v-for="ref in item.knowledge_refs"
              :key="ref.id"
              class="ref-link"
              :href="`/knowledge?entry=${ref.id}`"
              target="_blank"
              rel="noopener"
            >
              [K{{ ref.id }}] {{ ref.title }}
              <span v-if="ref.verification_status === 'pending'" class="pending-mark">待核验</span>
            </a>
          </div>
        </article>
      </div>

      <div v-if="analysis.unknown_items?.length" class="sub-block">
        <div class="block-label">未收录的成分（{{ analysis.unknown_items.length }}）</div>
        <div class="tag-list">
          <span v-for="name in analysis.unknown_items" :key="name" class="chip chip-muted">{{ name }}</span>
        </div>
        <p class="block-note">这些成分暂未匹配到知识库条目，系统不会凭空编造解释，可查阅包装说明或权威资料。</p>
      </div>

      <div v-if="analysis.unconfirmed?.length" class="sub-block">
        <div class="block-label">待确认事项</div>
        <ul class="unconfirmed-list">
          <li v-for="(item, index) in analysis.unconfirmed" :key="index">{{ item }}</li>
        </ul>
      </div>

      <div v-if="showCitations && analysis.citations?.length" class="sub-block">
        <div class="block-label">引用来源</div>
        <ul class="citation-list">
          <li v-for="citation in analysis.citations" :key="citation.knowledge_id">
            <span class="citation-title">[K{{ citation.knowledge_id }}] {{ citation.title }}</span>
            <span class="citation-source">{{ citation.source_name }}</span>
            <span v-if="!citation.verified" class="chip chip-warn">来源待核验</span>
            <div v-if="citation.claim" class="citation-claim">{{ citation.claim }}</div>
          </li>
        </ul>
      </div>

      <p class="disclaimer">{{ analysis.disclaimer }}</p>
    </template>
  </div>
</template>

<style scoped>
.mode-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.mode-row .chip .el-icon {
  margin-right: 2px;
}

.mode-notice {
  margin-bottom: 12px;
}

.mode-notice code {
  background: rgba(255, 255, 255, 0.6);
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 12px;
}

.summary {
  font-size: 14.5px;
  color: var(--text-2);
  line-height: 1.75;
  padding: 12px 14px;
  background: var(--brand-50);
  border-radius: 10px;
  border-left: 3px solid var(--brand);
  overflow-wrap: anywhere;
}

.chip-block {
  margin-top: 16px;
}

.block-label {
  font-size: 12.5px;
  font-weight: 650;
  color: var(--muted);
  margin-bottom: 8px;
  letter-spacing: 0.2px;
}

.ingredient-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.ingredient-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 13px;
  color: var(--text-2);
  max-width: 100%;
  overflow-wrap: anywhere;
}

.ingredient-chip .order {
  display: inline-grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--brand-100);
  color: var(--brand-700);
  font-size: 10.5px;
  font-weight: 700;
  flex: 0 0 auto;
}

.explain-list {
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.explain-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  background: var(--card);
}

.explain-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.explain-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.name {
  font-size: 15.5px;
  font-weight: 700;
  color: var(--text);
  overflow-wrap: anywhere;
}

.role {
  font-size: 12px;
  color: var(--muted);
}

.explain-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.purpose {
  margin-top: 8px;
  font-size: 13.5px;
  color: var(--brand-700);
  font-weight: 600;
}

.explanation {
  margin-top: 6px;
  font-size: 13.5px;
  color: var(--text-2);
  line-height: 1.75;
  overflow-wrap: anywhere;
}

.caution {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--warn);
  background: var(--warn-bg);
  border-radius: 8px;
  padding: 7px 10px;
  display: flex;
  gap: 6px;
  align-items: flex-start;
}

.refs {
  margin-top: 9px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.8;
}

.refs-label {
  margin-right: 4px;
}

.ref-link {
  margin-right: 10px;
  color: var(--brand);
  overflow-wrap: anywhere;
}

.pending-mark {
  font-size: 10.5px;
  color: var(--warn);
  border: 1px solid #ecd9b4;
  border-radius: 4px;
  padding: 0 3px;
  margin-left: 3px;
}

.sub-block {
  margin-top: 18px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.block-note {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}

.unconfirmed-list,
.citation-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.85;
}

.citation-list li {
  margin-bottom: 8px;
}

.citation-title {
  font-weight: 600;
  color: var(--text);
}

.citation-source {
  margin-left: 6px;
  color: var(--muted);
  font-size: 12px;
}

.citation-claim {
  font-size: 12.5px;
  color: var(--muted);
  margin-top: 2px;
  overflow-wrap: anywhere;
}

.disclaimer {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}

@media (max-width: 560px) {
  .explain-card {
    padding: 12px;
  }
  .summary {
    font-size: 13.5px;
  }
}
</style>
