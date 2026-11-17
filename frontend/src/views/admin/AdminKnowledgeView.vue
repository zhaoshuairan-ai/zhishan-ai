<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminApi,
  type AdminKnowledgeItem,
  type AdminMeta,
  type AdminKnowledgeList,
} from '@/api/admin'
import { ApiError } from '@/api/client'
import { useBreakpoint } from '@/composables/useBreakpoint'
import AdminRulesView from './AdminRulesView.vue'

const { isMobile } = useBreakpoint()
const activeSection = ref<'knowledge' | 'rules'>('knowledge')
const loading = ref(false)
const errorMessage = ref('')
const items = ref<AdminKnowledgeItem[]>([])
const stats = ref<AdminKnowledgeList['stats']>({ total: 0, published: 0, pending: 0, draft: 0, offline: 0 })
const categories = ref<Array<{ value: string; label: string }>>([])
const meta = ref<AdminMeta | null>(null)
const page = ref(1)
const pages = ref(1)
const total = ref(0)
const filters = reactive({ q: '', category: '', status: '', source: '', verification: '' })

const dialogOpen = ref(false)
const editing = ref<AdminKnowledgeItem | null>(null)
const saving = ref(false)
const estimatingNutrition = ref(false)
const summarizing = ref(false)
const composingKnowledge = ref(false)
const formError = ref('')
const form = reactive({
  title: '',
  category: 'additive',
  summary: '',
  content: '',
  source_name: '',
  source_url: '',
  source_type: 'editorial',
  verification_status: 'pending',
  status: 'draft',
  scope: '预包装食品标签',
  version: '1.0',
  aliases: '',
  keywords: '',
  usage_note: '',
  calories_per_100g: 0,
  carbs_per_100g: 0,
  protein_per_100g: 0,
  fat_per_100g: 0,
})

const dialogTitle = computed(() => (editing.value ? `编辑知识条目` : '新增知识条目'))
const formPanels = ref<string[]>(['basic'])

const isDishForm = computed(() => form.category === 'dish')

watch(
  () => form.category,
  (value) => {
    if (value !== 'dish') {
      formPanels.value = formPanels.value.filter(
        (panel) => panel !== 'nutrition',
      )
      return
    }

    // 菜品需要结构化营养字段，默认展开营养面板
    formPanels.value = formPanels.value.filter(
      (panel) => panel !== 'source' && panel !== 'extra',
    )
    if (!formPanels.value.includes('nutrition')) {
      formPanels.value = [...formPanels.value, 'nutrition']
    }
    if (!form.source_name.trim()) {
      form.source_name = '平台菜品资料整理'
    }
  },
)

const statusLabel: Record<string, string> = { published: '已发布', draft: '待审核', '草稿': '待审核', offline: '已下架' }

const NUTRITION_CATEGORIES = new Set(['dish', 'ingredient'])

function needsNutrition(category: string) {
  return NUTRITION_CATEGORIES.has(category)
}

function displayStatus(entry: AdminKnowledgeItem) {
  if (entry.status === 'offline') return '已下架'
  if (entry.status === 'published' && entry.verification_status === 'verified') {
    return '已发布'
  }
  return '待审核'
}

function displayStatusClass(entry: AdminKnowledgeItem) {
  if (entry.status === 'offline') return 'status-offline'
  if (entry.status === 'published' && entry.verification_status === 'verified') {
    return 'status-published'
  }
  return 'status-draft'
}

const statusTabs = computed(() => [
  { value: '', label: '全部', count: stats.value.total || 0 },
  { value: 'published', label: '已发布', count: stats.value.published || 0 },
  { value: 'pending', label: '待审核', count: stats.value.pending ?? stats.value.draft ?? 0 },
  { value: 'offline', label: '已下架', count: stats.value.offline || 0 },
])

function switchStatus(value: string) {
  filters.status = value
  page.value = 1
  load()
}

