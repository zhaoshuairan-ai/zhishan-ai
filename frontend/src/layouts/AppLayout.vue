<script setup lang="ts">

import { computed, ref, watch } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import { ElMessage, ElMessageBox } from 'element-plus'

import { useAuthStore } from '@/stores/auth'

import { useAppStore } from '@/stores/app'

import { useBreakpoint } from '@/composables/useBreakpoint'

import BrandMark from '@/components/BrandMark.vue'

import PantryReminder from '@/components/PantryReminder.vue'

import GlobalAiLauncher from '@/components/GlobalAiLauncher.vue'



const route = useRoute()

const router = useRouter()

const auth = useAuthStore()

// AI 食安智询官页面本身已有完整输入框，隐藏全局悬浮球避免遮挡
const showGlobalAiLauncher = computed(
  () =>
    auth.isAuthenticated &&
    route.name !== 'assistant' &&
    route.path !== '/assistant',
)

const app = useAppStore()

const { width } = useBreakpoint()



const drawerOpen = ref(false)



interface NavItem {

  name: string

  label: string

  icon: string

  short: string

  sub?: boolean

}



const navItems: NavItem[] = [

  { name: 'home', label: '仪表盘', icon: 'DataBoard', short: '首页' },

  { name: 'analyze', label: '开始检测', icon: 'Camera', short: '检测' },

  { name: 'knowledge', label: '智膳智库', icon: 'Reading', short: '智库' },

  { name: 'health-profile', label: '健康画像', icon: 'User', short: '画像' },

  { name: 'pantry', label: '家庭食材管家', icon: 'Food', short: '食材' },

  { name: 'assistant', label: 'AI 食安智询官', icon: 'ChatDotRound', short: '科普' },

  { name: 'settings', label: '设置', icon: 'Setting', short: '设置' },

]



const mobileNav: NavItem[] = [

  { name: 'home', label: '首页', icon: 'DataBoard', short: '首页' },

  { name: 'analyze', label: '检测', icon: 'Camera', short: '检测' },

  { name: 'knowledge', label: '智膳智库', icon: 'Reading', short: '智库' },

  { name: 'pantry', label: '家庭食材管家', icon: 'Food', short: '管家' },

  { name: 'settings', label: '我的', icon: 'User', short: '我的' },

]

const pageTitle = computed(() => (route.meta.title as string) || '智膳 AI')

const showBack = computed(() => !['home', 'login', 'admin-login'].includes(String(route.name || '')))

// 手机端返回键：非首页且确实存在上一级历史时才显示
const mobileCanGoBack = computed(() => {
  if (!showBack.value) return false
  return Boolean(window.history.state?.back)
})

const isDesktop = computed(() => width.value >= 768)

const userLabel = computed(() => auth.user?.display_name || auth.user?.username || '未登录')

const avatarText = computed(() => userLabel.value.slice(0, 1).toUpperCase())



watch(

  () => route.fullPath,

  () => {

    drawerOpen.value = false

  }

)



function isActive(name: string) {

  if (name === 'home') return route.name === 'home'

  if (name === 'history') return route.name === 'history' || route.name === 'result' || route.name === 'report'

  return route.name === name

}



function goBack() {

  const back = window.history.state?.back

  if (back) router.back()

  else router.push({ name: 'home' })

}



function navigate(name: string) {

  // 左侧导航属于同级切换，使用 replace 避免历史记录堆栈越来越深
  if (route.name !== name) router.replace({ name })

  drawerOpen.value = false

}



async function handleLogout() {

  try {

    await ElMessageBox.confirm('确定要退出登录吗？分析记录会保留在服务器，下次登录仍可查看。', '退出登录', {

      confirmButtonText: '退出',

      cancelButtonText: '取消',

      type: 'warning',

    })

  } catch {

    return

  }

  await auth.logout()

  ElMessage.success('已退出登录')

  router.push({ name: 'login' })

}



async function handleInstall() {

  const accepted = await app.promptInstall()

  if (accepted) ElMessage.success('已开始安装，可从主屏幕启动')

}

</script>



