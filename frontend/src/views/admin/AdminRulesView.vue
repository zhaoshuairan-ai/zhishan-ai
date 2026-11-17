<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type RuleItem, type RuleRevisionItem } from '@/api/admin'
import { ApiError } from '@/api/client'

const loading = ref(false)
const errorMessage = ref('')
const items = ref<RuleItem[]>([])
const stats = ref({ total: 0, enabled: 0, disabled: 0 })
const categories = ref<string[]>([])
const page = ref(1)
const pages = ref(1)
const total = ref(0)
const filters = reactive({ q: '', category: '', enabled: '' })

const dialogOpen = ref(false)
const editing = ref<RuleItem | null>(null)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  title: '',
  category: '字段完整性',
  description: '',
  basis: '',
  source_name: '',
  source_url: '',
  scope: '预包装食品标签（图片可见区域）',
  version: '1.0',
  effective_date: '',
  change_note: '',
})

const historyOpen = ref(false)
const historyLoading = ref(false)
const historyRule = ref<RuleItem | null>(null)
const revisions = ref<RuleRevisionItem[]>([])

const dialogTitle = computed(() => (editing.value ? '编辑核查规则' : '新增核查规则'))

// 版本差异中只展示中文字段名，避免把底层字段代码暴露给运营同学
const fieldLabels: Record<string, string> = {
  rule_id: '规则编号',
  title: '规则标题',
  category: '分类',
  description: '规则说明',
  basis: '核查依据',
  source_name: '来源名称',
  source_url: '来源链接',
  scope: '适用范围',
  version: '版本',
  effective_date: '生效日期',
  enabled: '启用状态',
  priority: '优先级',
  updated_at: '更新时间',
  created_at: '创建时间',
}

function fieldLabel(key: string) {
  return fieldLabels[key] || '其他字段'
}

async function load(reset = false) {
  if (reset) page.value = 1
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await adminApi.rules({
      q: filters.q.trim(),
      category: filters.category,
      enabled: filters.enabled,
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
    category: '字段完整性',
    description: '',
    basis: '',
    source_name: '',
    source_url: '',
    scope: '预包装食品标签（图片可见区域）',
    version: '1.0',
    effective_date: new Date().toISOString().slice(0, 10),
    change_note: '',
  })
  dialogOpen.value = true
}

function openEdit(rule: RuleItem) {
  editing.value = rule
  formError.value = ''
  Object.assign(form, {
    title: rule.title,
    category: rule.category,
    description: rule.description,
    basis: rule.basis,
    source_name: rule.source_name,
    source_url: rule.source_url || '',
    scope: rule.scope,
    version: rule.version,
    effective_date: rule.effective_date || '',
    change_note: '',
  })
  dialogOpen.value = true
}

async function save() {
  formError.value = ''
  if (!form.title.trim()) {
    formError.value = '规则标题不能为空'
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await adminApi.updateRule(editing.value.rule_id, { ...form })
      ElMessage.success('规则已更新，旧版本已保存')
    } else {
      const ruleId = window.prompt('请输入规则编号（字母/数字/下划线，例如 RULE_NEW_CHECK）') || ''
      if (!ruleId.trim()) {
        saving.value = false
        return
      }
      await adminApi.createRule({ ...form, rule_id: ruleId.trim() })
      ElMessage.success('规则已创建')
    }
    dialogOpen.value = false
    await load()
  } catch (error) {
    formError.value = (error as ApiError).message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function toggle(rule: RuleItem) {
  try {
    await adminApi.toggleRule(rule.rule_id, !rule.enabled)
    ElMessage.success(rule.enabled ? '规则已停用' : '规则已启用')
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '操作失败')
  }
}

async function openHistory(rule: RuleItem) {
  historyRule.value = rule
  historyOpen.value = true
  historyLoading.value = true
  try {
    const data = await adminApi.ruleRevisions(rule.rule_id)
    revisions.value = data.revisions
  } catch (error) {
    ElMessage.error((error as ApiError).message || '加载版本记录失败')
    revisions.value = []
  } finally {
    historyLoading.value = false
  }
}

