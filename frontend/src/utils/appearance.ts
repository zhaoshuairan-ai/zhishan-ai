/** 外观与字号偏好：本地持久化，启动时立即应用，避免闪烁。 */
export type Appearance = 'light' | 'dark' | 'system'

export interface UiPreferences {
  appearance: Appearance
  fontSize: number
  language: string
}

const STORAGE_KEY = 'fsai_ui_preferences'
const DEFAULT_PREFERENCES: UiPreferences = { appearance: 'light', fontSize: 14, language: 'zh-CN' }

export function loadUiPreferences(): UiPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_PREFERENCES }
    const parsed = JSON.parse(raw) as Partial<UiPreferences>
    const appearance = ['light', 'dark', 'system'].includes(String(parsed.appearance))
      ? (parsed.appearance as Appearance)
      : DEFAULT_PREFERENCES.appearance
    const fontSize = Number(parsed.fontSize)
    return {
      appearance,
      fontSize: Number.isFinite(fontSize) && fontSize >= 12 && fontSize <= 20 ? Math.round(fontSize) : 14,
      language: typeof parsed.language === 'string' ? parsed.language : 'zh-CN',
    }
  } catch {
    return { ...DEFAULT_PREFERENCES }
  }
}

export function saveUiPreferences(preferences: UiPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
  } catch {
    /* 隐私模式忽略 */
  }
}

export function resolveAppearance(appearance: Appearance): 'light' | 'dark' {
  if (appearance === 'system') {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return appearance
}

export function applyUiPreferences(preferences: UiPreferences): void {
  if (typeof document === 'undefined') return
  const resolved = resolveAppearance(preferences.appearance)
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.dataset.theme = resolved
  root.dataset.appearance = preferences.appearance
  root.style.colorScheme = resolved === 'dark' ? 'dark' : 'light'
  root.style.setProperty('--chat-font-size', `${preferences.fontSize}px`)
  root.lang = preferences.language || 'zh-CN'
}
