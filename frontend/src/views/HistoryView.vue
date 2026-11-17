<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { recordApi } from '@/api'
import { ApiError } from '@/api/client'
import type { RecordDetail, RecordListResult, RecordSummary } from '@/api/types'
import { useBreakpoint } from '@/composables/useBreakpoint'
import EmptyState from '@/components/EmptyState.vue'
import AuthImage from '@/components/AuthImage.vue'
import { formatDate, formatRelative, overallTagType, statusTagType } from '@/utils/format'

const router = useRouter()
const { isMobile } = useBreakpoint()

const list = ref<RecordListResult | null>(null)
const loading = ref(true)
const clearing = ref(false)
const errorMessage = ref('')
const query = ref('')
const status = ref('all')
const page = ref(1)
const perPage = 8
const editOpen = ref(false)
const editLoading = ref(false)
const editSaving = ref(false)
const editingRecord = ref<RecordSummary | null>(null)
const editForm = reactive({
  food_name: '',
  energy: undefined as number | undefined,
  protein: undefined as number | undefined,
  fat: undefined as number | undefined,
  carbohydrate: undefined as number | undefined,
  sodium: undefined as number | undefined,
  sugar: undefined as number | undefined,
})

const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'analyzed', label: '分析完成' },
  { value: 'corrected', label: '已校正' },
  { value: 'ocr_done', label: '已识别' },
  { value: 'uploaded', label: '已上传' },
]

let searchTimer: number | undefined

const items = computed(() => list.value?.items || [])

const visibleItems = computed(() => {
  const seen = new Set<string>()
  return items.value.filter((record) => {
    const key = displayName(record).trim().toLowerCase()
    if (!key) return true
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

const total = computed(() => list.value?.total || 0)
const stats = computed(() => list.value?.stats)
const isEmpty = computed(() => !loading.value && visibleItems.value.length === 0)

function historyEmoji(record: RecordSummary) {
  const name = displayName(record)
  if (/饮|茶|果汁|可乐|汽水|咖啡/.test(name)) return '🥤'
  if (/面|拉面|意面/.test(name)) return '🍜'
  if (/粥|饭|米/.test(name)) return '🍚'
  if (/沙拉|蔬菜|菜/.test(name)) return '🥗'
  if (/肉|鱼|鸡|虾|牛|猪/.test(name)) return '🍱'
  if (/饼|糕|糖|巧克力|零食/.test(name)) return '🍪'
  return '🍽️'
}

function historyStatusClass(record: RecordSummary) {
  if (record.status === 'analyzed') return 'is-ok'
  if (record.status === 'corrected') return 'is-blue'
  if (record.status === 'ocr_done') return 'is-amber'
  return 'is-muted'
}

function overallPillClass(record: RecordSummary) {
  if (record.overall_check === 'needs_review') return 'is-warn'
  if (record.overall_check === 'suspected') return 'is-danger'
  if (record.overall_check === 'none_found') return 'is-ok'
  return 'is-muted'
}

function handleEmptyAction() {
  // 有筛选条件时按钮是「清除筛选」；没有任何记录时直接去开始检测
  if (query.value || status.value !== 'all') {
    query.value = ''
    status.value = 'all'
    page.value = 1
    load()
    return
  }
  router.push({ name: 'analyze' })
}

function overallText(record: RecordSummary) {
  if (record.overall_check === 'none_found') return '未发现明显问题'
  if (record.overall_check === 'needs_review') return '需要进一步核实'
  if (record.overall_check === 'suspected') return '发现疑似问题'
  return '未核查'
}

function marketingName(text: string): boolean {
  if (!text) return false
  const foodHints = ['饼干', '面包', '饮料', '水', '牛奶', '酸奶', '茶', '咖啡', '薯片', '糖果', '巧克力', '方便面', '酱油', '醋', '零食', '食品', '坚果', '果冻', '罐头', '肉', '鱼', '肠', '酱', '粉', '油', '糖', '盐', '乳', '汁', '酒', '豆']
  if (foodHints.some((word) => text.includes(word))) return false
  return text.startsWith('#') || ['您', '新鲜养自己', '养自己', '元气', '唤醒', '轻负担', '宠粉', '种草', '打卡'].some((word) => text.includes(word))
}

function displayName(record: RecordSummary): string {
  const raw = (record.food_name_raw ?? record.food_name ?? '').trim()
  if (marketingName(raw)) return '[待完善] 某品牌食品'
  if (raw && raw !== '未命名食品') return raw
  const date = new Date(record.created_at)
  if (Number.isNaN(date.getTime())) return '未命名_未知日期'
  return `未命名_${date.getMonth() + 1}月${date.getDate()}日`
}

function nutritionValue(detail: RecordDetail, key: string): number | undefined {
  const item = detail.nutrition?.items?.find((row) => row.key === key)
  return typeof item?.value === 'number' ? item.value : undefined
}

async function openEdit(record: RecordSummary) {
  editingRecord.value = record
  editOpen.value = true
  editLoading.value = true
  editForm.food_name = record.food_name_raw ?? (record.food_name === '未命名食品' ? '' : record.food_name)
  editForm.energy = undefined
  editForm.protein = undefined
  editForm.fat = undefined
  editForm.carbohydrate = undefined
  editForm.sodium = undefined
  editForm.sugar = undefined
  try {
    const detail = await recordApi.detail(record.id)
    editForm.food_name = detail.record.food_name_raw ?? (detail.record.food_name === '未命名食品' ? '' : detail.record.food_name)
    editForm.energy = nutritionValue(detail, 'energy')
    editForm.protein = nutritionValue(detail, 'protein')
    editForm.fat = nutritionValue(detail, 'fat')
    editForm.carbohydrate = nutritionValue(detail, 'carbohydrate')
    editForm.sodium = nutritionValue(detail, 'sodium')
    editForm.sugar = nutritionValue(detail, 'sugar')
  } catch (error) {
    ElMessage.warning((error as ApiError).message || '营养成分加载失败，可先修改名称')
  } finally {
    editLoading.value = false
  }
}

async function saveEdit() {
  if (!editingRecord.value) return
  editSaving.value = true
  try {
    await recordApi.update(editingRecord.value.id, {
      food_name: editForm.food_name.trim(),
      nutrition: {
        energy: editForm.energy ?? null,
        protein: editForm.protein ?? null,
        fat: editForm.fat ?? null,
        carbohydrate: editForm.carbohydrate ?? null,
        sodium: editForm.sodium ?? null,
        sugar: editForm.sugar ?? null,
      },
    })
    ElMessage.success('食品信息已更新')
    editOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '保存失败')
  } finally {
    editSaving.value = false
  }
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    list.value = await recordApi.list({
      page: page.value,
      per_page: perPage,
      query: query.value.trim(),
      status: status.value,
    })
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '加载失败'
  } finally {
    loading.value = false
  }
}

function onSearchInput() {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    load()
  }, 420)
}

