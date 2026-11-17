/** 后端接口返回的数据结构（与 backend/app 的 to_public 保持一致）。 */

export interface ApiResponse<T> {
  success: boolean
  code: number
  message: string
  data: T
  details?: unknown
  request_id?: string
}

export interface User {
  id: number
  username: string
  display_name: string
  email: string | null
  is_active: boolean
  is_demo: boolean
  role: 'admin' | 'user'
  created_at: string
}

export interface AuthResult {
  token: string
  user: User
  expires_at: string | null
}

export interface UploadedImage {
  id: number
  original_name: string
  ext: string
  mime: string
  size_bytes: number
  width: number
  height: number
  url: string
}

export interface RecordSummary {
  id: number
  food_name: string
  food_name_raw?: string
  owner_name?: string
  data_complete?: boolean
  brand: string | null
  status: string
  status_label: string
  data_source: string
  analysis_mode: string | null
  is_demo: boolean
  ocr_provider: string | null
  overall_check: string | null
  summary: string | null
  created_at: string
  updated_at: string
  analyzed_at: string | null
  image_url: string | null
  image?: { width: number; height: number; size_bytes: number; mime: string } | null
  ingredient_count: number
  issue_count: number
  has_report: boolean
}

export interface FieldFlag {
  level: string
  status: string
  text: string
  note?: string | null
}

export interface OcrResult {
  id: number
  provider: string
  provider_label: string
  engine_version: string
  is_demo: boolean
  status: string
  raw_text: string
  corrected_text: string
  fields: Record<string, string>
  field_confidence: Record<string, number>
  field_flags: Record<string, FieldFlag>
  low_confidence_fields: string[]
  missing_fields: string[]
  duration_ms: number
  field_labels: Record<string, string>
  meta?: {
    preprocess?: { mode?: string; size?: number[]; grayscale?: boolean; autocontrast?: boolean; unsharp?: boolean } | null
    passes?: Array<{ pass: string; lines: number }> | null
    line_count?: number | null
    warning?: string | null
  }
  created_at: string
  updated_at: string
  corrected_at: string | null
}

export interface KnowledgeRef {
  id: number
  title: string
  verification_status?: string
  source_name?: string
}

export type Confidence = 'high' | 'medium' | 'low'
export type Evidence = 'knowledge_base' | 'general_knowledge' | 'unverified'

export interface IngredientExplain {
  name: string
  category: string
  role: string
  purpose: string
  simple_desc?: string
  explanation: string
  confidence: Confidence | string
  evidence: Evidence | string
  is_ai_generated?: boolean
  source_refs: string[]
  caution: string | null
  knowledge_refs?: KnowledgeRef[]
}

export interface Citation {
  knowledge_id: number
  title: string
  source_name: string
  source_url: string | null
  claim: string
  verified: boolean
  verified_label?: string
}

export interface IngredientTag {
  name: string
  value: string
  status: 'high' | 'medium' | 'low' | 'good' | 'neutral' | string
  label: string
}

export interface PersonalizationWarning {
  level: 'danger' | 'warning' | 'info' | 'none' | string
  title: string
  message: string
  reasons: string[]
}

export interface IngredientAnalysis {
  mode: 'ai' | 'rule' | 'demo'
  mode_label: string
  model: string | null
  prompt_version: string
  summary: string
  tags?: IngredientTag[]
  personalization?: PersonalizationWarning | null
  water_only?: boolean
  ingredients: IngredientExplain[]
  nutrition_notes: string[]
  unknown_items: string[]
  unconfirmed: string[]
  citations: Citation[]
  diff: Record<string, number> | null
  disclaimer: string
  error: string | null
  duration_ms: number
  created_at: string
}

export interface NutritionItem {
  key: string
  name: string
  value: number | null
  unit: string
  nrv_percent: number | null
  nrv_estimated?: boolean
  status: string
  status_label?: string
  nrv_percent_estimated?: number | null
  unit_inferred?: boolean
  value_kj?: number | null
  note?: string
}

