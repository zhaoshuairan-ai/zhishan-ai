/**
 * 管理员后台 API 客户端。
 *
 * 与前台使用同一后端、同一数据库，但使用独立的 localStorage 令牌键，
 * 避免管理员会话与普通用户会话互相覆盖。
 */
import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { API_BASE, ApiError, TOKEN_KEY } from './client'
import type { ApiResponse, RecordDetail, RecordSummary, User } from './types'

export const ADMIN_TOKEN_KEY = 'fsai_admin_token'
export const ADMIN_USER_KEY = 'fsai_admin_user'
export const ADMIN_EXPIRED_EVENT = 'fsai:admin-expired'

export interface AdminUser extends User {
  role: 'admin' | 'user'
}

export interface AdminOverview {
  totals: {
    users: number
    users_active: number
    users_disabled: number
    users_admin: number
    users_new_7d: number
    records: number
    analyzed: number
    failed: number
    success_rate: number
    real_records: number
    knowledge: number
    knowledge_published: number
    knowledge_draft: number
    assistant_entries: number
    rules: number
    rules_enabled: number
    feedback_open: number
  }
  trend: Array<{ date: string; count: number }>
  status_distribution: Array<{ status: string; count: number }>
  recent_audit: AuditLogItem[]
  generated_at: string
}

export interface AuditLogItem {
  id: number
  actor_username: string
  action: string
  action_label: string
  target_type: string
  target_id: string
  target_label: string
  detail: Record<string, unknown>
  detail_text: string
  result: string
  result_label: string
  ip: string
  created_at: string
}

export interface AdminUserItem extends User {
  role: 'admin' | 'user'
  is_active: boolean
  last_login_at: string | null
  record_count: number
}

export interface AdminUserList {
  items: AdminUserItem[]
  total: number
  page: number
  per_page: number
  pages: number
  stats: { total: number; active: number; disabled: number; admin: number }
}

export interface AdminRecordItem extends RecordSummary {
  username: string
  note_count: number
}

export interface AdminRecordList {
  items: AdminRecordItem[]
  total: number
  page: number
  per_page: number
  pages: number
  status_options: Array<{ value: string; label: string }>
}

export interface AdminRecordDetail extends RecordDetail {
  owner: { id: number; username: string; display_name: string; is_demo: boolean } | null
  notes: Array<{ id: number; admin_username: string; content: string; created_at: string }>
  feedback: FeedbackItem[]
}

export interface FeedbackItem {
  id: number
  user_id: number
  record_id: number | null
  content: string
  contact: string
  status: 'open' | 'resolved'
  status_label: string
  reply: string
  handled_by: string
  created_at: string
  updated_at: string
  username?: string
}

export interface PromptTemplateItem {
  id: number
  name: string
  scene: string
  model: string
  version: string
  system_prompt: string
  status: 'active' | 'draft'
  status_label: string
  updated_at: string | null
}

export interface AdminKnowledgeItem {
  id: number
  slug: string
  title: string
  category: string
  category_label: string
  summary: string
  content?: string
  scope: string
  source_name: string
  source_url: string | null
  source_type: string
  source_type_label: string
  is_ai_generated?: boolean
  source_kind?: 'ai' | 'local'
  verification_status: 'verified' | 'pending'
  verification_label: string
  status: 'published' | 'draft' | 'offline'
  version: string
  published_at: string | null
  updated_by: string
  updated_at: string
  is_featured: boolean
  usage_note?: string
  aliases?: string[]
  keywords?: string[]
  calories?: number
  carbs?: number
  protein?: number
  fat?: number
  calories_per_100g?: number
  carbs_per_100g?: number
  protein_per_100g?: number
  fat_per_100g?: number
  typical_portion_g?: number
}

export interface NutritionAIResult {
  status: 'success' | 'failed' | 'skipped'
  message: string
  filled_fields: string[]
}

export interface AdminKnowledgeList {
  items: AdminKnowledgeItem[]
  total: number
  page: number
  per_page: number
  pages: number
  categories: Array<{ value: string; label: string }>
  stats: { total: number; published: number; draft: number; offline: number; pending?: number; verified?: number; ai?: number; local?: number }
}

