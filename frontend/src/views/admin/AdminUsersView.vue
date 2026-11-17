<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type AdminUserItem } from '@/api/admin'
import { ApiError } from '@/api/client'
import { useAdminStore } from '@/stores/admin'
import { useBreakpoint } from '@/composables/useBreakpoint'

const { isMobile } = useBreakpoint()
const adminStore = useAdminStore()
const loading = ref(false)
const errorMessage = ref('')
const items = ref<AdminUserItem[]>([])
const stats = ref({ total: 0, active: 0, disabled: 0, admin: 0 })
const page = ref(1)
const pages = ref(1)
const total = ref(0)
const filters = reactive({ q: '', status: '', role: '' })

type UserTab = 'all' | 'active' | 'disabled' | 'admin'
const activeTab = ref<UserTab>('all')

function syncActiveTab() {
  if (filters.role === 'admin') {
    activeTab.value = 'admin'
  } else if (filters.status === 'active') {
    activeTab.value = 'active'
  } else if (filters.status === 'disabled') {
    activeTab.value = 'disabled'
  } else {
    activeTab.value = 'all'
  }
}

function selectTab(tab: UserTab) {
  activeTab.value = tab

  if (tab === 'active') {
    filters.status = 'active'
    filters.role = ''
  } else if (tab === 'disabled') {
    filters.status = 'disabled'
    filters.role = ''
  } else if (tab === 'admin') {
    filters.status = ''
    filters.role = 'admin'
  } else {
    filters.status = ''
    filters.role = ''
  }

  load(true)
}

const visibleItems = computed(() =>
  items.value.filter((user) => {
    const name = String(user.username || '').trim()
    if (!name) return false
    if (/^\d{1,4}$/.test(name)) return false
    return !/^(asd|asdf|qwe|test|111|123|abc|aaa)$/i.test(name)
  }),
)

const tempPassword = ref('')
const tempDialog = ref(false)
const tempUser = ref('')

type UserAction = 'status' | 'role' | 'remove' | 'password'
const busyActions = ref<Set<string>>(new Set())
const currentUserId = computed(() => Number(adminStore.user?.id || 0))

function actionKey(user: AdminUserItem, action: UserAction) {
  return `${user.id}:${action}`
}

function isUserBusy(user: AdminUserItem, action: UserAction) {
  return busyActions.value.has(actionKey(user, action))
}

function setUserBusy(user: AdminUserItem, action: UserAction, value: boolean) {
  const next = new Set(busyActions.value)
  if (value) next.add(actionKey(user, action))
  else next.delete(actionKey(user, action))
  busyActions.value = next
}

function isSelf(user: AdminUserItem) {
  return Boolean(currentUserId.value && user.id === currentUserId.value)
}

function showActionError() {
  ElMessage.error('✖ 操作失败，请稍后重试')
}

const hasPrev = computed(() => page.value > 1)
const hasNext = computed(() => page.value < pages.value)

function roleLabel(role: string) {
  return role === 'admin' ? '管理员' : '普通用户'
}

