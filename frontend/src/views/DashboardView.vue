<script setup lang="ts">

import { computed, onActivated, onMounted, ref } from 'vue'

import { useRouter } from 'vue-router'

import { ElMessage } from 'element-plus'

import { familyApi, pantryApi, systemApi } from '@/api'

import type {
  DashboardData,
  FamilyAlert,
  FamilyInfo,
  PantryReminder,
  RecordSummary,
} from '@/api/types'

import { useAuthStore } from '@/stores/auth'

import { useAppStore } from '@/stores/app'

import ChartCard from '@/components/ChartCard.vue'

import EmptyState from '@/components/EmptyState.vue'

import WeatherWidget from '@/components/WeatherWidget.vue'

import { useDietLog } from '@/composables/useDietLog'

import { formatRelative } from '@/utils/format'

import type { EChartsOption } from '@/utils/echarts'

import { baseTextStyle } from '@/utils/echarts'

const router = useRouter()

const auth = useAuthStore()

const app = useAppStore()



const data = ref<DashboardData | null>(null)

const loading = ref(true)

const errorMessage = ref('')

const familyAlert = ref<FamilyAlert | null>(null)

const familyInfo = ref<FamilyInfo | null>(null)

const pantryReminder = ref<PantryReminder | null>(null)

const weather = ref({
  city: '唐山市',
  temperature: 5,
  description: '霾',
  condition: 'haze',
  emoji: '🌫️',
})

const { totals: dietTotals } = useDietLog()

const healthDistribution = computed(() => {
  const value = data.value?.totals

  return [
    {
      name: '健康优选',
      value: value?.none_found || 0,
      color: '#88d6b1',
    },
    {
      name: '中规中矩',
      value: value?.needs_review || 0,
      color: '#f0d48a',
    },
    {
      name: '风险预警',
      value: value?.suspected || 0,
      color: '#f19a95',
    },
  ]
})

const healthyCount = computed(() => healthDistribution.value[0].value)
const generalCount = computed(() => healthDistribution.value[1].value)
const riskCount = computed(() => healthDistribution.value[2].value)

const calorieTarget = 1700



const totals = computed(() => data.value?.totals)

const isEmpty = computed(() => Boolean(data.value && totals.value && totals.value.records === 0))

const analyzedRate = computed(() => {

  if (!totals.value?.records) return 0

  return Math.round((totals.value.analyzed / totals.value.records) * 100)

})

const attentionCount = computed(() => (totals.value?.suspected || 0) + (totals.value?.needs_review || 0))

const todayCalories = computed(() => Math.round(dietTotals.value.calories || 0))

const remainingCalories = computed(() => Math.max(0, calorieTarget - todayCalories.value))

const expiringCount = computed(() => pantryReminder.value?.counts.expiring || 0)

const riskBlocked = computed(() => totals.value?.suspected || 0)

const familyCount = computed(() => familyInfo.value?.member_count || 1)

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 11) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const weatherAdvice = computed(() => {
  const temp = Number(weather.value.temperature)
  const text = String(weather.value.description || '')
  if (temp <= 15 || /雨|雪|霾|雾|降温/.test(text)) {
    return `今日${text || '天气变化'}${temp}℃，已为您优先推荐暖胃食谱。`
  }
  if (temp >= 28) {
    return `今日${temp}℃，已为您优先推荐清爽解腻食谱。`
  }
  return `今日${text || '天气舒适'}${temp}℃，已为您更新今日膳食建议。`
})

function applyWeather(next: {
  city: string
  emoji: string
  temperature: number
  description: string
  condition: string
}) {
  Object.assign(weather.value, next)
}

function goMealPlan() {
  router.push({ name: 'pantry', query: { tab: 'plan' } })
}

function recordEmoji(record: RecordSummary) {
  const name = `${record.food_name || ''} ${record.brand || ''}`
  if (/饮|茶|果汁|可乐|汽水|咖啡/.test(name)) return '🥤'
  if (/面|拉面|意面/.test(name)) return '🍜'
  if (/粥|饭|米/.test(name)) return '🍚'
  if (/沙拉|蔬菜|菜/.test(name)) return '🥗'
  if (/肉|鱼|鸡|虾|牛|猪/.test(name)) return '🍱'
  if (/饼|糕|糖|巧克力|零食/.test(name)) return '🍪'
  return '🍽️'
}

function recordCheckClass(record: RecordSummary) {
  if (record.overall_check === 'suspected') return 'is-danger'
  if (record.overall_check === 'needs_review') return 'is-warn'
  if (record.overall_check === 'none_found') return 'is-ok'
  return 'is-muted'
}

function recordCheckLabel(record: RecordSummary) {
  if (record.overall_check === 'none_found') return '未发现明显问题'
  if (record.overall_check === 'suspected') return '疑似问题'
  if (record.overall_check === 'needs_review') return '待核实'
  return '未核查'
}



