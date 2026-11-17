import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { applyUiPreferences, loadUiPreferences } from '@/utils/appearance'
import { useUiStore } from '@/stores/ui'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

import App from './App.vue'
import router from './router'
import './styles/main.css'

// 启动前先应用外观偏好，避免深色模式闪白
applyUiPreferences(loadUiPreferences())

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
useUiStore(pinia).init()
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 全量注册 Element Plus 图标，模板里可直接写 <el-icon><Camera /></el-icon>
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')

// PWA：只在生产构建中注册，避免开发时缓存干扰热更新
const pwaEnabled = import.meta.env.VITE_ENABLE_PWA !== 'false'
if (import.meta.env.PROD && pwaEnabled && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then(() => console.info('[PWA] Service Worker 已注册'))
      .catch((err) => console.warn('[PWA] Service Worker 注册失败', err))
  })
}
