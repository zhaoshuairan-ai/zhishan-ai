<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type PromptTemplateItem } from '@/api/admin'
import { ApiError } from '@/api/client'

const loading = ref(false)
const errorMessage = ref('')
const prompts = ref<PromptTemplateItem[]>([])
const savingId = ref(0)
const filter = ref<'all' | 'active' | 'draft'>('all')

const activeCount = computed(
  () => prompts.value.filter((item) => item.status === 'active').length,
)
const draftCount = computed(
  () => prompts.value.filter((item) => item.status === 'draft').length,
)
const filteredPrompts = computed(() => {
  if (filter.value === 'all') return prompts.value
  return prompts.value.filter((item) => item.status === filter.value)
})

const editOpen = ref(false)
const editingPrompt = ref<PromptTemplateItem | null>(null)
const editContent = ref('')
const editSaving = ref(false)

function setFilter(value: 'all' | 'active' | 'draft') {
  filter.value = value
}

function openEdit(item: PromptTemplateItem) {
  editingPrompt.value = item
  editContent.value = item.system_prompt || ''
  editOpen.value = true
}

async function saveEdit() {
  if (!editingPrompt.value) return
  if (!editContent.value.trim()) {
    ElMessage.warning('系统提示词不能为空')
    return
  }

  editSaving.value = true
  try {
    const data = await adminApi.updatePrompt(
      editingPrompt.value.id,
      editContent.value.trim(),
    )
    const index = prompts.value.findIndex(
      (row) => row.id === editingPrompt.value?.id,
    )
    if (index >= 0) prompts.value[index] = data.prompt
    ElMessage.success('✅ Prompt 已保存，版本号已更新')
    editOpen.value = false
  } catch (error) {
    ElMessage.error(
      (error as ApiError).message || 'Prompt 保存失败',
    )
  } finally {
    editSaving.value = false
  }
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await adminApi.prompts()
    prompts.value = data.items
  } catch (error) {
    errorMessage.value =
      (error as ApiError).message || 'Prompt 列表加载失败'
  } finally {
    loading.value = false
  }
}

async function publish(item: PromptTemplateItem) {
  savingId.value = item.id
  try {
    const data = await adminApi.publishPrompt(item.id)
    const index = prompts.value.findIndex((row) => row.id === item.id)
    if (index >= 0) prompts.value[index] = data.prompt
    ElMessage.success(`${item.name} 已发布，状态：生效中`)
  } catch (error) {
    ElMessage.error(
      (error as ApiError).message || '发布失败',
    )
  } finally {
    savingId.value = 0
  }
}

async function backToDraft(item: PromptTemplateItem) {
  savingId.value = item.id
  try {
    const data = await adminApi.draftPrompt(item.id)
    const index = prompts.value.findIndex((row) => row.id === item.id)
    if (index >= 0) prompts.value[index] = data.prompt
    ElMessage.success(`${item.name} 状态已变为草稿`)
  } catch (error) {
    ElMessage.error(
      (error as ApiError).message || '操作失败',
    )
  } finally {
    savingId.value = 0
  }
}

