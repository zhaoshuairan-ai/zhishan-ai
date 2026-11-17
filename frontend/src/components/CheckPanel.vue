<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CheckItem, CheckLevel, CheckResult } from '@/api/types'
import { levelClass } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    check: CheckResult | null
    expandAll?: boolean
    filterable?: boolean
    compact?: boolean
    /** 报告模式下把「通过」项合并为紧凑清单，避免报告过长 */
    compactPass?: boolean
  }>(),
  { expandAll: false, filterable: true, compact: false, compactPass: false }
)

type FilterKey = 'all' | 'attention' | CheckLevel

const filter = ref<FilterKey>('all')
const expanded = ref<Set<string>>(new Set())

const allFilters: Array<{ key: FilterKey; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'attention', label: '需关注' },
  { key: 'review', label: '待核实' },
  { key: 'suspected', label: '疑似问题' },
  { key: 'info', label: '提示' },
  { key: 'pass', label: '通过' },
]

const filters = computed(() => allFilters.filter((item) => !(props.compactPass && item.key === 'pass')))

const items = computed<CheckItem[]>(() => props.check?.items || [])
const counts = computed(() => props.check?.counts || {})

const filtered = computed(() => {
  if (filter.value === 'all') return items.value
  if (filter.value === 'attention') {
    return items.value.filter((item) => item.level === 'review' || item.level === 'suspected')
  }
  return items.value.filter((item) => item.level === filter.value)
})

const passItems = computed(() => (props.compactPass ? filtered.value.filter((item) => item.level === 'pass') : []))

const expandedItems = computed(() => {
  const source = props.compactPass ? filtered.value.filter((item) => item.level !== 'pass') : filtered.value
  const order: Record<string, number> = { suspected: 0, review: 1, info: 2, pass: 3, skip: 4 }
  return [...source].sort(
    (a, b) => (order[a.level] ?? 9) - (order[b.level] ?? 9),
  )
})

const grouped = computed(() => {
  const map = new Map<string, CheckItem[]>()
  for (const item of expandedItems.value) {
    const list = map.get(item.category) || []
    list.push(item)
    map.set(item.category, list)
  }
  return Array.from(map.entries()).map(([category, list]) => ({ category, list }))
})

function isExpanded(item: CheckItem): boolean {
  return props.expandAll || expanded.value.has(item.rule_id + item.result)
}

function toggle(item: CheckItem) {
  if (props.expandAll) return
  const key = item.rule_id + item.result
  const next = new Set(expanded.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
}

const overallClass = computed(() => {
  const overall = props.check?.overall
  if (overall === 'none_found') return 'overall-ok'
  if (overall === 'suspected') return 'overall-danger'
  return 'overall-warn'
})

const summaryChips = computed(() =>
  [
    { key: 'suspected', label: '疑似问题', tone: 'chip-danger' },
    { key: 'review', label: '待核实', tone: 'chip-warn' },
    { key: 'info', label: '提示', tone: 'chip-info' },
    { key: 'pass', label: '通过', tone: 'chip-ok' },
    { key: 'skip', label: '不适用', tone: 'chip-muted' },
  ].filter((entry) => (counts.value[entry.key] || 0) > 0)
)
</script>

<template>
  <div class="check-panel">
    <div v-if="!check" class="empty">
      <p>尚未执行标签核查。</p>
    </div>
    <template v-else>
      <div class="overall-box" :class="overallClass">
        <div class="overall-left">
          <el-icon class="overall-icon">
            <CircleCheckFilled v-if="check.overall === 'none_found'" />
            <WarningFilled v-else-if="check.overall === 'needs_review'" />
            <CircleCloseFilled v-else />
          </el-icon>
          <div>
            <div class="overall-label">{{ check.overall_label }}</div>
            <div class="overall-sub">
              基于 {{ Object.values(counts).reduce((a, b) => a + b, 0) }} 条规则 · 规则集版本 {{ check.ruleset_version }}
            </div>
          </div>
        </div>
        <div class="overall-chips">
          <span v-for="chip in summaryChips" :key="chip.key" class="chip" :class="chip.tone">
            {{ chip.label }} {{ counts[chip.key] }}
          </span>
        </div>
      </div>

      <p class="overall-note">
        以上结论来自对图片中可见文字的规则核查，仅代表「本次识别到的信息在逻辑与完整性上是否需要人工确认」，
        不代表监管部门结论，也不等同于食品不安全。
      </p>

      <div v-if="filterable" class="filter-row">
        <button
          v-for="option in filters"
          :key="option.key"
          type="button"
          class="filter-chip"
          :class="{ active: filter === option.key }"
          @click="filter = option.key"
        >
          {{ option.label }}
        </button>
      </div>

      <div v-if="!filtered.length" class="empty small">
        <p>该分类下没有核查条目。</p>
      </div>

      <div v-for="group in grouped" :key="group.category" class="rule-group">        <div class="group-title">
          {{ group.category }}
          <span>{{ group.list.length }}</span>
        </div>
        <div class="rule-list">
          <div v-for="item in group.list" :key="item.rule_id + item.result" class="rule-item" :class="levelClass(item.level)">
            <div class="rule-head" @click="toggle(item)">
              <span class="level-dot" />
              <span class="rule-title">{{ item.title }}</span>
              <span class="level-label">{{ item.level_label }}</span>
            </div>
            <div class="rule-result">{{ item.result }}</div>
            <div class="rule-reason">{{ item.reason }}</div>

            <div v-if="isExpanded(item)" class="rule-detail">
              <div v-if="item.basis" class="detail-row">
                <span class="detail-label">依据</span>
                <span class="detail-text">{{ item.basis }}</span>
              </div>
              <div v-if="item.source?.name" class="detail-row">
                <span class="detail-label">来源</span>
                <span class="detail-text">
                  {{ item.source.name }}
                  <span v-if="item.source.note" class="source-note">（{{ item.source.note }}）</span>
                </span>
              </div>
              <div v-if="item.todo" class="detail-row">
                <span class="detail-label">待确认</span>
                <span class="detail-text">{{ item.todo }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">规则版本</span>
                <span class="detail-text">{{ item.rule_id }} · {{ item.rule_version }} · 更新于 {{ item.rule_updated_at }}</span>
              </div>
            </div>

            <button v-if="!expandAll" type="button" class="detail-toggle" @click="toggle(item)">
              {{ isExpanded(item) ? '收起依据' : '查看依据与来源' }}
              <el-icon><ArrowDown v-if="!isExpanded(item)" /><ArrowUp v-else /></el-icon>
            </button>
          </div>
        </div>
      </div>

      <div v-if="compactPass && passItems.length" class="pass-block">
        <div class="group-title">
          未发现问题的项目
          <span>{{ passItems.length }}</span>
        </div>
        <div class="pass-chips">
          <span v-for="item in passItems" :key="item.rule_id + item.result" class="pass-chip" :title="item.result">
            {{ item.title }}
          </span>
        </div>
        <p class="pass-note">以上项目在本次识别的数据中未发现明显问题，不代表食品本身安全或合规。</p>
      </div>

      <p class="check-disclaimer">
        规则集版本 {{ check.ruleset_version }}。所有依据仅以标准名称形式引用，系统未收录标准原文，
        具体条款与限量请以官方发布的现行文本为准。
      </p>
    </template>
  </div>
</template>

<style scoped>
.overall-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid #c9e8d9;
  background: var(--ok-bg);
}

.overall-box.overall-warn {
  background: var(--warn-bg);
  border-color: #f0d8ac;
}

.overall-box.overall-danger {
  background: var(--danger-bg);
  border-color: #f2c4be;
}

.overall-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.overall-icon {
  font-size: 30px;
  color: var(--ok);
  flex: 0 0 auto;
}

.overall-warn .overall-icon {
  color: var(--warn);
}

.overall-danger .overall-icon {
  color: var(--danger);
}

.overall-label {
  font-size: 18px;
  font-weight: 750;
  color: #1f5a38;
}

.overall-warn .overall-label {
  color: #7a4d05;
}

.overall-danger .overall-label {
  color: #94291f;
}

.overall-sub {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.overall-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.overall-note {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.7;
}

.filter-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 16px 0 6px;
}

.filter-chip {
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text-2);
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 12.5px;
  cursor: pointer;
  min-height: 32px;
}