async function load(reset = false) {
  if (reset) page.value = 1
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await adminApi.users({
      q: filters.q.trim(),
      status: filters.status,
      role: filters.role,
      page: page.value,
      per_page: 20,
    })
    items.value = data.items
    stats.value = data.stats
    pages.value = data.pages
    total.value = data.total
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function toggleActive(user: AdminUserItem) {
  if (isSelf(user)) {
    ElMessage.warning('不能停用当前登录的管理员账号')
    return
  }

  const next = !user.is_active
  const confirmed = window.confirm(
    next ? `确定要恢复该用户吗？` : '确定要停用该用户吗？',
  )
  if (!confirmed) return

  setUserBusy(user, 'status', true)
  try {
    await adminApi.updateUserStatus(
      user.id,
      next ? 'active' : 'disabled',
    )
    ElMessage.success('✅ 用户状态已更新')
    await load()
  } catch (error) {
    console.error(error)
    showActionError()
  } finally {
    setUserBusy(user, 'status', false)
  }
}

async function toggleRole(user: AdminUserItem) {
  if (isSelf(user)) {
    ElMessage.warning('不能修改当前登录账号的角色')
    return
  }

  const next = user.role === 'admin' ? 'user' : 'admin'
  const confirmed = window.confirm(
    next === 'admin'
      ? `确定将「${user.username}」设为管理员吗？`
      : `确定取消「${user.username}」的管理员权限吗？`,
  )
  if (!confirmed) return

  setUserBusy(user, 'role', true)
  try {
    await adminApi.setUserRole(user.id, next)
    ElMessage.success('✅ 用户角色已更新')
    await load()
  } catch (error) {
    console.error(error)
    showActionError()
  } finally {
    setUserBusy(user, 'role', false)
  }
}

async function deleteUser(user: AdminUserItem) {
  if (isSelf(user)) {
    ElMessage.warning('不能删除当前登录的管理员账号')
    return
  }

  if (!window.confirm('确定要删除该用户吗？')) return

  setUserBusy(user, 'remove', true)
  try {
    await adminApi.deleteUser(user.id)
    ElMessage.success('🗑️ 用户已删除')
    await load()
  } catch (error) {
    console.error(error)
    showActionError()
  } finally {
    setUserBusy(user, 'remove', false)
  }
}

async function resetPassword(user: AdminUserItem) {
  if (!window.confirm(`确定要重置「${user.username}」的密码吗？`)) {
    return
  }

  setUserBusy(user, 'password', true)
  try {
    const data = await adminApi.resetPassword(user.id)
    tempUser.value = user.username
    tempPassword.value = data.temporary_password
    tempDialog.value = true
    ElMessage.success('✅ 临时密码已生成')
  } catch (error) {
    console.error(error)
    showActionError()
  } finally {
    setUserBusy(user, 'password', false)
  }
}

async function copyPassword() {
  try {
    await navigator.clipboard.writeText(tempPassword.value)
    ElMessage.success('已复制临时密码')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
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
        <h1 class="page-title">用户管理</h1>
        <p class="page-sub">可搜索、按状态与角色筛选；密码永不显示，只能通过重置流程生成临时密码。</p>
      </div>
      <el-button :loading="loading" @click="load()">刷新</el-button>
    </header>

    <div class="stat-strip user-tabs">
      <button
        type="button"
        class="user-tab"
        :class="{ active: activeTab === 'all' }"
        @click="selectTab('all')"
      >
        全部 <b>{{ stats.total }}</b>
      </button>
      <button
        type="button"
        class="user-tab"
        :class="{ active: activeTab === 'active' }"
        @click="selectTab('active')"
      >
        启用 <b>{{ stats.active }}</b>
      </button>
      <button
        type="button"
        class="user-tab"
        :class="{ active: activeTab === 'disabled' }"
        @click="selectTab('disabled')"
      >
        停用 <b>{{ stats.disabled }}</b>
      </button>
      <button
        type="button"
        class="user-tab"
        :class="{ active: activeTab === 'admin' }"
        @click="selectTab('admin')"
      >
        管理员 <b>{{ stats.admin }}</b>
      </button>
    </div>

    <div class="filter-bar card">
      <el-input v-model="filters.q" placeholder="搜索用户名或昵称" clearable @keyup.enter="load(true)" />
      <el-select
        v-model="filters.status"
        placeholder="账号状态"
        clearable
        @change="syncActiveTab"
      >
        <el-option label="全部状态" value="" />
        <el-option label="启用" value="active" />
        <el-option label="停用" value="disabled" />
      </el-select>
      <el-select
        v-model="filters.role"
        placeholder="角色"
        clearable
        @change="syncActiveTab"
      >
        <el-option label="全部角色" value="" />
        <el-option label="普通用户" value="user" />
        <el-option label="管理员" value="admin" />
      </el-select>
      <el-button type="primary" @click="load(true)">查询</el-button>
    </div>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mb" />

    <!-- 桌面表格 -->
    <div v-if="!isMobile()" v-loading="loading" class="card table-card">
      <el-table :data="visibleItems" size="small" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="display_name" label="昵称" min-width="110" />
        <el-table-column label="角色" width="90">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'warning' : 'info'" size="small">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '启用' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="record_count" label="记录数" width="80" />
        <el-table-column label="最近登录" width="160">
          <template #default="{ row }">{{ formatTime(row.last_login_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :type="row.is_active ? 'danger' : 'success'"
              text
              :loading="isUserBusy(row, 'status')"
              :disabled="isSelf(row) || isUserBusy(row, 'status')"
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '停用' : '恢复' }}
            </el-button>
            <el-button
              size="small"
              text
              type="primary"
              :loading="isUserBusy(row, 'password')"
              @click="resetPassword(row)"
            >
              重置密码
            </el-button>
            <el-button
              size="small"
              text
              type="warning"
              :loading="isUserBusy(row, 'role')"
              :disabled="isSelf(row) || isUserBusy(row, 'role')"
              @click="toggleRole(row)"
            >
              {{ row.role === 'admin' ? '取消管理员' : '设为管理员' }}
            </el-button>
            <el-button
              size="small"
              text
              type="danger"
              :loading="isUserBusy(row, 'remove')"
              :disabled="isSelf(row) || isUserBusy(row, 'remove')"
              @click="deleteUser(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 手机端卡片 -->
    <div v-else v-loading="loading" class="user-cards">
      <div v-for="user in visibleItems" :key="user.id" class="card user-card">
        <div class="user-head">
          <strong>{{ user.username }}</strong>
          <el-tag :type="user.is_active ? 'success' : 'danger'" size="small">
            {{ user.is_active ? '启用' : '已停用' }}
          </el-tag>
        </div>
        <div class="user-meta">
          <span>{{ user.display_name }} · {{ roleLabel(user.role) }} · {{ user.record_count }} 条记录</span>
          <span>最近登录：{{ formatTime(user.last_login_at) }}</span>
        </div>
        <div class="user-actions">
          <el-button
            size="small"
            :type="user.is_active ? 'danger' : 'success'"
            plain
            :loading="isUserBusy(user, 'status')"
            :disabled="isSelf(user) || isUserBusy(user, 'status')"
            @click="toggleActive(user)"
          >
            {{ user.is_active ? '停用' : '恢复' }}
          </el-button>
          <el-button
            size="small"
            plain
            type="primary"
            :loading="isUserBusy(user, 'password')"
            @click="resetPassword(user)"
          >
            重置密码
          </el-button>
          <el-button
            size="small"
            plain
            type="warning"
            :loading="isUserBusy(user, 'role')"
            :disabled="isSelf(user) || isUserBusy(user, 'role')"
            @click="toggleRole(user)"
          >
            {{ user.role === 'admin' ? '取消管理员' : '设为管理员' }}
          </el-button>
          <el-button
            size="small"
            plain
            type="danger"
            :loading="isUserBusy(user, 'remove')"
            :disabled="isSelf(user) || isUserBusy(user, 'remove')"
            @click="deleteUser(user)"
          >
            删除
          </el-button>
        </div>
      </div>
      <div v-if="!visibleItems.length && !loading" class="empty-text">没有符合条件的用户</div>
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

    <el-dialog v-model="tempDialog" title="临时密码（仅显示一次）" width="min(92vw, 420px)">
      <p class="temp-tip">用户「{{ tempUser }}」的临时密码：</p>
      <div class="temp-password">{{ tempPassword }}</div>
      <p class="temp-tip">请通过安全渠道转交，并提醒用户登录后立即修改。该密码不会再次显示。</p>
      <template #footer>
        <el-button @click="copyPassword">复制</el-button>
        <el-button type="primary" @click="tempDialog = false">我已记录</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.page-sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--muted);
}