const trendOption = computed<EChartsOption>(() => ({

  textStyle: baseTextStyle,

  grid: { left: 6, right: 14, top: 20, bottom: 4, containLabel: true },

  tooltip: {
    trigger: 'axis',
    formatter: (params: unknown) => {

    const list = params as Array<{ axisValue: string; value: number }>

    if (!list?.[0]) return ''
      const [month, day] = String(list[0].axisValue).split('-')
      return `${Number(month)}月${Number(day)}日：共进行了 ${list[0].value} 次食品分析`

  } },

  xAxis: {

    type: 'category',

    data: (data.value?.trend || []).map((item) => item.label),

    axisLabel: { color: '#7a8a84', fontSize: 10.5, interval: 1 },

    axisLine: { lineStyle: { color: '#e3eae7' } },

    axisTick: { show: false },

  },

  yAxis: {

    type: 'value',

    minInterval: 1,

    axisLabel: { color: '#7a8a84', fontSize: 11, formatter: '{value} 次' },

    splitLine: { lineStyle: { color: '#eef2f0' } },

  },

  series: [

    {

      type: 'line',

      smooth: true,

      symbolSize: 5,

      data: (data.value?.trend || []).map((item) => item.count),

      lineStyle: { width: 2.8, color: '#4fbd93' },

      itemStyle: { color: '#2f9c78' },

      areaStyle: {

        color: {

          type: 'linear',

          x: 0,

          y: 0,

          x2: 0,

          y2: 1,

          colorStops: [

            { offset: 0, color: 'rgba(79,189,147,0.30)' },

            { offset: 1, color: 'rgba(79,189,147,0.02)' },

          ],

        },

      },

    },

  ],

}))



const checkPieOption = computed<EChartsOption>(() => ({

  color: ['#88d6b1', '#f0d48a', '#f19a95'],

  textStyle: baseTextStyle,

  tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 条（{d}%）' },

  legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11.5, color: '#47554f' } },

  series: [

    {

      type: 'pie',

      radius: ['46%', '68%'],

      center: ['50%', '42%'],

      itemStyle: { borderColor: '#fff', borderWidth: 2 },

      label: { show: false },

      data: healthDistribution.value
        .filter((entry) => entry.value > 0)
        .map((entry) => ({ name: entry.name, value: entry.value })),

    },

  ],

}))



const DISH_NAME_PATTERN =
  /清蒸|红烧|爆炒|小炒|炒|焖|烤|炸|炖|煮|煎|汤|粥|饭|面|沙拉|凉拌|糖醋|宫保|麻婆|鱼香|寿司|汉堡|披萨|火锅|凉皮|饺子|包子|馒头/

const recentDishNames = computed(
  () =>
    new Set(
      (data.value?.recent_records || [])
        .filter((record) => record.ocr_provider === 'dish_vision')
        .map((record) => String(record.food_name || '').trim())
        .filter(Boolean),
    ),
)

const topIngredientItems = computed(() =>
  (data.value?.top_ingredients || [])
    .filter((item) => {
      const name = String(item.name || '').trim()
      if (!name) return false
      if (recentDishNames.value.has(name)) return false
      return !DISH_NAME_PATTERN.test(name)
    })
    .slice(0, 8),
)

const topOption = computed<EChartsOption>(() => ({

  color: ['#78c9a8'],

  textStyle: baseTextStyle,

  grid: { left: 6, right: 22, top: 10, bottom: 4, containLabel: true },

  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: unknown) => {
      const list = params as Array<{ name: string; value: number }>
      return list?.[0] ? `${list[0].name}<br/>共摄入 ${list[0].value} 次` : ''
    },
  },

  xAxis: {

    type: 'value',

    minInterval: 1,

    axisLabel: { color: '#7a8a84', fontSize: 11, formatter: '{value} 次' },

    splitLine: { lineStyle: { color: '#eef2f0' } },

  },

  yAxis: {

    type: 'category',

    inverse: true,

    data: topIngredientItems.value.map((item) => item.name),

    axisLabel: { color: '#47554f', fontSize: 11.5 },

    axisLine: { lineStyle: { color: '#e3eae7' } },

    axisTick: { show: false },

  },

  series: [

    {

      type: 'bar',

      data: topIngredientItems.value.map((item) => item.value),

      barWidth: '52%',

      itemStyle: { borderRadius: [0, 5, 5, 0] },

      label: { show: true, position: 'right', fontSize: 11, color: '#47554f' },

    },

  ],

}))



