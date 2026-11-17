import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  ADMIN_EXPIRED_EVENT,
  adminApi,
  cachedAdminUser,
  clearAdminSession,
  getAdminToken,
  setAdminSession,
  type AdminUser,
} from '@/api/admin'

/** 管理员会话：独立于普通用户 store，令牌存单独的 localStorage 键。 */
export const useAdminStore = defineStore('admin', () => {
  const token = ref<string>(getAdminToken())
  const user = ref<AdminUser | null>(cachedAdminUser())
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))
  const isAdmin = computed(() => token.value !== '' && user.value?.role === 'admin')
  const displayName = computed(() => user.value?.display_name || user.value?.username || '管理员')

  function apply(tokenValue: string, userValue: AdminUser) {
    token.value = tokenValue
    user.value = userValue
    setAdminSession(tokenValue, userValue)
  }

  function syncToken() {
    if (!token.value) token.value = getAdminToken()
    return token.value
  }

  function clear() {
    token.value = ''
    user.value = null
    clearAdminSession()
  }

  async function login(
    username: string,
    password: string,
    captcha?: { captcha_id: string; captcha_code: string }
  ) {
    loading.value = true
    try {
      const result = await adminApi.login(username, password, captcha)
      apply(result.token, result.user)
      return result
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    if (!token.value) return null
    const data = await adminApi.me()
    user.value = data.user
    return data
  }

  async function ensureUser() {
    if (!token.value) token.value = getAdminToken()
    if (!token.value) return false
    if (user.value?.role === 'admin') return true
    try {
      const data = await fetchMe()
      return data?.user.role === 'admin'
    } catch {
      clear()
      return false
    }
  }

  async function logout() {
    try {
      if (token.value) await adminApi.logout()
    } catch {
      /* 本地清理优先 */
    } finally {
      clear()
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener(ADMIN_EXPIRED_EVENT, () => {
      token.value = ''
      user.value = null
    })
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    isAdmin,
    displayName,
    syncToken,
    login,
    fetchMe,
    ensureUser,
    logout,
    clear,
  }
})