<template>

  <div class="app-shell">

    <!-- 桌面侧边导航 -->

    <aside v-if="isDesktop" class="app-sidebar">

      <div class="brand-area">

        <BrandMark />

      </div>

      <nav class="side-nav">

        <button

          v-for="item in navItems"

          :key="item.name"

          type="button"

          class="nav-item"

          :class="{ active: isActive(item.name), sub: item.sub }"

          @click="navigate(item.name)"

        >

          <el-icon><component :is="item.icon" /></el-icon>

          <span>{{ item.label }}</span>

        </button>

      </nav>

      <div class="side-footer">

        <div class="service-chip" :class="{ offline: !app.online }">

          <span class="dot" />

          {{ app.online ? '在线' : '离线' }}

        </div>

        <div class="version">v{{ app.settings?.app.version || '1.0.0' }}</div>

        <div v-if="auth.isAuthenticated" class="user-box">

          <el-dropdown trigger="click" placement="top-start">

            <div class="user-trigger">

              <div class="avatar">{{ avatarText }}</div>

              <div class="user-meta">

                <div class="user-name">{{ userLabel }}</div>

                <div class="user-role">

                  {{ auth.user?.is_demo ? '演示账号' : '普通账号' }}

                </div>

              </div>

              <el-icon class="caret"><ArrowUp /></el-icon>

            </div>

            <template #dropdown>

              <el-dropdown-menu>

                <el-dropdown-item @click="navigate('settings')">设置与帮助</el-dropdown-item>

                <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>

              </el-dropdown-menu>

            </template>

          </el-dropdown>

        </div>

        <el-button v-else type="primary" class="login-btn" @click="navigate('login')">登录 / 注册</el-button>

      </div>

    </aside>



    <!-- 移动端顶部栏 -->

    <header v-if="!isDesktop" class="mobile-header">
      <!-- 左侧固定区：九宫格常驻，二级页面再追加返回键 -->
      <div class="mobile-header-left">
        <button
          type="button"
          class="icon-btn"
          aria-label="打开菜单"
          title="打开菜单"
          @click="drawerOpen = true"
        >
          <el-icon><Menu /></el-icon>
        </button>

        <button
          v-if="mobileCanGoBack"
          type="button"
          class="icon-btn back-btn"
          aria-label="返回上一级"
          title="返回上一级"
          @click="goBack"
        >
          <el-icon><ArrowLeft /></el-icon>
        </button>
      </div>

      <!-- 中间标题区：绝对居中，不受两侧按钮影响 -->
      <div class="mobile-brand">
        <span class="mobile-title">{{ pageTitle }}</span>
      </div>

      <!-- 右侧固定区：只放铃铛通知 -->
      <div class="mobile-header-right">
        <PantryReminder />
      </div>
    </header>



    <!-- 桌面顶部条 -->

    <header v-if="isDesktop" class="app-header">

      <div class="header-left">

        <button v-if="showBack" type="button" class="back-btn" aria-label="返回上一级" title="返回上一级" @click="goBack">

          <el-icon><ArrowLeft /></el-icon>

          <span>返回</span>

        </button>

        <div class="header-title">

          <span class="crumb">智膳 AI</span>

          <el-icon class="crumb-sep"><ArrowRight /></el-icon>

          <span class="current">{{ pageTitle }}</span>

        </div>

      </div>

      <div class="header-actions">

        <span v-if="!app.online" class="chip chip-warn">离线模式</span>

        <PantryReminder />

        <el-button v-if="app.canInstall" text @click="handleInstall">

          <el-icon><Download /></el-icon>

          安装到主屏幕

        </el-button>

        <el-button text @click="navigate('knowledge')">

          <el-icon><Reading /></el-icon>

          智膳智库

        </el-button>

        <el-button v-if="auth.user?.role === 'admin'" text @click="router.push({ name: 'admin-dashboard' })">

          <el-icon><Setting /></el-icon>

          管理后台

        </el-button>

        <el-button type="primary" round @click="navigate('analyze')">

          <el-icon><Camera /></el-icon>

          开始检测

        </el-button>

      </div>

    </header>



    <main class="app-main pb-24 md:pb-0">

      <slot />

    </main>



    <!-- 移动端底部导航 -->

    <nav
      v-if="!isDesktop"
      class="mobile-tabbar fixed bottom-0 left-0 w-full z-50 md:hidden"
    >

      <button

        v-for="item in mobileNav"

        :key="item.name"

        type="button"

        class="tab-item"

        :class="{ active: isActive(item.name) }"

        @click="navigate(item.name)"

      >

        <el-icon><component :is="item.icon" /></el-icon>

        <span>{{ item.short }}</span>

      </button>

    </nav>



    <!-- 移动端抽屉菜单 -->

    <el-drawer v-model="drawerOpen" direction="ltr" size="78%" :with-header="false" class="nav-drawer">

      <div class="drawer-inner">

        <div class="drawer-brand">

          <BrandMark compact />

        </div>

        <nav class="drawer-nav">

          <button

            v-for="item in navItems"

            :key="item.name"

            type="button"

            class="drawer-item"

            :class="{ active: isActive(item.name), sub: item.sub }"

            @click="navigate(item.name)"

          >

            <el-icon><component :is="item.icon" /></el-icon>

            <span>{{ item.label }}</span>

            <el-icon class="arrow"><ArrowRight /></el-icon>

          </button>

        </nav>

        <div class="drawer-footer">

          <div v-if="auth.isAuthenticated" class="drawer-user">

            <div class="avatar">{{ avatarText }}</div>

            <div>

              <div class="user-name">{{ userLabel }}</div>

              <div class="user-role">{{ auth.user?.is_demo ? '演示账号（数据仅本账号可见）' : '已登录' }}</div>

            </div>

          </div>

          <div v-else class="drawer-guest">未登录 · 登录后可跨设备查看记录</div>

          <div class="drawer-actions">

            <el-button v-if="auth.user?.role === 'admin'" plain @click="router.push({ name: 'admin-dashboard' })">

              管理后台

            </el-button>

            <el-button v-if="auth.isAuthenticated" plain @click="handleLogout">退出登录</el-button>

            <el-button v-else type="primary" @click="navigate('login')">登录 / 注册</el-button>

            <PantryReminder />

        <el-button v-if="app.canInstall" text @click="handleInstall">安装应用</el-button>

          </div>

          <p class="drawer-note">

            版本 v{{ app.settings?.app.version || '1.0.0' }} ·

            {{ app.settings?.ai.configured ? 'AI 已配置' : '当前为规则/演示模式' }}

          </p>

        </div>

      </div>

    </el-drawer>

    <GlobalAiLauncher v-if="showGlobalAiLauncher" />

  </div>

