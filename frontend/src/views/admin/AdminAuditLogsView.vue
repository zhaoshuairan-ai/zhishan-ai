<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { adminApi, type AuditLogItem } from '@/api/admin'
import { ApiError } from '@/api/client'
import { useBreakpoint } from '@/composables/useBreakpoint'

const { isMobile } = useBreakpoint()
const loading = ref(false)
const errorMessage = ref('')
const items = ref<AuditLogItem[]>([])
const actions = ref<Array<{ value: string; label: string }>>([])
const page = ref(1)
const pages = ref(1)
const total = ref(0)
const filters = reactive({ action: '', actor: '', result: '' })
const expanded = ref<number | null>(null)

const resultType: Record<string, string> = { success: 'success', failure: 'danger', denied: 'warning' }

async function load(reset = false) {
  if (reset) page.value = 1
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await adminApi.auditLogs({
      action: filters.action,
      actor: filters.actor.trim(),
      result: filters.result,
      page: page.value,
      per_page: 20,
    })
    items.value = data.items
    actions.value = data.actions
    pages.value = data.pages
    total.value = data.total
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '加载失败'
  } finally {
    loading.value = false
  }
}

function toggleDetail(item: AuditLogItem) {
  expanded.value = expanded.value === item.id ? null : item.id
}

function formatTime(value: string) {
  return value ? value.replace('T', ' ').slice(0, 19) : '—'
}

function detailText(item: AuditLogItem) {
  return item.detail_text || '—'
}

onMounted(() => load())
</script>

<template>
  <div class="admin-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">操作审计</h1>
        <p class="page-sub">记录管理员登录、用户管理、知识库与规则变更、记录删除等操作；仅管理员可查看。</p>
      </div>
      <el-button :loading="loading" @click="load()">刷新</el-button>
    </header>

    <div class="filter-bar card">
      <el-input v-model="filters.actor" placeholder="操作人用户名" clearable @keyup.enter="load(true)" />
      <el-select v-model="filters.action" placeholder="操作类型">
        <el-option label="全部类型" value="" />
        <el-option v-for="item in actions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.result" placeholder="结果">
        <el-option label="全部结果" value="" />
        <el-option label="成功" value="success" />
        <el-option label="失败" value="failure" />
        <el-option label="被拒绝" value="denied" />
      </el-select>
      <el-button type="primary" @click="load(true)">查询</el-button>
    </div>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mb" />

    <div v-if="!isMobile()" v-loading="loading" class="card table-card">
      <el-table :data="items" size="small" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="操作人" width="120">
          <template #default="{ row }">{{ row.actor_username || '系统/未登录' }}</template>
        </el-table-column>
        <el-table-column prop="action_label" label="操作类型" width="150" />
        <el-table-column label="对象" min-width="150">
          <template #default="{ row }">
            <span>{{ row.target_label || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="plain"
              class="audit-result-pill"
              :class="`is-${row.result}`"
            >
              {{ row.result_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="详情" min-width="280">
          <template #default="{ row }">
            <span class="detail-text">{{ detailText(row) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else v-loading="loading" class="audit-cards">
      <div v-for="item in items" :key="item.id" class="card audit-card" @click="toggleDetail(item)">
        <div class="audit-head">
          <strong>{{ item.action_label }}</strong>
          <el-tag
            size="small"
            effect="plain"
            class="audit-result-pill"
            :class="`is-${item.result}`"
          >
            {{ item.result_label }}
          </el-tag>
        </div>
        <div class="audit-meta">
          <span>{{ item.actor_username || '系统/未登录' }} · {{ formatTime(item.created_at) }}</span>
          <span>{{ item.target_label || '—' }}</span>
        </div>
        <p v-if="expanded === item.id" class="audit-detail">{{ detailText(item) }}</p>
      </div>
      <div v-if="!items.length && !loading" class="empty-text">暂无审计日志</div>
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

.filter-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px;
  margin-bottom: 12px;
}

.filter-bar .el-input {
  flex: 1 1 180px;
}

.filter-bar .el-select {
  width: 150px;
}

.table-card {
  padding: 8px 10px;
}

.table-card :deep(.el-table .cell) {
  font-size: 12.5px;
  line-height: 1.55;
}

.table-card :deep(.el-table__row) {
  height: 58px;
}

.detail-text {
  color: #657b70;
  font-size: 12.5px;
  line-height: 1.65;
  word-break: break-word;
}

.audit-result-pill {
  border-radius: 999px;
  font-weight: 650;
}

.audit-result-pill.is-success {
  border-color: #c9ead8;
  background: #edf9f2;
  color: #24744f;
}

.audit-result-pill.is-failure {
  border-color: #f0cbc8;
  background: #fff2f0;
  color: #b23b32;
}

.audit-result-pill.is-denied {
  border-color: #f0dfb2;
  background: #fff9e9;
  color: #9a6a14;
}

.audit-cards {
  display: grid;
  gap: 10px;
}

.audit-card {
  padding: 12px 14px;
  cursor: pointer;
}

.audit-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.audit-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--muted);
}

.audit-detail {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.7;
  word-break: break-word;
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

.empty-text {
  text-align: center;
  color: var(--muted);
  padding: 18px;
  font-size: 13px;
}

@media (max-width: 767px) {
  .filter-bar .el-select {
    width: calc(50% - 4px);
  }
}
</style>