function changeStatus(value: string) {
  status.value = value
  page.value = 1
  load()
}

function openRecord(record: RecordSummary) {
  if (record.status === 'analyzed') router.push({ name: 'result', params: { id: record.id } })
  else router.push({ name: 'analyze', query: { record: record.id } })
}

async function clearAllRecords() {
  const count = stats.value?.total || 0
  if (!count) return
  try {
    await ElMessageBox.confirm(
      `将删除当前账号的全部 ${count} 条历史记录，图片和分析结果会一并删除且无法恢复。确定继续吗？`,
      '一键删除全部记录',
      { type: 'warning', confirmButtonText: '全部删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch {
    return
  }
  clearing.value = true
  try {
    const result = await recordApi.clearAll()
    ElMessage.success(`已删除 ${result.deleted_count} 条历史记录`)
    query.value = ''
    status.value = 'all'
    page.value = 1
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '清空失败')
  } finally {
    clearing.value = false
  }
}

async function removeRecord(record: RecordSummary) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${displayName(record)}」这条记录吗？图片与分析结果会一并删除且无法恢复。`,
      '删除记录',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await recordApi.remove(record.id)
    ElMessage.success('记录已删除')
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '删除失败')
  }
}

watch(page, load)

onMounted(load)
</script>

<template>
  <div class="page history-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">历史记录</h1>
        <p class="page-sub">
          记录保存在共享后端数据库中，刷新页面、重启服务或换设备登录都不会丢失
        </p>
      </div>
      <div class="page-actions">
        <el-button
          v-if="stats?.total"
          type="danger"
          plain
          :loading="clearing"
          @click="clearAllRecords"
        >
          <el-icon><Delete /></el-icon>
          一键删除
        </el-button>
        <el-button type="primary" @click="router.push({ name: 'analyze' })">
          <el-icon><Camera /></el-icon>
          新建分析
        </el-button>
      </div>
    </header>

    <div v-if="stats" class="stat-strip">
      <div class="strip-item">
        <span class="strip-value">{{ stats.total }}</span>
        <span class="strip-label">全部记录</span>
      </div>
      <div class="strip-item">
        <span class="strip-value">{{ stats.analyzed }}</span>
        <span class="strip-label">已完成分析</span>
      </div>
      <div class="strip-item">
        <span class="strip-value danger">{{ stats.suspected }}</span>
        <span class="strip-label">疑似问题</span>
      </div>
      <div class="strip-item">
        <span class="strip-value muted">{{ stats.demo }}</span>
        <span class="strip-label">演示记录（已标记）</span>
      </div>
    </div>

    <div class="card filter-card">
      <el-input
        v-model="query"
        placeholder="搜索食品名称，例如：饼干"
        clearable
        class="search-input"
        @input="onSearchInput"
        @keyup.enter="page = 1; load()"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="status-chips">
        <button
          v-for="option in statusOptions"
          :key="option.value"
          type="button"
          class="filter-chip"
          :class="{ active: status === option.value }"
          @click="changeStatus(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <div v-if="errorMessage" class="notice notice-danger mt">
      <el-icon><WarningFilled /></el-icon>
      <div>
        {{ errorMessage }}
        <el-button text type="primary" @click="load">重试</el-button>
      </div>
    </div>

    <div class="card table-card">
      <div v-if="loading" class="loading-block" style="height: 180px" />

      <EmptyState
        v-else-if="isEmpty"
        icon="Tickets"
        :title="query || status !== 'all' ? '没有匹配的记录' : '还没有任何分析记录'"
        :description="query || status !== 'all' ? '试试换一个关键词或清除筛选条件。' : '上传一张食品包装照片，几十秒后就能得到完整的标签分析。'"
        :action-text="query || status !== 'all' ? '清除筛选' : '去创建第一条记录'"
        @action="handleEmptyAction"
      />

      <!-- 桌面端卡片列表 -->
      <div v-else-if="!isMobile()" class="history-card-grid">
        <article
          v-for="record in visibleItems"
          :key="record.id"
          class="history-card"
          @click="openRecord(record)"
        >
          <div class="history-card-thumb">
            <AuthImage v-if="record.image_url" :src="record.image_url" ratio="1 / 1" />
            <span v-else class="history-card-emoji">{{ historyEmoji(record) }}</span>
          </div>

          <div class="history-card-main">
            <div class="history-card-head">
              <strong>{{ displayName(record) }}</strong>
              <span v-if="record.is_demo" class="history-pill is-muted">演示</span>
            </div>

            <div class="history-card-tags">
              <span class="history-pill" :class="historyStatusClass(record)">
                {{ record.status_label }}
              </span>
              <span v-if="record.data_complete" class="history-pill is-ok">数据完整</span>
              <span
                v-if="record.overall_check"
                class="history-pill"
                :class="overallPillClass(record)"
              >
                {{ overallText(record) }}
              </span>
            </div>

            <div class="history-card-meta">
              <span>{{ record.ingredient_count }} 种配料</span>
              <span>·</span>
              <span>{{ formatRelative(record.created_at) }}</span>
              <span>·</span>
              <span>{{ record.ocr_provider === 'dish_vision' ? 'AI 菜品识别' : record.ocr_provider === 'local_rapidocr' ? '本地 OCR' : record.ocr_provider === 'vision_llm' ? '视觉模型' : '—' }}</span>
            </div>
          </div>

          <div class="history-card-actions">
            <el-button text type="primary" size="small" @click.stop="openRecord(record)">
              {{ record.status === 'analyzed' ? '查看结果' : '继续分析' }}
            </el-button>
            <el-button text type="warning" size="small" @click.stop="openEdit(record)">
              编辑
            </el-button>
            <el-button text type="danger" size="small" @click.stop="removeRecord(record)">
              删除
            </el-button>
          </div>
        </article>
      </div>

      <!-- 移动端卡片 -->
      <div v-else class="mobile-list">
        <article v-for="record in visibleItems" :key="record.id" class="record-card" @click="openRecord(record)">
          <div class="record-top">
            <div class="record-thumb mobile-thumb">
              <AuthImage v-if="record.image_url" :src="record.image_url" ratio="1 / 1" />
              <span v-else class="thumb-placeholder">🍪</span>
            </div>
            <div class="record-name">
              {{ displayName(record) }}
              <el-tag
                v-if="record.overall_check === 'needs_review'"
                size="small"
                type="warning"
                effect="plain"
                class="incomplete-tag"
                @click.stop="openEdit(record)"
              >
                信息不全，点击完善
              </el-tag>
            </div>
            <span v-if="record.is_demo" class="chip chip-warn">演示</span>
          </div>
          <div class="record-tags">
            <el-tag :type="statusTagType(record.status)" size="small" effect="light">{{ record.status_label }}</el-tag>
            <el-tag v-if="record.data_complete" type="success" size="small" effect="light">数据完整</el-tag>
            <el-tag v-if="record.overall_check" :type="overallTagType(record.overall_check)" size="small" effect="plain">
              {{ overallText(record) }}
            </el-tag>
          </div>
          <div class="record-meta">
            <span>{{ record.ingredient_count }} 种配料</span>
            <span>·</span>
            <span>{{ formatRelative(record.created_at) }}</span>
          </div>
          <div class="record-actions">
            <el-button text type="primary" size="small" @click.stop="openRecord(record)">
              {{ record.status === 'analyzed' ? '查看结果' : '继续分析' }}
            </el-button>
            <el-button text type="warning" size="small" @click.stop="openEdit(record)">编辑</el-button>
            <el-button text type="danger" size="small" @click.stop="removeRecord(record)">删除</el-button>
          </div>
        </article>
      </div>

      <div v-if="!loading && total > 0" class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="perPage"
          :total="total"
          layout="prev, pager, next"
          background
          :pager-count="isMobile() ? 5 : 7"
          small
        />
        <span class="pager-text">共 {{ total }} 条 · 第 {{ page }} / {{ Math.max(1, list?.pages || 1) }} 页</span>
      </div>
    </div>
    <el-dialog v-model="editOpen" title="编辑食品信息" width="min(94vw, 560px)">
      <div v-loading="editLoading">
        <el-form label-position="top">
          <el-form-item label="食品名称">
            <el-input
              v-model="editForm.food_name"
              maxlength="120"
              show-word-limit
              placeholder="例如：手工苏打饼干；暂时不确定可以留空"
            />
          </el-form-item>
          <div class="edit-section-title">补充营养成分（每 100g / 100ml）</div>
          <div class="nutrition-edit-grid">
            <el-form-item label="能量（kJ）">
              <el-input-number v-model="editForm.energy" :min="0" :controls="false" placeholder="如 2000" />
            </el-form-item>
            <el-form-item label="蛋白质（g）">
              <el-input-number v-model="editForm.protein" :min="0" :controls="false" placeholder="如 8.5" />
            </el-form-item>
            <el-form-item label="脂肪（g）">
              <el-input-number v-model="editForm.fat" :min="0" :controls="false" placeholder="如 20" />
            </el-form-item>
            <el-form-item label="碳水化合物（g）">
              <el-input-number v-model="editForm.carbohydrate" :min="0" :controls="false" placeholder="如 60" />
            </el-form-item>
            <el-form-item label="钠（mg）">
              <el-input-number v-model="editForm.sodium" :min="0" :controls="false" placeholder="如 300" />
            </el-form-item>
            <el-form-item label="糖（g）">
              <el-input-number v-model="editForm.sugar" :min="0" :controls="false" placeholder="如 5" />
            </el-form-item>
          </div>
          <p class="edit-hint">留空的营养项不会覆盖原值；修改后会标记为人工补充。</p>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">保存修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.history-page {
  padding-bottom: 96px;
}

.stat-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.strip-item {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 11px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.strip-value {
  font-size: 21px;
  font-weight: 750;
  color: var(--brand-700);
  line-height: 1.2;
}

.strip-value.danger {
  color: var(--danger);
}

.strip-value.muted {
  color: var(--muted);
}

.strip-label {
  font-size: 11.5px;
  color: var(--muted);
}

.filter-card {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 14px 16px;
}

.search-input {
  max-width: 320px;
  flex: 1 1 220px;
}

.status-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
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

.mt {
  margin-top: 12px;
}

.table-card {
  margin-top: 14px;
}

.record-thumb {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  overflow: hidden;
  background: #f3f7f4;
  display: grid;
  place-items: center;
  border: 1px solid #e8efeb;
}

.record-thumb :deep(.auth-image) {
  width: 40px;
  height: 40px;
  aspect-ratio: auto !important;
}

.record-thumb :deep(.auth-image .state) {
  font-size: 8px;
}

.record-thumb :deep(.auth-image .state span) {
  display: none;
}

.thumb-placeholder {
  font-size: 22px;
  line-height: 1;
}

.status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.complete-tag {
  font-weight: 600;
}

.mobile-thumb {
  flex: none;
  margin-right: 8px;
}

.cell-name {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 5px 6px;
  min-width: 0;
}

.name-text {
  flex: 1 1 auto;
  min-width: 80px;
  font-weight: 600;
  line-height: 1.5;
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  word-break: break-word;
}

.cell-name .incomplete-tag {
  flex: none;
  margin-top: 1px;
}

:deep(.el-table__row) {
  cursor: pointer;
}

.mobile-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.record-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 13px 14px;
  background: var(--card);
}

.record-top {
  display: flex;
  align-items: center;
  gap: 7px;
  justify-content: space-between;
}

.record-name {
  font-size: 14.5px;
  font-weight: 650;
  min-width: 0;
  overflow-wrap: anywhere;
}

.record-tags {
  display: flex;
  gap: 6px;
  margin-top: 7px;
  flex-wrap: wrap;
}

.record-meta {
  margin-top: 7px;
  font-size: 12px;
  color: var(--muted);
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.record-actions {
  margin-top: 8px;
  display: flex;
  gap: 4px;
  border-top: 1px dashed var(--border);
  padding-top: 6px;
}

.record-actions :deep(.el-button) {
  padding: 4px 6px;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.pager-text {
  font-size: 12px;
  color: var(--muted);
}

@media (max-width: 768px) {
  .stat-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .filter-card {
    padding: 12px;
  }
  .search-input {
    max-width: none;
    flex-basis: 100%;
  }
  .status-chips {
    overflow-x: auto;
    flex-wrap: nowrap;
    width: 100%;
    padding-bottom: 2px;
  }
  .filter-chip {
    flex: 0 0 auto;
  }
}

.incomplete-tag {
  cursor: pointer;
}

.edit-section-title {
  margin: 4px 0 10px;
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}

.nutrition-edit-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}

.nutrition-edit-grid :deep(.el-input-number) {
  width: 100%;
}

.edit-hint {
  margin: 0;
  color: var(--muted);
  font-size: 11.5px;
}

@media (max-width: 520px) {
  .nutrition-edit-grid {
    grid-template-columns: 1fr;
  }
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ===== 历史记录卡片化 ===== */
.history-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.history-card {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 13px;
  border: 1px solid #edf2ef;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 4px 14px rgba(31, 91, 66, 0.045);
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}

.history-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 9px 22px rgba(31, 91, 66, 0.09);
}

.history-card-thumb {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  flex: 0 0 52px;
  overflow: hidden;
  border-radius: 13px;
  background: #f3f8f5;
}

.history-card-thumb :deep(.auth-image) {
  width: 52px;
  height: 52px;
  aspect-ratio: auto !important;
}

.history-card-emoji {
  font-size: 25px;
}

.history-card-main {
  flex: 1;
  min-width: 0;
}

.history-card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.history-card-head strong {
  overflow: hidden;
  color: #254638;
  font-size: 13.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}

.history-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 7px;
  border-radius: 999px;
  font-size: 9.5px;
  font-weight: 700;
  line-height: 1.35;
}

.history-pill.is-ok {
  background: #eaf7ef;
  color: #357c5b;
}

.history-pill.is-warn {
  background: #fff4dc;
  color: #a8741d;
}

.history-pill.is-danger {
  background: #fdeeea;
  color: #bd5b4c;
}

.history-pill.is-blue {
  background: #edf5fb;
  color: #4d7894;
}

.history-pill.is-amber {
  background: #fff7e9;
  color: #a47522;
}

.history-pill.is-muted {
  background: #f1f4f2;
  color: #80938a;
}

.history-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
  color: #8b9d94;
  font-size: 10.5px;
}

.history-card-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  flex: 0 0 auto;
}

.history-card-actions :deep(.el-button) {
  margin: 0;
  padding: 2px 4px;
  font-size: 11px;
}

@media (max-width: 900px) {
  .history-card-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

</style>
