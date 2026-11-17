<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAdminStore } from '@/stores/admin'
import { useAuthStore } from '@/stores/auth'
import { useBreakpoint } from '@/composables/useBreakpoint'
import BrandMark from '@/components/BrandMark.vue'

const route = useRoute()
const router = useRouter()
const admin = useAdminStore()
const auth = useAuthStore()
const { isDesktop } = useBreakpoint()
const drawerOpen = ref(false)

const items = [
  { name: 'admin-dashboard', path: '/admin/dashboard', label: '后台概览', icon: 'DataBoard' },
  { name: 'admin-users', path: '/admin/users', label: '用户管理', icon: 'User' },
  { name: 'admin-records', path: '/admin/records', label: '分析记录', icon: 'Tickets' },
  { name: 'admin-feedback', path: '/admin/feedback', label: '用户反馈', icon: 'ChatDotRound' },
  { name: 'admin-knowledge', path: '/admin/knowledge', label: '知识库管理', icon: 'Reading' },
  { name: 'admin-prompts', path: '/admin/prompts', label: 'Prompt 管理', icon: 'MagicStick' },
]

const advancedItems = [
  { name: 'admin-monitor', path: '/admin/monitor', label: '系统监控', icon: 'Monitor' },
  { name: 'admin-audit-logs', path: '/admin/audit-logs', label: '操作审计', icon: 'Document' },
]

const advancedOpen = ref(false)

const currentTitle = computed(() => (route.meta.title as string) || '管理后台')
const currentName = computed(() => String(route.name || ''))

function goBack() {
  const back = window.history.state?.back

  if (back) router.back()
  else router.push({ name: 'home' })
}

async function navigate(name: string, path?: string) {
  drawerOpen.value = false

  if (route.name === name) return

  try {
    // 显式传 path，避免只依赖路由 name 时被别名/嵌套路径解析失败
    if (path) await router.replace(path)
    else await router.replace({ name })
  } catch {
    ElMessage.error('页面打开失败，请刷新后重试')
  }
}

async function handleLogout() {
  await admin.logout()
  auth.clearAuth()
  ElMessage.success('已退出管理后台')
  router.replace({ name: 'admin-login' })
}

onMounted(() => {
  admin.ensureUser().catch(() => undefined)
  advancedOpen.value = advancedItems.some(
    (item) => item.name === currentName.value,
  )
})
</script>

<template>
  <div class="admin-shell">
    <!-- 桌面侧边栏 -->
    <aside v-if="isDesktop()" class="admin-side">
      <div class="admin-brand">
        <BrandMark compact />
      </div>
      <div class="admin-tag">管理后台</div>
      <nav class="admin-nav">
        <button
          v-for="item in items"
          :key="item.name"
          type="button"
          class="admin-nav-item"
          :class="{ active: currentName === item.name }"
          @click="navigate(item.name, item.path)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </button>

        <button
          type="button"
          class="admin-nav-item admin-nav-advanced"
          @click="advancedOpen = !advancedOpen"
        >
          <el-icon><Setting /></el-icon>
          <span>高级设置</span>
          <span class="admin-nav-chevron">{{ advancedOpen ? '⌃' : '⌄' }}</span>
        </button>

        <template v-if="advancedOpen">
          <button
            v-for="item in advancedItems"
            :key="item.name"
            type="button"
            class="admin-nav-item admin-nav-sub"
            :class="{ active: currentName === item.name }"
            @click="navigate(item.name, item.path)"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </button>
        </template>
      </nav>
      <div class="admin-side-footer">
        <div class="admin-user">
          <div class="avatar">{{ (admin.displayName || '管').slice(0, 1) }}</div>
          <div class="meta">
            <strong>{{ admin.displayName }}</strong>
            <small>管理员</small>
          </div>
        </div>
        <el-button text class="side-link" @click="router.push({ name: 'home' })">返回前台</el-button>
        <el-button text class="side-link danger" @click="handleLogout">退出登录</el-button>
      </div>
    </aside>

    <!-- 移动端顶栏 -->
    <header v-else class="admin-mobile-head">
      <button type="button" class="icon-btn" aria-label="返回上一级" title="返回上一级" @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <button type="button" class="icon-btn" aria-label="打开菜单" @click="drawerOpen = true">
        <el-icon><Menu /></el-icon>
      </button>
      <span class="mobile-title">{{ currentTitle }}</span>
      <button type="button" class="icon-btn" aria-label="退出登录" @click="handleLogout">
        <el-icon><SwitchButton /></el-icon>
      </button>
    </header>

    <main class="admin-main" :class="{ mobile: !isDesktop() }">
      <div class="admin-main-inner">
        <button v-if="isDesktop()" type="button" class="admin-back-btn" aria-label="返回上一级" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回上一级
        </button>
        <router-view />
      </div>
    </main>

    <el-drawer v-model="drawerOpen" direction="ltr" size="76%" :with-header="false">
      <div class="drawer-admin">
        <div class="admin-brand">
          <BrandMark compact />
        </div>
        <div class="admin-tag drawer-tag">管理后台</div>
        <nav class="admin-nav">
          <button
            v-for="item in items"
            :key="item.name"
            type="button"
            class="admin-nav-item"
            :class="{ active: currentName === item.name }"
            @click="navigate(item.name, item.path)"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </button>

          <button
            type="button"
            class="admin-nav-item admin-nav-advanced"
            @click="advancedOpen = !advancedOpen"
          >
            <el-icon><Setting /></el-icon>
            <span>高级设置</span>
            <span class="admin-nav-chevron">{{ advancedOpen ? '⌃' : '⌄' }}</span>
          </button>

          <template v-if="advancedOpen">
            <button
              v-for="item in advancedItems"
              :key="item.name"
              type="button"
              class="admin-nav-item admin-nav-sub"
              :class="{ active: currentName === item.name }"
              @click="navigate(item.name, item.path)"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </button>
          </template>
        </nav>
        <div class="drawer-footer">
          <el-button plain @click="router.push({ name: 'home' })">返回前台</el-button>
          <el-button type="danger" plain @click="handleLogout">退出登录</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.admin-shell {
  min-height: 100vh;
  background: #f7f9f7;
}

