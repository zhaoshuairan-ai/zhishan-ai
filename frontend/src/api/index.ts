/** 后端接口集合（按业务域分组，与 backend/app/api 保持一致）。 */
import { api } from './client'
import type {
  AnalyzeResult,
  AssistantAnswer,
  AssistantOverview,
  AssistantSession,
  PantryListResult,
  FamilyInfo,
  FamilyAlert,
  FavoriteListResult,
  FavoriteRecipe,
  PantryItem,
  PantryReminder,
  PantryShelfEstimate,
  ShoppingCheckoutResult,
  HealthProfile,
  RecipePlan,
  RecipeHistoryItem,
  PantryParseResult,
  AuthResult,
  DashboardData,
  HealthResult,
  DishDetailResult,
  DishListResult,
  KnowledgeEntry,
  KnowledgeListResult,
  OcrRunResult,
  RecordDetail,
  RecordListResult,
  ReportPayload,
  Ruleset,
  SettingsStatus,
  UploadResult,
  User,
} from './types'

export const authApi = {
  login: (username: string, password: string, captcha?: { captcha_id: string; captcha_code: string }) =>
    api.post<AuthResult>('/auth/login', { username, password, ...(captcha || {}) }),
  register: (payload: { username: string; password: string; display_name?: string; email?: string }) =>
    api.post<AuthResult>('/auth/register', payload),
  logout: () => api.post<{ logged_out: boolean }>('/auth/logout', {}),
  changePassword: (oldPassword: string, newPassword: string) =>
    api.post<AuthResult>('/auth/change-password', { old_password: oldPassword, new_password: newPassword }),
  me: () =>
    api.get<{ user: User; stats: { record_count: number; analyzed_count: number }; demo_hint: string | null }>(
      '/auth/me'
    ),
  updateProfile: (displayName: string) =>
    api.put<{ user: User }>('/auth/profile', { display_name: displayName }),
}

export const pipelineApi = {
  upload: (file: File, onProgress?: (percent: number) => void) =>
    api.upload<UploadResult>('/upload', file, onProgress),
  ocr: (recordId: number) => api.post<OcrRunResult>('/ocr', { record_id: recordId }, { timeout: 240000 }),
  correct: (recordId: number, fields: Record<string, string>, note?: string) =>
    api.put<{ record: RecordListResult['items'][number]; ocr: OcrRunResult['ocr'] }>(`/records/${recordId}/ocr`, {
      fields,
      note,
    }),
  analyze: (recordId: number, type: 'package' | 'dish' = 'package') =>
    api.post<AnalyzeResult>('/analyze', { record_id: recordId, type }, { timeout: 240000 }),
  reanalyze: (recordId: number) =>
    api.post<AnalyzeResult>(`/records/${recordId}/reanalyze`, {}, { timeout: 240000 }),
}

export const recordApi = {
  list: (params: { page?: number; per_page?: number; query?: string; status?: string }) =>
    api.get<RecordListResult>('/records', params),
  detail: (id: number) => api.get<RecordDetail>(`/records/${id}`),
  update: (id: number, payload: { food_name?: string; nutrition?: Record<string, number | null> }) =>
    api.put<RecordDetail>(`/records/${id}`, payload),
  remove: (id: number) => api.delete<{ deleted_id: number; deleted_files: string[] }>(`/records/${id}`),
  clearAll: () => api.delete<{ deleted_count: number }>('/records'),
}

export const favoriteApi = {
  list: () => api.get<FavoriteListResult>('/favorites'),
  add: (recipe_name: string, recipe_data: Record<string, unknown>) =>
    api.post<{ favorite: FavoriteRecipe; created: boolean }>('/favorites', { recipe_name, recipe_data }),
  missing: (id: number) =>
    api.get<FavoriteRecipe & { recipe_id: number }>(`/favorites/${id}/missing`),
  remove: (id: number) => api.delete<{ deleted_id: number }>(`/favorites/${id}`),
  schedule: (id: number) =>
    api.post<{ favorite: FavoriteRecipe; plan: RecipePlan; meal: Record<string, unknown>; message: string }>(
      `/favorites/${id}/schedule`,
    ),
}