export interface NutritionWarning {
  level: string
  message: string
  detail?: string
}

export interface Nutrition {
  basis: string
  basis_note?: string
  source: string
  items: NutritionItem[]
  warnings: NutritionWarning[]
  updated_at: string
}

export type CheckLevel = 'pass' | 'info' | 'review' | 'suspected' | 'skip'

export interface CheckSource {
  name: string
  type?: string
  note?: string
}

export interface CheckItem {
  rule_id: string
  title: string
  level_label: string
  rule_version: string
  rule_updated_at: string
  rule_name?: string
  category: string
  level: CheckLevel
  result: string
  reason: string
  basis?: string
  suggestion?: string
  todo?: string | null
  field?: string
  source?: CheckSource | null
}

export interface CheckResult {
  ruleset_version: string
  overall: string
  overall_label: string
  items: CheckItem[]
  counts: Record<string, number>
  coverage: Record<string, unknown>
  updated_at: string
}

export interface ReportMeta {
  report_no: string
  version: string
  generated_at: string
  generated_count: number
}

export interface DetailMeta {
  disclaimer?: string
  ruleset_version?: string
  is_demo?: boolean
  generated_at?: string
  demo_notice?: string
  mode_notice?: string
  app_name?: string
  app_subtitle?: string
  app_version?: string
  public_site_url?: string | null
  [key: string]: unknown
}

export interface HealthDimension {
  key: string
  label: string
  score: number
  max: number
  status?: 'ok' | 'unknown' | string
}

export interface HealthFinding {
  key: string
  title: string
  level: 'good' | 'watch' | 'info' | 'unknown' | string
  level_label: string
  summary: string
  detail: string
  basis: string
  confidence: string
}

export interface HealthAdditive {
  name: string
  ingredient_name: string
  role: string
  knowledge_id: number | null
  knowledge_title: string | null
  source_name: string | null
  risk_note: string | null
  compliance: string
}

export interface HealthAssessment {
  model_version: string
  score: number | null
  grade: string
  grade_label: string
  headline: string
  dimensions: HealthDimension[]
  score_note?: string
  unknown_dimensions?: string[]
  findings: HealthFinding[]
  additives: { count: number; items: HealthAdditive[] }
  sugar: { value_g: number | null; daily_ratio: number | null; package_sugar_g: number | null }
  trans_fat: { value_g: number | null; energy_ratio: number | null }
  sodium: { value_mg: number | null; nrv_percent: number | null }
  data_quality: {
    core_present: number
    core_total: number
    has_sugar: boolean
    has_trans_fat: boolean
    ingredient_count: number
    net_content_g: number | null
  }
  disclaimer: string
  generated_at: string
}

export interface RecordDetail {
  record: RecordSummary
  ocr: OcrResult | null
  ingredient: IngredientAnalysis | null
  nutrition: Nutrition | null
  check: CheckResult | null
  health: HealthAssessment | null
  report: ReportMeta | null
  meta: DetailMeta
}

export interface RecordListResult {
  items: RecordSummary[]
  total: number
  page: number
  per_page: number
  pages: number
  stats?: Record<string, number>
}

export interface UploadResult {
  record: RecordSummary
  image: UploadedImage
}

export interface OcrRunResult {
  record: RecordSummary
  ocr: OcrResult
  fields: Record<string, string>
  field_order?: string[]
  demo_warning: string | null
  ocr_warning?: string | null
  provider: {
    key: string
    label: string
    version: string
    is_demo: boolean
    duration_ms: number
  }
}

export interface AnalyzeResult {
  record: RecordSummary
  result: {
    analysis_mode: string
    mode_label?: string
    errors?: string[]
    [key: string]: unknown
  }
  detail: RecordDetail
  [key: string]: unknown
}

