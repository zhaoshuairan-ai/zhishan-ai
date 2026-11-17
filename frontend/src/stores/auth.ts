import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi } from '@/api'
import { cacheUser, cachedUser, clearSession, getToken, setSession } from '@/api/client'
import { clearAdminSession } from '@/api/admin'
import type { AuthResult, User } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(getToken())
  const user = ref<User | null>(cachedUser<User>())
  const demoHint = ref<string | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))
  const displayName = computed(() => user.value?.display_name || user.value?.username || '未登录')
  const isDemoAccount = computed(() => Boolean(user.value?.is_demo))

  function applyAuth(result: AuthResult) {
    token.value = result.token
    user.value = result.user
    setSession(result.token, result.expires_at)
    cacheUser(result.user)
  }

  function clearAuth() {
    token.value = ''
    user.value = null
    demoHint.value = null
    clearSession()
    clearAdminSession()
  }

  async function login(
    username: string,
    password: string,
    captcha?: { captcha_id: string; captcha_code: string }
  ) {
    loading.value = true
    try {
      const result = await authApi.login(username, password, captcha)
      applyAuth(result)
      await fetchMe().catch(() => undefined)
      return result
    } finally {
      loading.value = false
    }
  }

  async function register(payload: { username: string; password: string; display_name?: string; email?: string }) {
    loading.value = true
    try {
      const result = await authApi.register(payload)
      applyAuth(result)
      return result
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    if (!token.value) return null
    const data = await authApi.me()
    user.value = data.user
    demoHint.value = data.demo_hint
    cacheUser(data.user)
    return data
  }

  async function updateProfile(displayName: string) {
    const data = await authApi.updateProfile(displayName)
    user.value = data.user
    cacheUser(data.user)
    return data
  }

  async function changePassword(oldPassword: string, newPassword: string) {
    const result = await authApi.changePassword(oldPassword, newPassword)
    applyAuth(result)
    await fetchMe().catch(() => undefined)
    return result
  }

  async function logout() {
    try {
      if (token.value) await authApi.logout()
    } catch {
      /* 即使服务端失败也要清理本地登录态 */
    } finally {
      clearAuth()
    }
  }

  return {
    token,
    user,
    demoHint,
    loading,
    isAuthenticated,
    displayName,
    isDemoAccount,
    login,
    changePassword,
    updateProfile,
    register,
    fetchMe,
    logout,
    clearAuth,
    applyAuth,
  }
})