export const reportApi = {
  get: (recordId: number) => api.get<ReportPayload>(`/reports/${recordId}`),
}

export const knowledgeApi = {
  list: (params: { page?: number; per_page?: number; query?: string; category?: string; featured?: string }) =>
    api.get<KnowledgeListResult>('/knowledge', params),
  detail: (id: number) =>
    api.get<{ entry: KnowledgeEntry; related: KnowledgeEntry[] }>(`/knowledge/${id}`),
  fillDishNutrition: (id: number) =>
    api.post<{
      entry: KnowledgeEntry
      nutrition_ai: {
        status: 'success' | 'failed' | 'skipped'
        message: string
        filled_fields: string[]
      }
    }>(`/knowledge/${id}/nutrition`),
  estimateNutrition: (payload: {
    entry_id?: number
    title: string
    description?: string
  }) =>
    api.post<{
      entry: KnowledgeEntry | null
      nutrition_ai: {
        status: 'success' | 'failed' | 'skipped'
        message: string
        filled_fields: string[]
      }
      nutrition: {
        calories_per_100g: number
        carbs_per_100g: number
        protein_per_100g: number
        fat_per_100g: number
        typical_portion_g: number
      }
    }>('/knowledge/estimate', payload, { timeout: 120000 }),
}

export const dishApi = {
  list: (params: { page?: number; per_page?: number; query?: string; category?: string }) =>
    api.get<DishListResult>('/dishes', params),
  detail: (slug: string) => api.get<DishDetailResult>(`/dishes/${encodeURIComponent(slug)}`),
}

export const systemApi = {
  health: () => api.get<HealthResult>('/health'),
  dashboard: () => api.get<DashboardData>('/dashboard'),
  settings: () => api.get<SettingsStatus>('/settings/status'),
  rules: () => api.get<Ruleset>('/rules'),
}

export const assistantApi = {
  overview: () => api.get<AssistantOverview>('/assistant/overview'),
  ask: (
    question: string,
    sessionId?: number | null,
    context?: Record<string, unknown> | null,
    healthProfile?: HealthProfile | null,
  ) =>
    api.post<AssistantAnswer>(
      '/assistant/ask',
      {
        question,
        session_id: sessionId ?? null,
        context: context ?? null,
        health_data: healthProfile ?? null,
        health_profile: healthProfile ?? null,
      },
      { timeout: 120000 }
    ),
  sessions: () => api.get<{ items: AssistantSession[] }>('/assistant/sessions'),
  session: (id: number) => api.get<{ session: AssistantSession; disclaimer: string }>(`/assistant/sessions/${id}`),
  removeSession: (id: number) => api.delete<{ deleted_id: number }>(`/assistant/sessions/${id}`),
  clearSessions: () => api.delete<{ deleted: number }>('/assistant/sessions'),
}

export interface MyFeedbackItem {
  id: number
  user_id: number
  record_id: number | null
  content: string
  contact: string
  status: 'open' | 'resolved'
  status_label: string
  reply: string
  reply_content: string
  handled_by: string
  created_at: string
  updated_at: string
}

export const feedbackApi = {
  submit: (payload: { content: string; contact?: string; record_id?: number | null }) =>
    api.post<{ feedback: { id: number; status: string } }>('/feedback', payload),
  // 始终由后端根据当前登录令牌识别用户，避免本地缓存的 user 与 token 不一致时查错人
  mine: () =>
    api.get<{ items: MyFeedbackItem[]; unread: number }>('/feedback/mine'),
}

export const captchaApi = {
  fetch: () =>
    api.get<{ captcha_id: string; image: string; question: string; expires_in: number }>('/captcha'),
}

export const familyApi = {
  info: () => api.get<FamilyInfo | null>('/family'),
  create: () => api.post<FamilyInfo>('/family/create'),
  join: (inviteCode: string) => api.post<FamilyInfo>('/family/join', { invite_code: inviteCode }),
  leave: () =>
    api.post<{ left: boolean; action: 'left' | 'dissolved'; family_id: number | null }>(
      '/family/leave',
    ),
  rename: (name: string) => api.put<FamilyInfo>('/family/name', { name }),
  updateMemberName: (memberId: number, displayName: string) =>
    api.put<FamilyInfo>(`/family/members/${memberId}`, { display_name: displayName }),
  removeMember: (memberId: number) =>
    api.delete<{ removed_id: number; family: FamilyInfo }>(`/family/members/${memberId}`),
  alert: () => api.get<{ alert: FamilyAlert | null }>('/family/alert'),
}

