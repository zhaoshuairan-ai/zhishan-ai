<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi, type AdminOverview } from '@/api/admin'
import { ApiError } from '@/api/client'
import ChartCard from '@/components/ChartCard.vue'
import { CHART_COLORS, baseTextStyle, type EChartsOption } from '@/utils/echarts'

const router = useRouter()
const data = ref<AdminOverview | null>(null)
const loading = ref(true)
const errorMessage = ref('')

const totals = computed(() => data.value?.totals)

const cards = computed(() => [
  { label: '用户总数', value: totals.value?.users ?? '—', hint: `启用 ${totals.value?.users_active ?? 0} · 停用 ${totals.value?.users_disabled ?? 0}`, icon: 'User' },
  { label: '分析任务', value: totals.value?.records ?? '—', hint: `真实记录 ${totals.value?.real_records ?? 0} 条`, icon: 'Tickets' },
  { label: '分析成功率', value: totals.value ? `${totals.value.success_rate}%` : '—', hint: `已完成 ${totals.value?.analyzed ?? 0} 次`, icon: 'CircleCheck' },
  { label: '失败任务', value: totals.value?.failed ?? '—', hint: '处理失败的分析记录', icon: 'WarningFilled' },
  { label: '知识库条目', value: totals.value?.knowledge ?? '—', hint: `已发布 ${totals.value?.knowledge_published ?? 0} 条`, icon: 'Reading' },
  { label: '核查规则', value: totals.value?.rules ?? '—', hint: `启用 ${totals.value?.rules_enabled ?? 0} 条`, icon: 'SetUp' },
])

const trendOption = computed<EChartsOption>(() => {
  const trend = data.value?.trend || []
  return {
    textStyle: baseTextStyle,
    color: [CHART_COLORS[0]],
    grid: { left: 8, right: 16, top: 24, bottom: 6, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: trend.map((item) => item.date.slice(5)),
      axisLine: { lineStyle: { color: '#d8e2de' } },
      axisLabel: { color: '#7b8b86', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#eef3f1' } },
      axisLabel: { color: '#7b8b86', fontSize: 11 },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        data: trend.map((item) => item.count),
        areaStyle: { opacity: 0.18 },
        symbolSize: 5,
      },
    ],
  }
})

const aiUsageOption = computed<EChartsOption>(() => {
  const labels = ['11-09', '11-10', '11-11', '11-12', '11-13', '11-14', '11-15']

  return {
    textStyle: baseTextStyle,
    color: ['#5bc49a', '#7ab8e8'],
    grid: { left: 8, right: 20, top: 38, bottom: 6, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: {
      top: 2,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { fontSize: 11, color: '#607b70' },
      data: ['AI 调用次数', 'Token 消耗（万）'],
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: '#d8e2de' } },
      axisLabel: { color: '#7b8b86', fontSize: 11 },
    },
    yAxis: [
      {
        type: 'value',
        name: '次',
        minInterval: 1,
        nameTextStyle: { color: '#8a9e94', fontSize: 10 },
        splitLine: { lineStyle: { color: '#eef3f1' } },
        axisLabel: { color: '#7b8b86', fontSize: 10.5 },
      },
      {
        type: 'value',
        name: '万 Token',
        nameTextStyle: { color: '#8a9e94', fontSize: 10 },
        splitLine: { show: false },
        axisLabel: { color: '#7b8b86', fontSize: 10.5 },
      },
    ],
    series: [
      {
        name: 'AI 调用次数',
        type: 'bar',
        barWidth: '42%',
        data: [128, 156, 142, 188, 214, 196, 242],
        itemStyle: { borderRadius: [5, 5, 0, 0] },
      },
      {
        name: 'Token 消耗（万）',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        symbolSize: 5,
        data: [12.4, 15.8, 14.2, 18.9, 21.4, 19.8, 24.6],
        areaStyle: { opacity: 0.1 },
      },
    ],
  }
})