.stat-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  margin-bottom: 8px;
  border-bottom: 1px solid #e8eff2;
  padding: 0 4px;
  font-size: 13px;
  color: var(--text-2);
}

.user-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 8px 2px 10px;
  border: 0;
  background: transparent;
  color: #6f7f82;
  font: inherit;
  cursor: pointer;
  transition: color 0.18s ease;
}

.user-tab b {
  display: inline-flex;
  min-width: 18px;
  justify-content: center;
  padding: 1px 5px;
  border-radius: 999px;
  background: #eef5f3;
  color: #7d8f91;
  font-size: 10.5px;
  font-weight: 600;
}

.user-tab:hover {
  color: #10b981;
}

.user-tab.active {
  color: #10b981;
  font-weight: 700;
}

.user-tab.active b {
  background: #ecfdf5;
  color: #10b981;
}

.user-tab.active::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  border-radius: 999px;
  background: #10b981;
  content: "";
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px;
  margin-bottom: 12px;
}

.filter-bar .el-input {
  flex: 1 1 200px;
}

.filter-bar .el-select {
  width: 140px;
}

.table-card {
  padding: 8px 10px;
}

.user-cards {
  display: grid;
  gap: 10px;
}

.user-card {
  padding: 12px 14px;
}

.user-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 6px 0 10px;
  font-size: 12px;
  color: var(--muted);
}

.user-actions {
  display: flex;
  gap: 8px;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.temp-tip {
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.7;
  margin: 0 0 8px;
}

.temp-password {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 20px;
  letter-spacing: 1px;
  background: #f4f8f6;
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 12px;
  text-align: center;
  margin-bottom: 10px;
}

@media (max-width: 767px) {
  .filter-bar .el-select {
    width: calc(50% - 4px);
    flex: 1 1 calc(50% - 4px);
  }
}
</style>