export const pantryApi = {
  list: (params?: { status?: string; query?: string }) => api.get<PantryListResult>('/pantry', params),
  create: (payload: Record<string, unknown>) => api.post<{ item: PantryItem }>('/pantry', payload),
  update: (id: number, payload: Record<string, unknown>) =>
    api.put<{ item: PantryItem }>(`/pantry/${id}`, payload),
  remove: (id: number) => api.delete<{ deleted: boolean }>(`/pantry/${id}`),
  removeMany: (ids: number[]) => api.post<{ deleted: number; requested: number; missing: number[] }>('/pantry/batch-delete', { ids }),
  reminders: () => api.get<PantryReminder>('/pantry/reminders'),
  estimateShelfLife: (name: string) => api.get<PantryShelfEstimate>('/pantry/lookup/shelf-life', { name }),
  profile: () => api.get<HealthProfile>('/health-profile'),
  healthTip: (payload: { conditions: string[]; goals: string[]; allergies: string[]; notes: string }) =>
    api.post<{ tip: string; source: string }>('/health-profile/tip', payload, { timeout: 60000 }),
  saveProfile: (payload: Record<string, unknown>) => api.put<{ profile: HealthProfile }>('/health-profile', payload),
  plan: (payload: { meals: number; max_minutes: number; servings: number; budget?: number; preference?: string; weather?: { city?: string; condition?: string; temperature?: number; description?: string } }) =>
    api.post<RecipePlan>('/recipes/plan', payload, { timeout: 180000 }),
  history: (limit = 5) => api.get<{ items: RecipeHistoryItem[] }>('/recipes/history', { limit }),
  batch: (items: Record<string, unknown>[]) => api.post<{ count: number }>('/pantry/batch', { items }),
  importText: (text: string, source = 'voice') =>
    api.post<PantryParseResult>('/pantry/import/text', { text, source }, { timeout: 120000 }),
  importReceipt: (file: File, onProgress?: (percent: number) => void) =>
    api.upload<PantryParseResult>('/pantry/import/receipt', file, onProgress),
  rescue: (itemId: number, meals = 2) => api.post<RecipePlan>('/recipes/rescue', { item_id: itemId, meals }, { timeout: 180000 }),
  addRecipeFromAssistant: (messageId: number, version: 'novice' | 'chef' = 'novice') =>
    api.post<{ plan_id: number; meals: unknown[]; summary?: string }>('/recipes/from-assistant', { message_id: messageId, version }),
  consumeRecipe: (recipe_name: string, ingredients: Array<{ name: string; amount: string }>) =>
    api.post<{ recipe_name: string; consumed: any[]; missing: any[]; skipped: any[]; message: string }>('/pantry/consume', { recipe_name, ingredients }),
  checkoutShopping: (items: string[], includeStaples = false) =>
    api.post<ShoppingCheckoutResult>('/pantry/shopping/checkout', { items, include_staples: includeStaples }),
  removeMeal: (planId: number, mealIndex: number) =>
    api.post<{ deleted_plan: boolean; plan_id: number; result: RecipePlan | null; message: string }>(
      '/recipes/remove-meal',
      { plan_id: planId, meal_index: mealIndex },
    ),
  completeRecipe: (planId: number, mealIndex: number) =>
    api.post<{
      completed: boolean
      already_done: boolean
      consumed: Array<{ name: string; deducted: number; unit: string; estimated?: boolean }>
      missing: Array<{ name: string }>
      skipped?: Array<{ name: string; reason: string }>
      message: string
    }>(
      '/recipes/complete',
      { plan_id: planId, meal_index: mealIndex },
    ),
  notifyTest: () => api.post<{ counts: { expiring: number; expired: number }; channels: Array<{ channel: string; status: string; detail: string }> }>('/pantry/notify-test'),
}