export interface RuleItem {
  id: number
  rule_id: string
  title: string
  category: string
  level_default: string
  description: string
  basis: string
  source_name: string
  source_url: string | null
  scope: string
  version: string
  effective_date: string | null
  enabled: boolean
  created_by: string
  updated_by: string
  updated_at: string
}

export interface RuleList {
  items: RuleItem[]
  total: number
  page: number
  per_page: number
  pages: number
  categories: string[]
  stats: { total: number; enabled: number; disabled: number }
}

export interface RuleRevisionItem {
  id: number
  rule_id: string
  action: string
  action_label: string
  version: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  changed_by: string
  note: string
  changed_at: string
}

export interface MonitorData {
  services: {
    ocr: { provider: string; is_demo: boolean; vision_configured: boolean; status: string }
    ai: { provider: string; configured: boolean; model: string | null; mode: string }
    assistant: { dedicated_llm: boolean; model: string | null; general_answer: boolean }
  }
  requests: {
    records_total: number
    records_24h: number
    records_7d: number
    failed_total: number
    failed_24h: number
    ocr_total: number
    ocr_failed: number
    ai_total: number
    errors_24h: number
  }
  performance: { avg_ocr_ms: number; max_ocr_ms: number }
  recent_errors: Array<{ id: number; kind: string; level: string; message: string; detail: Record<string, unknown>; created_at: string }>
  generated_at: string
  note: string
}

export interface AdminMeta {
  knowledge_categories: Array<{ value: string; label: string }>
  source_types: Array<{ value: string; label: string }>
  verification: Array<{ value: string; label: string }>
  knowledge_status: Array<{ value: string; label: string }>
  record_status: Array<{ value: string; label: string }>
  audit_actions: Array<{ value: string; label: string }>
  audit_results: Array<{ value: string; label: string }>
  feedback_status: Array<{ value: string; label: string }>
}

export interface AuditLogList {
  items: AuditLogItem[]
  total: number
  page: number
  per_page: number
  pages: number
  actions: Array<{ value: string; label: string }>
}

export function getAdminToken(): string {
  try {
    // 管理员可能从普通登录页登录：此时复用同一个会话令牌，无需二次登录
    return localStorage.getItem(ADMIN_TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setAdminSession(token: string, user: unknown): void {
  try {
    localStorage.setItem(ADMIN_TOKEN_KEY, token)
    localStorage.setItem(ADMIN_USER_KEY, JSON.stringify(user))
  } catch {
    /* ignore */
  }
}

export function clearAdminSession(): void {
  try {
    localStorage.removeItem(ADMIN_TOKEN_KEY)
    localStorage.removeItem(ADMIN_USER_KEY)
  } catch {
    /* ignore */
  }
}

export function cachedAdminUser(): AdminUser | null {
  try {
    const raw = localStorage.getItem(ADMIN_USER_KEY)
    return raw ? (JSON.parse(raw) as AdminUser) : null
  } catch {
    return null
  }
}

const adminHttp = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
  headers: { Accept: 'application/json' },
})

adminHttp.interceptors.request.use((config) => {
  const token = getAdminToken()
  if (token) {
    config.headers = config.headers || {}
    ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
  }
  return config
})

adminHttp.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiResponse<unknown>>) => {
    if (!error.response) {
      return Promise.reject(new ApiError('无法连接服务器，请检查网络后重试', 0, 0))
    }
    const { status, data } = error.response
    const body = (data || {}) as ApiResponse<unknown>
    if (status === 401) {
      clearAdminSession()
      window.dispatchEvent(new CustomEvent(ADMIN_EXPIRED_EVENT))
    }
    return Promise.reject(new ApiError(body.message || '请求失败', status, Number(body.code) || 0, body.details))
  }
)

async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await adminHttp.request<ApiResponse<T>>(config)
  const body = response.data
  if (body && typeof body === 'object' && 'success' in body) {
    if (!body.success) throw new ApiError(body.message || '请求失败', response.status, body.code)
    return body.data as T
  }
  return body as unknown as T
}

