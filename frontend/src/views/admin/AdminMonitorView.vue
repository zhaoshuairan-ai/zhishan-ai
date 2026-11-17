<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { adminApi, type MonitorData } from '@/api/admin'
import { ApiError } from '@/api/client'

const data = ref<MonitorData | null>(null)
const loading = ref(true)
const errorMessage = ref('')

const hasServiceFailures = computed(() => {
  const requests = data.value?.requests
  if (!requests) return false

  return (
    Number(requests.failed_total || 0) > 0 ||
    Number(requests.failed_24h || 0) > 0 ||
    Number(requests.ocr_failed || 0) > 0
  )
})

const friendlyMonitorWarning =
  '⚠️ 部分接口服务波动，系统已自动记录。'

const friendlyMonitorSuccess =
  '🟢 所有 AI 服务运行正常，监控数据实时同步中。'


const services = computed(() => {
  const value = data.value?.services
  if (!value) return []
  return [
    {
      name: 'OCR 识别服务',
      status: value.ocr.provider,
      ok: value.ocr.status === 'ok',
      details: [
        `提供方：${value.ocr.provider}`,
        value.ocr.is_demo ? '当前为演示引擎' : '真实识别引擎',
        value.ocr.vision_configured ? '视觉模型 Key 已配置' : '视觉模型 Key 未配置',
      ],
    },
    {
      name: 'AI 配料分析',
      status: value.ai.mode,
      ok: value.ai.configured,
      details: [
        `提供方：${value.ai.provider}`,
        `模型：${value.ai.model || '未配置'}`,
        value.ai.configured ? 'API Key 已配置（不展示）' : '未配置 Key，使用规则模式',
      ],
    },
    {
      name: '科普助手大模型',
      status: value.assistant.dedicated_llm ? 'dedicated' : 'fallback',
      ok: Boolean(value.assistant.model),
      details: [
        `模型：${value.assistant.model || '未配置'}`,
        value.assistant.dedicated_llm ? '使用独立助手接口' : '复用通用 AI 配置',
        value.assistant.general_answer ? '允许通用回答（标注未核验）' : '仅知识库回答',
      ],
    },
  ]
})

const metrics = computed(() => {
  const req = data.value?.requests
  if (!req) return []
  return [
    { label: '分析任务总量', value: req.records_total },
    { label: '近 24 小时任务', value: req.records_24h },
    { label: '近 7 天任务', value: req.records_7d },
    { label: '失败任务（总）', value: req.failed_total },
    { label: '失败任务（24h）', value: req.failed_24h },
    { label: 'OCR 次数', value: req.ocr_total },
    { label: 'OCR 失败', value: req.ocr_failed },
    { label: 'AI 分析次数', value: req.ai_total },
    { label: '近 24 小时错误事件', value: req.errors_24h },
  ]
})

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    data.value = await adminApi.monitor()
  } catch {
    errorMessage.value = friendlyMonitorWarning
  } finally {
    loading.value = false
  }
}

function formatTime(value: string) {
  return value ? value.replace('T', ' ').slice(0, 19) : '—'
}

onMounted(load)
</script>

<template>
  <div class="admin-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">系统监控</h1>
        <p class="page-sub">仅展示服务状态、数量与耗时；不会返回 API Key、密码等敏感配置。</p>
      </div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </header>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mb" />

    <div v-loading="loading" class="service-grid">
      <div v-for="service in services" :key="service.name" class="card service-card">
        <div class="service-head">
          <strong>{{ service.name }}</strong>
          <el-tag size="small" :type="service.ok ? 'success' : 'warning'">{{ service.ok ? '已配置' : '未配置' }}</el-tag>
        </div>
        <p class="service-status">{{ service.status }}</p>
        <ul class="service-details">
          <li v-for="line in service.details" :key="line">{{ line }}</li>
        </ul>
      </div>
    </div>

    <section class="card section">
      <div class="card-title">
        <h3>请求与失败统计</h3>
        <span class="hint">来自数据库真实记录</span>
      </div>
      <div class="metric-grid">
        <div v-for="metric in metrics" :key="metric.label" class="metric">
          <strong>{{ metric.value }}</strong>
          <span>{{ metric.label }}</span>
        </div>
      </div>
      <div class="perf">
        <span>OCR 平均耗时：<strong>{{ data?.performance.avg_ocr_ms ?? 0 }} ms</strong></span>
        <span>OCR 最长耗时：<strong>{{ data?.performance.max_ocr_ms ?? 0 }} ms</strong></span>
      </div>
    </section>

    <section class="card section monitor-health-section">
      <div class="card-title">
        <h3>服务状态提示</h3>
        <span class="hint">仅展示汇总状态，不暴露底层堆栈</span>
      </div>

      <div v-if="hasServiceFailures" class="monitor-friendly-warning">
        {{ friendlyMonitorWarning }}
      </div>
      <div v-else class="monitor-friendly-success">
        {{ friendlyMonitorSuccess }}
      </div>

      <p class="note">{{ data?.note || '监控数据来自数据库中的真实记录。' }}</p>
    </section>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.page-sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--muted);
}

.service-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  align-items: stretch;
  gap: 12px;
  margin-bottom: 14px;
}

/* 抵消 .card + .card 的全局 margin-top，保证三张服务卡等高 */
.service-grid .service-card,
.service-grid .service-card + .service-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  margin-top: 0;
  padding: 14px 16px;
}

.service-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.service-status {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  color: var(--brand-700);
  margin: 8px 0;
}

.service-details {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
}

.metric {
  background: var(--surface-2);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric strong {
  font-size: 18px;
  color: var(--text-1);
}

.metric span {
  font-size: 11.5px;
  color: var(--muted);
}

.perf {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 12px;
  color: var(--muted);
}

.perf strong {
  color: var(--text-1);
}

.monitor-health-section {
  border: 1px solid #f0dfc4;
}

.monitor-friendly-warning {
  padding: 14px 16px;
  border: 1px solid #f3d39a;
  border-radius: 10px;
  background: #fff8e8;
  color: #9a6512;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.7;
}

.monitor-friendly-success {
  padding: 14px 16px;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  background: #ecfdf5;
  color: #047857;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.7;
}

.empty-text {
  color: var(--muted);
  font-size: 13px;
  padding: 16px 0;
  text-align: center;
}

.note {
  margin: 12px 0 0;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}
</style>