const recentRecords = computed(() => {
  const seen = new Set<string>()
  return (data.value?.recent_records || []).filter((record) => {
    const key = String(record.food_name || '').trim().toLowerCase()
    if (!key) return true
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

const hasCheckData = computed(() => healthDistribution.value.some((entry) => entry.value > 0))

const hasTopData = computed(() => topIngredientItems.value.length > 0)



async function load() {

  loading.value = true

  errorMessage.value = ''

  try {

    data.value = await systemApi.dashboard()

  } catch (error) {

    errorMessage.value = (error as Error).message

  } finally {

    loading.value = false

  }

  const [alertResult, infoResult, pantryResult] = await Promise.allSettled([
    familyApi.alert(),
    familyApi.info(),
    pantryApi.list({ status: 'expiring' }),
  ])

  familyAlert.value =
    alertResult.status === 'fulfilled' ? alertResult.value.alert : null

  familyInfo.value =
    infoResult.status === 'fulfilled' ? infoResult.value : null

  pantryReminder.value =
    pantryResult.status === 'fulfilled' ? pantryResult.value.reminder : null

}

function openRecord(record: RecordSummary) {

  if (record.status === 'analyzed') router.push({ name: 'result', params: { id: record.id } })

  else router.push({ name: 'analyze', query: { record: record.id } })

}



onMounted(load)
onActivated(load)



function openKnowledge(id: number) {

  router.push({ name: 'knowledge', query: { entry: String(id) } })

}



async function goAnalyze() {

  if (!app.online) {

    ElMessage.warning('当前处于离线状态，联网后才能上传并识别图片')

    return

  }

  router.push({ name: 'analyze' })

}

</script>



<template>

  <div class="page dashboard">

    <el-alert

      v-if="familyAlert"

      class="family-health-alert"

      type="warning"

      show-icon

      :closable="true"

      title="家庭健康提醒"

      @close="familyAlert = null"

    >

      <template #default>

        <strong>{{ familyAlert.message }}</strong>

        <span class="family-alert-detail">

          · {{ familyAlert.owner_name }} 刚加入「{{ familyAlert.item_name }}」，建议您关注今日饮食。

        </span>

      </template>

    </el-alert>



    <!-- 顶部智能问候与环境感知 -->
    <section class="home-hero">
      <div class="home-hero-copy">
        <span class="home-kicker">全场景健康膳食管家</span>
        <h1 class="home-title">{{ greeting }}，智膳管家已就绪</h1>
        <p class="home-sub">
          从今天的第一餐开始，把健康数据变成看得懂、做得到的日常选择。
        </p>

        <div class="home-actions">
          <button type="button" class="home-action home-action--primary" @click="goAnalyze">
            <span>📷</span>
            开始检测
          </button>
          <button type="button" class="home-action home-action--soft" @click="goMealPlan">
            <span>🥗</span>
            去配餐
          </button>
        </div>

        <div class="home-service-row">
          <span class="home-service-chip">
            OCR：{{ data?.service_status.ocr_label || '读取中…' }}
          </span>
          <span class="home-service-chip" :class="data?.service_status.ai_configured ? 'is-ok' : 'is-warn'">
            {{ data?.service_status.ai_configured ? `AI：${data?.service_status.ai_model}` : 'AI：规则模式' }}
          </span>
          <span class="home-service-chip is-muted">知识库 {{ data?.knowledge_stats.total ?? '—' }} 条</span>
        </div>
      </div>

      <div class="home-hero-side">
        <WeatherWidget @change="applyWeather" />
        <div class="home-ai-note">
          <span class="home-ai-label">✨ AI 今日提示</span>
          <p>{{ weatherAdvice }}</p>
        </div>
      </div>
    </section>

    <div v-if="errorMessage" class="notice notice-danger">

      <el-icon><WarningFilled /></el-icon>

      <div>

        仪表盘数据加载失败：{{ errorMessage }}

        <el-button text type="primary" @click="load">重试</el-button>

      </div>

    </div>



    <!-- 家庭健康 KPI -->
    <section class="health-kpi-grid">
      <article class="health-kpi health-kpi--calorie">
        <div class="health-kpi-icon">🔥</div>
        <div class="health-kpi-body">
          <span class="health-kpi-label">今日热量</span>
          <strong class="health-kpi-value">{{ todayCalories }}<em>kcal</em></strong>
          <small class="health-kpi-hint">剩余 {{ remainingCalories }} kcal</small>
        </div>
      </article>

      <article class="health-kpi health-kpi--expiring">
        <div class="health-kpi-icon">🧊</div>
        <div class="health-kpi-body">
          <span class="health-kpi-label">冰箱临期</span>
          <strong class="health-kpi-value">{{ expiringCount }}<em>件</em></strong>
          <small class="health-kpi-hint">建议优先安排食用</small>
        </div>
      </article>

      <article class="health-kpi health-kpi--risk">
        <div class="health-kpi-icon">🛡️</div>
        <div class="health-kpi-body">
          <span class="health-kpi-label">风险拦截</span>
          <strong class="health-kpi-value">{{ riskBlocked }}<em>次</em></strong>
          <small class="health-kpi-hint">拍照识别中需警惕的食品</small>
        </div>
      </article>

      <article class="health-kpi health-kpi--family">
        <div class="health-kpi-icon">👨‍👩‍👧</div>
        <div class="health-kpi-body">
          <span class="health-kpi-label">家庭共享</span>
          <strong class="health-kpi-value">{{ familyCount }}<em>人</em></strong>
          <small class="health-kpi-hint">{{ familyInfo?.family.name || '家庭健康档案' }}</small>
        </div>
      </article>
    </section>

    <!-- 空状态：首次使用引导 -->

    <section v-if="isEmpty && !loading" class="card section onboard">

      <div class="onboard-head">

        <div>

          <h2 class="onboard-title">第一次使用？跟着 5 步完成一次完整分析</h2>

          <p class="onboard-sub">整个流程约 1-2 分钟，所有结果都会保存在服务器，可跨设备查看。</p>

        </div>

        <el-button type="primary" size="large" @click="goAnalyze">

          <el-icon><Camera /></el-icon>

          开始第一次检测

        </el-button>

      </div>

      <ol class="steps">

        <li v-for="(step, index) in data?.onboarding.steps || []" :key="step.title">

          <span class="step-no">{{ index + 1 }}</span>

          <div>

            <div class="step-title">{{ step.title }}</div>

            <div class="step-desc">{{ step.description }}</div>

          </div>

        </li>

      </ol>

    </section>



    <!-- 图表区 -->

    <section class="chart-grid section">

      <div class="card chart-card">

        <div class="card-title">

          <h3>近 14 天检测活跃趋势</h3>

          <span class="hint">每日 AI 分析 / 检测次数</span>

        </div>

        <ChartCard

          :option="trendOption"

          height="250px"

          :empty="loading || (data?.trend || []).every((item) => item.count === 0)"

          empty-text="还没有分析记录，完成第一次检测后这里会出现趋势"

        />

      </div>

      <div class="card chart-card">

        <div class="card-title">

          <h3>近期食品健康度</h3>

          <span class="hint">按健康评分分层</span>

        </div>

        <ChartCard

          :option="checkPieOption"

          height="250px"

          :empty="loading || !hasCheckData"

          empty-text="暂无核查结果"

        />

      </div>

    </section>



    <section class="grid grid-2 section">

      <div class="card">

        <div class="card-title">

          <h3>高频摄入配料 Top 8</h3>

          <span class="hint">已排除菜品，仅统计配料/食材</span>

        </div>

        <ChartCard

          :option="topOption"

          :height="hasTopData ? `${Math.max(200, topIngredientItems.length * 46)}px` : '200px'"

          :empty="loading || !hasTopData"

          empty-text="暂无配料数据"

        />

      </div>

      <div class="card">

        <div class="card-title">

          <h3>健康核查统计</h3>

          <span class="hint">全部记录累计</span>

        </div>

        <div class="mini-stats">

          <div class="mini-stat">

            <span class="mini-value">{{ healthyCount }}</span>

            <span class="mini-label">健康优选</span>

          </div>

          <div class="mini-stat">

            <span class="mini-value">{{ generalCount }}</span>

            <span class="mini-label">中规中矩</span>

          </div>

          <div class="mini-stat danger">

            <span class="mini-value">{{ riskCount }}</span>

            <span class="mini-label">风险预警</span>

          </div>

        </div>

        <div class="divider" />

        <div class="knowledge-mini">

          <div class="row-between">

            <span class="text-small text-muted">知识库条目</span>

            <strong>{{ data?.knowledge_stats.total ?? '—' }} 条</strong>

          </div>

          <div class="row-between">

            <span class="text-small text-muted">已核对 / 待核验</span>

            <span class="text-small">{{ data?.knowledge_stats.verified ?? 0 }} / {{ data?.knowledge_stats.pending ?? 0 }}</span>

          </div>

          <div class="row-between">

            <span class="text-small text-muted">AI 引用来源次数</span>

            <span class="text-small">{{ totals?.knowledge_citations ?? 0 }}</span>

          </div>

          <el-button text type="primary" class="know-link" @click="router.push({ name: 'knowledge' })">

            打开知识库 →

          </el-button>

        </div>

      </div>

    </section>



    <!-- 最近记录 -->
    <section class="card section recent-section">
      <div class="card-title">
        <div>
          <h3>最近记录</h3>
          <span class="hint">每一次检测，都是更懂自己的一步</span>
        </div>
        <el-button text type="primary" @click="router.push({ name: 'history' })">查看全部 →</el-button>
      </div>

      <div v-if="loading" class="loading-block" style="height: 140px" />
      <EmptyState
        v-else-if="!recentRecords.length"
        icon="Tickets"
        title="还没有分析记录"
        description="上传一张食品包装照片，系统会自动识别并生成分析结果。"
        action-text="去上传第一张照片"
        @action="goAnalyze"
      />
      <div v-else class="recent-list">
        <button
          v-for="record in recentRecords"
          :key="record.id"
          type="button"
          class="recent-item"
          @click="openRecord(record)"
        >
          <div class="recent-thumb">{{ recordEmoji(record) }}</div>
          <div class="recent-main">
            <div class="recent-name">
              {{ record.food_name || '未命名食品' }}
              <span class="record-status" :class="recordCheckClass(record)">
                {{ recordCheckLabel(record) }}
              </span>
            </div>
            <div class="recent-meta">
              <span>{{ formatRelative(record.created_at) }}</span>
              <span>·</span>
              <span>{{ record.status_label }}</span>
              <span v-if="record.owner_name">· {{ record.owner_name }}</span>
              <span>{{ record.ingredient_count }} 种配料</span>
              <span v-if="record.ocr_provider">· {{ record.ocr_provider === 'local_rapidocr' ? '本地 OCR' : '视觉模型' }}</span>
            </div>
          </div>
          <el-icon class="recent-arrow"><ArrowRight /></el-icon>
        </button>
      </div>
    </section>

    <!-- 推荐知识 -->

    <section class="card section">

      <div class="card-title">

        <h3>先读这几条</h3>

        <span class="hint">每一条都标注了来源与核验状态</span>

      </div>

      <div class="knowledge-grid">

        <button

          v-for="entry in data?.featured_knowledge || []"

          :key="entry.id"

          type="button"

          class="knowledge-card"

          @click="openKnowledge(entry.id)"

        >

          <div class="knowledge-top">

            <span class="chip">{{ entry.category_label }}</span>

            <span class="chip" :class="entry.verification_status === 'verified' ? 'chip-ok' : 'chip-warn'">

              {{ entry.verification_status === 'verified' ? '已核对' : '待核验' }}

            </span>

          </div>

          <div class="knowledge-title">{{ entry.title }}</div>

          <p class="knowledge-summary">{{ entry.summary }}</p>

          <div class="knowledge-source">{{ entry.source_name }}</div>

        </button>

      </div>

    </section>



    <p class="footer-disclaimer">

      智膳 AI 仅对包装上的可见文字做识别、解释与逻辑核查，不进行实验室检测，不能判定食品是否安全或是否合规。

      AI 结果可能存在误差，请以产品实物与官方信息为准。

    </p>

  </div>

</template>



<style scoped>

.section {

  margin-top: 16px;

}



/* Hero */

.hero {

  position: relative;

  display: grid;

  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);

  gap: 20px;

  padding: 26px 28px;

  border-radius: 20px;

  background:

    radial-gradient(circle at 88% 8%, rgba(58, 190, 165, 0.32), transparent 42%),

    linear-gradient(135deg, #0a5147 0%, #0b6a5c 55%, #10897a 100%);

  color: #fff;

  overflow: hidden;

  box-shadow: 0 18px 40px rgba(11, 74, 65, 0.18);

}



.hero::after {

  content: '';

  position: absolute;

  right: -60px;

  bottom: -90px;

  width: 260px;

  height: 260px;

  border-radius: 50%;

  border: 1px solid rgba(255, 255, 255, 0.16);

}



.hero-content {

  position: relative;

  z-index: 1;

  min-width: 0;

}



.hero-badge {

  display: flex;

  align-items: center;

  gap: 10px;

  flex-wrap: wrap;

}



:deep(.hero .brand-name),

:deep(.hero .brand-sub) {

  color: #fff;

}



:deep(.hero .brand-sub) {

  color: rgba(255, 255, 255, 0.7);

}



.hero .brand-name {

  color: #fff;

}



.hero-chip {

  background: rgba(255, 255, 255, 0.16);

  border-color: rgba(255, 255, 255, 0.24);

  color: #eafaf6;

}



.hero-title {

  margin-top: 16px;

  font-size: 30px;

  line-height: 1.3;

  font-weight: 780;

  letter-spacing: -0.4px;

  color: #fff;

}



.hero-sub {

  margin-top: 10px;

  font-size: 14px;

  line-height: 1.8;

  color: rgba(255, 255, 255, 0.84);

  max-width: 640px;

}



.hero-actions {

  margin-top: 18px;

  display: flex;

  gap: 10px;

  flex-wrap: wrap;

}



.hero-actions :deep(.el-button--primary) {

  background: var(--card);

  border-color: #ffffff;

  color: var(--brand-700);

  font-weight: 650;

}



.hero-actions :deep(.el-button--primary:hover) {

  background: #eafaf6;

  border-color: #eafaf6;

  color: var(--brand-700);

}



.hero-actions :deep(.el-button.is-plain) {

  background: rgba(255, 255, 255, 0.12);

  border-color: rgba(255, 255, 255, 0.4);

  color: #ffffff;

}



.hero-actions :deep(.el-button.is-plain:hover) {

  background: rgba(255, 255, 255, 0.2);

  border-color: rgba(255, 255, 255, 0.6);

  color: #fff;

}



.hero-actions :deep(.el-button.is-text) {

  color: rgba(255, 255, 255, 0.86);

}



.hero-status {

  margin-top: 16px;

  display: flex;

  gap: 8px;

  flex-wrap: wrap;

}



.hero-status .chip {

  background: rgba(255, 255, 255, 0.13);

  border-color: rgba(255, 255, 255, 0.2);

  color: rgba(255, 255, 255, 0.9);

  max-width: 100%;

  white-space: normal;

  overflow-wrap: anywhere;

  line-height: 1.6;

  padding: 3px 10px;

}



.hero-side {

  position: relative;

  z-index: 1;

  display: flex;

  align-items: flex-end;

}



.hero-panel {

  width: 100%;

  background: rgba(255, 255, 255, 0.12);

  border: 1px solid rgba(255, 255, 255, 0.2);

  border-radius: 14px;

  padding: 14px 16px;

  backdrop-filter: blur(4px);

}



.panel-title {

  font-size: 12px;

  font-weight: 700;

  color: #cfeee6;

  letter-spacing: 0.6px;

  margin-bottom: 4px;

}



.hero-panel p {

  font-size: 12.5px;

  line-height: 1.75;

  color: rgba(255, 255, 255, 0.86);

}



.panel-small {

  font-size: 11.5px !important;

  color: rgba(255, 255, 255, 0.7) !important;

}



.panel-divider {

  height: 1px;

  background: rgba(255, 255, 255, 0.18);

  margin: 10px 0;

}



.data-notice {

  margin-top: 14px;

}



/* 引导 */

.onboard-head {

  display: flex;

  align-items: flex-start;

  justify-content: space-between;

  gap: 14px;

  flex-wrap: wrap;

}



.onboard-title {

  font-size: 18px;

}



.onboard-sub {

  margin-top: 4px;

  color: var(--muted);

  font-size: 13px;

}



.steps {

  list-style: none;

  padding: 0;

  margin: 18px 0 0;

  display: grid;

  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));

  gap: 12px;

}



.steps li {

  display: flex;

  gap: 10px;

  padding: 12px;

  border: 1px solid var(--border);

  border-radius: 12px;

  background: var(--surface-2);

  min-width: 0;

}



.step-no {

  width: 24px;

  height: 24px;

  border-radius: 50%;

  background: var(--brand);

  color: #fff;

  display: grid;

  place-items: center;

  font-size: 12px;

  font-weight: 700;

  flex: 0 0 auto;

}



.step-title {

  font-size: 13.5px;

  font-weight: 650;

}



.step-desc {

  margin-top: 2px;

  font-size: 12px;

  color: var(--muted);

  line-height: 1.65;

}



/* 迷你统计 */

.mini-stats {

  display: grid;

  grid-template-columns: repeat(3, minmax(0, 1fr));

  gap: 10px;

}



.mini-stat {

  background: var(--surface-2);

  border: 1px solid var(--border);

  border-radius: 12px;

  padding: 12px;

  text-align: center;

}



.mini-value {

  display: block;

  font-size: 22px;

  font-weight: 750;

  color: var(--ok);

  line-height: 1.2;

}



.mini-stat.danger .mini-value {

  color: var(--danger);

}



.mini-label {

  font-size: 11px;

  color: var(--muted);

  line-height: 1.4;

  display: block;

  margin-top: 3px;

}



.knowledge-mini {

  display: flex;

  flex-direction: column;

  gap: 7px;

}



.know-link {

  align-self: flex-start;

  padding-left: 0;

}



/* 最近记录 */

.recent-list {

  display: flex;

  flex-direction: column;

  gap: 8px;

}



.recent-item {

  display: flex;

  align-items: center;

  gap: 12px;

  width: 100%;

  text-align: left;

  padding: 12px 14px;

  border: 1px solid var(--border);

  border-radius: 12px;

  background: var(--card);

  cursor: pointer;

  transition: border-color 0.16s ease, transform 0.16s ease;

}



.recent-item:hover {

  border-color: var(--brand);

  transform: translateY(-1px);

}



.recent-main {

  min-width: 0;

  flex: 1;

}



.recent-name {

  display: flex;

  align-items: center;

  gap: 7px;

  font-size: 14.5px;

  font-weight: 650;

  flex-wrap: wrap;

  overflow-wrap: anywhere;

}



.recent-meta {

  margin-top: 3px;

  font-size: 12px;

  color: var(--muted);

  display: flex;

  gap: 5px;

  flex-wrap: wrap;

}



.recent-arrow {

  color: var(--border-strong);

  flex: 0 0 auto;

}



/* 知识卡片 */

.knowledge-grid {

  display: grid;

  grid-template-columns: repeat(4, minmax(0, 1fr));

  gap: 12px;

}



.knowledge-card {

  text-align: left;

  border: 1px solid var(--border);

  border-radius: 12px;

  background: var(--card);

  padding: 13px;

  cursor: pointer;

  display: flex;

  flex-direction: column;

  gap: 6px;

  min-width: 0;

  transition: border-color 0.16s ease, transform 0.16s ease;

}



.knowledge-card:hover {

  border-color: var(--brand);

  transform: translateY(-1px);

}



.knowledge-top {

  display: flex;

  gap: 5px;

  flex-wrap: wrap;

}



.knowledge-title {

  font-size: 14px;

  font-weight: 700;

  color: var(--text);

  overflow-wrap: anywhere;

}



.knowledge-summary {

  font-size: 12.5px;

  color: var(--muted);

  line-height: 1.7;

  display: -webkit-box;

  -webkit-line-clamp: 3;

  -webkit-box-orient: vertical;

  overflow: hidden;

}



.knowledge-source {

  font-size: 11px;

  color: var(--muted);

  margin-top: auto;

  padding-top: 4px;

  border-top: 1px dashed var(--border);

  overflow-wrap: anywhere;

}



.footer-disclaimer {

  margin-top: 22px;

  font-size: 11.5px;

  color: var(--muted);

  line-height: 1.75;

  text-align: center;

  padding: 0 8px;

}



@media (max-width: 1200px) {

  .knowledge-grid {

    grid-template-columns: repeat(2, minmax(0, 1fr));

  }

}



@media (max-width: 1024px) {

  .hero {

    grid-template-columns: minmax(0, 1fr);

  }

  .hero-side {

    align-items: stretch;

  }

  .hero-title {

    font-size: 25px;

  }

}



@media (max-width: 560px) {

  .hero {

    padding: 20px 16px;

    border-radius: 16px;

  }

  .hero-title {

    font-size: 21px;

    margin-top: 12px;

  }

  .hero-sub {

    font-size: 13px;

  }

  .hero-actions :deep(.el-button) {

    flex: 1 1 auto;

  }

  .hero-actions :deep(.el-button.is-text) {

    flex-basis: 100%;

    justify-content: flex-start;

  }

  .mini-stats {

    grid-template-columns: minmax(0, 1fr);

  }

  .knowledge-grid {

    grid-template-columns: minmax(0, 1fr);

  }

  .onboard-title {

    font-size: 16px;

  }

  .steps {

    grid-template-columns: minmax(0, 1fr);

  }

}


/* ===== C 端健康首页重构 ===== */
.home-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(290px, 0.65fr);
  gap: 22px;
  padding: 26px 28px;
  border: 1px solid #e5efe9;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 16px 38px rgba(31, 91, 66, 0.07);
}

.home-hero-copy {
  min-width: 0;
}

.home-kicker {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: #edf8f1;
  color: #3c7c60;
  font-size: 10.5px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

.home-title {
  margin: 16px 0 0;
  color: #12382a;
  font-size: clamp(25px, 3vw, 34px);
  font-weight: 850;
  line-height: 1.28;
  letter-spacing: -0.045em;
}

.home-sub {
  max-width: 540px;
  margin: 10px 0 0;
  color: #71867c;
  font-size: 13px;
  line-height: 1.8;
}

.home-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
}

.home-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 19px;
  border: 0;
  border-radius: 13px;
  font-family: inherit;
  font-size: 13px;
  font-weight: 750;
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
}

