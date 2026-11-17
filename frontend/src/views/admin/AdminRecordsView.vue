<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type AdminRecordDetail, type AdminRecordItem, type FeedbackItem } from '@/api/admin'
import { ApiError } from '@/api/client'
import { useBreakpoint } from '@/composables/useBreakpoint'

const { isMobile } = useBreakpoint()
const loading = ref(false)
const errorMessage = ref('')
const items = ref<AdminRecordItem[]>([])
const page = ref(1)
const filters = reactive({ q: '', status: '' })

const DISPLAY_PAGE_SIZE = 20
const HIDDEN_FOOD_NAMES = new Set(['清蒸鲈鱼', '未命名食品'])

const cleanedItems = computed(() => {
  const seen = new Set<string>()

  return [...items.value]
    .filter((record) => {
      const name = String(
        record.food_name || record.food_name_raw || '',
      ).trim()

      if (!name) return false
      if (HIDDEN_FOOD_NAMES.has(name)) return false

      const key = name.toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .sort((a, b) => {
      const timeA = Date.parse(a.created_at || '') || 0
      const timeB = Date.parse(b.created_at || '') || 0
      return timeB - timeA || b.id - a.id
    })
})

const total = computed(() => cleanedItems.value.length)
const pages = computed(() =>
  Math.max(1, Math.ceil(total.value / DISPLAY_PAGE_SIZE)),
)
const sequenceStart = computed(
  () => (page.value - 1) * DISPLAY_PAGE_SIZE,
)

const visibleItems = computed(() =>
  cleanedItems.value.slice(
    sequenceStart.value,
    sequenceStart.value + DISPLAY_PAGE_SIZE,
  ),
)

function recordCode(
  record: { created_at?: string | null },
  sequence: number,
) {
  const date = String(record.created_at || '')
    .slice(0, 10)
    .replace(/-/g, '')
  return `REC-${date || '00000000'}-${String(sequence).padStart(3, '0')}`
}

function businessCode(
  record: { id: number; created_at?: string | null },
) {
  const index = cleanedItems.value.findIndex(
    (item) => item.id === record.id,
  )
  return recordCode(record, index >= 0 ? index + 1 : 1)
}

const drawerOpen = ref(false)
const detailLoading = ref(false)
const detail = ref<AdminRecordDetail | null>(null)
const noteContent = ref('')
const savingNote = ref(false)

const reviewOpen = ref(false)
const reviewLoading = ref(false)
const reviewSaving = ref(false)
const reviewDetail = ref<AdminRecordDetail | null>(null)
const reviewImageUrl = ref('')
const detailImageUrl = ref('')
const reviewForm = reactive({
  food_name: '',
  brand: '',
  summary: '',
  overall_check: 'needs_review' as
    | 'none_found'
    | 'needs_review'
    | 'suspected',
  ocr_text: '',
  ingredient_summary: '',
})

const checkLabels: Record<string, string> = {
  none_found: '正常放行',
  needs_review: '需人工介入',
  suspected: '疑似风险',
}

function checkLabel(value: string | null | undefined) {
  return checkLabels[value || ''] || '待核查'
}

function splitOcrNutrition(value: unknown): string[] {
  return String(value || '')
    .split(/[、,，;；|]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function noteText(record: AdminRecordItem) {
  if (record.status === 'reviewed') return '已修改配料表'
  if (record.status === 'pending_review') return 'AI置信度低'
  if (record.overall_check === 'suspected') return '疑似风险待复核'
  if (record.overall_check === 'needs_review') return 'AI置信度低'
  if (record.status === 'analyzed') return 'AI自动核验'
  if (record.status === 'failed') return '处理失败待复核'
  return record.note_count ? `${record.note_count} 条备注` : '待处理'
}

function checkTagType(value: string | null | undefined) {
  if (value === 'none_found') return 'success'
  if (value === 'suspected') return 'danger'
  if (value === 'needs_review') return 'warning'
  return 'info'
}

function statusTagType(status: string) {
  if (status === 'analyzed') return 'success'
  if (status === 'pending_review') return 'warning'
  if (status === 'reviewed') return 'primary'
  if (status === 'failed') return 'danger'
  return 'info'
}

function reviewStatusLabel() {
  const record = reviewDetail.value?.record
  if (!record) return ''

  if (record.status === 'reviewed') return '已人工修正'
  if (record.overall_check === 'suspected') return '疑似风险'
  if (
    record.status === 'pending_review' ||
    record.overall_check === 'needs_review'
  ) {
    return '待复核'
  }
  return record.status_label
}

function clearReviewImage() {
  if (reviewImageUrl.value) {
    URL.revokeObjectURL(reviewImageUrl.value)
    reviewImageUrl.value = ''
  }
}

function clearDetailImage() {
  if (detailImageUrl.value) {
    URL.revokeObjectURL(detailImageUrl.value)
    detailImageUrl.value = ''
  }
}

async function openReview(record: AdminRecordItem) {
  reviewOpen.value = true
  reviewLoading.value = true
  reviewDetail.value = null
  clearReviewImage()

  try {
    const data = await adminApi.recordDetail(record.id)
    reviewDetail.value = data

    reviewForm.food_name = data.record.food_name || ''
    reviewForm.brand = data.record.brand || ''
    reviewForm.summary = data.record.summary || ''
    reviewForm.ocr_text =
      data.ocr?.corrected_text || data.ocr?.raw_text || ''
    reviewForm.ingredient_summary = data.ingredient?.summary || ''

    const overall = data.check?.overall || data.record.overall_check
    reviewForm.overall_check =
      overall === 'none_found' || overall === 'suspected'
        ? overall
        : 'needs_review'

    if (data.record.image_url) {
      try {
        const blob = await adminApi.recordImage(record.id)
        reviewImageUrl.value = URL.createObjectURL(blob)
      } catch {
        reviewImageUrl.value = ''
      }
    }
  } catch (error) {
    ElMessage.error((error as ApiError).message || '加载审核详情失败')
    reviewOpen.value = false
  } finally {
    reviewLoading.value = false
  }
}

async function saveReview() {
  if (!reviewDetail.value) return
  if (!reviewForm.food_name.trim()) {
    ElMessage.warning('食品名称不能为空')
    return
  }

  reviewSaving.value = true
  try {
    await adminApi.reviewRecord(reviewDetail.value.record.id, {
      food_name: reviewForm.food_name.trim(),
      brand: reviewForm.brand.trim(),
      summary: reviewForm.summary.trim(),
      overall_check: reviewForm.overall_check,
      ocr_text: reviewForm.ocr_text.trim(),
      ingredient_summary: reviewForm.ingredient_summary.trim(),
    })

    ElMessage.success('✅ 审核结果已保存，状态已更新为已人工修正')
    reviewOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '审核保存失败')
  } finally {
    reviewSaving.value = false
  }
}

onBeforeUnmount(clearReviewImage)

const feedbackItems = computed<FeedbackItem[]>(() => detail.value?.feedback || [])
async function load(reset = false) {
  if (reset) page.value = 1
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await adminApi.records({
      q: filters.q.trim(),
      status: filters.status,
      page: 1,
      per_page: 100,
    })
    items.value = data.items
    if (page.value > pages.value) page.value = pages.value
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '加载失败'
  } finally {
    loading.value = false
  }
}

function changePage(nextPage: number) {
  page.value = nextPage
}

async function openDetail(record: AdminRecordItem) {
  drawerOpen.value = true
  detailLoading.value = true
  detail.value = null
  noteContent.value = ''
  clearDetailImage()

  try {
    detail.value = await adminApi.recordDetail(record.id)

    try {
      const blob = await adminApi.recordImage(record.id)
      detailImageUrl.value = URL.createObjectURL(blob)
    } catch {
      detailImageUrl.value = ''
    }
  } catch (error) {
    ElMessage.error((error as ApiError).message || '加载详情失败')
    drawerOpen.value = false
  } finally {
    detailLoading.value = false
  }
}

async function saveNote() {
  if (!detail.value) return
  if (noteContent.value.trim().length < 2) {
    ElMessage.warning('备注至少 2 个字符')
    return
  }
  savingNote.value = true
  try {
    await adminApi.addNote(detail.value.record.id, noteContent.value.trim())
    ElMessage.success('备注已保存')
    detail.value = await adminApi.recordDetail(detail.value.record.id)
    noteContent.value = ''
  } catch (error) {
    ElMessage.error((error as ApiError).message || '保存失败')
  } finally {
    savingNote.value = false
  }
}

async function removeRecord(record: { id: number; food_name: string }) {
  try {
    await ElMessageBox.confirm(
      `确认删除记录 #${record.id}「${record.food_name}」？删除后记录、OCR 与分析结果都将无法恢复。`,
      '删除分析记录',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'error' }
    )
  } catch {
    return
  }
  try {
    await adminApi.deleteRecord(record.id)
    ElMessage.success('记录已删除')
    drawerOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '删除失败')
  }
}

