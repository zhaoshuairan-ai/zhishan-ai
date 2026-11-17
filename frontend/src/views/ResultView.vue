<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { pantryApi, pipelineApi, recordApi } from '@/api'
import { ApiError } from '@/api/client'
import type { IngredientExplain, IngredientTag, RecordDetail } from '@/api/types'
import AuthImage from '@/components/AuthImage.vue'
import NutritionPanel from '@/components/NutritionPanel.vue'
import CheckPanel from '@/components/CheckPanel.vue'
import HealthPanel from '@/components/HealthPanel.vue'
import SharePoster from '@/components/SharePoster.vue'
import { splitIngredientText } from '@/utils/ingredients'
import { useDietLog } from '@/composables/useDietLog'
import { formatDate, overallTagType, statusTagType } from '@/utils/format'

const route = useRoute()
const router = useRouter()

const detail = ref<RecordDetail | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const reanalyzing = ref(false)
const deleting = ref(false)
const professionalPanels = ref<string[]>([])
const ingredientDrawerOpen = ref(false)
const selectedIngredient = ref<IngredientExplain | null>(null)
const selectedIngredientName = ref('')
const showRawText = ref(false)

const recordId = computed(() => Number(route.params.id))
const record = computed(() => detail.value?.record || null)
const ocr = computed(() => detail.value?.ocr || null)
const fields = computed(() => ocr.value?.fields || {})
const analysis = computed(() => detail.value?.ingredient || null)
const nutrition = computed(() => detail.value?.nutrition || null)
const check = computed(() => detail.value?.check || null)
const health = computed(() => detail.value?.health || null)
const isDemo = computed(() => Boolean(detail.value?.meta.is_demo))

const isDishMode = computed(
  () =>
    record.value?.ocr_provider === 'dish_vision' ||
    ocr.value?.provider === 'dish_vision',
)

const { addMeal } = useDietLog()
const addingDiet = ref(false)

const dishNutrition = computed(() => {
  const items = nutrition.value?.items || []
  const valueOf = (key: string) =>
    Number(items.find((item) => item.key === key)?.value ?? 0)

  let dishRaw: Record<string, any> = {}
  try {
    dishRaw = JSON.parse(String(ocr.value?.raw_text || '')) as Record<string, any>
  } catch {
    dishRaw = {}
  }

  const totals = dishRaw?.dish?.totals || {}
  const weight =
    dishRaw?.recognition?.estimated_weight_g ||
    totals?.weight_g ||
    dishRaw?.dish?.estimated_weight_g ||
    0

  return {
    name: record.value?.food_name || dishRaw?.dish?.dish_name || '今日菜品',
    category: dishRaw?.dish?.category || '家常菜',
    weight_g: Number(weight) || 0,
    calories: Number(totals?.calories ?? valueOf('energy')),
    protein_g: Number(totals?.protein_g ?? valueOf('protein')),
    fat_g: Number(totals?.fat_g ?? valueOf('fat')),
    carbs_g: Number(totals?.carbs_g ?? valueOf('carbohydrate')),
  }
})

const ingredientNames = computed(() => {
  const fromAnalysis = (analysis.value?.ingredients || []).map((item) => item.name).filter(Boolean)
  const fromText = splitIngredientText(fields.value.ingredients_text)
  const names: string[] = []
  for (const name of [...fromAnalysis, ...fromText]) {
    const value = String(name || '').trim()
    if (value && !names.includes(value)) names.push(value)
  }
  return names
})
const topIngredientNames = computed(() => ingredientNames.value.slice(0, 5))
const showAllIngredients = ref(false)
const visibleIngredientNames = computed(() =>
  showAllIngredients.value ? ingredientNames.value : topIngredientNames.value,
)

const isWaterOnly = computed(() => {
  if (analysis.value?.water_only) return true
  const summary = String(analysis.value?.summary || '')
  if (summary.includes('纯净水') || summary.includes('纯饮用水') || summary.includes('饮用水')) return true
  const name = String(record.value?.food_name || '')
  if (/纯净水|饮用水|矿泉水/.test(name) && ingredientNames.value.length <= 2) return true
  return ingredientNames.value.length > 0
    && ingredientNames.value.every((item) => ['水', '饮用水', '纯净水', '矿泉水'].includes(item))
})