.home-action span {
  font-size: 16px;
}

.home-action--primary {
  background: #0f6b52;
  color: #ffffff;
  box-shadow: 0 9px 22px rgba(15, 107, 82, 0.24);
}

.home-action--primary:hover {
  background: #0b5a45;
  box-shadow: 0 12px 26px rgba(15, 107, 82, 0.3);
  transform: translateY(-1px);
}

.home-action--soft {
  background: #eef8f2;
  color: #2e7558;
}

.home-action--soft:hover {
  background: #e2f3e9;
  transform: translateY(-1px);
}

.home-service-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 17px;
}

.home-service-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: #f5f8f6;
  color: #7b9085;
  font-size: 10px;
}

.home-service-chip.is-ok {
  background: #edf8f1;
  color: #347c5c;
}

.home-service-chip.is-warn {
  background: #fff8eb;
  color: #a47320;
}

.home-service-chip.is-muted {
  color: #9aaba1;
}

.home-hero-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border: 1px solid #edf3ef;
  border-radius: 18px;
  background: linear-gradient(145deg, #f6fbf8 0%, #ffffff 100%);
}

.home-hero-side :deep(.weather-widget) {
  width: 100%;
}

.home-hero-side :deep(.weather-trigger) {
  width: 100%;
  justify-content: flex-start;
  border-color: #dcebe2;
  background: #ffffff;
  box-shadow: none;
}

