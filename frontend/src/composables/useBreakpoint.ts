import { onBeforeUnmount, onMounted, ref } from 'vue'

/** 视口断点：用于「桌面表格 / 手机卡片」等结构性切换，而不仅是 CSS 缩放。 */
export function useBreakpoint() {
  const width = ref(typeof window !== 'undefined' ? window.innerWidth : 1280)
  let timer: number | undefined

  const update = () => {
    window.clearTimeout(timer)
    timer = window.setTimeout(() => {
      width.value = window.innerWidth
    }, 120)
  }

  onMounted(() => {
    width.value = window.innerWidth
    window.addEventListener('resize', update, { passive: true })
    window.addEventListener('orientationchange', update)
  })

  onBeforeUnmount(() => {
    window.clearTimeout(timer)
    window.removeEventListener('resize', update)
    window.removeEventListener('orientationchange', update)
  })

  return {
    width,
    isMobile: () => width.value < 768,
    isTablet: () => width.value >= 768 && width.value < 1024,
    isDesktop: () => width.value >= 1024,
  }
}