async function load(reset = false) {
  if (reset) page.value = 1
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await adminApi.knowledge({
      q: filters.q.trim(),
      category: filters.category,
      status: filters.status,
      source: filters.source,
      verification: filters.verification,
      page: page.value,
      per_page: 20,
    })
    items.value = data.items
    stats.value = data.stats
    categories.value = data.categories
    pages.value = data.pages
    total.value = data.total
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  formError.value = ''
  Object.assign(form, {
    title: '',
    category: 'additive',
    summary: '',
    content: '',
    source_name: '',
    source_url: '',
    source_type: 'editorial',
    verification_status: 'pending',
    status: 'draft',
    scope: '预包装食品标签',
    version: '1.0',
    aliases: '',
    keywords: '',
    usage_note: '',
    calories_per_100g: 0,
    carbs_per_100g: 0,
    protein_per_100g: 0,
    fat_per_100g: 0,
  })
  formPanels.value = ['basic']
  dialogOpen.value = true
}

function openEdit(entry: AdminKnowledgeItem) {
  editing.value = entry
  formError.value = ''
  Object.assign(form, {
    title: entry.title,
    category: entry.category,
    summary: entry.summary,
    content: entry.content || '',
    source_name: entry.source_name,
    source_url: entry.source_url || '',
    source_type: entry.source_type,
    verification_status: entry.verification_status,
    status: entry.status,
    scope: entry.scope,
    version: entry.version,
    aliases: (entry.aliases || []).join(','),
    keywords: (entry.keywords || []).join(' '),
    usage_note: entry.usage_note || '',
    calories_per_100g: Number(entry.calories_per_100g ?? entry.calories ?? 0),
    carbs_per_100g: Number(entry.carbs_per_100g ?? entry.carbs ?? 0),
    protein_per_100g: Number(entry.protein_per_100g ?? entry.protein ?? 0),
    fat_per_100g: Number(entry.fat_per_100g ?? entry.fat ?? 0),
  })
  formPanels.value = entry.category === 'dish'
    ? ['basic', 'nutrition']
    : ['basic']
  dialogOpen.value = true
}

async function estimateNutrition() {
  if (!form.title.trim()) {
    formError.value = '请先填写菜品标题，再让 AI 测算'
    formPanels.value = ['basic']
    return
  }

  estimatingNutrition.value = true
  formError.value = ''

  try {
    const result = await adminApi.estimateDishNutrition({
      title: form.title.trim(),
      summary: form.summary,
      content: form.content,
    })

    if (result.status !== 'success') {
      ElMessage.warning(
        result.message || 'AI 测算失败，请手动填写营养数据',
      )
      return
    }

    form.calories_per_100g = Number(result.calories_per_100g || 0)
    form.carbs_per_100g = Number(result.carbs_per_100g || 0)
    form.protein_per_100g = Number(result.protein_per_100g || 0)
    form.fat_per_100g = Number(result.fat_per_100g || 0)
    formPanels.value = formPanels.value.includes('nutrition')
      ? formPanels.value
      : [...formPanels.value, 'nutrition']

    ElMessage.success('AI 已根据描述自动测算营养数据')
  } catch (error) {
    formError.value =
      (error as { message?: string }).message || 'AI 测算失败，请稍后重试'
  } finally {
    estimatingNutrition.value = false
  }
}

async function composeKnowledge() {
  if (!form.title.trim()) {
    formError.value = '请先填写菜品标题'
    return
  }

  if (form.category !== 'dish') {
    ElMessage.warning('请先将分类选择为「菜品」')
    return
  }

  composingKnowledge.value = true
  formError.value = ''

  try {
    const result = await adminApi.composeKnowledge(
      form.title.trim(),
    )

    form.content = result.content
    form.summary = result.summary
    form.calories_per_100g = Number(result.calories || 0)
    form.carbs_per_100g = Number(result.carbs || 0)
    form.protein_per_100g = Number(result.protein || 0)
    form.fat_per_100g = Number(result.fat || 0)

    formPanels.value = formPanels.value.includes('nutrition')
      ? formPanels.value
      : [...formPanels.value, 'nutrition']

    ElMessage.success('✨ AI 已生成正文、摘要和营养数据')
  } catch (error) {
    formError.value =
      (error as { message?: string }).message ||
      'AI 一键建库失败，请稍后重试'
  } finally {
    composingKnowledge.value = false
  }
}