.home-ai-note {
  padding: 12px 13px;
  border: 1px solid #dcefe3;
  border-radius: 13px;
  background: #eef9f2;
}

.home-ai-label {
  color: #357a5b;
  font-size: 10.5px;
  font-weight: 800;
}

.home-ai-note p {
  margin: 5px 0 0;
  color: #527565;
  font-size: 11.5px;
  line-height: 1.7;
}

/* ===== 健康 KPI ===== */
.health-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.health-kpi {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  min-width: 0;
  padding: 16px 15px;
  border: 1px solid transparent;
  border-radius: 17px;
}

.health-kpi--calorie {
  background: #eff9f3;
  border-color: #dcf0e3;
}

.health-kpi--expiring {
  background: #fff8ec;
  border-color: #f5e5c7;
}

.health-kpi--risk {
  background: #f3f8fb;
  border-color: #dcebf1;
}

.health-kpi--family {
  background: #f8f5fb;
  border-color: #e9e0f0;
}

.health-kpi-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  font-size: 18px;
}

.health-kpi-body {
  min-width: 0;
}

.health-kpi-label {
  display: block;
  color: #72877d;
  font-size: 10.5px;
  font-weight: 650;
}

.health-kpi-value {
  display: block;
  margin-top: 4px;
  color: #173d2e;
  font-size: 25px;
  font-weight: 850;
  letter-spacing: -0.04em;
  line-height: 1.1;
}

