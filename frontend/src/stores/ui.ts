import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  applyUiPreferences,
  loadUiPreferences,
  resolveAppearance,
  saveUiPreferences,
  type Appearance,
  type UiPreferences,
} from '@/utils/appearance'

export const useUiStore = defineStore('ui', () => {
  const preferences = ref<UiPreferences>(loadUiPreferences())
  const systemDark = ref(
    typeof window !== 'undefined' ? window.matchMedia?.('(prefers-color-scheme: dark)').matches : false
  )
  let mediaQuery: MediaQueryList | null = null

  const appearance = computed(() => preferences.value.appearance)
  const fontSize = computed(() => preferences.value.fontSize)
  const language = computed(() => preferences.value.language)
  const isDark = computed(() => resolveAppearance(appearance.value) === 'dark')

  function apply() {
    applyUiPreferences(preferences.value)
    saveUiPreferences(preferences.value)
  }

  function setAppearance(value: Appearance) {
    preferences.value.appearance = value
    apply()
  }

  function setFontSize(value: number) {
    const size = Math.min(20, Math.max(12, Math.round(Number(value) || 14)))
    preferences.value.fontSize = size
    apply()
  }

  function setLanguage(value: string) {
    preferences.value.language = value
    apply()
  }

  function onSystemChange(event: MediaQueryListEvent) {
    systemDark.value = event.matches
    if (preferences.value.appearance === 'system') apply()
  }

  function init() {
    apply()
    if (typeof window !== 'undefined' && window.matchMedia) {
      mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      systemDark.value = mediaQuery.matches
      mediaQuery.addEventListener('change', onSystemChange)
    }
  }

  function dispose() {
    mediaQuery?.removeEventListener('change', onSystemChange)
    mediaQuery = null
  }

  return {
    appearance,
    fontSize,
    language,
    isDark,
    init,
    dispose,
    setAppearance,
    setFontSize,
    setLanguage,
  }
})
