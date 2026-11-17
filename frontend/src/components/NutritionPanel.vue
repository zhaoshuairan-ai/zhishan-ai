<script setup lang="ts">
import { computed } from 'vue'
import type { Nutrition, NutritionItem } from '@/api/types'
import { basisLabel, nutritionValue } from '@/utils/format'
import type { EChartsOption } from '@/utils/echarts'
import { CHART_COLORS, baseTextStyle } from '@/utils/echarts'
import ChartCard from './ChartCard.vue'

const props = withDefaults(
  defineProps<{
    nutrition: Nutrition | null
    showCharts?: boolean
    compact?: boolean
    notes?: string[]
    notesLabel?: string
  }>(),
  { showCharts: true, compact: false, notes: () => [], notesLabel: '' }
)

const items = computed<NutritionItem[]>(() => props.nutrition?.items || [])
const coreItems = computed(() => items.value.filter((item) => ['energy', 'protein', 'fat', 'carbohydrate', 'sodium'].includes(item.key)))
const otherItems = computed(() => items.value.filter((item) => !coreItems.value.includes(item)))
const basis = computed(() => basisLabel(props.nutrition?.basis))
const hasValues = computed(() => items.value.some((item) => item.value !== null))
const warnings = computed(() =>
  (props.nutrition?.warnings || []).filter(
    (warning) => !/(计量基准|未在营养成分表|基准待确认)/.test(String(warning.message || '')),
  ),
)
const basisWarnings = computed(() =>
  (props.nutrition?.warnings || []).filter((warning) =>
    /(计量基准|未在营养成分表|基准待确认)/.test(String(warning.message || '')),
  ),
)
const basisIsDefault = computed(() =>
  Boolean(props.nutrition?.basis_note) ||
  (basisWarnings.value.length > 0 && props.nutrition?.basis === 'per_100g'),
)

function nrvOf(item: NutritionItem): string {
  if (item.nrv_percent !== null && item.nrv_percent !== undefined) return `${item.nrv_percent}%`
  if (item.nrv_percent_estimated !== null && item.nrv_percent_estimated !== undefined) return `≈${item.nrv_percent_estimated}%`
  return '—'
}

const nrvChartItems = computed(() =>
  coreItems.value.filter((item) => (item.nrv_percent ?? item.nrv_percent_estimated) !== null && item.value !== null)
)

const nrvOption = computed<EChartsOption>(() => ({
  color: [CHART_COLORS[0]],
  textStyle: baseTextStyle,
  grid: { left: 8, right: 18, top: 26, bottom: 4, containLabel: true },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: unknown) => {
      const list = params as Array<{ name: string; value: number }>
      const p = list?.[0]
      return p ? `${p.name}<br/>NRV：${p.value}%` : ''
    },
  },
  xAxis: {
    type: 'value',
    axisLabel: { formatter: '{value}%', color: '#7a8a84', fontSize: 11 },
    splitLine: { lineStyle: { color: '#eef2f0' } },
  },
  yAxis: {
    type: 'category',
    data: nrvChartItems.value.map((item) => item.name),
    axisLabel: { color: '#47554f', fontSize: 12 },
    axisLine: { lineStyle: { color: '#e3eae7' } },
    axisTick: { show: false },
  },
  series: [
    {
      type: 'bar',
      data: nrvChartItems.value.map((item) => ({
        name: item.name,
        value: item.nrv_percent ?? item.nrv_percent_estimated ?? 0,
      })),
      barWidth: '46%',
      itemStyle: { borderRadius: [0, 6, 6, 0], color: CHART_COLORS[0] },
      label: { show: true, position: 'right', formatter: '{c}%', color: '#47554f', fontSize: 11 },
    },
  ],
}))

const energySplit = computed(() => {
  const get = (key: string) => items.value.find((item) => item.key === key && item.value !== null)
  const protein = get('protein')
  const fat = get('fat')
  const carb = get('carbohydrate')
  const toGrams = (item?: NutritionItem) => {
    if (!item || item.value === null) return null
    if (item.unit === 'mg') return item.value / 1000
    return item.value
  }
  const p = toGrams(protein)
  const f = toGrams(fat)
  const c = toGrams(carb)
  if (p === null || f === null || c === null) return []
  const data = [
    { name: '蛋白质', value: p * 17 },
    { name: '脂肪', value: f * 37 },
    { name: '碳水化合物', value: c * 17 },
  ].filter((entry) => entry.value > 0)
  return data
})