.health-kpi-value em {
  margin-left: 3px;
  color: #7c9186;
  font-size: 10.5px;
  font-style: normal;
  font-weight: 600;
  letter-spacing: 0;
}

.health-kpi--expiring .health-kpi-value {
  color: #b97719;
}

.health-kpi-hint {
  display: block;
  margin-top: 5px;
  color: #84978d;
  font-size: 10px;
  line-height: 1.4;
}

/* ===== 图表卡片 ===== */
.chart-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr);
  gap: 16px;
}

.chart-grid > .card,
.chart-card {
  padding: 20px;
  border: 1px solid #e7f0ea;
  border-radius: 20px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(31, 91, 66, 0.045);
}

.chart-card .card-title {
  margin-bottom: 12px;
}

.chart-card .card-title h3 {
  color: #24483a;
}

/* ===== 最近记录卡片化 ===== */
.recent-section {
  padding: 20px;
  border-radius: 20px;
  background: #ffffff;
}

.recent-section .card-title {
  align-items: flex-start;
}

.recent-section .card-title h3 {
  margin-bottom: 3px;
}

.recent-list {
  gap: 9px;
}

.recent-item {
  align-items: center;
  gap: 12px;
  padding: 11px 12px;
  border: 1px solid transparent;
  border-radius: 15px;
  background: #f8faf9;
  transition: background 0.16s ease, transform 0.16s ease;
}