/** `POST /api/analyze` 的 multipart 上传响应（file + mode）。 */
export interface AnalyzeUploadResult {
  mode: 'packaging' | 'dish'
  record: RecordSummary
  image: UploadedImage
  limits: { max_mb: number; allowed: string }
  ocr?: OcrResult
  fields?: Record<string, string>
  field_order?: string[]
  demo_warning?: string | null
  ocr_warning?: string | null
  provider?: OcrRunResult['provider']
  result?: AnalyzeResult['result']
  detail?: RecordDetail
  stream_url?: string
}

export interface ReportSource {
  id: number
  title: string
  source_name: string
  source_url: string | null
  source_type: string
  verification_status: string
  version: string
  used_for?: string
  [key: string]: unknown
}

export interface RuleSource {
  name: string
  type?: string
  note?: string
  rule_ids: string[]
}

export interface ReportPayload {
  report: ReportMeta
  record: RecordSummary
  ocr: OcrResult | null
  ingredient: IngredientAnalysis | null
  nutrition: Nutrition | null
  check: CheckResult | null
  health: HealthAssessment | null
  check_overall_label: string
  sources: ReportSource[]
  rule_sources: RuleSource[]
  ruleset: {
    version: string
    updated_at: string
    disclaimer: string
  }
  meta: DetailMeta
}

export interface DashboardTotals {
  records: number
  analyzed: number
  demo_records: number
  demo_analyzed: number
  real_records: number
  real_analyzed: number
  ingredients_explained: number
  ingredients_real: number
  knowledge_citations: number
  suspected: number
  needs_review: number
  none_found: number
}

export interface ChartPoint {
  key?: string
  name?: string
  value?: number
  date?: string
  label?: string
  count?: number
}

export interface DashboardData {
  totals: DashboardTotals
  status_distribution: ChartPoint[]
  check_distribution: ChartPoint[]
  level_counts: Record<string, number>
  trend: ChartPoint[]
  top_ingredients: ChartPoint[]
  recent_records: RecordSummary[]
  featured_knowledge: KnowledgeEntry[]
  knowledge_stats: Record<string, unknown>
  service_status: {
    ocr_provider: string
    ocr_label: string
    ai_mode: string
    ai_configured: boolean
    ai_model: string | null
  }
  onboarding: {
    is_first_visit: boolean
    steps: Array<{ title: string; description: string }>
  }
  generated_at: string
}

export interface HealthResult {
  status: string
  app: string
  version: string
  env: string
  uptime_seconds: number
  server_time: string
  checks: {
    database: { status: string; engine: string }
    storage: { status: string; file_count: number }
    ocr: { status: string; provider: string; is_demo_possible: boolean }
    ai: { status: string; mode: string }
  }
}

export interface Ruleset {
  version: string
  updated_at: string
  rule_count: number
  disclaimer: string
  rules?: Array<Record<string, unknown>>
}

export interface SettingsStatus {
  app: {
    name: string
    subtitle: string
    version: string
    env: string
    public_site_url: string | null
  }
  ocr: {
    configured_provider: string
    active_provider: string
    active_label: string
    providers: Array<{ key: string; name: string; available: boolean; is_demo: boolean }>
    vision_base_url: string | null
    vision_endpoint: string | null
    vision_model: string | null
    vision_key: string
  }
  ai: {
    mode: string
    configured: boolean
    provider: string
    base_url: string
    model: string
    api_key: string
    prompt_version: string
  }
  assistant?: {
    mode: string
    fallback_enabled: string
    general_answer_enabled: string
    llm_base_url: string
    llm_model: string
    llm_key: string
    dedicated_llm: boolean
  }
  storage: {
    database: string
    upload_dir: string
    upload_dir_exists: boolean
    file_count: number
    total_bytes: number
    max_upload_mb: number
    allowed_formats: string[]
    image_max_edge: number
    [key: string]: unknown
  }
  security: {
    password_hashing: string
    session_days: number
    cors_origins: string[]
    demo_mode: boolean
    api_key_in_logs: boolean
  }
  demo_account: {
    exists: boolean
    username: string | null
    password_hint: string | null
  }
  ruleset: {
    version: string
    updated_at: string
    rule_count: number
  }
  limits: { page_size: number; max_page_size: number }
  runtime: { python: string; flask: string }
}