const waterHeadline = '✅ 这是纯净水，0卡0脂，无需评估。'
const personalization = computed(() => analysis.value?.personalization || null)
const posterOpen = ref(false)
const addingPantry = ref(false)
const personalizationTitle = computed(() =>
  String(personalization.value?.title || '个性化健康预警').replace(/^⚠️\s*/, ''),
)
const summaryText = computed(() => {
  if (isWaterOnly.value) return waterHeadline
  const raw = String(analysis.value?.summary || health.value?.headline || '已完成标签解读，请查看下方明细。').trim()
  const sentence = raw.split(/[。；]/).find((part) => part.trim()) || raw
  if (sentence.trim().length > 30) return `${sentence.trim().slice(0, 29)}…`
  return `${sentence.trim()}。`
})

const hasNutrition = computed(() =>
  !isWaterOnly.value && Boolean(nutrition.value?.items?.some((item) => item.value !== null)),
)
const hasCheck = computed(() => !isWaterOnly.value && Boolean(check.value?.items?.length))
const hasHealth = computed(() => !isWaterOnly.value && Boolean(health.value?.score !== null || health.value?.findings?.length))
const showIngredientCard = computed(() => !isWaterOnly.value && topIngredientNames.value.length > 0)
const showProfessional = computed(() => !isWaterOnly.value && (hasNutrition.value || hasCheck.value || hasHealth.value))

const score = computed(() => {
  if (isWaterOnly.value) return 100
  return typeof health.value?.score === 'number' ? health.value.score : null
})
const scorePercent = computed(() => (typeof score.value === 'number' ? Math.max(0, Math.min(100, score.value)) : 0))
const grade = computed(() => {
  if (isWaterOnly.value) return 'A'
  return health.value?.grade || 'NA'
})
const gradeLabel = computed(() => {
  if (isWaterOnly.value) return '纯净饮用水'
  return health.value?.grade_label || (score.value === null ? '数据不足' : '健康评分')
})
const scoreTone = computed(() => {
  if (isWaterOnly.value) return 'green'

  const gradeCode = String(grade.value || '').toUpperCase()
  if (gradeCode === 'A') return 'green'
  if (gradeCode === 'B') return 'amber'
  if (gradeCode === 'C' || gradeCode === 'D') return 'red'

  if (scorePercent.value >= 85) return 'green'
  if (scorePercent.value >= 70) return 'amber'
  if (scorePercent.value >= 55) return 'amber'
  return 'red'
})
const scoreRingStyle = computed(() => {
  const color = scoreTone.value === 'green' ? '#2f9b6f'
    : scoreTone.value === 'amber' ? '#d99a2b'
      : '#d9534f'
  return {
    background: `conic-gradient(${color} 0 ${scorePercent.value}%, #edf2ef ${scorePercent.value}% 100%)`,
  }
})

const tags = computed<IngredientTag[]>(() => {
  if (isWaterOnly.value) {
    return [
      { name: '能量', value: '0 kcal', status: 'good', label: '0卡' },
      { name: '脂肪', value: '0 g', status: 'good', label: '0脂' },
      { name: '添加', value: '0', status: 'good', label: '无添加' },
    ]
  }
  if (analysis.value?.tags?.length) return analysis.value.tags.slice(0, 3)
  const items = (nutrition.value?.items || []).filter((item) => item.value !== null)
  const priority = ['sodium', 'fat', 'sugar', 'carbohydrate', 'protein']
  const result: IngredientTag[] = []
  for (const key of priority) {
    const item = items.find((entry) => entry.key === key)
    if (!item) continue
    const value = Number(item.value ?? 0)
    let status = ['high', 'medium', 'low', 'good', 'neutral'].includes(item.status) ? item.status : 'neutral'
    if (key === 'sodium') status = value >= 400 ? 'high' : value >= 200 ? 'medium' : 'good'
    else if (key === 'fat') status = value >= 17.5 ? 'high' : value >= 10 ? 'medium' : 'good'
    else if (key === 'sugar') status = value >= 15 ? 'high' : value >= 5 ? 'medium' : 'good'
    else if (key === 'carbohydrate') status = value >= 60 ? 'high' : value >= 30 ? 'medium' : 'good'
    else if (key === 'protein') status = value >= 10 ? 'good' : 'medium'
    result.push({
      name: item.name,
      value: `${item.value ?? ''}${item.unit || ''}`,
      status,
      label: item.status_label || (status === 'high' ? '偏高' : status === 'good' ? '较优' : '适中'),
    })
    if (result.length >= 3) break
  }
  return result
})