.filter-chip.active {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}

.rule-group {
  margin-top: 18px;
}

.group-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.group-title span {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  background: #f2f5f4;
  border-radius: 999px;
  padding: 0 7px;
}

.rule-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rule-item {
  border: 1px solid var(--border);
  border-left: 3px solid var(--border-strong);
  border-radius: 10px;
  padding: 11px 13px;
  background: var(--card);
}

.rule-item.level-pass {
  border-left-color: var(--ok);
}

.rule-item.level-info {
  border-left-color: var(--info);
}

.rule-item.level-review {
  border-left-color: var(--warn);
}

.rule-item.level-suspected {
  border-left-color: var(--danger);
}

.rule-item.level-skip {
  border-left-color: #d7e0dd;
  background: #fbfcfc;
}

.rule-head {
  display: flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  flex-wrap: wrap;
}

.level-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--border-strong);
  flex: 0 0 auto;
}

.level-pass .level-dot {
  background: var(--ok);
}

.level-info .level-dot {
  background: var(--info);
}

.level-review .level-dot {
  background: var(--warn);
}

.level-suspected .level-dot {
  background: var(--danger);
}

.rule-title {
  font-size: 13.5px;
  font-weight: 650;
  color: var(--text);
}

.level-label {
  font-size: 11.5px;
  color: var(--muted);
  margin-left: auto;
  white-space: nowrap;
}

.rule-result {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
  overflow-wrap: anywhere;
}

.rule-reason {
  margin-top: 3px;
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.rule-detail {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.7;
  align-items: flex-start;
}

.detail-label {
  flex: 0 0 56px;
  color: var(--muted);
  font-weight: 600;
}

.detail-text {
  color: var(--text-2);
  overflow-wrap: anywhere;
}

.source-note {
  color: var(--muted);
}

.detail-toggle {
  margin-top: 7px;
  border: none;
  background: transparent;
  color: var(--brand);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.check-disclaimer {
  margin-top: 16px;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}

.pass-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.pass-chip {
  font-size: 11.5px;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--ok-bg);
  color: #256b4b;
  border: 1px solid #c9e8d9;
}

.pass-note {
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted);
}

@media (max-width: 560px) {
  .overall-label {
    font-size: 16px;
  }
  .overall-icon {
    font-size: 25px;
  }
  .level-label {
    margin-left: 0;
  }
  .detail-label {
    flex-basis: 48px;
  }
}
</style>