</template>



<style scoped>

.app-shell {

  min-height: 100vh;

  background: var(--bg);

}



/* ---------- 桌面侧栏 ---------- */

.app-sidebar {

  position: fixed;

  inset: 0 auto 0 0;

  width: var(--sidebar-w);

  background: var(--card);

  border-right: 1px solid var(--border);

  display: flex;

  flex-direction: column;

  padding: 18px 14px 16px;

  z-index: 20;

}



.brand-area {

  padding: 2px 6px 18px;

}



.side-nav {

  display: flex;

  flex-direction: column;

  gap: 4px;

  flex: 1;

  overflow-y: auto;

}



.nav-item.sub {

  padding-left: 34px;

  font-size: 12.5px;

}



.nav-item {

  display: flex;

  align-items: center;

  gap: 10px;

  width: 100%;

  padding: 10px 12px;

  border: none;

  background: transparent;

  border-radius: 10px;

  color: var(--text-2);

  font-size: 14.5px;

  cursor: pointer;

  text-align: left;

  transition: background 0.16s ease, color 0.16s ease;

}



.nav-item:hover {

  background: var(--brand-50);

  color: var(--brand-600);

}



.nav-item.active {

  background: var(--brand-100);

  color: var(--brand-700);

  font-weight: 600;

}



.side-footer {

  border-top: 1px solid var(--border);

  padding-top: 12px;

  display: flex;

  flex-direction: column;

  gap: 8px;

}



.service-chip {

  display: inline-flex;

  align-items: center;

  gap: 6px;

  font-size: 12px;

  color: var(--ok);

}



.service-chip .dot {

  width: 7px;

  height: 7px;

  border-radius: 50%;

  background: var(--ok);

  box-shadow: 0 0 0 3px rgba(47, 158, 111, 0.15);

}



.service-chip.offline {

  color: var(--warn);

}



.service-chip.offline .dot {

  background: var(--warn);

  box-shadow: 0 0 0 3px rgba(196, 122, 8, 0.15);

}



.version {

  font-size: 11.5px;

  color: var(--muted);

}



.user-box {

  margin-top: 4px;

}