export const adminApi = {
  login(username: string, password: string, captcha?: { captcha_id: string; captcha_code: string }) {
    return request<{ token: string; user: AdminUser; expires_at: string }>({
      url: '/admin/auth/login',
      method: 'POST',
      data: { username, password, ...(captcha || {}) },
    })
  },
  me() {
    return request<{ user: AdminUser }>({ url: '/admin/auth/me', method: 'GET' })
  },
  logout() {
    return request<{ logged_out: boolean }>({ url: '/admin/auth/logout', method: 'POST' })
  },
  meta() {
    return request<AdminMeta>({ url: '/admin/meta', method: 'GET' })
  },
  dashboard() {
    return request<AdminOverview>({ url: '/admin/dashboard', method: 'GET' })
  },
  users(params: Record<string, unknown>) {
    return request<AdminUserList>({ url: '/admin/users', method: 'GET', params })
  },
  updateUser(id: number, isActive: boolean) {
    return request<{ user: User }>({ url: `/admin/users/${id}`, method: 'PATCH', data: { is_active: isActive } })
  },
  updateUserStatus(id: number, status: 'active' | 'disabled') {
    return request<{ user: AdminUser }>({
      url: `/admin/users/${id}/status`,
      method: 'PATCH',
      data: { status },
    })
  },
  deleteUser(id: number) {
    return request<{ deleted: boolean; id: number }>({ url: `/admin/users/${id}`, method: 'DELETE' })
  },
  setUserRole(id: number, role: 'admin' | 'user') {
    return request<{ user: AdminUser }>({
      url: `/admin/users/${id}/role`,
      method: 'PATCH',
      data: { role },
    })
  },
  resetPassword(id: number) {
    return request<{ user_id: number; temporary_password: string }>({
      url: `/admin/users/${id}/reset-password`,
      method: 'POST',
    })
  },
  records(params: Record<string, unknown>) {
    return request<AdminRecordList>({ url: '/admin/records', method: 'GET', params })
  },
  recordDetail(id: number) {
    return request<AdminRecordDetail>({ url: `/admin/records/${id}`, method: 'GET' })
  },
  recordImage(id: number) {
    return adminHttp
      .get<Blob>(`/admin/records/${id}/image`, {
        responseType: 'blob',
      })
      .then((response) => response.data)
  },
  reviewRecord(
    id: number,
    payload: {
      food_name: string
      brand?: string
      summary?: string
      overall_check: 'none_found' | 'needs_review' | 'suspected'
      ocr_text?: string
      ingredient_summary?: string
    },
  ) {
    return request<AdminRecordDetail>({
      url: `/admin/records/${id}/review`,
      method: 'PUT',
      data: payload,
    })
  },
  addNote(id: number, content: string) {
    return request<{ note: { id: number } }>({ url: `/admin/records/${id}/notes`, method: 'POST', data: { content } })
  },
  deleteRecord(id: number) {
    return request<{ deleted: boolean }>({ url: `/admin/records/${id}`, method: 'DELETE', data: { confirm: true } })
  },
  feedback(params: Record<string, unknown>) {
    return request<{ items: FeedbackItem[]; total: number; stats: { open: number; resolved: number } }>({
      url: '/admin/feedback',
      method: 'GET',
      params,
    })
  },
  resolveFeedback(id: number, status: string, reply: string) {
    return request<{ feedback: FeedbackItem }>({
      url: `/admin/feedback/${id}`,
      method: 'PATCH',
      data: { status, reply },
    })
  },
  replyFeedback(feedbackId: number, replyContent: string) {
    return request<{ feedback: FeedbackItem }>({
      url: '/admin/feedback/reply',
      method: 'POST',
      data: {
        feedback_id: feedbackId,
        reply_content: replyContent,
      },
    })
  },
  prompts() {
    return request<{ items: PromptTemplateItem[] }>({
      url: '/admin/prompts',
      method: 'GET',
    })
  },
  publishPrompt(id: number) {
    return request<{ prompt: PromptTemplateItem }>({
      url: `/admin/prompts/${id}/publish`,
      method: 'POST',
    })
  },
  draftPrompt(id: number) {
    return request<{ prompt: PromptTemplateItem }>({
      url: `/admin/prompts/${id}/draft`,
      method: 'POST',
    })
  },
  updatePrompt(id: number, systemPrompt: string) {
    return request<{ prompt: PromptTemplateItem }>({
      url: `/admin/prompts/${id}`,
      method: 'PUT',
      data: { system_prompt: systemPrompt },
    })
  },
  knowledge(params: Record<string, unknown>) {
    return request<AdminKnowledgeList>({ url: '/admin/knowledge', method: 'GET', params })
  },
  composeKnowledge(title: string) {
    return request<{
      content: string
      summary: string
      calories: number
      carbs: number
      protein: number
      fat: number
    }>({
      url: '/admin/knowledge/ai-compose',
      method: 'POST',
      data: { title },
      timeout: 120000,
    })
  },
  summarizeKnowledge(payload: { title: string; content: string }) {
    return request<{ summary: string }>({
      url: '/admin/knowledge/summarize',
      method: 'POST',
      data: payload,
    })
  },
  estimateDishNutrition(payload: { title: string; summary?: string; content?: string }) {
    return request<{
      status: 'success' | 'failed' | 'skipped'
      message: string
      calories_per_100g: number
      carbs_per_100g: number
      protein_per_100g: number
      fat_per_100g: number
      typical_portion_g: number
    }>({
      url: '/admin/knowledge/estimate-nutrition',
      method: 'POST',
      data: payload,
    })
  },
  createKnowledge(payload: Record<string, unknown>) {
    return request<{ entry: AdminKnowledgeItem; nutrition_ai?: NutritionAIResult }>({ url: '/admin/knowledge', method: 'POST', data: payload })
  },
  updateKnowledge(id: number, payload: Record<string, unknown>) {
    return request<{ entry: AdminKnowledgeItem; nutrition_ai?: NutritionAIResult }>({ url: `/admin/knowledge/${id}`, method: 'PUT', data: payload })
  },
  enrichDishKnowledge(id: number) {
    return request<{ entry: AdminKnowledgeItem }>({
      url: `/admin/knowledge/${id}/enrich`,
      method: 'POST',
    })
  },
  verifyKnowledge(id: number) {
    return request<{ entry: AdminKnowledgeItem; nutrition_ai?: NutritionAIResult }>({
      url: `/admin/knowledge/${id}/verify`,
      method: 'POST',
    })
  },
  publishKnowledge(id: number, status: string) {
    return request<{ entry: AdminKnowledgeItem; nutrition_ai?: NutritionAIResult }>({
      url: `/admin/knowledge/${id}/publish`,
      method: 'POST',
      data: { status },
    })
  },
  deleteKnowledge(id: number) {
    return request<{ deleted: boolean }>({ url: `/admin/knowledge/${id}`, method: 'DELETE' })
  },
  rules(params: Record<string, unknown>) {
    return request<RuleList>({ url: '/admin/rules', method: 'GET', params })
  },
  createRule(payload: Record<string, unknown>) {
    return request<{ rule: RuleItem }>({ url: '/admin/rules', method: 'POST', data: payload })
  },
  updateRule(ruleId: string, payload: Record<string, unknown>) {
    return request<{ rule: RuleItem }>({ url: `/admin/rules/${ruleId}`, method: 'PUT', data: payload })
  },
  toggleRule(ruleId: string, enabled: boolean) {
    return request<{ rule: RuleItem }>({
      url: `/admin/rules/${ruleId}/toggle`,
      method: 'POST',
      data: { enabled },
    })
  },
  ruleRevisions(ruleId: string) {
    return request<{ rule: RuleItem; revisions: RuleRevisionItem[] }>({
      url: `/admin/rules/${ruleId}/revisions`,
      method: 'GET',
    })
  },
  monitor() {
    return request<MonitorData>({ url: '/admin/monitor', method: 'GET' })
  },
  auditLogs(params: Record<string, unknown>) {
    return request<AuditLogList>({ url: '/admin/audit-logs', method: 'GET', params })
  },
}
