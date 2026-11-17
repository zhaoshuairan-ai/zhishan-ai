/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface ImportMetaEnv {
  /** 后端 API 前缀，默认 /api；跨域部署时填完整地址，如 https://api.example.com/api */
  readonly VITE_API_BASE_URL?: string
  /** 是否注册 Service Worker（PWA） */
  readonly VITE_ENABLE_PWA?: string
  /** 前端站点名称 */
  readonly VITE_APP_TITLE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