const statusLabels: Record<string, string> = {
  uploaded: '已上传',
  ocr_done: '已识别',
  corrected: '已校正',
  analyzed: '分析完成',
  failed: '处理失败',
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    data.value = await adminApi.dashboard()
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="admin-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">后台概览</h1>
        <p class="page-sub">数据来自后端数据库的真实记录；没有数据的指标显示为 0。</p>
      </div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </header>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mb" />

    <div v-loading="loading" class="stat-grid">
      <div v-for="card in cards" :key="card.label" class="stat-card card">
        <div class="stat-icon"><el-icon><component :is="card.icon" /></el-icon></div>
        <div class="stat-value">{{ card.value }}</div>
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-hint">{{ card.hint }}</div>
      </div>
    </div>

    <div class="grid-2 section">
      <section class="card">
        <div class="card-title">
          <h3>近 14 天分析记录</h3>
          <span class="hint">按创建日期统计</span>
        </div>
        <ChartCard :option="trendOption" height="260px" :empty="!data?.trend?.some((item) => item.count > 0)" empty-text="近 14 天暂无分析记录" />
      </section>

      <section class="card">
        <div class="card-title">
          <h3>任务状态分布</h3>
          <span class="hint">全量记录</span>
        </div>
        <div v-if="!data?.status_distribution?.length" class="empty-text">暂无记录</div>
        <ul v-else class="status-list">
          <li v-for="item in data.status_distribution" :key="item.status">
            <span>{{ statusLabels[item.status] || item.status }}</span>
            <strong>{{ item.count }}</strong>
          </li>
        </ul>
      </section>
    </div>

    <div class="grid-2 section">
      <section class="card">
        <div class="card-title">
          <h3>最近操作</h3>
          <el-button text type="primary" @click="router.push({ name: 'admin-audit-logs' })">查看全部</el-button>
        </div>
        <div v-if="!data?.recent_audit?.length" class="empty-text">暂无审计记录</div>
        <ul v-else class="audit-list">
          <li v-for="item in data.recent_audit" :key="item.id">
            <div>
              <strong>{{ item.actor_username || '系统' }}</strong>
              <span class="action">{{ item.action_label }}</span>
            </div>
            <time>{{ item.created_at?.replace('T', ' ').slice(0, 19) }}</time>
          </li>
        </ul>
      </section>

      <section class="card">
        <div class="card-title"><h3>快捷管理</h3></div>
        <div class="shortcut-grid">
          <button type="button" class="shortcut" @click="router.push({ name: 'admin-users' })">
            <el-icon><User /></el-icon>
            <span>用户管理</span>
          </button>
          <button type="button" class="shortcut" @click="router.push({ name: 'admin-knowledge' })">
            <el-icon><Reading /></el-icon>
            <span>知识库</span>
          </button>
          <button type="button" class="shortcut" @click="router.push({ name: 'admin-prompts' })">
            <el-icon><MagicStick /></el-icon>
            <span>Prompt 管理</span>
          </button>
          <button type="button" class="shortcut" @click="router.push({ name: 'admin-monitor' })">
            <el-icon><Monitor /></el-icon>
            <span>系统监控</span>
          </button>
        </div>
        <p class="footer-note">
          管理员共 {{ totals?.users_admin ?? 0 }} 个；近 7 天新增用户 {{ totals?.users_new_7d ?? 0 }} 个；
          待处理反馈 {{ totals?.feedback_open ?? 0 }} 条。
        </p>
      </section>
    </div>

    <section class="card section ai-usage-card">
      <div class="card-title">
        <div>
          <h3>近 7 天 AI 调用与 Token 消耗趋势</h3>
          <span class="hint">静态运营模拟数据 · 反映成本与调用规模</span>
        </div>
        <el-tag type="success" effect="plain">AI Ops</el-tag>
      </div>
      <ChartCard :option="aiUsageOption" height="260px" :empty="false" />
    </section>
  </div>
</template>

<style scoped>
.ai-usage-card {
  margin-top: 0;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.page-sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--muted);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  align-items: stretch;
  gap: 12px;
  margin-bottom: 16px;
}

/* 抵消全局 .card + .card 的 margin-top，保证所有 KPI 卡片等高 */
.stat-grid .stat-card,
.stat-grid .stat-card + .stat-card {
  height: 100%;
  margin-top: 0;
}

.stat-card {
  padding: 14px 16px;
  position: relative;
}

.stat-icon {
  position: absolute;
  right: 14px;
  top: 14px;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: var(--brand-50);
  color: var(--brand-700);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-1);
}

.stat-label {
  font-size: 12.5px;
  color: var(--text-2);
  margin-top: 2px;
}

.stat-hint {
  font-size: 11px;
  color: var(--muted);
  margin-top: 4px;
}

.grid-2 {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  align-items: stretch;
  gap: 16px;
  margin-bottom: 16px;
}

/* 同一行卡片严格等高、同顶，不再受全局 .card + .card 的 margin-top 影响 */
.grid-2 > .card,
.grid-2 > .card + .card {
  height: 100%;
  margin-top: 0;
}

.empty-text {
  color: var(--muted);
  font-size: 12.5px;
  padding: 18px 0;
}

.status-list,
.audit-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.status-list li,
.audit-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  padding: 8px 10px;
  background: var(--surface-2);
  border-radius: 8px;
}

.audit-list .action {
  color: var(--muted);
  margin-left: 6px;
  font-size: 12px;
}

.audit-list time {
  color: var(--muted);
  font-size: 11.5px;
  white-space: nowrap;
}

.shortcut-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.shortcut {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card);
  cursor: pointer;
  font-size: 13px;
}

.shortcut:hover {
  border-color: #9ed4c8;
  background: var(--brand-50);
}

.footer-note {
  margin: 14px 0 0;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}

@media (max-width: 1023px) {
  .grid-2 {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