.user-trigger {

  display: flex;

  align-items: center;

  gap: 9px;

  padding: 8px;

  border-radius: 12px;

  background: var(--brand-50);

  cursor: pointer;

  width: 100%;

}



.avatar {

  width: 34px;

  height: 34px;

  border-radius: 50%;

  background: var(--brand);

  color: #fff;

  display: grid;

  place-items: center;

  font-weight: 700;

  font-size: 15px;

  flex: 0 0 auto;

}



.user-meta {

  min-width: 0;

  flex: 1;

}



.user-name {

  font-size: 13.5px;

  font-weight: 600;

  white-space: nowrap;

  overflow: hidden;

  text-overflow: ellipsis;

}



.user-role {

  font-size: 11.5px;

  color: var(--muted);

}



.caret {

  color: var(--muted);

  font-size: 12px;

}



.login-btn {

  width: 100%;

}



/* ---------- 桌面顶栏 ---------- */

.app-header {

  position: sticky;

  top: 0;

  z-index: 15;

  height: var(--header-h);

  margin-left: var(--sidebar-w);

  padding: 0 26px;

  background: rgba(255, 255, 255, 0.9);

  backdrop-filter: blur(8px);

  border-bottom: 1px solid var(--border);

  display: flex;

  align-items: center;

  justify-content: space-between;

  gap: 16px;

}



.header-left {

  display: flex;

  align-items: center;

  gap: 10px;

  min-width: 0;

}



.back-btn {

  display: inline-flex;

  align-items: center;

  gap: 4px;

  border: 1px solid #dce8e1;

  background: #fff;

  color: #49695a;

  border-radius: 8px;

  padding: 6px 9px;

  font-size: 12px;

  cursor: pointer;

  white-space: nowrap;

}



.back-btn:hover {

  border-color: #9bc7b0;

  color: #1f7a5f;

  background: #f5fbf7;

}



.back-btn .el-icon {

  font-size: 14px;

}



.header-title {

  display: flex;

  align-items: center;

  gap: 7px;

  font-size: 14px;

  color: var(--muted);

  min-width: 0;

}



.crumb-sep {

  font-size: 11px;

}



.current {

  color: var(--text);

  font-weight: 600;

  font-size: 15px;

  white-space: nowrap;

  overflow: hidden;

  text-overflow: ellipsis;

}



.header-actions {

  display: flex;

  align-items: center;

  gap: 6px;

}



/* ---------- 主区域 ---------- */

.app-main {

  margin-left: var(--sidebar-w);

  min-height: calc(100vh - var(--header-h));

}



/* ---------- 移动端 ---------- */

.mobile-header {

  position: sticky;

  top: 0;

  z-index: 15;

  height: 56px;

  display: flex;

  align-items: center;

  justify-content: space-between;

  gap: 8px;

  padding: 0 10px;

  background: rgba(255, 255, 255, 0.94);

  backdrop-filter: blur(8px);

  border-bottom: 1px solid var(--border);

}



