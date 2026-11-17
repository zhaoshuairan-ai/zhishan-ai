<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { echarts, type EChartsOption } from '@/utils/echarts'

const props = withDefaults(
  defineProps<{
    option: EChartsOption
    height?: string
    empty?: boolean
    emptyText?: string
  }>(),
  { height: '280px', empty: false, emptyText: '暂无数据' }
)

const chartEl = ref<HTMLDivElement | null>(null)
const chart = shallowRef<echarts.ECharts | null>(null)
const printImage = ref('')
let observer: ResizeObserver | null = null

function render() {
  if (!chartEl.value || props.empty) return
  if (!chart.value) {
    chart.value = echarts.init(chartEl.value, undefined, { renderer: 'canvas' })
  }
  chart.value.setOption(props.option, true)
}

function preparePrintImage() {
  if (!chart.value || props.empty) {
    printImage.value = ''
    return
  }

  try {
    // Resize first so the captured bitmap matches the print layout.
    chart.value.resize()
    printImage.value = chart.value.getDataURL({
      type: 'png',
      pixelRatio: 2,
      backgroundColor: '#ffffff',
    })
  } catch {
    printImage.value = ''
  }
}

function clearPrintImage() {
  printImage.value = ''
}

onMounted(() => {
  render()
  if (chartEl.value && 'ResizeObserver' in window) {
    observer = new ResizeObserver(() => {
      chart.value?.resize()
    })
    observer.observe(chartEl.value)
  }
  window.addEventListener('orientationchange', () => chart.value?.resize())
  // 点击“打印 / 保存 PDF”时由 ReportView 派发；beforeprint 兼容 Ctrl+P
  window.addEventListener('report:prepare-print', preparePrintImage)
  window.addEventListener('report:cleanup-print', clearPrintImage)
  window.addEventListener('beforeprint', preparePrintImage)
  window.addEventListener('afterprint', clearPrintImage)
})

watch(
  () => props.option,
  () => {
    if (props.empty) {
      chart.value?.dispose()
      chart.value = null
      return
    }
    render()
  },
  { deep: true }
)

watch(
  () => props.empty,
  (val) => {
    if (!val) setTimeout(render, 0)
  }
)

onBeforeUnmount(() => {
  observer?.disconnect()
  chart.value?.dispose()
  chart.value = null
  window.removeEventListener('report:prepare-print', preparePrintImage)
  window.removeEventListener('report:cleanup-print', clearPrintImage)
  window.removeEventListener('beforeprint', preparePrintImage)
  window.removeEventListener('afterprint', clearPrintImage)
})
</script>

<template>
  <div
    class="chart-box"
    :class="{
      'is-empty': empty,
      'is-print-ready': Boolean(printImage),
    }"
    :style="{ height }"
  >
    <div v-if="empty" class="chart-empty">
      <el-icon><DataLine /></el-icon>
      <span>{{ emptyText }}</span>
    </div>

    <div v-show="!empty" ref="chartEl" class="chart-canvas" />

    <!-- 打印前由 ECharts.getDataURL() 生成的静态图 -->
    <img
      v-if="printImage"
      :src="printImage"
      class="chart-print-image"
      alt=""
    />
  </div>
</template>

<style scoped>
.chart-box {
  width: 100%;
  position: relative;
  min-width: 0;
}

.chart-canvas {
  width: 100%;
  height: 100%;
}

.chart-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--muted);
  font-size: 13px;
  background: var(--surface-2);
  border-radius: 12px;
}

.chart-empty .el-icon {
  font-size: 26px;
  color: var(--border-strong);
}
<
.chart-print-image {
  display: none;
}

@media print {
  .chart-box.is-empty {
    display: none !important;
  }
}
</style>