.recent-item:hover {
  background: #f1f8f4;
  border-color: transparent;
  transform: translateY(-1px);
}

.recent-thumb {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  flex: 0 0 46px;
  border-radius: 13px;
  background: linear-gradient(135deg, #eef9f2, #e5f3eb);
  font-size: 23px;
}

.recent-name {
  color: #254638;
  font-size: 13.5px;
}

.recent-meta {
  color: #8b9d94;
  font-size: 10.5px;
}

.record-status {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.3;
}

.record-status.is-warn {
  background: #fff4dc;
  color: #ad761f;
}

.record-status.is-danger {
  background: #fdeeea;
  color: #bd5b4c;
}

.record-status.is-ok {
  background: #eaf7ef;
  color: #357c5b;
}

.record-status.is-muted {
  background: #f0f3f2;
  color: #8a9b93;
}

.recent-arrow {
  color: #a6b8ad;
}

/* ===== 知识推荐横向卡片 ===== */
.knowledge-grid {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 1px 1px 8px;
  scrollbar-width: thin;
  scrollbar-color: #c7d7cf transparent;
}

.knowledge-grid::-webkit-scrollbar {
  height: 7px;
}

.knowledge-grid::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: #c7d7cf;
}

.knowledge-card {
  flex: 0 0 260px;
  min-width: 0;
  border: 1px solid #e8f0eb;
  border-radius: 16px;
  background: #ffffff;
  padding: 14px;
}