.mobile-header-left,
.mobile-header-right {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.mobile-header-left {
  min-width: 40px;
  gap: 8px;
}

.mobile-header-right {
  gap: 0;
}

.mobile-header .back-btn {

  border: 0;

  background: transparent;

  padding: 0;

  width: 34px;

}

.icon-btn.compact {
  width: 32px;
  height: 32px;
  font-size: 17px;
}



.icon-btn {

  width: 40px;

  height: 40px;

  border: none;

  background: transparent;

  border-radius: 10px;

  display: grid;

  place-items: center;

  color: var(--text-2);

  font-size: 19px;

  cursor: pointer;

}



.icon-btn:active {

  background: var(--brand-50);

}



.mobile-brand {

  position: absolute;
  left: 50%;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  max-width: calc(100% - 184px);
  transform: translateX(-50%);
  pointer-events: none;

}



.mini-mark {

  width: 26px;

  height: 26px;

  border-radius: 8px;

  background: linear-gradient(140deg, var(--brand), #14a08c);

  color: #fff;

  display: grid;

  place-items: center;

  font-size: 14px;

  font-weight: 700;

  flex: 0 0 auto;

}



.mobile-title {

  max-width: 100%;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.2;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

}



.offline-dot {

  width: 9px;

  height: 9px;

  border-radius: 50%;

  background: var(--warn);

}



.mobile-tabbar {

  position: fixed;

  left: 0;

  right: 0;

  bottom: 0;

  z-index: 50;

  display: flex;

  width: 100%;
  min-height: var(--tabbar-h, 60px);

  background: rgba(255, 255, 255, 0.97);

  backdrop-filter: blur(10px);

  border-top: 1px solid var(--border);

  padding: 5px 4px calc(5px + env(safe-area-inset-bottom));

}



.tab-item {

  flex: 1;

  border: none;

  background: transparent;

  display: flex;

  flex-direction: column;

  align-items: center;

  gap: 2px;

  padding: 5px 0;

  color: var(--muted);

  font-size: 11px;

  cursor: pointer;

  border-radius: 10px;

  min-height: 48px;

}



.tab-item .el-icon {

  font-size: 20px;

}



.tab-item.active {

  color: var(--brand);

  font-weight: 600;

}



.tab-item:active {

  background: var(--brand-50);

}



/* ---------- 抽屉 ---------- */

.drawer-inner {

  display: flex;

  flex-direction: column;

  height: 100%;

  padding: 18px 14px calc(18px + env(safe-area-inset-bottom));

}



.drawer-brand {

  padding: 4px 6px 16px;

}



.drawer-nav {

  flex: 1;

  display: flex;

  flex-direction: column;

  gap: 2px;

  overflow-y: auto;

}



.drawer-item {

  display: flex;

  align-items: center;

  gap: 11px;

  padding: 13px 12px;

  border: none;

  background: transparent;

  border-radius: 11px;

  color: var(--text-2);

  font-size: 15px;

  text-align: left;

  width: 100%;

  cursor: pointer;

  min-height: 48px;

}



.drawer-item.sub {

  padding-left: 34px;

  font-size: 13.5px;

}



.drawer-item .arrow {

  margin-left: auto;

  color: var(--border-strong);

  font-size: 12px;

}



.drawer-item.active {

  background: var(--brand-100);

  color: var(--brand-700);

  font-weight: 600;

}



.drawer-footer {

  border-top: 1px solid var(--border);

  padding-top: 12px;

}



.drawer-user {

  display: flex;

  align-items: center;

  gap: 10px;

  margin-bottom: 10px;

}



.drawer-guest {

  font-size: 13px;

  color: var(--muted);

  margin-bottom: 10px;

}



.drawer-actions {

  display: flex;

  gap: 8px;

  flex-wrap: wrap;

}



.drawer-note {

  margin-top: 12px;

  font-size: 11.5px;

  color: var(--muted);

}



@media (max-width: 767px) {

  .app-main {

    margin-left: 0;

    /* 给固定底部导航留出空间，避免页面内容与输入框被盖住 */

    /* pb-24：底部导航约 60px + 24px 安全间距 + 安全区 */
    padding-bottom: calc(var(--tabbar-h, 60px) + env(safe-area-inset-bottom) + 36px);

  }

}



/* ---------- 专业营养师工作台：深橄榄绿侧栏 ---------- */
.app-sidebar {
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
  color: var(--sidebar-text);
}

.app-sidebar .brand-area :deep(.brand-name) {
  color: #ffffff;
}

.app-sidebar .brand-area :deep(.brand-name span) {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.12);
}

.app-sidebar .brand-area :deep(.brand-sub) {
  color: var(--sidebar-text);
}

.app-sidebar .side-footer {
  border-top-color: var(--sidebar-border);
}

.app-sidebar .nav-item {
  color: var(--sidebar-text);
}

.app-sidebar .nav-item:hover {
  background: rgba(255, 255, 255, 0.07);
  color: var(--sidebar-text-hover);
}

.app-sidebar .nav-item.active {
  background: var(--sidebar-active);
  color: #ffffff;
  font-weight: 650;
}

.app-sidebar .nav-item.active .el-icon {
  color: #ffffff;
}

.app-sidebar .service-chip {
  color: #b7d6c2;
}

.app-sidebar .version {
  color: var(--sidebar-text);
}

.app-sidebar .user-trigger {
  background: rgba(255, 255, 255, 0.06);
}

.app-sidebar .user-name {
  color: #ffffff;
}

.app-sidebar .user-role {
  color: var(--sidebar-text);
}

.app-sidebar .caret {
  color: var(--sidebar-text);
}

.app-sidebar .avatar {
  background: var(--sidebar-active);
}
</style>
