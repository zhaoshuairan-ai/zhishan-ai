<script setup lang="ts">
import { computed, ref } from 'vue'
import type { HealthAssessment, HealthFinding } from '@/api/types'

const props = defineProps<{ health: HealthAssessment | null }>()

const score = computed(() => props.health?.score ?? null)
const grade = computed(() => props.health?.grade || 'NA')
const gradeLabel = computed(() => props.health?.grade_label || '数据不足')
const percent = computed(() => (typeof score.value === 'number' ? Math.max(0, Math.min(100, score.value)) : 0))

const gaugeStyle = computed(() => ({
  background: score.value === null
    ? 'conic-gradient(#dfe8e5 0 100%)'
    : `conic-gradient(var(--brand) 0 ${percent.value}%, #e6efec ${percent.value}% 100%)`,
}))

const gradeClass = computed(() => {
  if (score.value === null) return 'na'
  if (percent.value >= 85) return 'a'
  if (percent.value >= 70) return 'b'
  if (percent.value >= 55) return 'c'
  if (percent.value >= 40) return 'd'
  return 'e'
})

function finding(key: string): HealthFinding | null {
  return props.health?.findings.find((item) => item.key === key) || null
}

const focusFindings = computed(() =>
  ['trans_fat', 'sugar', 'additives'].map((key) => finding(key)).filter((item): item is HealthFinding => Boolean(item))
)

const otherFindings = computed(() =>
  (props.health?.findings || []).filter((item) => !['trans_fat', 'sugar', 'additives'].includes(item.key))
)

const additives = computed(() => props.health?.additives?.items || [])
const showAllAdditives = ref(false)
const visibleAdditives = computed(() => (showAllAdditives.value ? additives.value : additives.value.slice(0, 5)))

function levelType(level: string) {
  if (level === 'good') return 'success'
  if (level === 'watch') return 'warning'
  if (level === 'unknown') return 'info'
  return 'primary'
}
</script>

<template>
  <div v-if="!health" class="health-empty">该记录尚未生成健康评估。</div>

  <div v-else class="health">
    <div class="health-top">
      <div class="score-ring" :style="gaugeStyle">
        <div class="score-inner">
          <strong>{{ score === null ? '—' : score }}</strong>
          <span>{{ score === null ? '未评分' : '健康分' }}</span>
        </div>
      </div>
      <div class="health-summary">
        <div class="summary-tags">
          <span class="grade-badge" :class="gradeClass">{{ grade === 'NA' ? '数据不足' : `${grade} · ${gradeLabel}` }}</span>
          <span class="model-tag">自建模型 v{{ health.model_version }}</span>
        </div>
        <p class="headline">{{ health.headline }}</p>
        <p class="quality-line">
          营养数据 {{ health.data_quality.core_present }}/{{ health.data_quality.core_total }} 项 ·
          糖{{ health.data_quality.has_sugar ? '已标注' : '未标注' }} ·
          反式脂肪{{ health.data_quality.has_trans_fat ? '已标注' : '未标注' }} ·
          配料 {{ health.data_quality.ingredient_count }} 项
        </p>
      </div>
    </div>

    <div class="health-disclaimer">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ health.disclaimer }}</span>
    </div>

    <div class="focus-grid">
      <article v-for="item in focusFindings" :key="item.key" class="focus-card" :class="item.level">
        <div class="focus-head">
          <strong>{{ item.title }}</strong>
          <el-tag size="small" :type="levelType(item.level)" effect="plain">{{ item.level_label }}</el-tag>
        </div>
        <p class="focus-summary">{{ item.summary }}</p>
        <p class="focus-detail">{{ item.detail }}</p>
        <p class="focus-basis">依据：{{ item.basis }} · 置信度 {{ item.confidence }}</p>
      </article>
    </div>

    <div class="dimension-block">
      <div class="block-title">评分构成（{{ health.model_version }}）</div>
      <div class="dimension-list">
        <div v-for="dimension in health.dimensions" :key="dimension.key" class="dimension-row">
          <span class="dimension-label">{{ dimension.label }}</span>
          <div class="dimension-bar" :class="{ unknown: dimension.status === 'unknown' }">
            <span
              :style="{ width: dimension.status === 'unknown' ? '0%' : `${Math.round((dimension.score / dimension.max) * 100)}%` }"
            />
          </div>
          <span class="dimension-value">
            {{ dimension.status === 'unknown' ? '数据不足' : `${dimension.score}/${dimension.max}` }}
          </span>
        </div>
      </div>
      <p v-if="health.score_note" class="score-note">{{ health.score_note }}</p>
    </div>

    <div v-if="additives.length" class="additive-block">
      <div class="block-title">
        识别到的添加剂（{{ health.additives.count }}）
        <span class="block-hint">合规性需要具体品类、用量与适用范围，本站只标记「待核实」</span>
      </div>
      <ul class="additive-list">
        <li v-for="item in visibleAdditives" :key="item.name">
          <div class="additive-head">
            <strong>{{ item.name }}</strong>
            <el-tag size="small" type="info" effect="plain">{{ item.compliance }}</el-tag>
          </div>
          <p class="additive-role">{{ item.role }}</p>
          <p v-if="item.risk_note" class="additive-risk">{{ item.risk_note }}</p>
          <p v-else class="additive-risk muted">未发现需要特别提示的人群注意事项；不代表没有风险，需以标准与检测为准。</p>
        </li>
      </ul>
      <button
        v-if="additives.length > 5"
        type="button"
        class="additive-toggle"
        @click="showAllAdditives = !showAllAdditives"
      >
        {{ showAllAdditives ? '收起' : `展开全部 ${additives.length} 种添加剂` }}
      </button>
      <p class="additive-note">
        GB 2760 对添加剂的食品类别、使用量与残留量有明确规定；本系统未收录具体限量，无法判断本产品是否合规。
      </p>
    </div>

    <div v-if="otherFindings.length" class="dimension-block">
      <div class="block-title">其他指标</div>
      <ul class="other-list">
        <li v-for="item in otherFindings" :key="item.key">
          <div class="other-head">
            <strong>{{ item.title }}</strong>
            <el-tag size="small" :type="levelType(item.level)" effect="plain">{{ item.level_label }}</el-tag>
          </div>
          <p>{{ item.summary }}</p>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.health-empty {
  padding: 18px 0;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.health-top {
  display: flex;
  gap: 18px;
  align-items: center;
}

.score-ring {
  width: 104px;
  height: 104px;
  border-radius: 50%;
  padding: 8px;
  flex-shrink: 0;
  --brand: var(--brand-700);
}

.score-inner {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: var(--card);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
}

.score-inner strong {
  font-size: 30px;
  line-height: 1;
  color: var(--text-1);
}

.score-inner span {
  font-size: 11px;
  color: var(--muted);
}

.health-summary {
  flex: 1;
  min-width: 0;
}

.summary-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.grade-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  color: #fff;
  background: #7a8a84;
}