async function summarizeContent() {
  if (!form.content.trim()) {
    ElMessage.warning('请先填写内容正文，再生成摘要')
    return
  }

  summarizing.value = true
  formError.value = ''

  try {
    const result = await adminApi.summarizeKnowledge({
      title: form.title.trim(),
      content: form.content,
    })
    form.summary = result.summary
    ElMessage.success('✨ AI 已生成摘要')
  } catch (error) {
    formError.value =
      (error as { message?: string }).message || 'AI 摘要生成失败，请稍后重试'
  } finally {
    summarizing.value = false
  }
}

async function save() {
  formError.value = ''

  if (!form.title.trim()) {
    formPanels.value = ['basic']
    formError.value = '标题不能为空'
    return
  }

  if (!form.summary.trim()) {
    formPanels.value = ['basic']
    formError.value = '请填写摘要，或点击 AI 生成'
    return
  }
  if (form.category !== 'dish' && !form.source_name.trim()) {
    if (!formPanels.value.includes('source')) {
      formPanels.value = [...formPanels.value, 'source']
    }
    formError.value = '来源名称不能为空，已展开「溯源信息」'
    return
  }

  // 菜品表单不展示来源字段，保存时自动补默认资料说明
  if (form.category === 'dish' && !form.source_name.trim()) {
    form.source_name = '平台菜品资料整理'
  }
  saving.value = true
  try {
    const payload = { ...form }
    let nutritionAi: { status: string; message: string } | undefined
    let savedEntry: AdminKnowledgeItem | null = null

    if (editing.value) {
      const result = await adminApi.updateKnowledge(
        editing.value.id,
        payload,
      )
      nutritionAi = result.nutrition_ai
      savedEntry = result.entry
    } else {
      const result = await adminApi.createKnowledge(payload)
      nutritionAi = result.nutrition_ai
      savedEntry = result.entry
    }

    dialogOpen.value = false

    if (savedEntry?.status === 'published') {
      filters.status = ''
      page.value = 1
    }

    await load(true)

    const hasNutrition =
      Number(savedEntry?.calories ?? savedEntry?.calories_per_100g ?? 0) > 0

    if (
      needsNutrition(form.category) &&
      nutritionAi?.status === 'success' &&
      hasNutrition
    ) {
      ElMessage.success(
        '保存成功！AI 已为您自动补全该菜品的营养数据。',
      )
    } else if (
      needsNutrition(form.category) &&
      (nutritionAi?.status === 'failed' || !hasNutrition)
    ) {
      ElMessage.warning(
        '保存成功，但 AI 测算失败，请手动补充营养数据。',
      )
    } else {
      ElMessage.success(editing.value ? '条目已更新' : '条目已创建')
    }
  } catch (error) {
    formError.value = (error as ApiError).message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function toggleStatus(entry: AdminKnowledgeItem, status: string) {
  const labels: Record<string, string> = { published: '发布', offline: '下架', draft: '转为草稿' }
  ElMessage.closeAll()

  try {
    const result = await adminApi.publishKnowledge(entry.id, status)

    const hasNutrition =
      Number(result.entry?.calories ?? result.entry?.calories_per_100g ?? 0) > 0

    if (status !== 'published' || !needsNutrition(entry.category)) {
      // 下架/草稿，或添加剂/术语/科普等无需营养数据的分类
      ElMessage.success(`已${labels[status] || '更新'}：${entry.title}`)
    } else if (
      result.nutrition_ai?.status === 'success' &&
      hasNutrition
    ) {
      ElMessage.success(
        '发布成功！AI 已为您自动补全该菜品的营养数据。',
      )
    } else if (result.nutrition_ai?.status === 'failed') {
      ElMessage.warning(
        '发布成功，但 AI 测算失败，请手动补充营养数据。',
      )
    } else {
      ElMessage.success(`已${labels[status] || '更新'}：${entry.title}`)
    }

    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '操作失败')
  }
}

async function verify(entry: AdminKnowledgeItem) {
  // 清掉之前可能堆叠的黄色警告，避免一次操作堆满屏幕
  ElMessage.closeAll()

  try {
    const result = await adminApi.verifyKnowledge(entry.id)

    const hasNutrition =
      Number(result.entry?.calories ?? result.entry?.calories_per_100g ?? 0) > 0

    if (!needsNutrition(entry.category)) {
      // 非菜品/配料直接审核通过，不显示营养测算警告
      ElMessage.success(`已审核通过：${entry.title}`)
    } else if (result.nutrition_ai?.status === 'success' && hasNutrition) {
      ElMessage.success(
        `已审核通过：${entry.title}；AI 已自动补全营养数据`,
      )
    } else if (result.nutrition_ai?.status === 'failed') {
      ElMessage.warning(
        `已审核通过：${entry.title}；AI 测算失败，请手动补充营养数据`,
      )
    } else {
      ElMessage.success(`已审核通过：${entry.title}`)
    }

    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '审核失败')
  }
}