export interface KnowledgeEntry {
  id: number
  slug: string
  title: string
  status: string
  aliases: string[]
  keywords: string[]
  category: string
  category_label: string
  summary: string
  content?: string
  usage_note?: string
  source_name: string
  source_url: string | null
  source_type: string
  source_type_label: string
  verification_status: string
  verification_label: string
  version: string
  updated_at: string | null
  is_featured: boolean
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

export interface KnowledgeListResult {
  items: KnowledgeEntry[]
  total: number
  page: number
  per_page: number
  pages: number
  categories: Array<{ value: string; label: string; count: number }>
  verification_labels: Record<string, string>
}

// ---------------- 常见菜品营养库（热量字典） ----------------
export interface DishInfo {
  slug: string
  dish_name: string
  aliases: string[]
  category: string
  calories_per_100g: number
  protein_per_100g: number
  fat_per_100g: number
  carbs_per_100g: number
  typical_portion_g: number
  health_tip: string
  source: string
}

export interface DishNutritionTotals {
  weight_g: number
  calories: number
  protein_g: number
  fat_g: number
  carbs_g: number
}

export interface DishAnalysisInfo extends DishInfo {
  estimated_weight_g: number
  totals: DishNutritionTotals
  matched: boolean
  recognition_name?: string
  confidence?: string
}

export interface DishListResult {
  items: DishInfo[]
  total: number
  page: number
  per_page: number
  pages: number
  query: string
  category: string
  categories: Array<{ value: string; label: string; count: number }>
  source: string
}

export interface DishDetailResult {
  dish: DishInfo
  related: DishInfo[]
}

// ---------------- 食安科普与辟谣助手（RAG） ----------------
export interface AssistantSource {
  id: string
  name: string
  publisher: string
  year: string | null
  url: string | null
  kind: string
  kind_label: string
  verified: boolean
}

export interface AssistantSection {
  key: 'conclusion' | 'explanation' | 'evidence' | 'caution' | string
  label: string
  text: string
}

export interface AssistantEntryBrief {
  id: number
  slug: string
  title: string
  category: string
  category_label: string
  summary: string
  verification_status: 'verified' | 'pending'
  verification_label: string
  sources: AssistantSource[]
}

export interface AssistantRelated {
  slug: string
  title: string
  category_label: string
}

export type RecipeVersionKey = 'novice' | 'chef'

export interface RecipeVersion {
  steps: string[]
  tips: string[]
}

export interface RecipeVersions {
  novice: RecipeVersion
  chef: RecipeVersion
}

export interface RecipeSummary {
  title: string
  time: string
  difficulty: string
  main_ingredients: string[]
  safety: string
}

export interface RecipeOption {
  title: string
  time: string
  difficulty: string
  main_ingredients: string[]
  safety: string
}

export interface AssistantAnswer {
  session_id: number
  message_id: number
  matched: boolean
  coverage: 'direct' | 'related' | 'general' | 'profile' | 'context' | 'none' | 'recipe' | 'recipe_options' | 'pantry_recipe' | 'inventory'
  mode: 'retrieval' | 'ai' | 'ai_rerank' | 'ai_general' | string
  mode_label: string
  mode_note: string | null
  answer: string
  sections: AssistantSection[]
  evidence: string
  sources: AssistantSource[]
  entry: AssistantEntryBrief | null
  related: AssistantRelated[]
  disclaimer: string
  ai_check: { kept_sentences: number; dropped_sentences: number; citations: number } | null
  ai_error: string | null
  context_used?: boolean
  recipe_title?: string
  recipe_source?: string
  recipe_subject?: string
  recipe_options?: RecipeOption[]
  recipe_summary?: RecipeSummary
  recipe_versions?: RecipeVersions
  recipe_data?: Record<string, unknown>
  pantry_plan_id?: number | null
  pantry_dishes?: PantryRecommendationDish[]
  pantry_shopping?: string[]
  pantry_trace?: string[]
  pantry_servings?: number
  action?: string | null
  action_label?: string
  inventory_items?: Array<{ id: number; name: string; quantity: number; unit: string; status_text?: string; expires_at?: string | null }>
  used_items?: string[]
  safety_notes?: string[]
}

export interface AssistantMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  mode: string
  matched_slug: string | null
  sources: AssistantSource[]
  payload: {
    sections?: AssistantSection[]
    evidence?: string
    coverage?: 'direct' | 'related' | 'general' | 'profile' | 'none' | 'recipe' | 'recipe_options' | 'pantry_recipe' | 'inventory' | 'context'
    ai_error?: string | null
    matched?: boolean
    entry?: AssistantEntryBrief | null
    related?: AssistantRelated[]
    mode_note?: string | null
    ai?: { kept_sentences: number; dropped_sentences: number } | null
    retrieval?: Array<{ slug: string; score: number }>
    context_used?: boolean
    context_recipe?: Record<string, unknown>
    retrieval_query?: string
    recipe_title?: string
    recipe_source?: string
    recipe_subject?: string
    recipe_options?: RecipeOption[]
    recipe_summary?: RecipeSummary
    recipe_versions?: RecipeVersions
    recipe_data?: Record<string, unknown>
    pantry_plan_id?: number | null
    pantry_dishes?: PantryRecommendationDish[]
    pantry_shopping?: string[]
    pantry_trace?: string[]
    pantry_servings?: number
    action?: string | null
    action_label?: string
    inventory_items?: Array<{ id: number; name: string; quantity: number; unit: string; status_text?: string; expires_at?: string | null }>
    used_items?: string[]
    safety_notes?: string[]
  }
  created_at: string
}