.knowledge-card:hover {
  border-color: #b9dcc9;
  background: #fbfefc;
}

@media (max-width: 1120px) {
  .home-hero {
    grid-template-columns: minmax(0, 1fr);
  }

  .home-hero-side {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
    align-items: center;
  }

  .health-kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .home-hero {
    padding: 20px 18px;
    border-radius: 20px;
  }

  .home-hero-side {
    display: flex;
  }

  .home-title {
    font-size: 24px;
  }

  .home-action {
    flex: 1 1 auto;
  }

  .health-kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 9px;
  }

  .health-kpi {
    padding: 13px 12px;
  }

  .health-kpi-value {
    font-size: 21px;
  }

  .recent-section {
    padding: 16px;
  }

  .recent-thumb {
    width: 40px;
    height: 40px;
    flex-basis: 40px;
    font-size: 20px;
  }
}


/* KPI 悬停交互 */
.health-kpi {
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.health-kpi:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 24px rgba(31, 91, 66, 0.10);
}

/* 健康核查统计：投屏时更清晰 */
.knowledge-mini .row-between {
  color: #4b5563;
  font-size: 13px;
}

.knowledge-mini .row-between .text-muted,
.knowledge-mini .row-between .text-small {
  color: #4b5563 !important;
  font-size: 13px !important;
}

.knowledge-mini .row-between strong {
  color: #374151 !important;
  font-size: 13.5px;
}

.knowledge-mini .row-between .text-small:last-child {
  color: #374151 !important;
  font-size: 13px !important;
}

</style>
