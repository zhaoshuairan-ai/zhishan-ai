/**
 * Axios 封装：
 * - API 前缀来自环境变量 VITE_API_BASE_URL（默认 /api），绝不硬编码 localhost；
 * - 统一解包 { success, code, message, data } 结构；
 * - 统一错误对象 ApiError（含 HTTP 状态码与业务码）；
 * - 401 时清理登录态并广播事件，由路由/布局跳转登录页。
 */
import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import type { ApiResponse } from './types'

/**
 * API 基础地址解析：
 * 1. 显式配置 VITE_API_BASE_URL 时优先使用；
 * 2. 单服务部署（8000）与 Vite 代理（5173）使用同源 /api，手机访问最稳；
 * 3. 前端被部署到其他静态端口时，按当前浏览器 hostname 拼后端 8000。
 *
 * 不使用 localhost / 127.0.0.1，避免手机访问时指向手机自身。
 */
function resolveApiBase(): string {
  const configured = (import.meta.env.VITE_API_BASE_URL || '').trim()
  if (configured) {
    return configured.replace(/\/+$/, '')
  }

  if (typeof window === 'undefined') {
    return '/api'
  }

  const { protocol, hostname, port } = window.location

  // 8000 单服务、80/443 反向代理、5173 Vite 代理：同源请求即可。
  if (!port || port === '8000' || port === '80' || port === '443' || port === '5173') {
    return '/api'
  }

  // HTTPS 页面不能跨端口请求 HTTP 后端，交给反向代理处理。
  if (protocol === 'https:') {
    return '/api'
  }

  // 前端被其他静态服务器托管时，动态指向当前局域网 IP 的后端 8000。
  return `${protocol}//${hostname}:8000/api`
}

export const API_BASE = resolveApiBase()

export const TOKEN_KEY = 'fsai_token'
export const USER_KEY = 'fsai_user'
export const EXPIRES_KEY = 'fsai_token_expires'
export const AUTH_EXPIRED_EVENT = 'fsai:auth-expired'

export class ApiError extends Error {
  status: number
  code: number
  details?: unknown
  requestId?: string

  constructor(message: string, status = 0, code = 0, details?: unknown, requestId?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }

  get isNetworkError(): boolean {
    return this.status === 0
  }

  get isTimeout(): boolean {
    return this.code === 50400 || this.status === 504
  }

  get isAuth(): boolean {
    return this.status === 401
  }
}

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setSession(token: string, expiresAt?: string | null): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
    if (expiresAt) localStorage.setItem(EXPIRES_KEY, expiresAt)
  } catch {
    /* 隐私模式下 localStorage 可能不可用，退化为内存态 */
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(EXPIRES_KEY)
  } catch {
    /* ignore */
  }
}

export function cachedUser<T>(): T | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

export function cacheUser(user: unknown): void {
  try {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } catch {
    /* ignore */
  }
}

export const http = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
  headers: { Accept: 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
  }

  // FormData 必须由浏览器/Axios 自动生成 multipart/form-data 及 boundary。
  // 即使某个全局默认值写死了 JSON，这里也要在图片上传时移除。
  if (typeof FormData !== 'undefined' && config.data instanceof FormData && config.headers) {
    const headers = config.headers as unknown as {
      delete?: (name: string) => void
      [key: string]: unknown
    }
    if (typeof headers.delete === 'function') {
      headers.delete('Content-Type')
      headers.delete('content-type')
    } else {
      delete headers['Content-Type']
      delete headers['content-type']
    }
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiResponse<unknown>>) => {
    if (!error.response) {
      const message =
        error.code === 'ECONNABORTED' || error.message?.includes('timeout')
          ? '请求超时：分析可能仍在后台运行，请稍后到历史记录查看，或重试。'
          : '无法连接服务器：请检查网络连接，并确认后端服务已启动。'
      return Promise.reject(new ApiError(message, 0, error.code === 'ECONNABORTED' ? 50400 : 0))
    }
    const { status, data } = error.response
    const body = (data || {}) as ApiResponse<unknown>
    let message = body.message || '请求失败，请稍后重试'
    if (status === 413) message = '上传文件过大，请压缩图片后重试。'
    if (status === 401) {
      clearSession()
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
    }
    return Promise.reject(
      new ApiError(message, status, Number(body.code) || 0, (body as { details?: unknown }).details, body.request_id)
    )
  }
)

async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<ApiResponse<T>>(config)
  const body = response.data
  if (body && typeof body === 'object' && 'success' in body) {
    if (!body.success) {
      throw new ApiError(body.message || '请求失败', response.status, body.code, body.details, body.request_id)
    }
    return body.data as T
  }
  return body as unknown as T
}

async function postForm<T>(
  url: string,
  form: FormData,
  onProgress?: (percent: number) => void,
): Promise<T> {
  return request<T>({
    url,
    method: 'POST',
    data: form,
    timeout: 240000,
    // 不设置 Content-Type：浏览器会自动生成
    // multipart/form-data; boundary=...
    onUploadProgress: (event) => {
      if (!onProgress) return
      const total = event.total || 0
      if (total > 0) onProgress(Math.min(100, Math.round((event.loaded / total) * 100)))
    },
  })
}

export const api = {
  get<T>(url: string, params?: Record<string, unknown>, config?: AxiosRequestConfig): Promise<T> {
    return request<T>({ ...config, url, method: 'GET', params })
  },
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request<T>({ ...config, url, method: 'POST', data })
  },
  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request<T>({ ...config, url, method: 'PUT', data })
  },
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return request<T>({ ...config, url, method: 'DELETE' })
  },
  upload<T>(url: string, file: File, onProgress?: (percent: number) => void): Promise<T> {
    const form = new FormData()
    form.append('file', file)
    return postForm<T>(url, form, onProgress)
  },
  async blob(url: string): Promise<Blob> {
    const response = await http.get(url.replace(/^\/api/, ''), { responseType: 'blob' })
    return response.data as Blob
  },
}

/** 把后端返回的 /api/xxx 路径转换成当前 API 基地址下的完整路径 */
export function assetUrl(path: string): string {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE}${path.replace(/^\/api/, '')}`
}