async function remove(entry: AdminKnowledgeItem) {
  try {
    await ElMessageBox.confirm(`确认删除知识条目「${entry.title}」？该操作不可恢复。`, '删除条目', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'error',
    })
  } catch {
    return
  }
  try {
    await adminApi.deleteKnowledge(entry.id)
    ElMessage.success('条目已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '删除失败')
  }
}

function formatTime(value: string | null) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

onMounted(async () => {
  await load()
  try {
    meta.value = await adminApi.meta()
  } catch {
    /* 元数据失败不影响列表 */
  }
})
</script>

<template>
  <div class="admin-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">知识库管理</h1>
        <p class="page-sub">支持新增、编辑、发布、下架与删除；未核验的编辑内容不能直接发布。</p>
      </div>
      <div class="head-actions">
        <el-button :loading="loading" @click="load()">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增条目</el-button>
      </div>
    </header>

    <div class="admin-subtabs">
      <button
        type="button"
        class="admin-subtab"
        :class="{ active: activeSection === 'knowledge' }"
        @click="activeSection = 'knowledge'"
      >
        知识库条目
      </button>
      <button
        type="button"
        class="admin-subtab"
        :class="{ active: activeSection === 'rules' }"
        @click="activeSection = 'rules'"
      >
        核查规则
      </button>
    </div>

    <div v-if="activeSection === 'knowledge'">
    <div class="status-tabs">
      <button
        v-for="tab in statusTabs"
        :key="tab.value"
        type="button"
        class="status-tab"
        :class="{ active: filters.status === tab.value }"
        @click="switchStatus(tab.value)"
      >
        {{ tab.label }}
        <span>{{ tab.count }}</span>
      </button>
    </div>

    <div class="filter-bar card">
      <el-input v-model="filters.q" placeholder="搜索标题、slug 或关键词" clearable @keyup.enter="load(true)" />
      <el-select v-model="filters.category" placeholder="分类" @change="load(true)">
        <el-option label="全部分类" value="" />
        <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" @change="switchStatus(filters.status)">
        <el-option label="全部状态" value="" />
        <el-option label="已发布" value="published" />
        <el-option label="待审核" value="pending" />
        <el-option label="已下架" value="offline" />
      </el-select>
      <el-select v-model="filters.source" placeholder="来源" @change="load(true)">
        <el-option label="全部来源" value="" />
        <el-option label="本地知识库" value="local" />
        <el-option label="大模型生成" value="ai" />
      </el-select>
      <el-select v-model="filters.verification" placeholder="核验状态" @change="load(true)">
        <el-option label="全部核验状态" value="" />
        <el-option label="待核验" value="pending" />
        <el-option label="已核验" value="verified" />
      </el-select>
      <el-button type="primary" @click="load(true)">查询</el-button>
    </div>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mb" />

    <div v-if="!isMobile()" v-loading="loading" class="card table-card">
      <el-table :data="items" class="knowledge-table" size="default" stripe>
        <el-table-column prop="id" label="ID" width="62" />

        <el-table-column label="标题" min-width="210">
          <template #default="{ row }">
            <div class="title-cell">
              <strong>{{ row.title }}</strong>
              <small>{{ row.slug }}</small>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="category_label" label="分类" width="110" />

        <!-- 来源拆成三行：类型胶囊 / 标准名称 / 核验状态 -->
        <el-table-column label="来源" min-width="230">
          <template #default="{ row }">
            <div class="source-stack">
              <span
                class="source-type-pill"
                :class="{ 'is-ai': row.is_ai_generated }"
              >
                {{ row.is_ai_generated ? 'AI 生成' : '权威库' }}
              </span>

              <span class="source-name">{{ row.source_name }}</span>

              <span
                class="verify-note"
                :class="row.verification_status === 'pending' ? 'is-pending' : 'is-verified'"
              >
                {{ row.verification_label }}
              </span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="104">
          <template #default="{ row }">
            <span class="status-pill" :class="displayStatusClass(row)">
              {{ displayStatus(row) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="version" label="版本" width="76" />

        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>

        <el-table-column label="操作" width="304" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button size="small" text type="primary" @click="openEdit(row)">
                编辑
              </el-button>

              <el-button
                v-if="row.verification_status === 'pending'"
                size="small"
                text
                type="success"
                @click="verify(row)"
              >
                审核通过
              </el-button>

              <el-button
                v-if="row.status !== 'published' && row.verification_status !== 'pending'"
                size="small"
                text
                type="success"
                @click="toggleStatus(row, 'published')"
              >
                发布
              </el-button>

              <el-button
                v-else
                size="small"
                text
                type="warning"
                @click="toggleStatus(row, 'offline')"
              >
                下架
              </el-button>

              <el-button
                class="danger-action"
                size="small"
                text
                type="danger"
                @click="remove(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else v-loading="loading" class="kb-cards">
      <div v-for="entry in items" :key="entry.id" class="card kb-card">
        <div class="kb-head">
          <strong>{{ entry.title }}</strong>
          <span class="status-pill" :class="displayStatusClass(entry)">
            {{ displayStatus(entry) }}
          </span>
        </div>
        <div class="kb-meta">
          <span>{{ entry.category_label }} · v{{ entry.version }}</span>
          <div class="source-stack">
            <span class="source-type-pill" :class="{ 'is-ai': entry.is_ai_generated }">
              {{ entry.is_ai_generated ? 'AI 生成' : '权威库' }}
            </span>
            <span class="source-name">{{ entry.source_name }}</span>
            <span
              class="verify-note"
              :class="entry.verification_status === 'pending' ? 'is-pending' : 'is-verified'"
            >
              {{ entry.verification_label }}
            </span>
          </div>
          <span>更新 {{ formatTime(entry.updated_at) }}</span>
        </div>
        <div class="kb-actions">
          <el-button size="small" plain @click="openEdit(entry)">编辑</el-button>
          <el-button
            v-if="entry.verification_status === 'pending'"
            size="small" plain type="success"
            @click="verify(entry)"
          >审核通过</el-button>
          <el-button
            v-if="entry.status !== 'published' && entry.verification_status !== 'pending'"
            size="small" plain type="success"
            @click="toggleStatus(entry, 'published')"
          >发布</el-button>
          <el-button v-else size="small" plain type="warning" @click="toggleStatus(entry, 'offline')">下架</el-button>
          <el-button size="small" plain type="danger" @click="remove(entry)">删除</el-button>
        </div>
      </div>
      <div v-if="!items.length && !loading" class="empty-text">没有符合条件的条目</div>
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="prev, pager, next"
        :disabled="loading"
        @current-change="load()"
      />
      <span class="pager-hint">共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页</span>
    </div>

    <el-dialog
      v-model="dialogOpen"
      :title="dialogTitle"
      width="min(94vw, 720px)"
      top="6vh"
      class="knowledge-dialog"
    >
      <el-alert
        v-if="formError"
        :title="formError"
        type="error"
        show-icon
        :closable="false"
        class="mb"
      />

      <el-form label-position="top" class="kb-form">
        <el-collapse v-model="formPanels" class="kb-collapse">
          <!-- 基础信息：默认展开 -->
          <el-collapse-item name="basic">
            <template #title>
              <div class="panel-title">
                <span class="panel-index">01</span>
                <strong>基础信息</strong>
                <small>标题、分类与正文</small>
              </div>
            </template>

            <div class="form-section">
              <el-form-item label="标题" required>
                <div class="title-input-row">
                  <el-input
                    v-model="form.title"
                    maxlength="160"
                    show-word-limit
                    placeholder="例如：驴肉火烧"
                  />

                  <el-button
                    v-if="isDishForm"
                    type="primary"
                    :loading="composingKnowledge"
                    class="title-ai-button"
                    @click="composeKnowledge"
                  >
                    ✨ AI 一键建库
                  </el-button>
                </div>
              </el-form-item>

              <div class="form-row">
                <el-form-item label="分类" required>
                  <el-select v-model="form.category">
                    <el-option
                      v-for="item in meta?.knowledge_categories || []"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>

                <el-form-item label="版本">
                  <el-input v-model="form.version" maxlength="20" />
                </el-form-item>

                <el-form-item label="状态">
                  <el-select v-model="form.status">
                    <el-option label="待审核" value="draft" />
                    <el-option label="已发布" value="published" disabled />
                    <el-option label="已下架" value="offline" />
                  </el-select>
                </el-form-item>
              </div>

              <el-form-item required>
                <template #label>
                  <div class="summary-label-row">
                    <span>摘要</span>
                    <el-button
                      size="small"
                      text
                      type="primary"
                      :loading="summarizing"
                      @click="summarizeContent"
                    >
                      ✨ AI 总结核心结论
                    </el-button>
                  </div>
                </template>

                <el-input
                  v-model="form.summary"
                  type="textarea"
                  :rows="2"
                  maxlength="200"
                  show-word-limit
                  placeholder="用一两句话说明这条知识的核心结论"
                />
              </el-form-item>

              <el-form-item label="内容正文">
                <el-input
                  v-model="form.content"
                  type="textarea"
                  :rows="5"
                  maxlength="4000"
                  show-word-limit
                  placeholder="填写完整说明、适用条件或引用内容"
                />
              </el-form-item>
            </div>
          </el-collapse-item>

          <!-- 菜品营养数据：只在分类为菜品时出现 -->
          <el-collapse-item v-if="isDishForm" name="nutrition">
            <template #title>
              <div class="panel-title">
                <span class="panel-index">02</span>
                <strong>营养数据</strong>
                <small>热量与三大营养素，按每 100g 填写</small>
              </div>
            </template>

            <div class="form-section">
              <div class="nutrition-form-toolbar">
                <div class="nutrition-form-copy">
                  <strong>每 100g 营养数据</strong>
                  <small>留空时保存后端会自动调用 AI 补全</small>
                </div>

                <el-button
                  type="primary"
                  plain
                  :loading="estimatingNutrition"
                  @click="estimateNutrition"
                >
                  ✨ 根据描述自动测算
                </el-button>
              </div>

              <div class="form-row nutrition-form-row">
                <el-form-item label="热量 (kcal/100g)">
                  <el-input-number
                    v-model="form.calories_per_100g"
                    :min="0"
                    :max="2000"
                    :precision="1"
                    controls-position="right"
                  />
                </el-form-item>

                <el-form-item label="碳水 (g/100g)">
                  <el-input-number
                    v-model="form.carbs_per_100g"
                    :min="0"
                    :max="100"
                    :precision="1"
                    controls-position="right"
                  />
                </el-form-item>

                <el-form-item label="蛋白质 (g/100g)">
                  <el-input-number
                    v-model="form.protein_per_100g"
                    :min="0"
                    :max="100"
                    :precision="1"
                    controls-position="right"
                  />
                </el-form-item>

                <el-form-item label="脂肪 (g/100g)">
                  <el-input-number
                    v-model="form.fat_per_100g"
                    :min="0"
                    :max="100"
                    :precision="1"
                    controls-position="right"
                  />
                </el-form-item>
              </div>

              <p class="nutrition-form-hint">
                填写后保存会直接使用这些数值；未填写或全部为 0 时，保存时后端会强制调用 AI 自动补全。
              </p>
            </div>
          </el-collapse-item>

          <!-- 溯源信息：菜品不显示，其它知识分类仍保留 -->
          <el-collapse-item v-if="!isDishForm" name="source">
            <template #title>
              <div class="panel-title">
                <span class="panel-index">02</span>
                <strong>溯源信息</strong>
                <small>来源、链接与核验状态</small>
              </div>
            </template>

            <div class="form-section">
              <div class="form-row">
                <el-form-item label="来源名称" required>
                  <el-input
                    v-model="form.source_name"
                    maxlength="200"
                    placeholder="如 GB 2760《食品安全国家标准 食品添加剂使用标准》"
                  />
                </el-form-item>

                <el-form-item label="来源类型">
                  <el-select v-model="form.source_type">
                    <el-option
                      v-for="item in meta?.source_types || []"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
              </div>

              <div class="form-row">
                <el-form-item label="来源链接">
                  <el-input
                    v-model="form.source_url"
                    maxlength="300"
                    placeholder="https://…"
                  />
                </el-form-item>

                <el-form-item label="核验状态">
                  <el-select v-model="form.verification_status">
                    <el-option label="已核对来源" value="verified" />
                    <el-option label="待核验" value="pending" />
                  </el-select>
                </el-form-item>
              </div>
            </div>
          </el-collapse-item>

          <!-- 扩展信息：菜品不显示，其它知识分类仍保留 -->
          <el-collapse-item v-if="!isDishForm" name="extra">
            <template #title>
              <div class="panel-title">
                <span class="panel-index">03</span>
                <strong>扩展信息</strong>
                <small>适用范围、关键词与使用提示</small>
              </div>
            </template>

            <div class="form-section">
              <div class="form-row">
                <el-form-item label="适用范围">
                  <el-input
                    v-model="form.scope"
                    maxlength="200"
                    placeholder="例如：预包装食品标签"
                  />
                </el-form-item>

                <el-form-item label="关键词（空格分隔）">
                  <el-input
                    v-model="form.keywords"
                    maxlength="300"
                    placeholder="例如：防腐剂 苯甲酸"
                  />
                </el-form-item>
              </div>

              <el-form-item label="别名（逗号分隔）">
                <el-input
                  v-model="form.aliases"
                  maxlength="300"
                  placeholder="例如：苯甲酸钠,安息香酸钠"
                />
              </el-form-item>

              <el-form-item label="使用提示">
                <el-input
                  v-model="form.usage_note"
                  type="textarea"
                  :rows="2"
                  maxlength="500"
                  show-word-limit
                  placeholder="补充容易误用的边界或提醒"
                />
              </el-form-item>
            </div>
          </el-collapse-item>
        </el-collapse>

        <p class="policy-note">
          未核验的「编辑整理」内容不能直接发布为权威条目；请先核对来源并保存为待审核，审核通过后再发布。
        </p>
      </el-form>

      <template #footer>
        <div class="dialog-footer-actions">
          <el-button @click="dialogOpen = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">
            保存
          </el-button>
        </div>
      </template>
    </el-dialog>
    </div>

    <AdminRulesView v-else />
  </div>
</template>

<style scoped>
.admin-subtabs {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  padding: 4px;
  width: fit-content;
  border: 1px solid #e2ece6;
  border-radius: 10px;
  background: #f6faf8;
}

.admin-subtab {
  padding: 7px 13px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #71877c;
  font-family: inherit;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.admin-subtab.active {
  background: #14796b;
  color: #ffffff;
}

.page-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.page-sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--muted);
}

.head-actions {
  display: flex;
  gap: 8px;
}

.status-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.status-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid #e1ece6;
  border-radius: 8px;
  background: #ffffff;
  color: #607b70;
  font-family: inherit;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.status-tab > span {
  padding: 1px 6px;
  border-radius: 999px;
  background: #f0f6f3;
  color: #71877c;
  font-size: 10px;
}

.status-tab.active {
  border-color: #14796b;
  background: #14796b;
  color: #ffffff;
}

.status-tab.active > span {
  background: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}

.stat-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--text-2);
}