function formatTime(value: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

onMounted(load)
</script>

<template>
  <div class="admin-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">Prompt 管理</h1>
        <p class="page-sub">
          统一管理 AI 提示词模板、模型与版本；发布后状态变为“生效中”，草稿不会进入线上调用。
        </p>
      </div>
      <div class="head-actions">
        <el-tag
          type="success"
          effect="plain"
          class="stat-clickable"
          @click="setFilter('active')"
        >
          {{ activeCount }} 个生效模板
        </el-tag>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>
    </header>

    <div class="stat-strip">
      <span>提示词总数 {{ prompts.length }}</span>
      <button
        type="button"
        class="stat-clickable"
        :class="{ active: filter === 'active' }"
        @click="setFilter('active')"
      >
        生效 {{ activeCount }}
      </button>
      <button
        type="button"
        class="stat-clickable"
        :class="{ active: filter === 'draft' }"
        @click="setFilter('draft')"
      >
        草稿 {{ draftCount }}
      </button>
      <button
        type="button"
        class="stat-clickable"
        :class="{ active: filter === 'all' }"
        @click="setFilter('all')"
      >
        全部 {{ prompts.length }}
      </button>
      <span>模型 deepseek</span>
    </div>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      class="mb"
    />

    <div v-loading="loading" class="card table-card">
      <div v-if="!filteredPrompts.length && !loading" class="empty-text">
        当前筛选下暂无 Prompt 模板
      </div>

      <el-table v-else :data="filteredPrompts" size="small" stripe>
        <el-table-column prop="name" label="提示词名称" min-width="170">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
          </template>
        </el-table-column>

        <el-table-column prop="scene" label="使用场景" min-width="280" />

        <el-table-column prop="model" label="所属模型" width="120">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain">
              {{ row.model }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="version" label="版本号" width="100" />

        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.status === 'active' ? 'success' : 'warning'"
            >
              {{ row.status === 'active' ? '生效中' : '草稿' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">
            {{ formatTime(row.updated_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              text
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>

            <el-button
              v-if="row.status === 'draft'"
              size="small"
              type="primary"
              text
              :loading="savingId === row.id"
              @click="publish(row)"
            >
              发布
            </el-button>
            <el-button
              v-else
              size="small"
              type="warning"
              text
              :loading="savingId === row.id"
              @click="backToDraft(row)"
            >
              转为草稿
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <p class="publish-note">
      草稿状态说明：模板已保存但未发布，仅用于编辑和评审，不会进入 AI 实际调用链路。
    </p>
  </div>

    <el-drawer
      v-model="editOpen"
      title="编辑 Prompt"
      size="min(92vw, 760px)"
    >
      <div v-if="editingPrompt" class="prompt-edit-body">
        <div class="prompt-edit-meta">
          <strong>{{ editingPrompt.name }}</strong>
          <span>
            {{ editingPrompt.scene }} · 当前 {{ editingPrompt.version }}
          </span>
        </div>

        <label class="prompt-edit-label">系统提示词内容</label>
        <el-input
          v-model="editContent"
          type="textarea"
          :rows="16"
          maxlength="20000"
          show-word-limit
          placeholder="填写该 Prompt 的系统提示词..."
        />

        <div class="prompt-edit-footer">
          <el-button @click="editOpen = false">取消</el-button>
          <el-button
            type="primary"
            :loading="editSaving"
            @click="saveEdit"
          >
            保存并升级版本
          </el-button>
        </div>
      </div>
    </el-drawer>

</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.page-title {
  margin: 0;
  color: #173e32;
  font-size: 22px;
  font-weight: 800;
}

.page-sub {
  margin: 5px 0 0;
  color: #7b8f86;
  font-size: 12.5px;
  line-height: 1.6;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.stat-clickable {
  border: 1px solid #e1ece6;
  border-radius: 999px;
  background: #fff;
  color: #527064;
  font-family: inherit;
  font-size: 11.5px;
  padding: 5px 10px;
  cursor: pointer;
}

.stat-clickable:hover,
.stat-clickable.active {
  border-color: #b8ddcc;
  background: #edf8f2;
  color: #1f6b50;
}

.el-tag.stat-clickable {
  cursor: pointer;
}

.prompt-edit-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.prompt-edit-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  border-radius: 10px;
  background: #f4f8f6;
}

.prompt-edit-meta strong {
  color: #173e32;
  font-size: 14px;
}

.prompt-edit-meta span {
  color: #789086;
  font-size: 11.5px;
}

.prompt-edit-label {
  color: #3f6355;
  font-size: 12px;
  font-weight: 700;
}

.prompt-edit-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

.stat-strip span {
  padding: 5px 10px;
  border: 1px solid #e1ece6;
  border-radius: 999px;
  background: #fff;
  color: #527064;
  font-size: 11.5px;
}

.table-card {
  padding: 10px;
}

.empty-text {
  padding: 24px;
  color: #8a9e94;
  text-align: center;
  font-size: 13px;
}

.publish-note {
  margin: 10px 2px 0;
  color: #8a9e94;
  font-size: 11px;
  line-height: 1.6;
}
</style>
