import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { systemApi } from '@/api'
import type { SettingsStatus } from '@/api/types'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export const useAppStore = defineStore('app', () => {
  const online = ref(typeof navigator !== 'undefined' ? navigator.onLine : true)
  const settings = ref<SettingsStatus | null>(null)
  const settingsLoading = ref(false)
  const settingsError = ref('')
  const installEvent = ref<BeforeInstallPromptEvent | null>(null)
  const installDismissed = ref(false)
  const networkInitialized = ref(false)

  const canInstall = computed(() => Boolean(installEvent.value) && !installDismissed.value)
  const isStandalone = computed(
    () =>
      typeof window !== 'undefined' &&
      (window.matchMedia('(display-mode: standalone)').matches ||
        (window.navigator as unknown as { standalone?: boolean }).standalone === true)
  )

  function initNetwork() {
    if (networkInitialized.value || typeof window === 'undefined') return
    networkInitialized.value = true
    window.addEventListener('online', () => {
      online.value = true
    })
    window.addEventListener('offline', () => {
      online.value = false
    })
    window.addEventListener('beforeinstallprompt', (event) => {
      event.preventDefault()
      installEvent.value = event as BeforeInstallPromptEvent
    })
  }

  async function loadSettings(force = false) {
    if (settings.value && !force) return settings.value
    settingsLoading.value = true
    settingsError.value = ''
    try {
      settings.value = await systemApi.settings()
      return settings.value
    } catch (error) {
      settingsError.value = (error as Error).message
      return null
    } finally {
      settingsLoading.value = false
    }
  }

  async function promptInstall() {
    if (!installEvent.value) return false
    await installEvent.value.prompt()
    const choice = await installEvent.value.userChoice
    installEvent.value = null
    if (choice.outcome === 'dismissed') installDismissed.value = true
    return choice.outcome === 'accepted'
  }

  function dismissInstall() {
    installDismissed.value = true
  }

  return {
    online,
    settings,
    settingsLoading,
    settingsError,
    installEvent,
    installDismissed,
    canInstall,
    isStandalone,
    initNetwork,
    loadSettings,
    promptInstall,
    dismissInstall,
  }
})