export interface AssistantSession {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count?: number
  messages?: AssistantMessage[]
}

export interface AssistantOverview {
  stats: {
    entries: number
    verified: number
    pending: number
    categories: Array<{ key: string; label: string }>
    verification_labels: Record<string, string>
    mode: 'retrieval' | 'ai'
    mode_label: string
  }
  featured: Array<{ slug: string; title: string; question: string; category_label: string }>
  disclaimer: string
}

// ---------------- 家庭食材管家与食谱 Agent ----------------
export interface ShoppingCheckoutResult {
  purchased: Array<{ name: string; quantity: number; unit: string; remaining?: number; expires_at?: string; merged: boolean }>
  count: number
  fresh_count?: number
  staple_count?: number
  message: string
  delivery: string
  estimated_arrival?: string
  staples?: string[]
}

export interface PantryItem {
  id: number
  name: string
  category: string
  category_label: string
  quantity: number
  unit: string
  purchased_at: string | null
  expires_at: string | null
  days_left: number | null
  status: 'expired' | 'expiring' | 'fresh' | 'no_expiry'
  status_text: string
  note: string
  owner_id?: number
  owner_name?: string
  is_shared?: boolean
  created_at: string
  rescue_available?: boolean
  rescue?: {
    item_id: number
    item_name: string
    recipe_name: string
    steps: string[]
    source: string
    note: string
  }
}

export interface PantryParseItem {
  name: string
  quantity: number
  unit: string
  category: string
  purchased_at: string
  expires_at: string
  shelf_life_days: number | null
  shelf_life_confidence: number
  shelf_life_confidence_label: string
  shelf_life_alternatives: number[]
  shelf_life_basis: string
  storage: string
  shelf_life_source: string
  shelf_life_note: string
  shelf_life_warning: string | null
  note: string
}

export interface PantryShelfEstimate {
  name: string
  days: number | null
  storage: string
  note: string
  source: string
  confidence_percent: number
  confidence_label: string
  alternatives: number[]
  basis: string
  warning: string | null
}