.stat-strip span {
  background: #eef5f3;
  border-radius: 999px;
  padding: 3px 10px;
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

.title-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.title-cell small {
  color: var(--muted);
  font-size: 11.5px;
}

.kb-cards {
  display: grid;
  gap: 10px;
}

.kb-card {
  padding: 12px 14px;
}

.kb-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.kb-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 6px 0 10px;
  font-size: 12px;
  color: var(--muted);
}

.kb-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
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

.form-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 10px;
}

.form-row .el-form-item {
  min-width: 0;
}

.policy-note {
  font-size: 11.5px;
  color: var(--muted);
  margin: 0;
}

.empty-text {
  text-align: center;
  color: var(--muted);
  padding: 18px;
  font-size: 13px;
}

@media (max-width: 767px) {
  .form-row {
    grid-template-columns: 1fr;
  }

  .filter-bar .el-select {
    width: calc(50% - 4px);
    flex: 1 1 calc(50% - 4px);
  }
}

/* ---------- 知识库表格：来源分层、行高与状态胶囊 ---------- */
.table-card {
  padding: 14px 16px;
}

.knowledge-table :deep(.el-table__cell) {
  padding: 16px 0;
}

.knowledge-table :deep(.el-table .cell) {
  line-height: 1.55;
  padding: 0 14px;
}