function changedFields(item: RuleRevisionItem): string[] {
  if (!item.before || !item.after) return []
  const keys = new Set([...Object.keys(item.before), ...Object.keys(item.after)])
  const changed: string[] = []
  keys.forEach((key) => {
    if (JSON.stringify(item.before?.[key]) !== JSON.stringify(item.after?.[key])) changed.push(key)
  })
  return changed
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '（空）'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatTime(value: string | null) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

onMounted(() => load())
</script>

<template>
  <div class="admin-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">核查规则</h1>
        <p class="page-sub">维护规则来源、版本、生效日期、适用范围与启停；每次修改都会保留旧版本快照。</p>
      </div>
      <div class="head-actions">
        <el-button :loading="loading" @click="load()">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增规则</el-button>
      </div>
    </header>

    <div class="stat-strip">
      <span>全部 {{ stats.total }}</span>
      <span>启用 {{ stats.enabled }}</span>
      <span>停用 {{ stats.disabled }}</span>
    </div>

    <div class="filter-bar card">
      <el-input v-model="filters.q" placeholder="搜索规则编号或标题" clearable @keyup.enter="load(true)" />
      <el-select v-model="filters.category" placeholder="分类">
        <el-option label="全部分类" value="" />
        <el-option v-for="category in categories" :key="category" :label="category" :value="category" />
      </el-select>
      <el-select v-model="filters.enabled" placeholder="状态">
        <el-option label="全部状态" value="" />
        <el-option label="启用" value="true" />
        <el-option label="停用" value="false" />
      </el-select>
      <el-button type="primary" @click="load(true)">查询</el-button>
    </div>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mb" />

    <div v-loading="loading" class="rule-cards">
      <article v-for="rule in items" :key="rule.rule_id" class="card rule-card">
        <div class="rule-content">
          <div class="rule-head">
            <div class="rule-title-wrap">
              <strong class="rule-title">{{ rule.title }}</strong>
              <span class="rule-category">{{ rule.category }}</span>
            </div>

            <span class="rule-status" :class="rule.enabled ? 'is-enabled' : 'is-disabled'">
              {{ rule.enabled ? '启用' : '停用' }}
            </span>
          </div>

          <p class="rule-desc">{{ rule.description || '（无说明）' }}</p>

          <div class="rule-meta">
            <span>版本 {{ rule.version }}</span>
            <span>生效 {{ rule.effective_date || '—' }}</span>
            <span>更新 {{ formatTime(rule.updated_at) }}</span>
          </div>

          <div class="rule-source">
            <span><b>依据</b>{{ rule.basis || '—' }}</span>
            <span><b>来源</b>{{ rule.source_name || '—' }}</span>
          </div>
        </div>

        <div class="rule-actions">
          <el-button class="rule-action" size="small" plain @click="openEdit(rule)">
            编辑
          </el-button>
          <el-button
            class="rule-action"
            size="small"
            :type="rule.enabled ? 'warning' : 'success'"
            plain
            @click="toggle(rule)"
          >
            {{ rule.enabled ? '停用' : '启用' }}
          </el-button>
          <el-button class="rule-action" size="small" plain @click="openHistory(rule)">
            版本记录
          </el-button>
        </div>
      </article>
      <div v-if="!items.length && !loading" class="empty-text">没有符合条件的规则</div>
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

    <el-dialog v-model="dialogOpen" :title="dialogTitle" width="min(94vw, 640px)" top="6vh">
      <el-alert v-if="formError" :title="formError" type="error" show-icon :closable="false" class="mb" />
      <el-form label-position="top">
        <el-form-item label="规则标题" required>
          <el-input v-model="form.title" maxlength="120" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="分类">
            <el-input v-model="form.category" maxlength="40" />
          </el-form-item>
          <el-form-item label="版本">
            <el-input v-model="form.version" maxlength="20" />
          </el-form-item>
          <el-form-item label="生效日期">
            <el-input v-model="form.effective_date" placeholder="YYYY-MM-DD" maxlength="10" />
          </el-form-item>
        </div>
        <el-form-item label="规则说明">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="1000" />
        </el-form-item>
        <el-form-item label="核查依据">
          <el-input v-model="form.basis" type="textarea" :rows="2" maxlength="1000" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="来源名称">
            <el-input v-model="form.source_name" maxlength="200" />
          </el-form-item>
          <el-form-item label="来源链接">
            <el-input v-model="form.source_url" maxlength="300" placeholder="https://…" />
          </el-form-item>
        </div>
        <el-form-item label="适用范围">
          <el-input v-model="form.scope" maxlength="200" />
        </el-form-item>
        <el-form-item v-if="editing" label="变更说明（写入版本记录）">
          <el-input v-model="form.change_note" maxlength="300" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="historyOpen"
      :title="historyRule ? `版本记录 · ${historyRule.title}` : '版本记录'"
      size="min(94vw, 700px)"
    >
      <div v-loading="historyLoading">
        <div v-if="!revisions.length && !historyLoading" class="empty-text">暂无版本记录</div>
        <div v-for="item in revisions" :key="item.id" class="revision card">
          <div class="revision-head">
            <strong>{{ item.action_label }} · v{{ item.version }}</strong>
            <time>{{ formatTime(item.changed_at) }}</time>
          </div>
          <p class="revision-meta">{{ item.changed_by || '系统' }}<span v-if="item.note"> · {{ item.note }}</span></p>
          <div v-if="changedFields(item).length" class="diff">
            <div v-for="key in changedFields(item)" :key="key" class="diff-row">
              <span class="diff-key">{{ fieldLabel(key) }}</span>
              <div class="diff-values">
                <span class="before">{{ formatValue(item.before?.[key]) }}</span>
                <el-icon><Right /></el-icon>
                <span class="after">{{ formatValue(item.after?.[key]) }}</span>
              </div>
            </div>
          </div>
          <p v-else class="revision-meta">（仅启停状态变化或无字段差异）</p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
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

.rule-cards {
  display: grid;
  gap: 14px;
}

.rule-card {
  display: flex;
  gap: 18px;
  align-items: stretch;
  padding: 18px 18px 18px 20px;
  border: 1px solid #e7f0ea;
  border-radius: 14px;
  background: #fbfdfc;
  box-shadow: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.rule-card:hover {
  border-color: #cfe3d7;
  box-shadow: 0 6px 18px rgba(38, 84, 61, 0.05);
}

.rule-content {
  flex: 1;
  min-width: 0;
}

.rule-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.rule-title-wrap {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.rule-title {
  color: #274638;
  font-size: 14px;
  line-height: 1.5;
}

.rule-category {
  padding: 2px 8px;
  border-radius: 999px;
  background: #f0f6f2;
  color: #6b8175;
  font-size: 10.5px;
  font-weight: 600;
}

.rule-status {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.rule-status.is-enabled {
  background: #e9f8f0;
  color: #257a55;
}

.rule-status.is-disabled {
  background: #f0f2f1;
  color: #6d7d75;
}

.rule-desc {
  margin: 10px 0;
  color: #526b5f;
  font-size: 12.5px;
  line-height: 1.75;
}

.rule-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 10px;
}

.rule-meta span {
  padding: 2px 8px;
  border-radius: 999px;
  background: #f4f8f6;
  color: #7b8f84;
  font-size: 11px;
}

.rule-source {
  display: grid;
  gap: 5px;
  margin-bottom: 0;
  color: #7b8f84;
  font-size: 11.5px;
  line-height: 1.65;
}

.rule-source b {
  display: inline-block;
  min-width: 34px;
  margin-right: 6px;
  color: #4c6859;
  font-weight: 650;
}

.rule-actions {
  flex: 0 0 104px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  padding-left: 16px;
  border-left: 1px solid #edf4ef;
}

.rule-actions .rule-action {
  width: 100%;
  min-height: 32px;
  margin-left: 0;
  border-radius: 8px;
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

.revision {
  padding: 12px 14px;
  margin-bottom: 10px;
}

.revision-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.revision-head time {
  color: var(--muted);
  font-size: 11.5px;
}

.revision-meta {
  margin: 6px 0;
  font-size: 12px;
  color: var(--muted);
}

.diff {
  display: grid;
  gap: 6px;
}

.diff-row {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 8px;
  font-size: 12px;
  align-items: start;
}

.diff-key {
  color: var(--muted);
  word-break: break-all;
}

.diff-values {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  word-break: break-word;
}

.diff-values .before {
  background: #fdf1ef;
  border-radius: 4px;
  padding: 1px 5px;
}

.diff-values .after {
  background: #edf8f2;
  border-radius: 4px;
  padding: 1px 5px;
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
  }

  .rule-card {
    flex-direction: column;
    gap: 14px;
    padding: 16px;
  }

  .rule-actions {
    flex: 0 0 auto;
    flex-direction: row;
    width: 100%;
    padding: 12px 0 0;
    border-top: 1px solid #edf4ef;
    border-left: 0;
  }

  .rule-actions .rule-action {
    flex: 1;
  }
}
</style>