async function resolveFeedback(item: FeedbackItem) {
  try {
    const { value } = await ElMessageBox.prompt('填写处理说明（可选）', '处理反馈', {
      confirmButtonText: '标记已处理',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：已联系用户并修正标签识别问题',
    })
    await adminApi.resolveFeedback(item.id, 'resolved', value || '')
    ElMessage.success('反馈已标记为已处理')
    if (detail.value) detail.value = await adminApi.recordDetail(detail.value.record.id)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error((error as ApiError).message || '操作失败')
  }
}

function formatTime(value: string | null) {
  return value ? value.replace('T', ' ').slice(0, 19) : '—'
}

onMounted(() => load())
</script>

<template>
  <div class="admin-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">分析记录</h1>
        <p class="page-sub">查看 OCR、AI 分析、核查依据与复核备注；删除需要二次确认。</p>
      </div>
      <el-button :loading="loading" @click="load()">刷新</el-button>
    </header>

    <div class="filter-bar card">
      <el-input v-model="filters.q" placeholder="搜索食品名称或品牌" clearable @keyup.enter="load(true)" />
      <el-select v-model="filters.status" placeholder="状态">
        <el-option label="全部状态" value="" />
        <el-option label="已上传" value="uploaded" />
        <el-option label="已识别" value="ocr_done" />
        <el-option label="已校正" value="corrected" />
        <el-option label="分析完成" value="analyzed" />
        <el-option label="待复核" value="pending_review" />
        <el-option label="已人工修正" value="reviewed" />
        <el-option label="处理失败" value="failed" />
      </el-select>
      <el-button type="primary" @click="load(true)">查询</el-button>
    </div>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mb" />

    <div v-if="!isMobile()" v-loading="loading" class="card table-card">
      <el-table :data="visibleItems" row-key="id" size="small" stripe>
        <el-table-column label="序号" width="64" align="center">
          <template #default="{ $index }">
            {{ sequenceStart + $index + 1 }}
          </template>
        </el-table-column>

        <el-table-column label="记录编号" width="176">
          <template #default="{ row }">
            <span class="record-code">{{ businessCode(row) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="食品" min-width="150">
          <template #default="{ row }">
            <div class="food-cell">
              <strong>{{ row.food_name }}</strong>
              <small v-if="row.brand">（{{ row.brand }}）</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="所属用户" min-width="100" />
        <el-table-column label="状态" width="112">
          <template #default="{ row }">
            <el-tag
              size="small"
              class="record-status-pill"
              :type="statusTagType(row.status)"
            >
              {{ row.status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="核查" width="126">
          <template #default="{ row }">
            <el-tag
              size="small"
              class="record-check-pill"
              :type="checkTagType(row.overall_check)"
            >
              {{ checkLabel(row.overall_check) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" width="120">
          <template #default="{ row }">{{ noteText(row) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button class="record-action-btn" size="small" text type="warning" @click="openReview(row)">审核</el-button>
            <el-button class="record-action-btn" size="small" text type="primary" @click="openDetail(row)">查看</el-button>
            <el-button class="record-action-btn" size="small" text type="danger" @click="removeRecord(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else v-loading="loading" class="record-cards">
      <div v-for="(record, index) in visibleItems" :key="record.id" class="card record-card">
        <div class="record-head">
          <strong>{{ sequenceStart + index + 1 }}. {{ record.food_name }}</strong>
          <span class="record-code">{{ businessCode(record) }}</span>
          <el-tag size="small" class="record-status-pill" :type="statusTagType(record.status)">
            {{ record.status_label }}
          </el-tag>
        </div>
        <div class="record-meta">
          <span>{{ record.username }} · {{ formatTime(record.created_at) }}</span>
          <span>备注：{{ noteText(record) }}</span>
        </div>
        <div class="record-actions">
          <el-button class="record-action-btn" size="small" plain type="warning" @click="openReview(record)">审核</el-button>
          <el-button class="record-action-btn" size="small" plain type="primary" @click="openDetail(record)">查看详情</el-button>
          <el-button class="record-action-btn" size="small" plain type="danger" @click="removeRecord(record)">删除</el-button>
        </div>
      </div>
      <div v-if="!visibleItems.length && !loading" class="empty-text">没有符合条件的记录</div>
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="prev, pager, next"
        :disabled="loading"
        @current-change="changePage"
      />
      <span class="pager-hint">共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页</span>
    </div>

    <el-drawer v-model="drawerOpen" title="分析记录详情" size="min(94vw, 880px)" class="record-detail-drawer" @closed="clearDetailImage">
      <div v-loading="detailLoading" class="detail-body">
        <template v-if="detail">
          <div class="detail-hero detail-card">
            <div class="detail-thumb">
              <img
                v-if="detailImageUrl"
                :src="detailImageUrl"
                class="detail-thumb-img"
                alt="用户上传的食品标签原图"
              />
              <div v-else class="detail-thumb-placeholder">
                <span>🍽️</span>
                <small>暂无原图</small>
              </div>
            </div>

            <div class="detail-hero-main">
              <div class="detail-head-row">
                <div>
                  <h3>{{ businessCode(detail.record) }} · {{ detail.record.food_name }}</h3>
                  <p>
                    所属用户：{{ detail.owner?.username || '—' }}
                    · 状态：{{ detail.record.status_label }}
                    · 创建：{{ formatTime(detail.record.created_at) }}
                  </p>
                </div>
                <el-button type="danger" plain size="small" @click="removeRecord(detail.record)">删除记录</el-button>
              </div>

              <div class="detail-overview-grid">
                <div class="detail-overview-item">
                  <span>食品名称</span>
                  <strong>{{ detail.record.food_name || '—' }}</strong>
                </div>
                <div class="detail-overview-item">
                  <span>品牌</span>
                  <strong>{{ detail.record.brand || '未填写' }}</strong>
                </div>
                <div class="detail-overview-item">
                  <span>配料数量</span>
                  <strong>{{ detail.ingredient?.ingredients?.length || 0 }} 种</strong>
                </div>
                <div class="detail-overview-item">
                  <span>核查结论</span>
                  <strong>{{ detail.check?.overall_label || detail.record.overall_check || '待核查' }}</strong>
                </div>
              </div>
            </div>
          </div>

          <div class="detail-tabs-row">
            <el-tabs class="detail-tabs">
            <el-tab-pane label="OCR 识别">
              <div class="ocr-data-panel">
                <div class="ocr-fields-grid">
                  <div
                    v-for="(value, key) in detail.ocr?.fields || {}"
                    :key="key"
                    class="ocr-field-card"
                  >
                    <span class="ocr-field-label">
                      {{ detail.ocr?.field_labels?.[key as string] || key }}
                    </span>

                    <div
                      v-if="key === 'nutrition_text' || key === 'ingredients_text'"
                      class="ocr-value-tags"
                    >
                      <span
                        v-for="(item, index) in splitOcrNutrition(value)"
                        :key="`${key}-${index}`"
                        class="ocr-value-tag"
                      >
                        {{ item }}
                      </span>
                    </div>

                    <strong v-else class="ocr-field-value">
                      {{ value || '未识别' }}
                    </strong>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="AI 分析">
              <div v-if="detail.ingredient" class="ai-block detail-card">
                <p class="summary">{{ detail.ingredient.summary }}</p>
                <div class="kv">
                  <span>模式</span><strong>{{ detail.ingredient.mode_label }}</strong>
                  <span>模型</span><strong>{{ detail.ingredient.model || '规则引擎' }}</strong>
                  <span>耗时</span><strong>{{ detail.ingredient.duration_ms }} ms</strong>
                </div>
                <ul class="ingredient-list">
                  <li v-for="item in detail.ingredient.ingredients" :key="item.name">
                    <strong>{{ item.name }}</strong>
                    <span>{{ item.role || item.category }} · {{ item.explanation }}</span>
                  </li>
                </ul>
                <p v-if="!detail.ingredient.ingredients.length" class="empty-text">暂无配料解读</p>
              </div>
              <p v-else class="empty-text">该记录尚未完成 AI 分析</p>
            </el-tab-pane>

            <el-tab-pane label="核查依据">
              <div v-if="detail.check" class="check-block detail-card">
                <p class="summary">整体结论：{{ detail.check.overall_label }}（规则集 {{ detail.check.ruleset_version }}）</p>
                <ul class="check-list">
                  <li v-for="item in detail.check.items" :key="item.rule_id + item.result">
                    <div class="check-head">
                      <strong>{{ item.title }}</strong>
                      <el-tag size="small" :type="item.level === 'suspected' ? 'danger' : item.level === 'review' ? 'warning' : 'success'">
                        {{ item.level_label }}
                      </el-tag>
                    </div>
                    <p>{{ item.result }}</p>
                    <small>依据：{{ item.basis }} · 来源：{{ item.source?.name || '—' }} · 版本 {{ item.rule_version }}</small>
                  </li>
                </ul>
              </div>
              <p v-else class="empty-text">该记录尚未生成核查结果</p>
            </el-tab-pane>

            <el-tab-pane label="营养成分">
              <div v-if="detail.nutrition" class="detail-nutrition-wrap">
                <div class="detail-section-head">
                  <strong>每 100g 营养测算</strong>
                  <span>{{ detail.nutrition.basis_note || 'AI / 人工测算' }}</span>
                </div>

                <div class="detail-grid detail-nutrition-grid">
                  <div
                    v-for="item in detail.nutrition.items"
                    :key="item.key || item.name"
                    class="detail-card nutrient-card"
                  >
                    <span class="nutrient-label">{{ item.name }}</span>
                    <el-tag
                      size="small"
                      effect="plain"
                      class="nutrient-tag"
                      :class="[
                        `nutrient-${item.key || item.name}`,
                        { 'nutrient-key': item.key === 'energy' || item.key === 'protein' },
                      ]"
                    >
                      {{ item.value ?? '—' }} {{ item.unit }}
                    </el-tag>
                    <small v-if="item.nrv_percent != null">
                      NRV {{ item.nrv_percent }}%
                    </small>
                  </div>
                </div>

                <div v-if="detail.nutrition.warnings?.length" class="detail-card detail-warning-card">
                  <span class="detail-card-label">营养提醒</span>
                  <p
                    v-for="(warning, index) in detail.nutrition.warnings"
                    :key="index"
                  >
                    {{ typeof warning === 'string' ? warning : warning.message }}
                  </p>
                </div>
              </div>
              <p v-else class="empty-text">该记录暂无营养成分数据</p>
            </el-tab-pane>

            <el-tab-pane label="复核备注">
              <div class="note-form detail-card">
                <el-input v-model="noteContent" type="textarea" :rows="3" maxlength="1000" show-word-limit placeholder="记录复核结论、联系用户情况或后续处理" />
                <el-button type="primary" :loading="savingNote" @click="saveNote">保存备注</el-button>
              </div>
              <ul v-if="detail.notes.length" class="note-list">
                <li v-for="note in detail.notes" :key="note.id">
                  <div class="note-head">
                    <strong>{{ note.admin_username }}</strong>
                    <time>{{ formatTime(note.created_at) }}</time>
                  </div>
                  <p>{{ note.content }}</p>
                </li>
              </ul>
              <p v-else class="empty-text">暂无复核备注</p>
            </el-tab-pane>

            <el-tab-pane :label="`用户反馈（${feedbackItems.length}）`">
              <ul v-if="feedbackItems.length" class="note-list">
                <li v-for="item in feedbackItems" :key="item.id">
                  <div class="note-head">
                    <strong>用户 #{{ item.user_id }}</strong>
                    <el-tag size="small" :type="item.status === 'open' ? 'warning' : 'success'">{{ item.status_label }}</el-tag>
                  </div>
                  <p>{{ item.content }}</p>
                  <small v-if="item.reply">处理说明：{{ item.reply }}</small>
                  <el-button v-if="item.status === 'open'" size="small" text type="primary" @click="resolveFeedback(item)">
                    标记已处理
                  </el-button>
                </li>
              </ul>
              <p v-else class="empty-text">该记录暂无用户反馈</p>
            </el-tab-pane>
            </el-tabs>

            <div v-if="detail.ocr" class="detail-engine-meta">
              <span>引擎 {{ detail.ocr.provider_label || '—' }}</span>
              <span>耗时 {{ detail.ocr.duration_ms ?? 0 }} ms</span>
              <span>状态 {{ detail.ocr.status || '—' }}</span>
            </div>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>

    <el-drawer
      v-model="reviewOpen"
      title="人工审核"
      size="min(96vw, 980px)"
      class="record-review-drawer"
      @closed="clearReviewImage"
    >
      <div v-loading="reviewLoading" class="review-layout">
        <template v-if="reviewDetail">
          <aside class="review-image-pane">
            <div class="review-pane-title">用户上传原图</div>
            <img
              v-if="reviewImageUrl"
              :src="reviewImageUrl"
              class="review-image"
              alt="用户上传的食品标签原图"
            />
            <div v-else class="review-image-empty">
              该记录暂无关联图片
            </div>
            <p class="review-image-meta">
              {{ reviewDetail.owner?.username || '未知用户' }}
              · {{ formatTime(reviewDetail.record.created_at) }}
            </p>
          </aside>

          <section class="review-data-pane">
            <div class="review-pane-head">
              <div>
                <span class="review-eyebrow">B 端人工复核</span>
                <h3>{{ reviewDetail.record.food_name }}</h3>
              </div>
              <el-tag
                size="small"
                :type="statusTagType(reviewDetail.record.status)"
              >
                {{ reviewStatusLabel() }}
              </el-tag>
            </div>

            <el-form label-position="top" class="review-form">
              <div class="review-form-row">
                <el-form-item label="食品名称">
                  <el-input
                    v-model="reviewForm.food_name"
                    maxlength="120"
                    show-word-limit
                  />
                </el-form-item>
                <el-form-item label="品牌">
                  <el-input
                    v-model="reviewForm.brand"
                    maxlength="120"
                  />
                </el-form-item>
              </div>

              <el-form-item label="AI 分析摘要 / 审核结论">
                <el-input
                  v-model="reviewForm.summary"
                  type="textarea"
                  :rows="3"
                  maxlength="2000"
                  show-word-limit
                />
              </el-form-item>

              <el-form-item label="人工核查结论">
                <el-select
                  v-model="reviewForm.overall_check"
                  class="review-select"
                >
                  <el-option label="正常放行" value="none_found" />
                  <el-option label="需人工介入" value="needs_review" />
                  <el-option label="疑似风险" value="suspected" />
                </el-select>
              </el-form-item>

              <el-form-item label="OCR 原文（可修正）">
                <el-input
                  v-model="reviewForm.ocr_text"
                  type="textarea"
                  :rows="4"
                  maxlength="20000"
                />
              </el-form-item>

              <el-form-item label="配料解读（可修正）">
                <el-input
                  v-model="reviewForm.ingredient_summary"
                  type="textarea"
                  :rows="3"
                  maxlength="2000"
                />
              </el-form-item>
            </el-form>

            <div
              v-if="reviewDetail.ingredient?.ingredients?.length"
              class="review-ingredients"
            >
              <span class="review-pane-title">AI 识别配料</span>
              <div class="review-ingredient-tags">
                <el-tag
                  v-for="item in reviewDetail.ingredient.ingredients"
                  :key="item.name"
                  size="small"
                  effect="plain"
                >
                  {{ item.name }}
                </el-tag>
              </div>
            </div>

            <footer class="review-footer">
              <el-button @click="reviewOpen = false">取消</el-button>
              <el-button
                type="primary"
                :loading="reviewSaving"
                @click="saveReview"
              >
                保存人工修正
              </el-button>
            </footer>
          </section>
        </template>
      </div>
    </el-drawer>

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

.filter-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px;
  margin-bottom: 12px;
}

.filter-bar .el-input {
  flex: 1 1 220px;
}

.filter-bar .el-select {
  width: 150px;
}

.table-card {
  padding: 8px 10px;
}

.food-cell {
  display: flex;
  flex-direction: column;
}

.food-cell small {
  color: var(--muted);
}

.record-cards {
  display: grid;
  gap: 10px;
}

.record-card {
  padding: 12px 14px;
}

.record-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.record-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
  color: var(--muted);
  margin: 6px 0 10px;
}

.record-actions {
  display: flex;
  gap: 8px;
}

.pager {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.pager-hint {
  font-size: 12px;
  color: var(--muted);
}

.detail-body {
  min-height: 200px;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 8px;
}

.detail-head h3 {
  margin: 0 0 4px;
  font-size: 16px;
}

.detail-head p {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

.kv {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
}

.kv strong {
  color: var(--text-1);
  font-weight: 600;
}

.text-block {
  background: var(--surface-2);
  border-radius: 8px;
  padding: 10px;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow: auto;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.kv-item {
  background: var(--surface-2);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
}

.kv-item span {
  color: var(--muted);
}

.summary {
  font-size: 13px;
  line-height: 1.8;
  margin: 0 0 8px;
}

.ingredient-list,
.check-list,
.note-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.ingredient-list li {
  background: var(--surface-2);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12.5px;
}

.ingredient-list span {
  color: var(--muted);
  line-height: 1.6;
}

.check-list li {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 9px 10px;
}

.check-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.check-list p {
  margin: 4px 0;
  font-size: 12.5px;
}

.check-list small {
  color: var(--muted);
  font-size: 11.5px;
  line-height: 1.6;
}

.note-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.note-form .el-button {
  align-self: flex-end;
}

.note-list li {
  background: var(--surface-2);
  border-radius: 8px;
  padding: 9px 11px;
}

.note-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
}

.note-list p {
  margin: 5px 0;
  font-size: 12.5px;
  line-height: 1.7;
}

.note-list small {
  display: block;
  color: var(--muted);
  font-size: 11.5px;
  margin-bottom: 4px;
}

.empty-text {
  color: var(--muted);
  font-size: 13px;
  padding: 16px 0;
  text-align: center;
}

.record-code {
  color: #527064;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.record-head .record-code {
  margin-left: auto;
  font-size: 10px;
}


.review-layout {
  display: grid;
  grid-template-columns: minmax(260px, 0.95fr) minmax(360px, 1.4fr);
  gap: 22px;
  min-height: 520px;
}

.review-image-pane,
.review-data-pane {
  min-width: 0;
}

.review-image-pane {
  padding: 14px;
  border: 1px solid #e4eee8;
  border-radius: 14px;
  background: #f7faf8;
}

.review-pane-title {
  display: block;
  margin-bottom: 10px;
  color: #2b5747;
  font-size: 12px;
  font-weight: 700;
}

.review-image {
  display: block;
  width: 100%;
  max-height: 620px;
  object-fit: contain;
  border-radius: 10px;
  background: #ffffff;
}

.review-image-empty {
  display: grid;
  min-height: 360px;
  place-items: center;
  border: 1px dashed #cddfd6;
  border-radius: 10px;
  background: #fff;
  color: #8aa197;
  font-size: 12.5px;
}

.review-image-meta {
  margin: 10px 0 0;
  color: #7b9489;
  font-size: 11.5px;
}

.review-data-pane {
  display: flex;
  flex-direction: column;
}

.review-pane-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #edf2ef;
}

.review-eyebrow {
  color: #9aafa4;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.review-pane-head h3 {
  margin: 5px 0 0;
  color: #173e32;
  font-size: 19px;
}

.review-form {
  margin-top: 14px;
}

.review-form-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.review-select {
  width: 100%;
}

.review-ingredients {
  padding: 10px 12px;
  border-radius: 10px;
  background: #f4f8f6;
}

.review-ingredient-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.review-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: auto;
  padding-top: 16px;
}

.record-status-pill,
.record-check-pill {
  border-radius: 999px;
  font-weight: 650;
}

.record-action-btn + .record-action-btn {
  margin-left: 16px;
}

@media (max-width: 900px) {
  .review-layout {
    grid-template-columns: 1fr;
  }

  .review-image {
    max-height: 320px;
  }

  .review-image-empty {
    min-height: 220px;
  }
}

@media (max-width: 767px) {
  .review-form-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 767px) {
  .record-head {
    flex-wrap: wrap;
  }

  .record-head .record-code {
    width: 100%;
    margin-left: 0;
  }
}


/* ---------- SaaS 审核 / 详情抽屉精修 ---------- */
.record-review-drawer :deep(.el-drawer),
.record-detail-drawer :deep(.el-drawer) {
  border-radius: 12px;
  background: #f7f9fc;
  overflow: hidden;
}

.record-review-drawer :deep(.el-drawer__header),
.record-detail-drawer :deep(.el-drawer__header) {
  margin: 0;
  padding: 22px 24px 16px;
  background: #f7f9fc;
  color: #1d2b3a;
  font-weight: 700;
}

.record-review-drawer :deep(.el-drawer__body),
.record-detail-drawer :deep(.el-drawer__body) {
  padding: 24px;
  background: #f7f9fc;
}

.review-layout {
  gap: 20px;
}

.review-image-pane {
  padding: 16px;
  border: 1px solid #e3eaf2;
  border-radius: 12px;
  background: #eff2f6;
}

.review-pane-title {
  color: #516173;
  font-size: 12px;
  letter-spacing: 0.03em;
}

.review-image {
  width: 100%;
  max-height: 560px;
  object-fit: contain;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(31, 45, 61, 0.1);
}

.review-image-empty {
  min-height: 320px;
  border: 1px dashed #cbd6e2;
  border-radius: 10px;
  background: #f8fafc;
  color: #8a99aa;
}

.review-image-meta {
  color: #748396;
}

.review-pane-head {
  border-bottom: 0;
  padding-bottom: 4px;
}

.review-eyebrow {
  color: #8b9aab;
}

.review-pane-head h3 {
  color: #172536;
  font-size: 20px;
}

.review-form {
  padding: 16px;
  border: 1px solid #e6edf4;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(31, 45, 61, 0.04);
}

.review-form :deep(.el-input__wrapper),
.review-form :deep(.el-textarea__inner),
.review-form :deep(.el-select__wrapper) {
  border-radius: 8px;
  background: #f2f5f8;
  box-shadow: none !important;
  border: 1px solid transparent;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.review-form :deep(.el-input__wrapper:hover),
.review-form :deep(.el-textarea__inner:hover),
.review-form :deep(.el-select__wrapper:hover) {
  border-color: #cbd8e5;
}

.review-form :deep(.el-input__wrapper.is-focus),
.review-form :deep(.el-textarea__inner:focus),
.review-form :deep(.el-select__wrapper.is-focused) {
  border-color: #10b981;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1) !important;
}

.review-form :deep(.el-form-item__label) {
  color: #5d6d7f;
  font-size: 12px;
  font-weight: 600;
}

.review-ingredients {
  padding: 14px;
  border: 1px solid #d9f3e7;
  border-radius: 12px;
  background: #f4fdf8;
}

.review-ingredient-tags :deep(.el-tag) {
  border-color: #a7f3d0;
  border-radius: 999px;
  background: #ecfdf5;
  color: #10b981;
  font-weight: 600;
}

.review-footer {
  position: sticky;
  bottom: -24px;
  justify-content: flex-end;
  margin-top: 12px;
  padding: 14px 0 24px;
  background: linear-gradient(180deg, rgba(247, 249, 252, 0), #f7f9fc 32%);
}

.review-footer .el-button--primary {
  min-width: 148px;
}

/* 详情页顶部胶囊 Tab */
.record-detail-drawer :deep(.el-tabs__header) {
  margin: 0 0 16px;
}

.record-detail-drawer :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.record-detail-drawer :deep(.el-tabs__active-bar) {
  display: none;
}

.record-detail-drawer :deep(.el-tabs__item) {
  height: 34px;
  margin-right: 8px;
  padding: 0 15px;
  border: 1px solid #e1e9f1;
  border-radius: 999px;
  background: #ffffff;
  color: #6b7c8f;
  font-size: 12.5px;
  font-weight: 600;
  transition: all 0.18s ease;
}

.record-detail-drawer :deep(.el-tabs__item:hover) {
  border-color: #b8dccc;
  color: #0f6b52;
}

.record-detail-drawer :deep(.el-tabs__item.is-active) {
  border-color: #0f6b52;
  background: #0f6b52;
  color: #ffffff;
}

.detail-body {
  background: transparent;
}

.detail-head.detail-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 16px;
  border: 1px solid #e6edf4;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(31, 45, 61, 0.04);
}

.detail-head h3 {
  color: #172536;
}

.detail-head p {
  color: #7c8b9b;
}

.detail-card {
  padding: 14px;
  border: 1px solid #e6edf4;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(31, 45, 61, 0.04);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-meta-card {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.detail-meta-card span,
.detail-card-label {
  color: #8a99aa;
  font-size: 11.5px;
}

.detail-meta-card strong {
  color: #213549;
  font-size: 13px;
}

.detail-text-card {
  margin-top: 12px;
  background: #f8fafc;
  border-color: #edf2f7;
  color: #425466;
}

.kv-grid.detail-grid {
  margin-top: 12px;
}

.kv-grid .kv-item {
  padding: 12px;
  border: 1px solid #edf2f7;
  border-radius: 10px;
  background: #f8fafc;
}

.kv-grid .kv-item span {
  color: #8a99aa;
  font-size: 11px;
}

.kv-grid .kv-item strong {
  margin-top: 4px;
  color: #213549;
  font-size: 12.5px;
}

.ai-block.detail-card,
.check-block.detail-card {
  padding: 16px;
}

.ingredient-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.ingredient-list li {
  padding: 9px 10px;
  border: 1px solid #d9f3e7;
  border-radius: 9px;
  background: #f4fdf8;
}

.ingredient-list li strong {
  color: #087f5b;
}

.check-list li {
  padding: 10px 12px;
  border: 1px solid #edf2f7;
  border-radius: 10px;
  background: #f8fafc;
}

.note-list li {
  padding: 12px;
  border: 1px solid #edf2f7;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 2px 10px rgba(31, 45, 61, 0.03);
}

.detail-nutrition-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.detail-section-head strong {
  color: #213549;
  font-size: 14px;
}

.detail-section-head span {
  color: #8a99aa;
  font-size: 11.5px;
}

.nutrient-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.nutrient-label {
  color: #7b8a9b;
  font-size: 12px;
}

.nutrient-tag {
  border-radius: 999px;
  font-weight: 700;
}

.nutrient-energy {
  border-color: #fed7aa !important;
  background: #fff7ed !important;
  color: #ea580c !important;
}

.nutrient-protein {
  border-color: #bbf7d0 !important;
  background: #ecfdf5 !important;
  color: #059669 !important;
}

.nutrient-fat {
  border-color: #fecaca !important;
  background: #fff1f2 !important;
  color: #dc2626 !important;
}

.nutrient-carbs {
  border-color: #fde68a !important;
  background: #fffbeb !important;
  color: #d97706 !important;
}

.nutrient-sodium {
  border-color: #bfdbfe !important;
  background: #eff6ff !important;
  color: #2563eb !important;
}

.detail-warning-card {
  border-color: #fde68a;
  background: #fffbeb;
}

.detail-warning-card p {
  margin: 6px 0 0;
  color: #92400e;
  font-size: 12px;
}

@media (max-width: 767px) {
  .record-review-drawer :deep(.el-drawer__body),
  .record-detail-drawer :deep(.el-drawer__body) {
    padding: 16px;
  }

  .detail-grid,
  .detail-meta-card,
  .ingredient-list {
    grid-template-columns: 1fr;
  }

  .review-layout {
    grid-template-columns: 1fr;
  }
}

</style>

<style>
/* 抽屉被 Teleport 到 body 后，使用全局选择器保证 SaaS 质感生效 */
.record-review-drawer.el-drawer,
.record-detail-drawer.el-drawer {
  border-radius: 12px;
  background: #f7f9fc;
}

.record-review-drawer .el-drawer__header,
.record-detail-drawer .el-drawer__header {
  margin: 0;
  padding: 22px 24px 16px;
  background: #f7f9fc;
  color: #1d2b3a;
  font-weight: 700;
}

.record-review-drawer .el-drawer__body,
.record-detail-drawer .el-drawer__body {
  padding: 24px;
  background: #f7f9fc;
}

.record-detail-drawer .el-tabs__header {
  margin: 0 0 16px;
}

.record-detail-drawer .el-tabs__nav-wrap::after,
.record-detail-drawer .el-tabs__active-bar {
  display: none;
}

.record-detail-drawer .el-tabs__item {
  height: 34px;
  margin-right: 8px;
  padding: 0 15px;
  border: 1px solid #e1e9f1;
  border-radius: 999px;
  background: #ffffff;
  color: #6b7c8f;
  font-size: 12.5px;
  font-weight: 600;
}

.record-detail-drawer .el-tabs__item.is-active {
  border-color: #0f6b52;
  background: #0f6b52;
  color: #ffffff;
}

.review-image-pane {
  background: #eff2f6;
}

.review-form .el-input__wrapper,
.review-form .el-textarea__inner,
.review-form .el-select__wrapper {
  border-radius: 8px;
  background: #f2f5f8;
  box-shadow: none !important;
  border: 1px solid transparent;
}

.review-form .el-input__wrapper.is-focus,
.review-form .el-textarea__inner:focus,
.review-form .el-select__wrapper.is-focused {
  border-color: #10b981;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1) !important;
}

.review-ingredient-tags .el-tag {
  border-color: #a7f3d0;
  border-radius: 999px;
  background: #ecfdf5;
  color: #10b981;
  font-weight: 600;
}

.review-footer {
  position: sticky;
  bottom: -24px;
  justify-content: flex-end;
  padding: 14px 0 24px;
  background: linear-gradient(180deg, rgba(247, 249, 252, 0), #f7f9fc 32%);
}

@media (max-width: 767px) {
  .record-review-drawer .el-drawer__body,
  .record-detail-drawer .el-drawer__body {
    padding: 16px;
  }
}
</style>

<style>
/* 详情页重构：左侧缩略图 + 状态降噪 + Grid 概览 */
.record-detail-drawer .detail-hero {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  margin-bottom: 16px;
  padding: 16px;
  border: 1px solid #e6edf4;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(31, 45, 61, 0.04);
}

.detail-thumb {
  flex: 0 0 150px;
  width: 150px;
  height: 150px;
  overflow: hidden;
  border: 1px solid #e3eaf2;
  border-radius: 12px;
  background: #eff2f6;
  box-shadow: 0 4px 14px rgba(31, 45, 61, 0.08);
}

.detail-thumb-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.detail-thumb-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  gap: 4px;
  color: #8a99aa;
  background: linear-gradient(145deg, #f4f7fa, #e8eef4);
}

.detail-thumb-placeholder span {
  font-size: 32px;
}

.detail-thumb-placeholder small {
  font-size: 11px;
}

.detail-hero-main {
  flex: 1 1 auto;
  min-width: 0;
}

.detail-head-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.detail-head-row h3 {
  margin: 0;
  color: #172536;
  font-size: 18px;
  line-height: 1.35;
}

.detail-head-row p {
  margin: 6px 0 0;
  color: #7c8b9b;
  font-size: 12px;
}

.detail-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}

.detail-overview-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid #edf2f7;
  border-radius: 9px;
  background: #f8fafc;
}

.detail-overview-item span {
  color: #8a99aa;
  font-size: 10.5px;
}

.detail-overview-item strong {
  overflow: hidden;
  color: #213549;
  font-size: 12.5px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-tabs-row {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.detail-tabs {
  flex: 1 1 auto;
  min-width: 0;
}

.detail-engine-meta {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  color: #9aa8b6;
  font-size: 10.5px;
  line-height: 1.5;
  white-space: nowrap;
}

.detail-engine-meta span + span::before {
  content: "·";
  margin-right: 8px;
  color: #c2ccd7;
}

.nutrient-card.nutrient-key .nutrient-tag {
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.01em;
}

.nutrient-card.nutrient-key .nutrient-label {
  color: #425466;
  font-weight: 700;
}

@media (max-width: 900px) {
  .detail-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-tabs-row {
    flex-direction: column;
    gap: 6px;
  }

  .detail-engine-meta {
    margin-top: 0;
    padding-left: 2px;
  }
}

@media (max-width: 767px) {
  .record-detail-drawer .detail-hero {
    padding: 12px;
  }

  .detail-thumb {
    flex-basis: 104px;
    width: 104px;
    height: 104px;
  }

  .detail-overview-grid {
    grid-template-columns: 1fr 1fr;
  }

  .detail-head-row {
    flex-direction: column;
    gap: 8px;
  }
}
</style>

<style>
/* OCR 数据区：居中、限宽、卡片包裹 */
.record-detail-drawer .el-tabs__header {
  display: flex;
  justify-content: center;
  width: 100%;
}

.record-detail-drawer .el-tabs__nav-wrap,
.record-detail-drawer .el-tabs__nav-scroll {
  display: flex;
  justify-content: center;
}

.record-detail-drawer .el-tabs__nav {
  display: flex;
  justify-content: center;
}

.ocr-data-panel {
  box-sizing: border-box;
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
  border: 1px solid #e8eef4;
  border-radius: 8px;
  background: #f8fafc;
}

.ocr-fields-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 14px;
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
}

.ocr-field-card {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
  padding: 13px 14px;
  border: 1px solid #edf2f7;
  border-radius: 8px;
  background: #ffffff;
}

.ocr-field-label {
  color: #8a99aa;
  font-size: 11px;
  line-height: 1.4;
}

.ocr-field-value {
  overflow-wrap: anywhere;
  color: #213549;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.6;
}

.ocr-value-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ocr-value-tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border: 1px solid #d9f3e7;
  border-radius: 999px;
  background: #ecfdf5;
  color: #0f8a65;
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.45;
}

@media (max-width: 767px) {
  .ocr-data-panel {
    padding: 16px;
  }

  .ocr-fields-grid {
    grid-template-columns: 1fr;
  }
}
</style>