.admin-side {
  position: fixed;
  top: 0;
  bottom: 0;
  left: 0;
  width: 232px;
  background: #2e4233;
  color: #d7e5e1;
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
  z-index: 20;
}

.admin-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px 16px;
}

.admin-brand :deep(.brand-name) {
  color: #fff;
}

.admin-brand :deep(.brand-sub) {
  color: #8fb8ae;
}

.admin-tag {
  margin: -8px 6px 14px;
  font-size: 10.5px;
  letter-spacing: 2px;
  color: #8fb8ae;
}

.admin-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  margin-top: 6px;
}

.admin-nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 11px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: #b9d2cb;
  font-size: 13.5px;
  cursor: pointer;
  text-align: left;
}

.admin-nav-item:hover {
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
}

.admin-nav-item.active {
  background: #14796b;
  color: #fff;
}

.admin-nav-advanced {
  margin-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0;
  color: #8fb8ae;
}

.admin-nav-chevron {
  margin-left: auto;
  font-size: 11px;
}

.admin-nav-sub {
  padding-left: 27px;
  font-size: 12.5px;
}

.admin-side-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.admin-user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 8px;
}

.admin-user .avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #14796b;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 13px;
}

.admin-user .meta {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.admin-user strong {
  font-size: 12.5px;
  color: #fff;
}

.admin-user small {
  font-size: 10.5px;
  color: #8fb8ae;
}

.side-link {
  justify-content: flex-start;
  color: #b9d2cb !important;
}

.side-link.danger {
  color: #f0a79f !important;
}

.admin-main {
  margin-left: 232px;
  min-height: 100vh;
}

.admin-main.mobile {
  margin-left: 0;
  padding-top: 52px;
}

.admin-main-inner {
  padding: 20px 22px 40px;
  max-width: 1280px;
}

.admin-mobile-head {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 52px;
  z-index: 25;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  background: #0d2f2a;
  color: #fff;
}

.mobile-title {
  font-size: 14px;
  font-weight: 600;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  color: #fff;
  font-size: 18px;
  cursor: pointer;
}

.drawer-admin {
  display: flex;
  flex-direction: column;
  height: 100%;
  color: var(--text-1);
}

.drawer-admin .admin-brand :deep(.brand-name) {
  color: var(--text-1);
}

.drawer-admin .admin-brand :deep(.brand-sub) {
  color: var(--muted);
}

.drawer-tag {
  color: var(--muted);
}

.drawer-admin .admin-nav-item {
  color: var(--text-2);
}

.drawer-admin .admin-nav-item.active {
  background: var(--brand-50);
  color: var(--brand-700);
}

.drawer-footer {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.admin-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0 0 10px;
  border: 1px solid #dce8e1;
  background: #fff;
  color: #49695a;
  border-radius: 8px;
  padding: 5px 9px;
  font-size: 12px;
  cursor: pointer;
}

.admin-back-btn:hover {
  border-color: #9bc7b0;
  color: #1f7a5f;
}

@media (max-width: 1023px) {
  .admin-main-inner {
    padding: 14px 12px 32px;
  }
}

/* ---------- 管理后台侧栏同步品牌深橄榄绿 ---------- */
.admin-side {
  background: var(--sidebar-bg, #2e4233);
  border-right: 1px solid var(--sidebar-border, rgba(255, 255, 255, 0.08));
  color: var(--sidebar-text, #a3b1a6);
}

.admin-brand :deep(.brand-name) {
  color: #ffffff;
}

.admin-brand :deep(.brand-name span) {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.12);
}

.admin-brand :deep(.brand-sub) {
  color: var(--sidebar-text, #a3b1a6);
}

.admin-nav-item {
  color: var(--sidebar-text, #a3b1a6);
}

.admin-nav-item:hover {
  background: rgba(255, 255, 255, 0.07);
  color: #ffffff;
}

.admin-nav-item.active {
  background: var(--sidebar-active, #405a46);
  color: #ffffff;
}

.admin-tag {
  color: var(--sidebar-text, #a3b1a6);
}

.admin-side .side-link {
  color: var(--sidebar-text, #a3b1a6);
}

.admin-side .side-link:hover {
  color: #ffffff;
}
</style>