.grade-badge.a {
  background: #2f9e6f;
}

.grade-badge.b {
  background: #4b9e6f;
}

.grade-badge.c {
  background: #c47a08;
}

.grade-badge.d {
  background: #d2691e;
}

.grade-badge.e {
  background: #cf4237;
}

.grade-badge.na {
  background: #7a8a84;
}

.model-tag {
  font-size: 11px;
  color: var(--muted);
}

.headline {
  margin: 8px 0 4px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-2);
}

.quality-line {
  margin: 0;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}

.health-disclaimer {
  margin-top: 14px;
  padding: 9px 12px;
  border-radius: 8px;
  background: var(--warn-bg);
  color: #8a5a12;
  font-size: 11.5px;
  line-height: 1.8;
  display: flex;
  gap: 6px;
  align-items: flex-start;
}

.focus-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.focus-card {
  border: 1px solid var(--border);
  border-left: 3px solid var(--border);
  border-radius: 10px;
  padding: 11px 12px;
  background: var(--card);
}

.focus-card.good {
  border-left-color: #2f9e6f;
}

.focus-card.watch {
  border-left-color: #c47a08;
}

.focus-card.unknown {
  border-left-color: #9aa8a3;
}

.focus-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.focus-head strong {
  font-size: 13px;
}

.focus-summary {
  margin: 7px 0 4px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-2);
}

.focus-detail {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.8;
  color: var(--muted);
}

.focus-basis {
  margin: 6px 0 0;
  font-size: 10.5px;
  color: var(--muted);
}

.dimension-block,
.additive-block {
  margin-top: 16px;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.block-hint {
  margin-left: 6px;
  font-weight: 400;
  font-size: 11px;
  color: var(--muted);
}

.dimension-list {
  display: grid;
  gap: 6px;
}

.dimension-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--text-2);
}

.dimension-label {
  width: 86px;
  flex-shrink: 0;
}

.dimension-bar {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: var(--surface-2);
  overflow: hidden;
}

.dimension-bar span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--brand);
}

.dimension-bar.unknown {
  opacity: 0.45;
}

.dimension-value {
  min-width: 52px;

  width: 44px;
  text-align: right;
  color: var(--muted);
  font-size: 11.5px;
}

.score-note {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.7;
}

.additive-list,
.other-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.additive-list li,
.other-list li {
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 9px 11px;
  background: var(--card);
}

.additive-head,
.other-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.additive-head strong,
.other-head strong {
  font-size: 12.5px;
}

.additive-role {
  margin: 4px 0 0;
  font-size: 11.5px;
  color: var(--muted);
}

.additive-risk {
  margin: 4px 0 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-2);
}

.additive-risk.muted {
  color: var(--muted);
}

.additive-toggle {
  margin-top: 8px;
  border: none;
  background: transparent;
  color: var(--brand-700);
  font-size: 11.5px;
  padding: 0;
  cursor: pointer;
}

.additive-note {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.8;
  color: var(--muted);
}

.other-list p {
  margin: 5px 0 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--muted);
}

@media (max-width: 767px) {
  .health-top {
    gap: 12px;
    align-items: flex-start;
  }

  .score-ring {
    width: 88px;
    height: 88px;
  }

  .score-inner strong {
    font-size: 25px;
  }

  .focus-grid {
    grid-template-columns: 1fr;
  }

  .dimension-label {
    width: 76px;
  }
}
</style>