const energyOption = computed<EChartsOption>(() => ({
  color: ['#6fd0a7', '#7ab8e8', '#f2cf6b'],
  textStyle: baseTextStyle,
  tooltip: {
    trigger: 'item',
    formatter: '{b}<br/>约 {c} kJ（{d}%）',
  },
  legend: {
    bottom: 0,
    itemWidth: 10,
    itemHeight: 10,
    textStyle: { color: '#47554f', fontSize: 11.5 },
  },
  series: [
    {
      name: '能量来源估算',
      type: 'pie',
      radius: ['46%', '68%'],
      center: ['50%', '44%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      data: energySplit.value.map((entry) => ({ ...entry, value: Math.round(entry.value) })),
    },
  ],
}))

const hasNrv = computed(() => nrvChartItems.value.length > 0)
const hasEnergy = computed(() => energySplit.value.length > 0)
</script>

<template>
  <div class="nutrition-panel">
    <div v-if="!nutrition" class="empty">
      <p>尚未解析营养成分表。</p>
    </div>
    <template v-else>
      <div class="basis-row">
        <span class="chip">计量基准：{{ basis }}{{ basisIsDefault ? '（默认）' : '' }}</span>
        <span class="chip chip-muted">来源：{{ nutrition.source === 'ocr' ? '标签识别' : '人工填写' }}</span>
        <span v-if="!hasValues" class="chip chip-warn">未识别到任何数值</span>
      </div>
      <p v-if="basisIsDefault" class="basis-default-note">
        计量基准：默认按每 100g 展示（未识别到表头）
      </p>

      <div class="table-wrap">
        <table class="nutri-table">
          <thead>
            <tr>
              <th scope="col">项目</th>
              <th scope="col">含量</th>
              <th scope="col">NRV%</th>
              <th scope="col">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in coreItems" :key="item.key" :class="{ missing: item.value === null }">
              <td class="name-cell">{{ item.name }}</td>
              <td class="value-cell">{{ nutritionValue(item) }}</td>
              <td>{{ nrvOf(item) }}</td>
              <td>
                <span v-if="item.value === null" class="chip chip-muted">未识别</span>
                <span v-else-if="item.unit_inferred" class="chip chip-warn">单位待确认</span>
                <span v-else class="chip chip-ok">已识别</span>
              </td>
            </tr>
            <tr v-for="item in otherItems" :key="item.key" :class="{ missing: item.value === null }">
              <td class="name-cell">{{ item.name }}</td>
              <td class="value-cell">{{ nutritionValue(item) }}</td>
              <td>{{ nrvOf(item) }}</td>
              <td>
                <span class="chip chip-muted">{{ item.value === null ? '未识别' : '附加项目' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="table-note">
        「未识别」表示图片中没有读到对应数值，系统不会自动补全或估算；NRV% 带 ≈ 号的是平台按内置参考值估算的结果。
      </p>

      <div v-if="notes.length" class="notes-block">
        <div class="notes-title">
          <el-icon><MagicStick /></el-icon>
          营养解读
          <span v-if="notesLabel">{{ notesLabel }}</span>
        </div>
        <ul class="notes-list">
          <li v-for="(note, index) in notes" :key="index">{{ note }}</li>
        </ul>
        <p class="notes-hint">以上为对标签数值的理解辅助，不构成健康建议或安全性结论。</p>
      </div>

      <template v-if="showCharts && !compact">
        <div class="grid grid-2 chart-grid">
          <div class="chart-block">
            <div class="chart-title">核心营养素 NRV% <span>{{ basis }}</span></div>
            <ChartCard :option="nrvOption" :height="'250px'" :empty="!hasNrv" empty-text="缺少可计算 NRV% 的数据" />
          </div>
          <div class="chart-block">
            <div class="chart-title">能量来源估算 <span>按 Atwater 系数折算</span></div>
            <ChartCard
              :option="energyOption"
              :height="'250px'"
              :empty="!hasEnergy"
              empty-text="无供能营养素数据（可能为 0 能量产品或未识别）"
            />
          </div>
        </div>
        <p class="chart-note">
          能量来源为估算值（蛋白质 17 kJ/g、脂肪 37 kJ/g、碳水化合物 17 kJ/g），膳食纤维、糖醇、酒精等因素会造成偏差。
        </p>
      </template>

      <div v-if="warnings.length" class="warning-list">
        <div v-for="(warning, index) in warnings" :key="index" class="warning-item" :class="`w-${warning.level}`">
          <el-icon><WarningFilled /></el-icon>
          <div>
            <div class="warning-msg">{{ warning.message }}</div>
            <div v-if="warning.detail" class="warning-detail">{{ warning.detail }}</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.basis-default-note {
  margin: -4px 0 10px;
  color: #8a9e93;
  font-size: 10.5px;
  line-height: 1.6;
}

.basis-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border: 1px solid var(--border);
  border-radius: 12px;
}

.nutri-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 420px;
  font-size: 14px;
}

.nutri-table th {
  text-align: left;
  padding: 10px 12px;
  background: var(--surface-2);
  color: var(--muted);
  font-weight: 600;
  font-size: 12.5px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.nutri-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #f1f5f3;
  color: var(--text-2);
}

.nutri-table tr:last-child td {
  border-bottom: none;
}

.nutri-table tr.missing td {
  color: var(--muted);
  background: #fcfdfd;
}

.name-cell {
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}

.value-cell {
  font-variant-numeric: tabular-nums;
  font-weight: 650;
  color: var(--brand-700);
  white-space: nowrap;
}

.table-note,
.chart-note {
  margin-top: 8px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.65;
}

.notes-block {
  margin-top: 14px;
  border: 1px solid #cfe7e1;
  background: var(--brand-50);
  border-radius: 12px;
  padding: 12px 14px;
}

.notes-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--brand-700);
  margin-bottom: 6px;
}

.notes-title span {
  font-weight: 500;
  font-size: 11.5px;
  color: var(--muted);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0 7px;
}

.notes-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.85;
}

.notes-hint {
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted);
}

.chart-grid {
  margin-top: 16px;
}

.chart-block {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  min-width: 0;
}

.chart-title {
  font-size: 13.5px;
  font-weight: 650;
  margin-bottom: 6px;
}

.chart-title span {
  font-weight: 400;
  color: var(--muted);
  font-size: 11.5px;
  margin-left: 4px;
}

.warning-list {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.warning-item {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.6;
  border: 1px solid #f3e0bd;
  background: var(--warn-bg);
  color: #6b4d12;
}

.warning-item.w-suspected {
  background: var(--danger-bg);
  border-color: #f6cdc8;
  color: #8b2f26;
}

.warning-detail {
  font-size: 12px;
  opacity: 0.85;
  margin-top: 2px;
  overflow-wrap: anywhere;
}

@media (max-width: 560px) {
  .nutri-table {
    min-width: 380px;
    font-size: 13px;
  }
  .nutri-table th,
  .nutri-table td {
    padding: 9px 10px;
  }
}
</style>
