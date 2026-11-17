<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import OfflineBanner from '@/components/OfflineBanner.vue'
import { AUTH_EXPIRED_EVENT } from '@/api/client'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const app = useAppStore()
const auth = useAuthStore()

const isBlank = computed(() => route.meta.layout === 'blank')
const isAdminArea = computed(() => route.path.startsWith('/admin'))

const onVisibilityChange = () => refreshSession()
const onWindowFocus = () => refreshSession()

let lastSessionRefresh = 0

function refreshSession(force = false) {
  if (document.visibilityState !== 'visible') return
  if (!auth.isAuthenticated) return
  const now = Date.now()
  if (!force && now - lastSessionRefresh < 15000) return
  lastSessionRefresh = now
  auth.fetchMe().catch(() => undefined)
}

function onAuthExpired() {
  const wasSignedIn = auth.isAuthenticated
  auth.clearAuth()
  if (wasSignedIn && (route.meta.requiresAuth || route.name === 'home')) {
    ElMessage.warning('登录状态已失效，请重新登录')
    router.push({ name: 'login', query: { redirect: route.fullPath } })
  }
}

onMounted(() => {
  app.initNetwork()
  window.addEventListener(AUTH_EXPIRED_EVENT, onAuthExpired)
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('focus', onWindowFocus)
  if (auth.isAuthenticated) {
    auth.fetchMe().catch(() => undefined)
  }
  app.loadSettings().catch(() => undefined)
})

// 页面切换时刷新一次角色：被管理员提升后无需重新登录即可看到入口
watch(
  () => route.fullPath,
  () => refreshSession()
)

onBeforeUnmount(() => {
  window.removeEventListener(AUTH_EXPIRED_EVENT, onAuthExpired)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('focus', onWindowFocus)
})
</script>

<template>
  <OfflineBanner />
  <router-view v-if="isAdminArea" />
  <AppLayout v-else-if="!isBlank">
    <router-view v-slot="{ Component }">
      <component :is="Component" />
    </router-view>
  </AppLayout>
  <router-view v-else />
</template>