export interface PantryRecommendationDish {
  meal_index: number
  meal_type: string
  name: string
  ingredients: RecipeIngredient[]
  main_ingredients?: RecipeIngredient[]
  auxiliary_ingredients?: RecipeIngredient[]
  steps: string[]
  nutrition: Record<string, number>
  missing: RecipeIngredient[]
  tips: string
  versions?: RecipeVersions
}

export interface PantryParseResult {
  mode: 'ai' | 'rule' | string
  source: string
  items: PantryParseItem[]
  warnings: string[]
  count: number
  ocr?: {
    provider: string
    provider_label: string
    is_demo: boolean
    line_count: number
    raw_text: string
    warning: string | null
  }
}

export interface PantryReminder {
  expiring: PantryItem[]
  expired: PantryItem[]
  urgent: PantryItem[]
  urgent_count: number
  counts: { expiring: number; expired: number; total: number }
  window_days: number
  message: string
}

export interface FamilyMember {
  id: number
  username: string
  display_name: string
  initial: string
  avatar_url: string | null
  is_self: boolean
  is_owner: boolean
  role: '户主' | '成员' | string
}

export interface FamilyInfo {
  family: {
    id: number
    invite_code: string
    name: string
    owner_id: number | null
    created_at: string | null
  }
  members: FamilyMember[]
  member_count: number
  is_owner: boolean
}

export interface FamilyAlert {
  message: string
  item_name: string
  owner_name: string
  item_id: number
  created_at: string | null
  source: string
}

export interface PantryListResult {
  items: PantryItem[]
  total: number
  categories: Array<{ value: string; label: string }>
  reminder: PantryReminder
}

export interface HealthProfile {
  conditions: string[]
  condition_labels: string[]
  goals: string[]
  goal_labels: string[]
  allergies: string[]
  notes: string
  updated_at: string | null
  options?: {
    conditions: Array<{ value: string; label: string }>
    goals: Array<{ value: string; label: string }>
  }
}

export interface RecipeIngredient {
  name: string
  amount: string
  from_pantry: boolean
  expiring: boolean
  role?: 'main' | 'auxiliary' | string
}

export interface RecipeMeal {
  meal_type: string
  name: string
  ingredients: RecipeIngredient[]
  main_ingredients?: RecipeIngredient[]
  auxiliary_ingredients?: RecipeIngredient[]
  steps: string[]
  nutrition: Record<string, number>
  suitability: Record<string, string>
  tips: string
  version?: RecipeVersionKey
  versions?: RecipeVersions
  missing?: RecipeIngredient[]
}

export interface FavoriteRecipe {
  id: number
  recipe_name: string
  recipe_data: Record<string, unknown>
  created_at: string
  main_ingredients: Array<{ name: string; amount: string; from_pantry?: boolean }>
  missing: Array<{ name: string; amount: string }>
  energy_kcal: number
  nutrition?: Record<string, number>
}

export interface FavoriteListResult {
  items: FavoriteRecipe[]
  total: number
}

export interface RecipePlan {
  plan_id: number
  mode: 'ai' | 'rule' | string
  mode_label: string
  model: string | null
  summary: string
  meals: RecipeMeal[]
  shopping_list: string[]
  agent_trace: string[]
  warnings: string[]
  nutrition_totals: { energy_kcal: number; protein_g: number; sodium_mg: number; sugar_g: number }
  servings?: number
  budget?: number
  weather?: Record<string, unknown> | null
  profile: HealthProfile
  focus_item?: PantryItem | null
  rule_vetoes?: string[]
  focus_in_final?: boolean
  requested_meals?: number
  actual_meals?: number
  pantry_count: number
  ai_error: string | null
  disclaimer: string
  model_version: string
  generated_at: string
}

export interface RecipeHistoryItem {
  id: number
  mode: string
  model: string | null
  request: Record<string, unknown>
  result: RecipePlan
  created_at: string
}