.source-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.source-type-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  background: #eaf4fd;
  color: #2f6f9f;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.source-type-pill.is-ai {
  background: #edf4fd;
  color: #4a6f92;
}

.source-name {
  color: #40584d;
  font-size: 12.5px;
  line-height: 1.5;
  word-break: break-word;
}

.verify-note {
  font-size: 10.5px;
  line-height: 1.4;
}

.verify-note.is-pending {
  color: #c07a1b;
}

.verify-note.is-verified {
  color: #3b8b6b;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.status-published {
  background: #e9f8f0;
  color: #257a55;
}

.status-draft {
  background: #fff4df;
  color: #b26a00;
  border: 1px solid #f3d39a;
}

.status-offline {
  background: #fff5e8;
  color: #a86a19;
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-actions :deep(.el-button) {
  margin-left: 0;
}

.row-actions .danger-action {
  margin-left: 6px;
}

/* ---------- 新增/编辑知识：折叠面板 ---------- */
.kb-collapse {
  border: 0;
}

.kb-collapse :deep(.el-collapse-item) {
  margin-bottom: 10px;
  border: 1px solid #e4efe8;
  border-radius: 12px;
  background: #fbfdfc;
  overflow: hidden;
}

.kb-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 54px;
  padding: 0 14px;
  border-bottom: 1px solid transparent;
  background: #fbfdfc;
}