function tagEmoji(status: string): string {
  if (status === 'high') return '🔴'
  if (status === 'medium') return '🟠'
  if (status === 'low' || status === 'good') return '🟢'
  return '⚪'
}

function openIngredient(name: string) {
  selectedIngredientName.value = name
  const found = (analysis.value?.ingredients || []).find((item) => item.name === name)
  selectedIngredient.value = found || null
  ingredientDrawerOpen.value = true
}

function ingredientSummary(item: IngredientExplain | null): string {
  if (!item) return '暂无这条配料的详细解释。'
  const raw = String(item.simple_desc || item.explanation || item.purpose || '').trim()
  if (!raw) return '暂无这条配料的详细解释。'
  const sentence = raw.split(/[。；]/).find((part) => part.trim()) || raw
  return `${sentence.trim()}。`
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    detail.value = await recordApi.detail(recordId.value)
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function reanalyze() {
  reanalyzing.value = true
  try {
    await pipelineApi.reanalyze(recordId.value)
    ElMessage.success('已重新分析，结果已更新')
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '重新分析失败')
  } finally {
    reanalyzing.value = false
  }
}

async function removeRecord() {
  try {
    await ElMessageBox.confirm(
      '删除后该记录、图片与分析结果都会从服务器移除且无法恢复，确定继续吗？',
      '删除记录',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  deleting.value = true
  try {
    await recordApi.remove(recordId.value)
    ElMessage.success('记录已删除')
    router.replace({ name: 'history' })
  } catch (error) {
    ElMessage.error((error as ApiError).message || '删除失败')
  } finally {
    deleting.value = false
  }
}

function askAiNutritionist() {
  const foodName = record.value?.food_name || '这款食品'
  const context = {
    title: foodName,
    ingredients: analysis.value?.ingredients || ingredientNames.value,
    nutrition: nutrition.value?.items || [],
    summary: summaryText.value,
    personalization: personalization.value || null,
  }

  const reasons = personalization.value?.reasons || []
  let prompt = ''
  if (reasons.some((item) => item.includes('减脂')) || String(personalization.value?.message || '').includes('减脂')) {
    prompt = `系统提示我减脂期吃【${foodName}】容易脂肪超标，但我已经吃了几片，今天该怎么补救？`
  } else if (personalization.value?.message) {
    prompt = `系统提示我【${foodName}】${personalization.value.message}，但我已经吃了一些，今天该怎么补救？`
  } else {
    prompt = `系统提示我【${foodName}】${summaryText.value}，但我已经吃了一些，今天该怎么补救？`
  }

  router.push({
    name: 'assistant',
    query: {
      context: JSON.stringify(context),
      prompt,
    },
  })
}

async function addToFamilyPantry() {
  if (!record.value) return
  addingPantry.value = true
  try {
    const expiry = String(fields.value.expiry_date || '').trim().slice(0, 10)
    await pantryApi.create({
      name: record.value.food_name || '检测食品',
      category: 'other',
      quantity: 1,
      unit: '份',
      note: '从分析结果加入家庭库存',
      expires_at: /^\d{4}-\d{2}-\d{2}$/.test(expiry) ? expiry : undefined,
    })
    ElMessageBox.alert('已成功加入家庭库存', '库存已同步', {
      type: 'success',
      confirmButtonText: '知道了',
    }).catch(() => undefined)
  } catch (error) {
    ElMessage.error((error as ApiError).message || '加入库存失败')
  } finally {
    addingPantry.value = false
  }
}

async function addDishToDiet() {
  if (!isDishMode.value) {
    await addToFamilyPantry()
    return
  }

  const meal = dishNutrition.value
  if (!meal.calories) {
    ElMessage.warning('这道菜暂时没有可用的热量数据，请重新分析后再记录')
    return
  }

  addingDiet.value = true
  try {
    addMeal(meal)
    await ElMessageBox.alert(
      `已记录今日热量摄入：${Math.round(meal.calories)} kcal`,
      '今日饮食已记录',
      { type: 'success', confirmButtonText: '知道了' },
    ).catch(() => undefined)
  } finally {
    addingDiet.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page result-page">
    <div v-if="loading" class="loading-wrap">
      <div class="loading-block" style="height: 120px" />
      <div class="loading-block" style="height: 240px; margin-top: 14px" />
    </div>

    <div v-else-if="errorMessage" class="card">
      <div class="empty">
        <h4>结果加载失败</h4>
        <p class="empty-desc">{{ errorMessage }}</p>
        <div class="row" style="justify-content: center; margin-top: 14px">
          <el-button type="primary" @click="load">重试</el-button>
          <el-button @click="router.push({ name: 'history' })">返回历史记录</el-button>
        </div>
      </div>
    </div>

    <template v-else-if="detail && record">
      <header class="result-head">
        <div class="head-main">
          <div class="head-tags">
            <el-tag :type="statusTagType(record.status)" effect="light" size="small">{{ record.status_label }}</el-tag>
            <el-tag v-if="record.overall_check && !isWaterOnly" :type="overallTagType(record.overall_check)" effect="light" size="small">
              {{ check?.overall_label || '已核查' }}
            </el-tag>
            <span v-if="isDemo" class="chip chip-warn"><el-icon><Warning /></el-icon> 演示数据</span>
            <span v-if="analysis" class="chip" :class="analysis.mode === 'ai' ? 'chip-ok' : 'chip-warn'">
              {{ analysis.mode_label }}
            </span>
          </div>
          <p class="result-sub">
            记录 #{{ record.id }} · 上传于 {{ formatDate(record.created_at, true) }}
            <span v-if="record.analyzed_at"> · 分析于 {{ formatDate(record.analyzed_at, true) }}</span>
          </p>
        </div>
        <div class="head-actions">
          <el-button type="primary" @click="posterOpen = true">
            <el-icon><Picture /></el-icon>
            生成海报
          </el-button>
          <el-button @click="router.push({ name: 'report', params: { id: record.id } })">
            <el-icon><Document /></el-icon>
            查看报告
          </el-button>
          <el-button :loading="reanalyzing" @click="reanalyze">
            <el-icon><Refresh /></el-icon>
            重新分析
          </el-button>
          <el-button @click="router.push({ name: 'analyze', query: { record: record.id } })">
            <el-icon><EditPen /></el-icon>
            编辑识别结果
          </el-button>
          <el-button text type="danger" :loading="deleting" @click="removeRecord">
            <el-icon><Delete /></el-icon>
            删除
          </el-button>
        </div>
      </header>

      <div v-if="isDemo" class="notice notice-danger mb">
        <el-icon><WarningFilled /></el-icon>
        <div>本记录包含<strong>演示数据</strong>，用于功能展示，不能作为真实识别结果引用。</div>
      </div>
      <div v-if="detail.meta.mode_notice" class="notice notice-info mb">
        <el-icon><InfoFilled /></el-icon>
        <div>{{ detail.meta.mode_notice }}</div>
      </div>
      <div v-if="record.status !== 'analyzed'" class="notice notice-brand mb">
        <el-icon><InfoFilled /></el-icon>
        <div>
          该记录尚未完成分析。
          <el-button text type="primary" @click="router.push({ name: 'analyze', query: { record: record.id } })">
            继续完成分析 →
          </el-button>
        </div>
      </div>

      <!-- 区块 1：AI 结论卡 -->
      <section class="verdict-card" :class="{ water: isWaterOnly }">
        <div class="verdict-head">
          <div v-if="record.image_url" class="verdict-thumb">
            <AuthImage :src="record.image_url" alt="食品标签缩略图" ratio="1 / 1" />
          </div>
          <div v-else class="verdict-thumb verdict-placeholder">🥫</div>

          <div class="verdict-title">
            <span class="verdict-kicker">AI 结论 · 首屏速读</span>
            <h1 class="wrap-anywhere">{{ record.food_name || '未命名食品' }}</h1>
            <p class="verdict-meta">
              {{ analysis?.mode_label || '待分析' }}
              <span v-if="analysis?.model"> · {{ analysis.model }}</span>
            </p>
          </div>

          <div class="score-wrap" :class="scoreTone">
            <div class="score-ring" :style="scoreRingStyle">
              <div class="score-inner">
                <strong>{{ score === null ? '—' : score }}</strong>
                <span>{{ score === null ? '未评分' : '分' }}</span>
              </div>
            </div>
            <div class="score-caption">
              <b>{{ grade === 'NA' ? '数据不足' : `${grade} 级` }}</b>
              <span>{{ gradeLabel }}</span>
            </div>
          </div>
        </div>

        <p class="verdict-summary" :class="{ water: isWaterOnly }">{{ summaryText }}</p>

        <div
          v-if="personalization && personalization.level !== 'none'"
          class="personalization-alert"
          :class="personalization.level"
        >
          <strong>⚠️ {{ personalizationTitle }}</strong>
          <p>{{ personalization.message }}</p>
        </div>

        <div v-if="tags.length" class="verdict-tags">
          <span v-for="tag in tags" :key="`${tag.name}-${tag.label}`" class="verdict-tag" :class="tag.status">
            <span>{{ tagEmoji(tag.status) }}</span>
            <b>{{ tag.name }}</b>
            <em>{{ tag.label }}</em>
            <small v-if="tag.value">{{ tag.value }}</small>
          </span>
        </div>

        <div class="verdict-footer">
          <span class="verdict-note">
            {{ isWaterOnly ? '这是包装标签解读，不是实验室检测结论' : '健康分为自建参考模型，不构成医学诊断' }}
          </span>
          <div class="verdict-footer-actions">
            <el-button
              v-if="isDishMode"
              type="success"
              plain
              :loading="addingDiet"
              @click="addDishToDiet"
            >
              🍚 记入今日饮食
            </el-button>
            <el-button
              v-else
              plain
              :loading="addingPantry"
              @click="addToFamilyPantry"
            >
              加入家庭库存
            </el-button>
            <el-button type="success" round @click="askAiNutritionist">🤖 问问 AI 营养师</el-button>
          </div>
        </div>
      </section>

      <!-- 区块 2：配料表解析卡 -->
      <section v-if="showIngredientCard" class="card ingredient-card">
        <div class="card-title">
          <h3><el-icon class="title-icon"><Collection /></el-icon> 配料表解析</h3>
          <span class="hint">点击任意配料查看科普解释</span>
        </div>
        <div class="top-ingredients">
          <button
            v-for="(name, index) in visibleIngredientNames"
            :key="`${name}-${index}`"
            type="button"
            class="top-ingredient"
            @click="openIngredient(name)"
          >
            <span class="ingredient-order">{{ index + 1 }}</span>
            <span>{{ name }}</span>
            <el-icon><ArrowRight /></el-icon>
          </button>
          <button
            v-if="ingredientNames.length > 5"
            type="button"
            class="ingredient-expand"
            @click="showAllIngredients = !showAllIngredients"
          >
            {{ showAllIngredients ? '收起' : `+${ingredientNames.length - 5} 查看全部` }}
          </button>
        </div>
        <p class="ingredient-more">
          共 {{ ingredientNames.length }} 项配料{{ showAllIngredients ? '' : ' · 当前显示前 5 项' }}
        </p>
      </section>

      <!-- 区块 3：专业核查卡，默认折叠 -->
      <section v-if="showProfessional" class="card professional-card">
        <el-collapse v-model="professionalPanels">
          <el-collapse-item name="professional">
            <template #title>
              <span class="professional-title">⚙️ 查看国家标签合规核查与营养明细</span>
            </template>
            <div class="professional-body">
              <section v-if="hasNutrition" class="professional-section">
                <h4>营养明细</h4>
                <NutritionPanel
                  :nutrition="nutrition"
                  :notes="analysis?.nutrition_notes || []"
                  :notes-label="analysis?.mode_label"
                />
              </section>
              <section v-if="hasCheck" class="professional-section">
                <h4>国家标签辅助核查</h4>
                <CheckPanel :check="check" />
              </section>
              <section v-if="hasHealth" class="professional-section">
                <h4>健康评估明细</h4>
                <HealthPanel :health="health" />
              </section>
              <el-empty v-if="!hasNutrition && !hasCheck && !hasHealth" description="暂无可展开的专业核查明细" />
            </div>
          </el-collapse-item>

          <el-collapse-item v-if="ocr?.raw_text || ocr?.corrected_text" name="raw">
            <template #title><span class="professional-title">📄 原始 OCR 记录与透明度</span></template>
            <div class="raw-box">
              <div class="raw-title">原始 OCR 文本（未修改）</div>
              <pre class="raw-text">{{ ocr?.raw_text || '（无）' }}</pre>
              <div class="raw-title">校正后的标签文本</div>
              <pre class="raw-text">{{ ocr?.corrected_text || '（无）' }}</pre>
              <div class="transparency">
                <div class="trans-row"><span>OCR 引擎</span><span>{{ ocr?.provider_label || '—' }}</span></div>
                <div class="trans-row"><span>识别状态</span><span>{{ ocr?.status === 'success' ? '成功' : ocr?.status === 'partial' ? '部分识别' : '失败' }}</span></div>
                <div class="trans-row"><span>规则集</span><span>{{ detail.meta.ruleset_version }}</span></div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </section>

      <p v-if="detail.meta.disclaimer" class="final-disclaimer">{{ detail.meta.disclaimer }}</p>

      <el-drawer v-model="ingredientDrawerOpen" :title="selectedIngredient?.name || selectedIngredientName" size="min(94vw, 520px)">
        <div v-if="selectedIngredient" class="ingredient-detail">
          <div class="ingredient-detail-tags">
            <el-tag v-if="selectedIngredient.is_ai_generated" size="small" type="warning" effect="light">
              ⚠️ AI常识推断，待官方核实
            </el-tag>
            <el-tag v-else size="small" type="success" effect="light">权威国标库</el-tag>
            <el-tag size="small" effect="plain">{{ selectedIngredient.category || '未分类' }}</el-tag>
            <el-tag v-if="selectedIngredient.role" size="small" type="info" effect="plain">{{ selectedIngredient.role }}</el-tag>
          </div>
          <p class="ingredient-simple">{{ ingredientSummary(selectedIngredient) }}</p>
          <div v-if="selectedIngredient.explanation" class="ingredient-block">
            <h4>进一步说明</h4>
            <p>{{ selectedIngredient.explanation }}</p>
          </div>
          <div v-if="selectedIngredient.caution" class="ingredient-caution">
            ⚠️ {{ selectedIngredient.caution }}
          </div>
          <p class="ingredient-source">依据：{{ selectedIngredient.evidence || 'unverified' }}</p>
        </div>
        <div v-else class="ingredient-detail">
          <p class="ingredient-simple">这条配料暂未收录详细科普说明，建议结合包装原文和官方资料核对。</p>
        </div>
      </el-drawer>

      <SharePoster
        v-if="record"
        v-model="posterOpen"
        :food-name="record.food_name"
        :score="score"
        :grade="grade"
        :grade-label="gradeLabel"
        :summary="summaryText"
        :warning="personalization"
        :tags="tags"
      />
    </template>
  </div>
</template>

<style scoped>
.result-page {
  padding-bottom: 72px;
}

.loading-wrap {
  padding-top: 8px;
}

.result-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 17px 20px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: var(--shadow);
}

.head-main {
  min-width: 0;
  flex: 1 1 320px;
}

.head-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
  align-items: center;
}

.result-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.head-actions {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

.mb {
  margin-top: 11px;
}

.verdict-card {
  margin-top: 14px;
  padding: 22px;
  border: 1px solid #cfe3d8;
  border-radius: 18px;
  background:
    radial-gradient(circle at 96% 3%, rgba(47, 155, 111, 0.12), transparent 32%),
    linear-gradient(135deg, #ffffff 0%, #f7fcf9 100%);
  box-shadow: 0 12px 30px rgba(31, 90, 71, 0.08);
}

.verdict-card.water {
  border-color: #bfe6cb;
  background: linear-gradient(135deg, #f3fcf6 0%, #e8f8ed 100%);
}

.verdict-head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.verdict-thumb {
  flex: none;
  width: 72px;
  height: 72px;
  border-radius: 15px;
  overflow: hidden;
  border: 1px solid #dcebe2;
  background: #f3f8f5;
}

.verdict-thumb :deep(.auth-image) {
  width: 72px;
  height: 72px;
  aspect-ratio: auto !important;
}

.verdict-placeholder {
  display: grid;
  place-items: center;
  font-size: 30px;
}

.verdict-title {
  flex: 1;
  min-width: 0;
}

.verdict-kicker {
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: #6b8b7c;
}

.verdict-title h1 {
  margin: 4px 0 3px;
  font-size: 24px;
  line-height: 1.3;
  color: #173d30;
}

.verdict-meta {
  margin: 0;
  color: #789087;
  font-size: 11.5px;
}

.score-wrap {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}

.score-ring {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  position: relative;
}

.score-ring::after {
  content: '';
  position: absolute;
  inset: 7px;
  border-radius: 50%;
  background: #fff;
}

.score-inner {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1;
}

.score-inner strong {
  font-size: 25px;
  color: #284f3d;
}

.score-inner span {
  margin-top: 3px;
  font-size: 9px;
  color: #8a9e93;
}

.score-caption {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}

.score-caption b {
  font-size: 11.5px;
  color: #355c4c;
}

.score-caption span {
  font-size: 9.5px;
  color: #8a9e93;
}

.verdict-summary {
  margin: 18px 0 13px;
  font-size: 19px;
  line-height: 1.65;
  font-weight: 650;
  color: #234b39;
}

.verdict-summary.water {
  color: #1f7a4f;
  font-size: 21px;
}

.personalization-alert {
  margin: 0 0 13px;
  padding: 11px 13px;
  border: 1px solid #f2c8bc;
  border-radius: 10px;
  background: #fff3f0;
  color: #a74432;
}

.personalization-alert.warning {
  border-color: #f0d7a5;
  background: #fffaf0;
  color: #946b1d;
}

.personalization-alert.danger {
  border-color: #f0b9ad;
  background: #ffefeb;
  color: #a23c2d;
}

.personalization-alert strong {
  display: block;
  margin-bottom: 3px;
  font-size: 12.5px;
}

.personalization-alert p {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
}

.verdict-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.verdict-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 9px;
  border-radius: 999px;
  border: 1px solid #e0ebe4;
  background: #f7fbf8;
  font-size: 11px;
  color: #5f786b;
}

.verdict-tag b {
  font-weight: 650;
}

.verdict-tag em {
  font-style: normal;
  font-weight: 700;
}

.verdict-tag small {
  color: #96a99e;
}

.verdict-tag.high {
  border-color: #f2c6bd;
  background: #fff5f2;
  color: #b14e39;
}

.verdict-tag.medium {
  border-color: #f0d7a5;
  background: #fffaf0;
  color: #9d711c;
}

.verdict-tag.good,
.verdict-tag.low {
  border-color: #bfe3cb;
  background: #f3fbf5;
  color: #2d7a52;
}

.verdict-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.verdict-footer {
  margin-top: 16px;
  padding-top: 13px;
  border-top: 1px solid #edf3ef;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.verdict-note {
  font-size: 10.5px;
  color: #8a9e93;
}

.ingredient-card,
.professional-card {
  margin-top: 14px;
}

.ingredient-card .card-title {
  margin-bottom: 12px;
}

.top-ingredients {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.top-ingredient {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 11px;
  border: 1px solid #d9e9df;
  border-radius: 10px;
  background: #f8fcf9;
  color: #355c4c;
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.top-ingredient:hover {
  border-color: #86bea2;
  background: #eff9f3;
}

.ingredient-order {
  display: inline-grid;
  place-items: center;
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: #e4f2e9;
  color: #2d7a5e;
  font-size: 9px;
}

.top-ingredient .el-icon {
  color: #91a99b;
  font-size: 11px;
}

.ingredient-expand {
  display: inline-flex;
  align-items: center;
  padding: 8px 11px;
  border: 1px solid #e1e8e4;
  border-radius: 10px;
  background: #f5f7f6;
  color: #7b8d84;
  font-size: 12px;
  cursor: pointer;
}

.ingredient-expand:hover {
  border-color: #b9cfc1;
  color: #3f6b55;
}

.ingredient-more {
  margin: 10px 0 0;
  color: #8a9e93;
  font-size: 11px;
}

.professional-card {
  padding: 0 18px;
}

.professional-card :deep(.el-collapse) {
  border-top: 0;
  border-bottom: 0;
}

.professional-card :deep(.el-collapse-item__header) {
  height: 52px;
  font-size: 13px;
  color: #355c4c;
  background: transparent;
  border-bottom: 1px solid #edf2ef;
}

.professional-title {
  font-weight: 650;
}

.professional-body {
  padding: 4px 0 18px;
}

.professional-section {
  padding: 14px 0;
  border-bottom: 1px dashed #e5eee8;
}

.professional-section:last-child {
  border-bottom: 0;
}

.professional-section h4 {
  margin: 0 0 8px;
  color: #355c4c;
  font-size: 13px;
}

.raw-box {
  padding: 4px 0 16px;
}

.raw-title {
  font-size: 11.5px;
  color: var(--muted);
  margin: 10px 0 4px;
}

.raw-text {
  max-height: 220px;
  overflow: auto;
  margin: 0;
  padding: 12px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-family: 'Cascadia Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.transparency {
  margin-top: 10px;
  display: grid;
  gap: 4px;
}

.trans-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 11.5px;
  color: var(--muted);
}

.final-disclaimer {
  margin: 13px 4px 0;
  color: #9aaca3;
  font-size: 10.5px;
  line-height: 1.7;
}

.ingredient-detail {
  padding: 4px 2px;
}

.ingredient-detail-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.ingredient-simple {
  margin: 0 0 14px;
  color: #294c3c;
  font-size: 15px;
  line-height: 1.8;
}

.ingredient-block h4 {
  margin: 0 0 5px;
  color: #4d6d5e;
  font-size: 12px;
}

.ingredient-block p {
  margin: 0;
  color: #5d7568;
  font-size: 13px;
  line-height: 1.8;
}

.ingredient-caution {
  margin-top: 14px;
  padding: 10px;
  border-radius: 8px;
  background: #fff8ec;
  color: #8a621d;
  font-size: 12px;
  line-height: 1.7;
}

.ingredient-source {
  margin: 16px 0 0;
  color: #9aaca3;
  font-size: 10.5px;
}

.notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.7;
}

@media (max-width: 720px) {
  .verdict-head {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .verdict-title {
    flex: 1 1 150px;
  }

  .score-wrap {
    margin-left: auto;
  }

  .verdict-summary {
    font-size: 17px;
  }

  .verdict-footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .verdict-footer .el-button {
    width: 100%;
  }
}

.score-wrap.red .score-caption b {
  color: #bf4a43;
}

.score-wrap.amber .score-caption b {
  color: #a8771d;
}

.score-wrap.green .score-caption b {
  color: #2f7d5e;
}

</style>