.kb-collapse :deep(.el-collapse-item__header.is-active) {
  border-bottom-color: #edf5f0;
}

.kb-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
  background: transparent;
}

.kb-collapse :deep(.el-collapse-item__content) {
  padding: 14px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.panel-index {
  display: inline-grid;
  place-items: center;
  width: 23px;
  height: 23px;
  border-radius: 7px;
  background: #e8f4ed;
  color: #2c7c5b;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
}

.panel-title strong {
  color: #2e4f40;
  font-size: 13px;
}

.panel-title small {
  color: #91a39a;
  font-size: 10.5px;
  font-weight: 400;
}

.title-input-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

.title-input-row .el-input {
  flex: 1 1 auto;
  min-width: 0;
}

.title-ai-button {
  flex: 0 0 auto;
  white-space: nowrap;
}

.summary-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
}

.summary-label-row .el-button {
  flex: 0 0 auto;
}

.nutrition-form-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.nutrition-form-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.nutrition-form-copy strong {
  color: #25463a;
  font-size: 13px;
}

.nutrition-form-copy small,
.nutrition-form-hint {
  color: #8a9a92;
  font-size: 11.5px;
}

.nutrition-form-row {
  margin-bottom: 0;
}

.nutrition-form-hint {
  margin: 2px 0 0;
  line-height: 1.7;
}

@media (max-width: 767px) {
  .nutrition-form-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .nutrition-form-toolbar .el-button {
    width: 100%;
  }
}

.form-section {
  display: grid;
  gap: 2px;
}

.kb-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.kb-form :deep(.el-form-item__label) {
  color: #49675a;
  font-size: 12px;
  font-weight: 650;
}

.dialog-footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.policy-note {
  margin-top: 8px;
}

@media (max-width: 767px) {
  .panel-title small {
    display: none;
  }

  .knowledge-table {
    font-size: 12px;
  }

  .row-actions {
    flex-wrap: wrap;
    gap: 6px;
  }
}

</style>
