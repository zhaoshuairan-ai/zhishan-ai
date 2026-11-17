<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import RecipeSummaryCard from '@/components/RecipeSummaryCard.vue'
import RecipeDetailDrawer from '@/components/RecipeDetailDrawer.vue'
import { useRoute, useRouter } from 'vue-router'
import { assistantApi, favoriteApi, pantryApi } from '@/api'
import { ApiError } from '@/api/client'
import type {
  AssistantAnswer,
  AssistantMessage,
  AssistantOverview,
  AssistantSession,
  AssistantSource,
  HealthProfile,
  PantryRecommendationDish,
  RecipeOption,
} from '@/api/types'

const router = useRouter()
const route = useRoute()
const overview = ref<AssistantOverview | null>(null)
const sessions = ref<AssistantSession[]>([])

const HEALTH_PROFILE_CACHE_KEY = 'fsai_assistant_health_profile_v1'

function readCachedHealthProfile(): HealthProfile | null {
  try {
    const raw = localStorage.getItem(HEALTH_PROFILE_CACHE_KEY)
    return raw ? (JSON.parse(raw) as HealthProfile) : null
  } catch {
    return null
  }
}

const healthProfile = ref<HealthProfile | null>(readCachedHealthProfile())

async function loadAssistantHealthProfile(): Promise<HealthProfile | null> {
  try {
    const profile = await pantryApi.profile()
    healthProfile.value = profile
    try {
      localStorage.setItem(
        HEALTH_PROFILE_CACHE_KEY,
        JSON.stringify(profile),
      )
    } catch {
      /* localStorage 不可用时保留内存画像 */
    }
    return profile
  } catch {
    return healthProfile.value || readCachedHealthProfile()
  }
}
const sessionId = ref<number | null>(null)
const messages = ref<AssistantMessage[]>([])
const question = ref('')
const sending = ref(false)
const loadingSession = ref(false)
const errorMessage = ref('')
const historyOpen = ref(false)
const listRef = ref<HTMLElement | null>(null)
const inputRef = ref<{ focus: () => void; resizeTextarea?: () => void } | null>(null)
const expandedDishes = ref<Set<string>>(new Set())
const doneDishes = ref<Set<string>>(new Set())
const completingDish = ref('')
const savingRecipe = ref<number | null>(null)
const savedRecipeIds = ref<Set<number>>(new Set())
const favoriteIds = ref<Map<string, number>>(new Map())
const favoritingName = ref('')
const contextRecipe = ref<Record<string, unknown> | null>(null)
const contextTitle = computed(() => String(contextRecipe.value?.title || contextRecipe.value?.name || ''))
const isKnowledgeContext = computed(() => contextRecipe.value?.context_type === 'knowledge')
const contextSubject = computed(() =>
  isKnowledgeContext.value ? '这个成分' : contextRecipe.value?.meal_type ? '这道菜' : '这款食品',
)
const consumingRecipe = ref(false)
const activeRecipeMissing = ref<Array<{ name: string; amount: string }>>([])
const recipeDrawerOpen = ref(false)
const activeRecipeMessage = ref<AssistantMessage | null>(null)
const activeRecipeVersion = ref<'novice' | 'chef'>('novice')
const speechSupported = ref(false)
const listening = ref(false)
const speakingId = ref<number | null>(null)
let recognition: any = null
let voiceBase = ''
let voiceStartTimer: ReturnType<typeof setTimeout> | null = null


const stats = computed(() => overview.value?.stats)
const featured = computed(() => overview.value?.featured || [])
const hasMessages = computed(() => messages.value.length > 0)

// 空态/对话态切换时让多行输入框重新计算高度（Element Plus 不会自动收缩）
watch(hasMessages, async () => {
  await nextTick()
  inputRef.value?.resizeTextarea?.()
})
const currentSession = computed(() => sessions.value.find((item) => item.id === sessionId.value) || null)
const modeLabel = computed(() => stats.value?.mode_label || '检索直答（逐字来自知识库）')

const QUICK_PROMPTS = [
  { label: '🔍 查配料', prompt: '请帮我查一下这几种配料的作用和安全风险：' },
  { label: '🩺 营养建议', prompt: '结合我的健康画像，请给我一些今天的营养建议。' },
  { label: '🥬 食材相克', prompt: '请问以下两种食物可以一起吃吗？（例如：螃蟹和柿子）' },
  { label: '📜 饮食禁忌', prompt: '请根据我的健康画像，帮我整理一下我最近的饮食禁忌。' },
]

const FEATURED_ICONS = ['🔥', '❓', '🥗', '🧂', '🌙', '💧']

function featuredIcon(index: number) {
  return FEATURED_ICONS[index % FEATURED_ICONS.length]
}

function fillQuickPrompt(prompt: string) {
  question.value = prompt
  nextTick(() => {
    inputRef.value?.focus()
    inputRef.value?.resizeTextarea?.()
  })
}

function formatTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`
}

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

async function loadOverview() {
  try {
    overview.value = await assistantApi.overview()
  } catch {
    /* 概览失败不阻塞提问 */
  }
}

function isMeaningfulQuestion(value: string) {
  const text = String(value || '').trim()
  if (!text) return false
  // 纯数字、纯标点、1-4 位连续英文字母（如 9999 / asd）视为无意义提问
  if (/^\d+$/.test(text)) return false
  if (/^[\s\p{P}\p{S}]+$/u.test(text)) return false
  if (/^[a-zA-Z]{1,4}$/.test(text)) return false
  if (/^(.)\1{3,}$/.test(text)) return false
  return true
}

async function loadSessions() {
  try {
    const data = await assistantApi.sessions()
    const seen = new Set<string>()

    sessions.value = data.items.filter((item) => {
      if (!isMeaningfulQuestion(item.title)) return false

      const key = item.title
        .trim()
        .toLowerCase()
        .replace(/[，。！？、：:；;,.!?\s]+/g, '')

      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  } catch {
    /* 未登录或网络异常时保持空列表 */
  }
}

async function openSession(id: number) {
  if (contextRecipe.value) {
    clearContextMode()
    messages.value = []
  }
  if (id === sessionId.value) {
    historyOpen.value = false
    return
  }
  loadingSession.value = true
  try {
    const data = await assistantApi.session(id)
    sessionId.value = id
    messages.value = data.session.messages || []
    historyOpen.value = false
    scrollToBottom()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '无法打开该对话')
  } finally {
    loadingSession.value = false
  }
}

function newChat() {
  clearContextMode()
  contextRecipe.value = null
  sessionId.value = null
  messages.value = []
  question.value = ''
  errorMessage.value = ''
  historyOpen.value = false
  inputRef.value?.focus()
}

async function clearHistory() {
  if (!sessions.value.length) return
  try {
    await ElMessageBox.confirm(
      `将删除全部 ${sessions.value.length} 条历史对话，删除后无法恢复。`,
      '清空历史记录',
      { type: 'warning', confirmButtonText: '全部删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const result = await assistantApi.clearSessions()
    sessions.value = []
    newChat()
    ElMessage.success(`已清空 ${result.deleted} 条历史对话`)
  } catch (error) {
    ElMessage.error((error as ApiError).message || '清空失败')
  }
}

async function removeSession(id: number) {
  try {
    await ElMessageBox.confirm('删除后这段对话将无法恢复，确定删除吗？', '删除对话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await assistantApi.removeSession(id)
    sessions.value = sessions.value.filter((item) => item.id !== id)
    if (sessionId.value === id) newChat()
    ElMessage.success('已删除')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '删除失败')
  }
}

function toAssistantMessage(data: AssistantAnswer): AssistantMessage {
  return {
    id: data.message_id,
    role: 'assistant',
    content: data.answer,
    mode: data.mode,
    matched_slug: data.entry?.slug ?? null,
    sources: data.sources,
    payload: {
      sections: data.sections,
      coverage: data.coverage,
      evidence: data.evidence,
      matched: data.matched,
      entry: data.entry,
      related: data.related,
      mode_note: data.mode_note,
      ai: data.ai_check,
      ai_error: data.ai_error,
      context_used: data.context_used,
      recipe_title: data.recipe_title,
      recipe_source: data.recipe_source,
      recipe_subject: data.recipe_subject,
      recipe_options: data.recipe_options,
      recipe_summary: data.recipe_summary,
      recipe_versions: data.recipe_versions,
      recipe_data: data.recipe_data,
      pantry_plan_id: data.pantry_plan_id,
      pantry_dishes: data.pantry_dishes,
      pantry_shopping: data.pantry_shopping,
      pantry_trace: data.pantry_trace,
      pantry_servings: data.pantry_servings,
      action: data.action,
      action_label: data.action_label,
      inventory_items: data.inventory_items,
      used_items: data.used_items,
      safety_notes: data.safety_notes,
    },
    created_at: new Date().toISOString(),
  }
}

function pantryDishes(message: AssistantMessage): PantryRecommendationDish[] {
  return message.payload?.pantry_dishes || []
}

const STAPLE_WORDS = ['油', '盐', '酱油', '生抽', '老抽', '蚝油', '醋', '料酒', '淀粉', '糖', '胡椒', '花椒', '八角', '桂皮', '香叶', '味精', '鸡精', '豆瓣酱', '番茄酱', '辣椒酱', '芝麻', '孜然', '咖喱', '五香粉', '十三香', '香油', '腐乳', '豆豉']
const FRESH_WORDS = ['菜', '鱼', '肉', '蛋', '果', '葱', '姜', '蒜', '青椒', '瓜', '豆', '菌', '菇']
const STAPLE_EXCEPTIONS = ['生抽', '老抽', '酱油', '蚝油', '料酒', '醋', '淀粉', '胡椒', '花椒', '豆瓣酱', '番茄酱', '辣椒酱', '香油', '芝麻', '孜然', '咖喱', '蒸鱼豉油', '豉油', '鱼露', '豆豉']

function isStapleName(name: string): boolean {
  const text = name || ''
  if (STAPLE_EXCEPTIONS.some((word) => text.includes(word))) return true
  if (FRESH_WORDS.some((word) => text.includes(word))) return false
  return STAPLE_WORDS.some((word) => text.includes(word))
}

function dishMain(dish: PantryRecommendationDish) {
  return (dish.ingredients || []).filter((item) => item.role !== 'auxiliary')
}

function dishAuxiliary(dish: PantryRecommendationDish) {
  return (dish.ingredients || []).filter((item) => item.role === 'auxiliary')
}

function dishMissing(dish: PantryRecommendationDish) {
  return (dish.missing || []).filter((item) => !isStapleName(item.name))
}

function dishKey(message: AssistantMessage, dish: PantryRecommendationDish): string {
  return `${message.id}-${dish.meal_index}`
}

function isDishDone(message: AssistantMessage, dish: PantryRecommendationDish): boolean {
  return doneDishes.value.has(dishKey(message, dish))
}

function isDishExpanded(message: AssistantMessage, dish: PantryRecommendationDish): boolean {
  return expandedDishes.value.has(dishKey(message, dish))
}

function toggleDish(message: AssistantMessage, dish: PantryRecommendationDish) {
  const key = dishKey(message, dish)
  const next = new Set(expandedDishes.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedDishes.value = next
}

async function completeDish(message: AssistantMessage, dish: PantryRecommendationDish) {
  const planId = message.payload?.pantry_plan_id
  if (!planId) return
  const key = dishKey(message, dish)
  completingDish.value = key
  try {
    const result = await pantryApi.completeRecipe(planId, dish.meal_index)
    doneDishes.value = new Set(doneDishes.value).add(key)
    if (result.already_done) {
      ElMessage.info('这道菜已经完成过，库存不会重复扣减')
    } else {
      const consumed = result.consumed.map((item) => `${item.name} -${item.deducted}${item.unit}`).join('、')
      const estimated = result.consumed.filter((item) => item.estimated).length
      const skipped = (result.skipped || []).length
      const base = consumed ? `已完成，扣减：${consumed}` : '已完成，但没有可精确扣减的库存'
      if (estimated || skipped) {
        ElMessage.warning(`${base}${estimated ? `；${estimated} 项按 1 个库存单位估算扣减` : ''}${skipped ? `；${skipped} 项用量不明确未扣减` : ''}`)
      } else {
        ElMessage.success(base)
      }
    }
  } catch (error) {
    ElMessage.error((error as ApiError).message || '完成失败')
  } finally {
    completingDish.value = ''
  }
}

function goInventory() {
  router.push('/inventory')
}

function recipeNameOf(message: AssistantMessage): string {
  return String(message.payload?.recipe_title || (message.payload?.recipe_data as Record<string, unknown> | undefined)?.title || '')
}

function recipeDataOf(message: AssistantMessage): Record<string, unknown> {
  const data = message.payload?.recipe_data
  if (data && typeof data === 'object') return data as Record<string, unknown>
  return {
    title: recipeNameOf(message),
    ingredients: message.payload?.recipe_summary?.main_ingredients || [],
  }
}

function dishFavoriteData(dish: PantryRecommendationDish): Record<string, unknown> {
  return {
    title: dish.name,
    name: dish.name,
    ingredients: dish.ingredients,
    main_ingredients: dish.main_ingredients,
    auxiliary_ingredients: dish.auxiliary_ingredients,
    steps: dish.steps,
    nutrition: dish.nutrition,
    versions: dish.versions,
    tips: dish.tips,
  }
}

async function loadFavorites() {
  try {
    const result = await favoriteApi.list()
    favoriteIds.value = new Map(result.items.map((item) => [item.recipe_name, item.id]))
  } catch {
    // 收藏状态加载失败不影响问答主流程
  }
}

async function toggleFavorite(name: string, data: Record<string, unknown>) {
  if (!name || favoritingName.value) return
  favoritingName.value = name
  try {
    const existing = favoriteIds.value.get(name)
    if (existing) {
      await favoriteApi.remove(existing)
      const next = new Map(favoriteIds.value)
      next.delete(name)
      favoriteIds.value = next
      ElMessage.success('已取消收藏')
    } else {
      const result = await favoriteApi.add(name, data)
      const next = new Map(favoriteIds.value)
      next.set(name, result.favorite.id)
      favoriteIds.value = next
      ElMessage.success('已加入我的收藏')
    }
  } catch (error) {
    ElMessage.error((error as ApiError).message || '收藏操作失败')
  } finally {
    favoritingName.value = ''
  }
}

function recipeIngredientsForConsume(message: AssistantMessage): Array<{ name: string; amount: string }> {
  const data = recipeDataOf(message)
  const raw = Array.isArray(data.ingredients) ? data.ingredients : []
  const result: Array<{ name: string; amount: string }> = []
  for (const value of raw) {
    if (typeof value === 'object' && value) {
      const item = value as { name?: string; amount?: string }
      if (item.name) result.push({ name: String(item.name), amount: String(item.amount || '') })
    } else {
      const text = String(value || '').trim()
      const match = text.match(/^(.+?)\s+([\d一二三四五六七八九十百半].*)$/)
      result.push(match ? { name: match[1].trim(), amount: match[2].trim() } : { name: text, amount: '' })
    }
  }
  return result
}

function isAuxName(name: string): boolean {
  return /(盐|生抽|老抽|酱油|蚝油|醋|料酒|食用油|白糖|冰糖|淀粉|胡椒粉|花椒|葱|姜|蒜|豆瓣酱|鸡精|味精|水)/.test(name)
}

async function refreshActiveRecipeMissing(message: AssistantMessage) {
  const ingredients = recipeIngredientsForConsume(message).filter(
    (item) => item.name && !isAuxName(item.name),
  )
  if (!ingredients.length) {
    activeRecipeMissing.value = []
    return
  }
  try {
    const pantry = await pantryApi.list()
    const names = (pantry.items || []).map((item) => item.name)
    activeRecipeMissing.value = ingredients.filter(
      (item) => !names.some((name) => name.includes(item.name) || item.name.includes(name)),
    )
  } catch {
    activeRecipeMissing.value = []
  }
}

async function consumeActiveRecipe() {
  const message = activeRecipeMessage.value
  if (!message || consumingRecipe.value) return
  if (activeRecipeMissing.value.length) {
    ElMessage.warning('还有主食材未补齐，请先采购后再开始做')
    return
  }
  const ingredients = recipeIngredientsForConsume(message)
  if (!ingredients.length) {
    ElMessage.warning('这道菜还没有可扣减的食材数据')
    return
  }
  consumingRecipe.value = true
  try {
    const result = await pantryApi.consumeRecipe(recipeNameOf(message), ingredients)
    if (result.consumed?.length) {
      ElMessage.success(`已完成烹饪，扣减 ${result.consumed.length} 项库存`)
      activeRecipeMissing.value = result.missing || []
    } else if (result.missing?.length) {
      ElMessage.warning('库存中没有找到对应食材，暂未扣减，请先补购')
    } else {
      ElMessage.info(result.message)
    }
  } catch (error) {
    ElMessage.error((error as ApiError).message || '扣减库存失败')
  } finally {
    consumingRecipe.value = false
  }
}

function addMissingToShopping() {
  const first = activeRecipeMissing.value[0]
  if (!first) return
  router.push({ name: 'pantry', query: { tab: 'plan', purchase: first.name } })
  recipeDrawerOpen.value = false
  ElMessage.info(`已打开采购清单，请确认缺少的「${first.name}」`)
}

function goRecipePlan() {
  router.push({ path: '/pantry', query: { tab: 'plan' } })
}

function openRecipeDetails(message: AssistantMessage, version: 'novice' | 'chef' = 'novice') {
  activeRecipeMessage.value = message
  activeRecipeVersion.value = version
  recipeDrawerOpen.value = true
  activeRecipeMissing.value = []
  refreshActiveRecipeMissing(message)
}

function chooseRecipeOption(option: RecipeOption) {
  if (sending.value) return
  send(`我选${option.title}，请给出做法`)
}

function saveActiveRecipe(version: 'novice' | 'chef' = 'novice') {
  if (activeRecipeMessage.value) saveRecipeToPlan(activeRecipeMessage.value, version)
}

async function saveRecipeToPlan(message: AssistantMessage, version: 'novice' | 'chef' = 'novice') {
  const id = message.id
  savingRecipe.value = id
  try {
    await pantryApi.addRecipeFromAssistant(id, version)
    savedRecipeIds.value = new Set(savedRecipeIds.value).add(id)
    ElMessage.success('已加入食谱规划，可在食谱规划里查看缺料并扣减库存')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '加入食谱失败')
  } finally {
    savingRecipe.value = null
  }
}

function parseContextFromRoute(): Record<string, unknown> | null {
  const raw = route.query.context
  const value = Array.isArray(raw) ? raw[0] : raw
  if (!value) return null
  try {
    const parsed = JSON.parse(String(value))
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function clearContextMode() {
  if (!contextRecipe.value && !route.query.context) return
  contextRecipe.value = null
  if (route.query.context) router.replace({ name: 'assistant' })
}

function renderContextGreeting() {
  const title = String(contextRecipe.value?.title || contextRecipe.value?.name || '这道菜')
  sessionId.value = null
  messages.value = [{
    id: -Date.now(),
    role: 'assistant',
    content: isKnowledgeContext.value
      ? `🤖：已为您切换到【${title}】专属问答模式。想了解它的用途、安全边界或健康替代吗？`
      : `🤖：已为您切换到【${title}】专属问答模式。关于${contextSubject.value}的火候、食材替换或营养禁忌，您想了解什么？`,
    mode: 'context_ai',
    matched_slug: null,
    sources: [],
    payload: { coverage: 'context', context_recipe: contextRecipe.value || undefined },
    created_at: new Date().toISOString(),
  }]
  question.value = ''
  scrollToBottom()
}

async function send(text?: string) {
  if (listening.value) stopVoice()
  const value = (text ?? question.value).trim()
  if (!value || sending.value) return
  if (value.length < 2) {
    ElMessage.warning('问题太短了，请多写几个字')
    return
  }
  if (!isMeaningfulQuestion(value)) {
    ElMessage.warning('请输入具体问题，纯数字或乱码不会保存到历史记录')
    return
  }
  messages.value.push({
    id: -Date.now(),
    role: 'user',
    content: value,
    mode: 'user',
    matched_slug: null,
    sources: [],
    payload: {},
    created_at: new Date().toISOString(),
  })
  question.value = ''
  sending.value = true
  errorMessage.value = ''
  scrollToBottom()
  try {
    const liveProfile = await loadAssistantHealthProfile()
    const data = await assistantApi.ask(
      value,
      sessionId.value,
      contextRecipe.value,
      liveProfile,
    )
    sessionId.value = data.session_id
    messages.value.push(toAssistantMessage(data))
    await loadSessions()
  } catch (error) {
    messages.value.pop()
    question.value = value
    errorMessage.value = (error as ApiError).message || '提问失败，请稍后重试'
    ElMessage.error(errorMessage.value)
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function setupSpeech() {
  const w = window as any
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition
  speechSupported.value = Boolean(Ctor)
  if (!Ctor || recognition) return
  const instance = new Ctor()
  instance.lang = 'zh-CN'
  instance.continuous = false
  instance.interimResults = true
  instance.onstart = () => {
    listening.value = true
    if (voiceStartTimer) {
      clearTimeout(voiceStartTimer)
      voiceStartTimer = null
    }
  }
  instance.onresult = (event: any) => {
    let finalText = ''
    let interimText = ''
    for (let index = event.resultIndex || 0; index < event.results.length; index += 1) {
      const result = event.results[index]
      const transcript = result?.[0]?.transcript || ''
      if (result?.isFinal) finalText += transcript
      else interimText += transcript
    }
    const text = (finalText || interimText).trim()
    if (!text) return
    const combined = voiceBase ? `${voiceBase} ${text}` : text
    question.value = combined.slice(0, 200)
    nextTick(() => inputRef.value?.resizeTextarea?.())
  }
  instance.onend = () => {
    listening.value = false
  }
  instance.onerror = (event: any) => {
    listening.value = false
    if (voiceStartTimer) {
      clearTimeout(voiceStartTimer)
      voiceStartTimer = null
    }
    const code = event?.error || ''
    if (code === 'not-allowed' || code === 'service-not-allowed') {
      ElMessage.warning('麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试')
    } else if (code === 'no-speech') {
      ElMessage.info('没有听清，请靠近麦克风再说一次')
    } else if (code === 'audio-capture') {
      ElMessage.warning('没有找到麦克风设备')
    } else if (code !== 'aborted') {
      ElMessage.warning('语音识别失败，请改用文字输入')
    }
  }
  recognition = instance
}

function toggleVoice() {
  if (!speechSupported.value) {
    ElMessage.info('当前浏览器不支持语音识别，请使用 Chrome/Edge，或直接输入文字')
    return
  }
  if (listening.value) {
    stopVoice()
    return
  }
  voiceBase = question.value.trim()
  try {
    recognition?.start()
    if (voiceStartTimer) clearTimeout(voiceStartTimer)
    voiceStartTimer = setTimeout(() => {
      if (!listening.value) {
        ElMessage.info('语音识别未能启动，请检查麦克风权限后重试')
        stopVoice()
      }
    }, 1600)
  } catch {
    ElMessage.info('语音识别暂时不可用，请直接输入文字')
  }
}

function stopVoice() {
  if (voiceStartTimer) {
    clearTimeout(voiceStartTimer)
    voiceStartTimer = null
  }
  try {
    recognition?.stop()
  } catch {
    /* ignore */
  }
  listening.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    send()
  }
}

/** 把 AI 回答里的 [K1] 渲染成可读的引用角标 */
function segments(text: string) {
  const parts: Array<{ type: 'text' | 'cite'; value: string }> = []
  const pattern = /\[K(\d{1,2})\]/g
  let lastIndex = 0
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > lastIndex) parts.push({ type: 'text', value: text.slice(lastIndex, index) })
    parts.push({ type: 'cite', value: match[1] })
    lastIndex = index + match[0].length
  }
  if (lastIndex < text.length) parts.push({ type: 'text', value: text.slice(lastIndex) })
  return parts
}

function plainText(text: string) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/`/g, '')
}

function needsIngredientPhoto(message: AssistantMessage) {
  if (message.role !== 'assistant') return false
  const text = [
    message.content,
    ...sectionsOf(message).map((section) => section.text),
  ].join(' ')

  return (
    /(?:配料表|包装标签|配料信息).{0,40}(?:没|未|还没|上传|发送|发来|提供|拍照)/.test(text) ||
    /(?:没|未|还没).{0,40}(?:配料表|包装标签|配料信息)/.test(text)
  )
}

function goIngredientPhoto() {
  router.push({ name: 'analyze' })
}

function paragraphs(text: string) {
  return plainText(text)
    .split(/\n{2,}/)
    .filter((item) => item.trim())
}

function relatedOf(message: AssistantMessage) {
  return message.payload?.related || []
}

function verifiedCount(sources: AssistantSource[]) {
  return sources.filter((item) => item.verified).length
}

function sectionsOf(message: AssistantMessage) {
  return message.payload?.sections || []
}

function speechTextOf(message: AssistantMessage) {
  const sections = sectionsOf(message)
  if (sections.length) {
    return sections.map((section) => `${section.label}：${section.text}`).join('。')
  }
  return String(message.content || '')
}

function toggleSpeak(message: AssistantMessage) {
  if (!('speechSynthesis' in window)) {
    ElMessage.warning('当前浏览器不支持语音播报')
    return
  }

  const synth = window.speechSynthesis
  if (speakingId.value === message.id) {
    synth.cancel()
    speakingId.value = null
    return
  }

  synth.cancel()
  const text = speechTextOf(message)
    .replace(/\[K\d+\]/g, '')
    .replace(/[*_#>`]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) return

  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  utterance.rate = 1
  utterance.pitch = 1
  utterance.onend = () => {
    if (speakingId.value === message.id) speakingId.value = null
  }
  utterance.onerror = () => {
    if (speakingId.value === message.id) speakingId.value = null
  }
  speakingId.value = message.id
  synth.speak(utterance)
}

function entryOf(message: AssistantMessage) {
  return message.payload?.entry || null
}

onMounted(async () => {
  setupSpeech()
  contextRecipe.value = parseContextFromRoute()
  await Promise.all([
    loadOverview(),
    loadSessions(),
    loadFavorites(),
    loadAssistantHealthProfile(),
  ])
  if (contextRecipe.value) renderContextGreeting()

  const rawPrompt = route.query.prompt
  const initialPrompt = String(Array.isArray(rawPrompt) ? rawPrompt[0] : rawPrompt || '').trim()
  if (initialPrompt) {
    await send(initialPrompt)
    const query = { ...route.query }
    delete query.prompt
    router.replace({ name: 'assistant', query })
  }
})

onUnmounted(() => {
  try {
    recognition?.abort?.()
  } catch {
    /* ignore */
  }
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  speakingId.value = null
  recognition = null
})
</script>

<template>
  <div class="assistant-page">
    <header class="assistant-hero card">
      <div class="hero-main">
        <div class="hero-badge">
          <el-icon><ChatDotRound /></el-icon>
          RAG 知识库问答
        </div>
        <h1>AI 食安智询官</h1>
        <p>
          基于 RAG 增强检索与权威知识库构建。解答食安疑惑、提供营养建议、规划家常菜谱，所有科普均带权威来源。
        </p>
        <div class="hero-meta">
          <el-tag size="small" type="success" effect="light">{{ modeLabel }}</el-tag>
          <span class="hero-stat">已核对 {{ stats?.verified ?? '—' }} 条 · 待核验 {{ stats?.pending ?? '—' }} 条</span>
        </div>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="newChat">
          <el-icon><Plus /></el-icon>
          新对话
        </el-button>
        <el-button class="history-btn" plain @click="historyOpen = true">
          <el-icon><Clock /></el-icon>
          历史对话
        </el-button>
      </div>
    </header>

    <div class="assistant-body">
      <aside class="session-panel card">
        <div class="panel-head">
          <span>历史对话</span>
          <div class="panel-head-actions">
            <el-button text size="small" @click="newChat">新建</el-button>
            <el-button text size="small" type="danger" :disabled="!sessions.length" @click="clearHistory">
              清空历史
            </el-button>
          </div>
        </div>
        <div v-if="!sessions.length" class="panel-empty">还没有对话，问一个问题就会生成</div>
        <ul v-else class="session-list session-list-main">
          <li
            v-for="item in sessions"
            :key="item.id"
            :class="{ active: item.id === sessionId }"
            @click="openSession(item.id)"
          >
            <div class="session-main">
              <div class="session-title" :title="item.title">
                {{ item.title }}
              </div>
              <span class="session-count">
                {{ item.message_count ?? 0 }} 条对话
              </span>
            </div>

            <div class="session-side">
              <span class="session-time">
                {{ formatTime(item.updated_at) }}
              </span>
              <el-icon
                class="session-del"
                aria-label="删除对话"
                @click.stop="removeSession(item.id)"
              >
                <Delete />
              </el-icon>
            </div>
          </li>
        </ul>
      </aside>

      <section class="chat card">
        <div class="knowledge-source">
          <span class="knowledge-source-icon" aria-hidden="true">🔐</span>
          <span>知识来源：中国食物成分表、GB 2760 国家标准</span>
        </div>

        <div ref="listRef" class="chat-list">
          <div v-if="!hasMessages" class="welcome">
            <div class="welcome-icon"><el-icon><Reading /></el-icon></div>
            <h2>从一个常见问题开始</h2>
            <p class="welcome-tip">
              每个回答都带「结论 / 为什么 / 依据 / 来源」；知识库没有的问题会说明情况，必要时给出 AI 补充回答。
            </p>
            <div class="suggestion-grid">
              <button
                v-for="(item, index) in featured"
                :key="item.slug"
                type="button"
                class="suggestion"
                @click="send(item.question || item.title)"
              >
                <span class="suggestion-icon" aria-hidden="true">{{ featuredIcon(index) }}</span>
                <span class="suggestion-copy">
                  <span class="suggestion-title">{{ item.title }}</span>
                  <span class="suggestion-cat">{{ item.category_label }}</span>
                </span>
              </button>
            </div>
            <div class="welcome-note">
              <el-icon><InfoFilled /></el-icon>
              本助手用于科普参考，不构成医疗诊断；身体不适请及时就医。
            </div>
          </div>

          <template v-for="message in messages" :key="message.id">
            <div v-if="message.role === 'user'" class="bubble-row user">
              <div class="bubble user-bubble">{{ message.content }}</div>
            </div>

            <div v-else class="answer">
              <div class="answer-head">
                <span class="answer-avatar"><el-icon><ChatDotRound /></el-icon></span>
                <div class="answer-head-main">
                  <template v-if="entryOf(message)">
                    <div class="answer-title">{{ entryOf(message)?.title }}</div>
                    <div class="answer-tags">
                      <el-tag size="small" effect="plain">{{ entryOf(message)?.category_label }}</el-tag>
                      <el-tag
                        size="small"
                        :type="entryOf(message)?.verification_status === 'verified' ? 'success' : 'warning'"
                        effect="light"
                      >
                        {{ entryOf(message)?.verification_label }}
                      </el-tag>
                      <el-tag v-if="message.payload?.coverage === 'related'" size="small" type="warning" effect="dark">
                        未直接命中
                      </el-tag>
                      <el-tag v-if="message.payload?.context_used" size="small" type="info" effect="plain">已结合上文</el-tag>
                      <span class="answer-mode">
                        {{ message.mode === 'ai' ? 'RAG 知识提炼 · 已溯源防幻觉' : message.mode === 'ai_rerank' ? 'AI 匹配相近条目 · 内容取自条目原文' : message.mode === 'ai_general' ? 'AI 补充回答' : '检索直答 · 未调用大模型' }}
                      </span>
                    </div>
                  </template>
                  <template v-else-if="message.payload?.coverage === 'recipe'">
                    <div class="answer-title">{{ message.payload?.recipe_title || '家常菜谱' }} · 新手步骤</div>
                    <div class="answer-tags">
                      <el-tag size="small" type="success" effect="plain">
                        {{ message.mode === 'recipe_ai' ? 'AI 烹饪步骤' : '菜谱整理' }}
                      </el-tag>
                      <span class="answer-mode">
                        {{ message.mode === 'recipe_ai' ? '按通用烹饪知识生成 · 非本站核验' : '新手分步教学 · 非食品安全结论' }}
                      </span>
                      <el-tag v-if="message.payload?.context_used" size="small" type="info" effect="plain">已结合上文</el-tag>
                    </div>
                  </template>
                  <template v-else-if="message.payload?.coverage === 'recipe_options'">
                    <div class="answer-title">推荐做法 · 先选一个</div>
                    <div class="answer-tags">
                      <el-tag size="small" type="success" effect="plain">菜谱教练</el-tag>
                      <span class="answer-mode">先给 2–3 个方向，选定后再展开步骤</span>
                    </div>
                  </template>
                  <template v-else-if="message.payload?.coverage === 'context'">
                    <div class="answer-title">当前{{ contextSubject === '这款食品' ? '食品' : '菜谱' }}专属问答 · {{ contextTitle }}</div>
                    <div class="answer-tags">
                      <el-tag size="small" type="success" effect="plain">已带入菜谱上下文</el-tag>
                      <span class="answer-mode">AI 会结合食材、步骤和营养回答省略追问</span>
                    </div>
                  </template>
                  <template v-else-if="message.payload?.coverage === 'pantry_recipe'">
                    <div class="answer-title">根据食材管家推荐 · {{ message.payload?.pantry_servings || 2 }} 人份</div>
                    <div class="answer-tags">
                      <el-tag size="small" type="success" effect="plain">食材管家</el-tag>
                      <span class="answer-mode">已结合现有库存、份量与健康画像</span>
                    </div>
                  </template>
                  <template v-else-if="message.payload?.coverage === 'inventory'">
                    <div class="answer-title">结合食材库存的回答</div>
                    <div class="answer-tags">
                      <el-tag size="small" type="success" effect="plain">食材管家</el-tag>
                      <span class="answer-mode">
                        已读取 {{ message.payload?.inventory_items?.length || 0 }} 项库存，结合问题回答
                      </span>
                    </div>
                  </template>
                  <template v-else-if="message.payload?.coverage === 'profile'">
                    <div class="answer-title">结合您的健康画像 · 专属建议</div>
                    <div class="answer-tags">
                      <el-tag size="small" type="success" effect="plain">专属营养</el-tag>
                      <span class="answer-mode">已读取您的健康档案</span>
                    </div>
                  </template>
                  <template v-else-if="message.payload?.coverage === 'general'">
                    <div class="answer-title">AI 营养师综合建议</div>
                    <div class="answer-tags">
                      <el-tag size="small" type="info" effect="plain">AI 补充</el-tag>
                      <span class="answer-mode">结合常识与您的健康画像</span>
                      <el-tag v-if="message.payload?.context_used" size="small" type="info" effect="plain">已结合上文</el-tag>
                    </div>
                  </template>
                  <div v-else class="answer-title">未在国标库中匹配到完全一致的答案</div>
                </div>
              </div>

              <div v-if="message.payload?.mode_note && message.payload?.coverage !== 'general'" class="mode-note">
                <el-icon><InfoFilled /></el-icon>
                {{ message.payload.mode_note }}
              </div>

              <div v-if="message.payload?.coverage === 'general'" class="general-warning">
                <el-icon><InfoFilled /></el-icon>
                <span>涉及用药、中毒、过敏请务必咨询医生或药师。</span>
              </div>

              <div v-if="message.payload?.coverage === 'recipe'" class="general-warning">
                <el-icon><InfoFilled /></el-icon>
                <span>菜谱用于烹饪参考，不是食品安全结论；生熟分开，肉类和蛋类要彻底加热。</span>
              </div>

              <div
                v-if="message.payload?.coverage === 'recipe_options' && message.payload?.recipe_options?.length"
                class="recipe-option-grid"
              >
                <button
                  v-for="option in message.payload.recipe_options"
                  :key="option.title"
                  type="button"
                  class="recipe-option"
                  :disabled="sending"
                  @click="chooseRecipeOption(option)"
                >
                  <div class="recipe-option-head">
                    <strong>{{ option.title }}</strong>
                    <span>{{ option.time || '约30分钟' }}</span>
                  </div>
                  <div class="recipe-option-main">
                    <span v-for="item in option.main_ingredients" :key="item">{{ item }}</span>
                  </div>
                  <p v-if="option.safety" class="recipe-option-safety">⚠️ {{ option.safety }}</p>
                  <span class="recipe-option-cta">选这个做法 →</span>
                </button>
              </div>

              <template v-if="message.payload?.matched === false">
                <p class="unmatched-text">{{ message.content }}</p>
                <div v-if="relatedOf(message).length" class="related-block">
                  <span class="related-label">看看这些相关问题：</span>
                  <button
                    v-for="item in relatedOf(message)"
                    :key="item.slug"
                    type="button"
                    class="related-chip"
                    @click="send(item.title)"
                  >
                    {{ item.title }}
                  </button>
                </div>
              </template>

              <template v-else>
                <div v-if="message.payload?.coverage === 'inventory'" class="ai-answer inventory-answer">
                  <p v-for="(paragraph, index) in paragraphs(message.content)" :key="index">{{ paragraph }}</p>
                </div>
                <div v-if="message.payload?.action === 'jump_to_inventory'" class="inventory-action">
                  <el-button type="success" plain @click="goInventory">
                    {{ message.payload?.action_label || '管理我的冰箱库存' }}
                  </el-button>
                </div>
                <RecipeSummaryCard
                  v-if="message.payload?.coverage === 'recipe' && message.payload?.recipe_summary"
                  :summary="message.payload.recipe_summary"
                  :versions="message.payload.recipe_versions || null"
                  :saved="savedRecipeIds.has(message.id)"
                  :saving="savingRecipe === message.id"
                  :favorite="favoriteIds.has(recipeNameOf(message))"
                  :favoriting="favoritingName === recipeNameOf(message)"
                  @view="openRecipeDetails(message, $event)"
                  @save="saveRecipeToPlan(message, $event)"
                  @favorite="toggleFavorite(recipeNameOf(message), recipeDataOf(message))"
                />
                <div v-if="sectionsOf(message).length && message.payload?.coverage !== 'recipe'" class="sections">
                  <div v-for="section in sectionsOf(message)" :key="section.key" class="section">
                    <div class="section-label">{{ section.label }}</div>
                    <p class="section-text">{{ section.text }}</p>
                  </div>
                </div>
                <div v-else-if="message.payload?.coverage !== 'recipe'" class="ai-answer">
                  <p v-for="(paragraph, index) in paragraphs(message.content)" :key="index">
                    <template v-for="(segment, segIndex) in segments(paragraph)" :key="segIndex">
                      <span v-if="segment.type === 'text'">{{ segment.value }}</span>
                      <sup v-else class="cite">{{ segment.value }}</sup>
                    </template>
                  </p>
                </div>

                <div v-if="needsIngredientPhoto(message)" class="ingredient-photo-action">
                  <el-button type="primary" plain @click="goIngredientPhoto">
                    <span class="emoji emoji1f4f7" aria-hidden="true">📷</span>
                    去拍照识别配料表
                  </el-button>
                </div>

                <div v-if="message.payload?.coverage === 'pantry_recipe' && pantryDishes(message).length" class="pantry-dishes">
                  <article
                    v-for="dish in pantryDishes(message)"
                    :key="dish.meal_index"
                    class="pantry-dish"
                  >
                    <div class="pantry-dish-head">
                      <div>
                        <span class="pantry-meal-type">{{ dish.meal_type }}</span>
                        <strong>{{ dish.name }}</strong>
                      </div>
                      <div class="pantry-dish-tags">
                        <button
                          type="button"
                          class="pantry-favorite"
                          :disabled="favoritingName === dish.name"
                          @click.stop="toggleFavorite(dish.name, dishFavoriteData(dish))"
                        >
                          {{ favoriteIds.has(dish.name) ? '⭐ 已收藏' : '☆ 收藏' }}
                        </button>
                        <el-tag v-if="dishMissing(dish).length" size="small" type="warning" effect="plain">
                          缺 {{ dishMissing(dish).length }} 项
                        </el-tag>
                        <el-tag v-if="isDishDone(message, dish)" size="small" type="success" effect="plain">已完成</el-tag>
                      </div>
                    </div>
                    <div class="pantry-ingredient-groups">
                      <div class="pantry-ingredient-group">
                        <span class="pantry-ingredient-label">主食材</span>
                        <div class="pantry-ingredients">
                          <span v-for="item in dishMain(dish)" :key="`${dish.meal_index}-${item.name}`" class="pantry-chip">
                            {{ item.name }} {{ item.amount }}
                            <em v-if="item.expiring">临期</em>
                          </span>
                        </div>
                      </div>
                      <div v-if="dishAuxiliary(dish).length" class="pantry-ingredient-group">
                        <span class="pantry-ingredient-label">辅料</span>
                        <div class="pantry-ingredients">
                          <span v-for="item in dishAuxiliary(dish)" :key="`${dish.meal_index}-${item.name}`" class="pantry-chip auxiliary">
                            {{ item.name }} {{ item.amount }}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div v-if="dishMissing(dish).length" class="pantry-missing-block">
                      <div class="pantry-missing-title">这道菜需要补购（{{ dishMissing(dish).length }}）</div>
                      <div class="pantry-missing-chips">
                        <span v-for="item in dishMissing(dish)" :key="item.name" class="pantry-missing-chip">
                          {{ item.name }} {{ item.amount }}
                        </span>
                      </div>
                    </div>
                    <p v-else class="pantry-ready">这道菜食材已齐，可以直接做</p>
                    <div class="pantry-actions">
                      <el-button size="small" @click="toggleDish(message, dish)">
                        {{ isDishExpanded(message, dish) ? '收起步骤' : '去做' }}
                      </el-button>
                      <el-button
                        size="small"
                        type="primary"
                        :loading="completingDish === dishKey(message, dish)"
                        :disabled="isDishDone(message, dish)"
                        @click="completeDish(message, dish)"
                      >
                        {{ isDishDone(message, dish) ? '已完成' : '已完成，扣减库存' }}
                      </el-button>
                    </div>
                    <ol v-if="isDishExpanded(message, dish)" class="pantry-steps">
                      <li v-for="(step, index) in dish.steps" :key="index">{{ step }}</li>
                    </ol>
                  </article>
                  <p v-if="message.payload?.pantry_shopping?.length" class="pantry-shopping">
                    全部可能需要补购：{{ message.payload.pantry_shopping.join('、') }}
                  </p>
                </div>

                <div v-if="!sectionsOf(message).length && message.payload?.evidence" class="evidence-block">
                  <span class="section-label">依据摘要</span>
                  <p class="section-text">{{ message.payload.evidence }}</p>
                </div>

                <div v-if="message.sources.length" class="sources">
                <div class="sources-hint">回答中的 [K1] 指向下方「{{ entryOf(message)?.title }}」条目的来源文档</div>
                  <div class="sources-title">
                    <el-icon><Link /></el-icon>
                    该条目的参考来源（{{ message.sources.length }}）
                    <span class="sources-verified">已核对 {{ verifiedCount(message.sources) }}</span>
                  </div>
                  <ol class="source-list">
                    <li v-for="(source, index) in message.sources" :key="source.id" class="source-item">
                      <span class="source-index">{{ index + 1 }}</span>
                      <div class="source-main">
                        <div class="source-name">
                          {{ source.name }}
                          <el-tag v-if="source.verified" size="small" type="success" effect="plain">已核对</el-tag>
                          <el-tooltip
                            v-else
                            :content="`来自${source.publisher || '机构'}官网或专栏的公开资料，未逐条核对原文，请以官方原文为准`"
                            placement="top"
                          >
                            <el-tag size="small" type="info" effect="plain">机构资料</el-tag>
                          </el-tooltip>
                        </div>
                        <div class="source-meta">
                          {{ source.publisher }}
                          <template v-if="source.year"> · {{ source.year }}</template>
                          <template v-if="source.kind_label"> · {{ source.kind_label }}</template>
                          <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">官网</a>
                        </div>
                      </div>
                    </li>
                  </ol>
                  <p class="sources-note">
                    「已核对」= 已核对到具体标准或文件名称；「机构资料」= 仅引用机构官网/专栏的公开资料，未逐条核对原文，请以官方原文为准。
                  </p>
                </div>

                <div v-if="relatedOf(message).length" class="related-block">
                  <span class="related-label">还可以问：</span>
                  <button
                    v-for="item in relatedOf(message)"
                    :key="item.slug"
                    type="button"
                    class="related-chip"
                    @click="send(item.title)"
                  >
                    {{ item.title }}
                  </button>
                </div>
              </template>

              <div v-if="message.payload?.ai_error" class="ai-error">AI 调用失败：{{ message.payload.ai_error }}</div>

              <div v-if="message.payload?.coverage === 'general'" class="general-tips">
                <p>可以补充品牌、配料或具体场景再问一次，答案会更贴近你的问题。</p>
                <p>想查看带来源的结论，可以试试「隔夜菜能不能吃」「阿斯巴甜」这类知识库已收录的问题。</p>
              </div>

              <div class="answer-tools">
                <button
                  type="button"
                  class="speak-btn"
                  :class="{ speaking: speakingId === message.id }"
                  :aria-label="speakingId === message.id ? '停止语音播报' : '语音播报'"
                  @click="toggleSpeak(message)"
                >
                  {{ speakingId === message.id ? '⏹ 停止播报' : '🔊 语音播报' }}
                </button>
              </div>

              <div class="answer-foot">
                <template v-if="message.payload?.coverage === 'general'">
                  以上内容由 AI 结合通用知识生成，仅供参考；具体产品请以包装标签与官方资料为准
                </template>
                <template v-else>
                  仅基于本站收录资料整理，不构成医疗或食品安全结论
                  <template v-if="message.payload?.ai?.dropped_sentences">
                    · 已剔除 {{ message.payload.ai.dropped_sentences }} 句无依据内容
                  </template>
                </template>
              </div>
            </div>
          </template>

          <div v-if="sending" class="thinking">
            <span class="dot" /><span class="dot" /><span class="dot" />
            正在检索知识库…
          </div>
        </div>

        <div v-if="errorMessage" class="chat-error">
          <el-icon><WarningFilled /></el-icon>
          {{ errorMessage }}
          <el-button text size="small" @click="send()">重试</el-button>
        </div>

        <div class="quick-prompts" aria-label="专业快捷提问">
          <span class="quick-prompts-label">快捷提问</span>
          <button
            v-for="item in QUICK_PROMPTS"
            :key="item.label"
            type="button"
            class="quick-chip"
            :title="`填入提示词：${item.prompt}`"
            @click="fillQuickPrompt(item.prompt)"
          >
            {{ item.label }}
          </button>
        </div>

        <div class="composer" :class="{ 'composer-large': !hasMessages }">
          <el-input
            ref="inputRef"
            v-model="question"
            type="textarea"
            :autosize="hasMessages ? { minRows: 1, maxRows: 4 } : { minRows: 2, maxRows: 5 }"
            resize="none"
            maxlength="200"
            show-word-limit
            placeholder="例如：隔夜菜到底能不能吃？西瓜和桃子一起吃会中毒吗？"
            @keydown="onKeydown"
          />
          <el-tooltip
            :content="speechSupported ? (listening ? '停止语音输入' : '语音提问') : '当前浏览器不支持语音识别'"
            placement="top"
          >
            <el-button
              class="voice-button"
              :class="{ listening }"
              circle
              :disabled="sending"
              aria-label="语音输入"
              @click="toggleVoice"
            >
              <el-icon><Microphone /></el-icon>
            </el-button>
          </el-tooltip>
          <el-button class="send-btn" type="primary" :loading="sending" :disabled="!question.trim()" @click="send()">
            提问
          </el-button>
        </div>
        <div class="composer-tip">
          <span v-if="listening" class="voice-status"><i class="voice-dot" />正在听，请说话…</span>
          <span v-else>Enter 发送，Shift + Enter 换行 · 当前对话{{ currentSession ? '已保存' : '尚未保存' }}</span>
        </div>
      </section>
    </div>

    <el-drawer v-model="historyOpen" title="历史对话" direction="rtl" size="min(86vw, 360px)">
      <div class="drawer-actions">
        <el-button type="primary" plain @click="newChat">开始新对话</el-button>
        <el-button type="danger" plain :disabled="!sessions.length" @click="clearHistory">清空历史</el-button>
      </div>
      <div v-if="!sessions.length" class="panel-empty">还没有对话</div>
      <ul v-else class="session-list drawer">
        <li
          v-for="item in sessions"
          :key="item.id"
          :class="{ active: item.id === sessionId }"
          @click="openSession(item.id)"
        >
          <div class="session-title">{{ item.title }}</div>
          <div class="session-meta">
            <span>{{ item.message_count ?? 0 }} 条</span>
            <span class="session-time">{{ formatTime(item.updated_at) }}</span>
            <el-icon class="session-del" @click.stop="removeSession(item.id)"><Delete /></el-icon>
          </div>
        </li>
      </ul>
    </el-drawer>

    <RecipeDetailDrawer
      :model-value="recipeDrawerOpen"
      :title="activeRecipeMessage?.payload?.recipe_title || '详细做法'"
      :summary="activeRecipeMessage?.payload?.recipe_summary || null"
      :sections="activeRecipeMessage?.payload?.sections || []"
      :versions="activeRecipeMessage?.payload?.recipe_versions || null"
      :default-version="activeRecipeVersion"
      :saved="activeRecipeMessage ? savedRecipeIds.has(activeRecipeMessage.id) : false"
      :saving="activeRecipeMessage ? savingRecipe === activeRecipeMessage.id : false"
      :nutrition="activeRecipeMessage ? (activeRecipeMessage.payload?.recipe_data as any)?.nutrition : null"
      :ingredients="activeRecipeMessage ? recipeIngredientsForConsume(activeRecipeMessage) : []"
      :missing="activeRecipeMissing"
      :consuming="consumingRecipe"
      @update:model-value="recipeDrawerOpen = $event"
      @save="saveActiveRecipe"
      @consume="consumeActiveRecipe"
      @add-to-shopping="addMissingToShopping"
    />
  </div>
</template>

<style scoped>
.assistant-page {
  display: grid;
  gap: 16px;
  background: #f3f8f5;
}

.assistant-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
  background: linear-gradient(120deg, var(--brand-50), #ffffff 60%);
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--brand-700);
  background: var(--card);
  border: 1px solid #cfe7e1;
  border-radius: 999px;
  padding: 3px 10px;
  margin-bottom: 8px;
}

.hero-main h1 {
  font-size: 22px;
  margin: 0 0 6px;
  color: var(--text-1);
}

.hero-main p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--text-2);
  max-width: 720px;
}

.hero-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.hero-stat {
  font-size: 12px;
  color: var(--muted);
}

.hero-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.assistant-body {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
}

/* 全局 .card + .card 会给聊天区加 16px 上边距，导致左右两栏顶部和底部错位 */
.assistant-body > .chat.card {
  margin-top: 0;
}

.session-panel {
  position: sticky;
  top: 14px;
  align-self: stretch;
  height: 100%;
  max-height: calc(100vh - 120px);
  overflow: auto;
  padding: 14px;
  border: 1px solid #e6efe9;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(31, 61, 50, 0.06);
  scrollbar-width: thin;
  scrollbar-color: #c7d2cc #f2f5f3;
  scrollbar-gutter: stable;
}

.session-panel::-webkit-scrollbar {
  width: 9px;
}

.session-panel::-webkit-scrollbar-track {
  border-radius: 999px;
  background: #f2f5f3;
}

.session-panel::-webkit-scrollbar-thumb {
  border: 2px solid #f2f5f3;
  border-radius: 999px;
  background: #c7d2cc;
}

.session-panel::-webkit-scrollbar-thumb:hover {
  background: #8fa198;
}

.panel-head-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
  padding: 2px 4px 8px;
}

.panel-empty {
  font-size: 12.5px;
  color: var(--muted);
  padding: 10px 6px;
  line-height: 1.7;
}

.session-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}

.session-list-main li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0;
  min-width: 0;
  padding: 9px 10px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;
}

.session-main {
  flex: 1;
  min-width: 0;
  margin-right: 16px;
}

.session-main .session-title {
  width: 100%;
  display: block;
}

.session-count {
  display: block;
  margin-top: 3px;
  color: var(--muted);
  font-size: 10.5px;
  line-height: 1.35;
}

.session-side {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex: 0 0 auto;
  gap: 8px;
  white-space: nowrap;
}

.session-side .session-time {
  margin-left: 0;
}

.session-side .session-del {
  flex: 0 0 auto;
}

.session-list li {
  padding: 9px 10px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;
}

.session-list li:hover {
  background: var(--brand-50);
}

.session-list li.active {
  background: var(--brand-50);
  border-color: #cfe7e1;
}

.session-title {
  font-size: 13px;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
}

.session-time {
  margin-left: auto;
  color: #9aaba2;
  font-variant-numeric: tabular-nums;
}

.session-del {
  margin-left: 0;
  cursor: pointer;
}

.session-del:hover {
  color: var(--danger);
}

.chat {
  display: flex;
  flex-direction: column;
  min-height: 520px;
  padding: 0;
  overflow: hidden;
  border: 1px solid #e6efe9;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(31, 61, 50, 0.06);
}

.knowledge-source {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 14px 16px 0;
  padding: 8px 12px;
  border: 1px solid #e3f0e9;
  border-radius: 10px;
  background: #f5faf7;
  color: #6e8a7d;
  font-size: 11.5px;
  line-height: 1.6;
}

.knowledge-source-icon {
  font-size: 13px;
  line-height: 1;
}

.chat-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  min-height: 380px;
  max-height: calc(100vh - 300px);
  padding: 18px;
  overflow-y: auto;
}

.welcome {
  margin: auto;
  text-align: center;
  max-width: 640px;
}

.welcome-icon {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: var(--brand-50);
  color: var(--brand-700);
  display: grid;
  place-items: center;
  font-size: 24px;
  margin: 0 auto 12px;
}

.welcome h2 {
  margin: 0 0 6px;
  font-size: 18px;
}

.welcome-tip {
  margin: 0 0 18px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}

.suggestion-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  text-align: left;
}

.suggestion {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e3eee8;
  border-radius: 14px;
  background: #f7fbf9;
  color: inherit;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.suggestion:hover {
  border-color: #a9d3c9;
  background: #ffffff;
  box-shadow: 0 8px 20px rgba(16, 94, 80, 0.09);
  transform: translateY(-2px);
}

.suggestion-icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  border-radius: 10px;
  background: #eaf5ef;
  font-size: 15px;
}

.suggestion-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.suggestion-title {
  color: var(--text-1);
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.5;
}

.suggestion-cat {
  color: var(--muted);
  font-size: 11.5px;
}

.welcome-note {
  margin-top: 16px;
  font-size: 12px;
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.bubble-row {
  display: flex;
}

.bubble-row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: min(84%, 620px);
  padding: 10px 14px;
  border-radius: 14px;
  font-size: var(--chat-font-size, 14px);
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-bubble {
  background: var(--brand-700);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.answer {
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px 16px;
  background: var(--card);
}

.answer-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.answer-avatar {
  width: 30px;
  height: 30px;
  border-radius: 10px;
  background: var(--brand-50);
  color: var(--brand-700);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.answer-head-main {
  min-width: 0;
}

.answer-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text-1);
}

.answer-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  flex-wrap: wrap;
}

.answer-mode {
  font-size: 11.5px;
  color: var(--muted);
}

.mode-note {
  margin-top: 10px;
  font-size: 12px;
  color: #8a6d1f;
  background: #fdf8ee;
  border: 1px solid #f0e2c8;
  border-radius: 8px;
  padding: 7px 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.recipe-option-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.recipe-option {
  text-align: left;
  border: 1px solid #dce8e1;
  border-radius: 13px;
  background: linear-gradient(180deg, #fbfdfb, #fff);
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.15s, box-shadow 0.15s;
  font: inherit;
}

.recipe-option:hover:not(:disabled) {
  border-color: #7fb49d;
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(31, 90, 71, 0.09);
}

.recipe-option:disabled {
  opacity: 0.65;
  cursor: wait;
}

.recipe-option-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
}

.recipe-option-head strong {
  font-size: 16px;
  color: #183c30;
}

.recipe-option-head span {
  flex: none;
  font-size: 10.5px;
  color: #5d8a77;
  background: #eef7f1;
  border-radius: 999px;
  padding: 2px 7px;
}

.recipe-option-main {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 9px;
}

.recipe-option-main span {
  font-size: 11px;
  color: #6b8177;
  border: 1px solid #e5eee9;
  border-radius: 999px;
  padding: 1px 7px;
}

.recipe-option-safety {
  margin: 9px 0 0;
  color: #8a5a12;
  font-size: 11.5px;
  line-height: 1.6;
}

.recipe-option-cta {
  display: inline-block;
  margin-top: 10px;
  color: #1f7a5f;
  font-size: 12px;
  font-weight: 600;
}

.sections {
  margin-top: 12px;
  display: grid;
  gap: 10px;
}

.section-label {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--brand-700);
  background: var(--brand-50);
  border-radius: 6px;
  padding: 1px 7px;
  margin-bottom: 4px;
}

.section-text {
  margin: 0;
  font-size: var(--chat-font-size, 14px);
  line-height: 1.85;
  color: var(--text-2);
  white-space: pre-wrap;
}

.ai-answer {
  margin-top: 12px;
  font-size: var(--chat-font-size, 14px);
  line-height: 1.9;
  color: #374151 !important;
}

.ai-answer p {
  margin: 0 0 10px;
  color: #374151 !important;
  opacity: 1;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.ai-answer,
.ai-answer *,
.section-text,
.unmatched-text {
  color: #374151 !important;
  opacity: 1;
}

.section-text {
  white-space: pre-wrap;
  line-height: 1.9;
}

.cite {
  color: var(--brand-700);
  font-weight: 700;
  font-size: 11px;
  padding: 0 2px;
}

.unmatched-text {
  margin: 12px 0 0;
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-2);
}

.evidence-block {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface-2);
  border: 1px solid var(--border);
}

.recipe-save-action {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 12px 0 4px;
}

.pantry-dishes {
  display: grid;
  gap: 10px;
  margin: 10px 0;
}

.pantry-dish {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  background: var(--card);
}

.pantry-favorite {
  border: 1px solid #f0dca8;
  background: #fffaf0;
  color: #a97812;
  border-radius: 999px;
  padding: 3px 7px;
  font-size: 10.5px;
  cursor: pointer;
  white-space: nowrap;
}

.pantry-favorite:disabled {
  opacity: 0.6;
  cursor: wait;
}

.pantry-dish-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.pantry-dish-head strong {
  font-size: 14px;
  margin-left: 6px;
}

.pantry-meal-type {
  font-size: 10.5px;
  color: var(--brand-700);
  background: var(--brand-50);
  border-radius: 999px;
  padding: 2px 7px;
}

.pantry-dish-tags {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.pantry-ingredient-groups {
  display: grid;
  gap: 4px;
  margin: 8px 0;
}

.pantry-ingredient-group {
  display: flex;
  align-items: flex-start;
  gap: 5px;
}

.pantry-ingredient-label {
  flex: none;
  font-size: 10px;
  color: #7b9188;
  background: #f2f7f4;
  border-radius: 5px;
  padding: 2px 5px;
  line-height: 1.65;
}

.pantry-chip.auxiliary {
  color: #7d8e84;
  background: #fafcfb;
}

.pantry-ingredients {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 8px 0;
}

.pantry-chip {
  font-size: 11.5px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--text-2);
}

.pantry-chip em {
  font-style: normal;
  color: var(--warn);
  margin-left: 3px;
}

.pantry-missing-block {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fdf8ef;
  border: 1px solid #f0dfc4;
}

.pantry-missing-title {
  font-size: 11.5px;
  font-weight: 600;
  color: #9a5a0a;
  margin-bottom: 5px;
}

.pantry-missing-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.pantry-missing-chip {
  font-size: 11px;
  color: #8a5a12;
  background: #fff;
  border: 1px solid #efdcc0;
  border-radius: 999px;
  padding: 1px 7px;
}

.pantry-ready {
  margin: 8px 0 0;
  font-size: 11px;
  color: #2f7a56;
}

.pantry-missing {
  margin: 4px 0;
  font-size: 11.5px;
  color: #a05c0a;
  line-height: 1.7;
}

.pantry-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.pantry-steps {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--text-2);
}

.pantry-shopping {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted);
}

.inventory-answer {
  margin-top: 10px;
}

.inventory-action {
  margin: 12px 0 4px;
}

.ingredient-photo-action {
  margin: 12px 0 4px;
}

.sources {
  margin-top: 14px;
  border-top: 1px dashed var(--border);
  padding-top: 12px;
}

.general-warning {
  margin-top: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  background: var(--warn-bg);
  border: 1px solid #f0dcb8;
  color: #8a5a12;
  font-size: 12.5px;
  display: flex;
  gap: 6px;
  align-items: flex-start;
  line-height: 1.7;
}

.general-tips {
  margin-top: 10px;
  padding-left: 2px;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.9;
}

.general-tips p {
  margin: 0;
}

.ai-error {
  margin-top: 10px;
  font-size: 11.5px;
  color: #8b2f26;
}

.sources-verified {
  margin-left: 6px;
  font-size: 11px;
  color: var(--brand-700);
  font-weight: 500;
}

.sources-note {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.7;
}

.sources-hint {
  font-size: 11.5px;
  color: var(--muted);
  margin-bottom: 6px;
}

.sources-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 8px;
}

.source-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.source-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.source-index {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 11px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.source-name {
  font-size: 13px;
  color: var(--text-1);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.source-meta {
  font-size: 11.5px;
  color: var(--muted);
  margin-top: 2px;
}

.source-meta a {
  color: var(--brand-700);
  margin-left: 4px;
}

.related-block {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.related-label {
  font-size: 12px;
  color: var(--muted);
}

.related-chip {
  border: 1px solid var(--border);
  background: var(--surface-2);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text-2);
  cursor: pointer;
}

.related-chip:hover {
  border-color: #9ed4c8;
  color: var(--brand-700);
}

.answer-foot {
  margin-top: 12px;
  font-size: 11px;
  color: var(--muted);
}

.thinking {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--muted);
  padding-left: 4px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-500, #0f8f7b);
  animation: blink 1s infinite ease-in-out;
}

.dot:nth-child(2) {
  animation-delay: 0.15s;
}

.dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes blink {
  0%,
  100% {
    opacity: 0.25;
  }
  50% {
    opacity: 1;
  }
}

.answer-tools {
  display: flex;
  justify-content: flex-start;
  margin-top: 10px;
}

.speak-btn {
  padding: 5px 10px;
  border: 1px solid #dce8e2;
  border-radius: 999px;
  background: #f8fcfa;
  color: #4b6b5d;
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, color 0.16s ease;
}

.speak-btn:hover,
.speak-btn.speaking {
  border-color: #a9d3c9;
  background: #eaf5ef;
  color: #1f7a5f;
}

.chat-error {
  margin: 0 16px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--danger-bg);
  color: #8b2f26;
  font-size: 12.5px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.quick-prompts {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 16px 0;
  border-top: 1px solid var(--border);
  background: var(--card);
}

.quick-prompts-label {
  color: var(--muted);
  font-size: 11px;
  margin-right: 2px;
}

.quick-chip {
  padding: 6px 12px;
  border: 1px solid #dce9e2;
  border-radius: 999px;
  background: #f4faf7;
  color: #316a59;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.2;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(31, 61, 50, 0.03);
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.quick-chip:hover {
  border-color: #a9d3c9;
  background: #eaf5ef;
  transform: translateY(-1px);
}

.quick-chip:active {
  transform: translateY(0);
}

.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 8px 16px 6px;
  background: var(--card);
}

.composer :deep(.el-textarea) {
  flex: 1;
}

.composer :deep(.el-textarea__inner) {
  padding: 10px 14px;
  border: 1px solid #dce8e2;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 3px 10px rgba(31, 61, 50, 0.05);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.composer :deep(.el-textarea__inner:hover) {
  border-color: #b7d4c7;
}

.composer :deep(.el-textarea__inner:focus) {
  border-color: #91c6b1;
  box-shadow: 0 0 0 3px rgba(15, 123, 108, 0.1);
}

/* 刚开始还没有对话时，输入框更大、更醒目，方便直接开始提问 */
.composer-large {
  padding: 16px 18px 10px;
  gap: 12px;
}

.composer-large :deep(.el-textarea__inner) {
  padding: 14px 16px;
  font-size: 14.5px;
  line-height: 1.7;
  border-radius: 12px;
  background: var(--surface-2);
  box-shadow: 0 0 0 1px var(--border) inset;
}

.composer-large :deep(.el-textarea__inner:hover) {
  box-shadow: 0 0 0 1px #a9d3c9 inset;
}

.composer-large :deep(.el-textarea__inner:focus) {
  background: var(--card);
  box-shadow: 0 0 0 2px rgba(15, 123, 108, 0.18) inset;
}

.composer-large :deep(.el-button) {
  height: 54px;
  padding: 0 26px;
  font-size: 15px;
  border-radius: 11px;
}

.composer :deep(.send-btn) {
  min-width: 78px;
  height: 40px;
  padding: 0 20px;
  border: 0 !important;
  border-radius: 12px !important;
  background: #0f6b52 !important;
  color: #ffffff !important;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 6px 16px rgba(15, 107, 82, 0.2);
}

.composer :deep(.send-btn:hover) {
  background: #0b5a45 !important;
  box-shadow: 0 8px 18px rgba(15, 107, 82, 0.26);
}

.composer-large :deep(.send-btn) {
  height: 54px;
  font-size: 14px;
}

.composer :deep(.voice-button) {
  flex: 0 0 42px;
  width: 42px;
  height: 42px;
  padding: 0;
  border-radius: 50%;
  color: var(--brand-700);
}

.composer-large :deep(.voice-button) {
  height: 42px;
  width: 42px;
  padding: 0;
  border-radius: 50%;
}

.composer :deep(.voice-button.listening) {
  color: #c0392b;
  border-color: #e6a39b;
  background: #fdf1ef;
  animation: voice-pulse 1.4s ease-in-out infinite;
}

.voice-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #c0392b;
}

.voice-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #d64541;
  display: inline-block;
  animation: voice-pulse 1.1s ease-in-out infinite;
}

@keyframes voice-pulse {
  0%,
  100% {
    opacity: 1;
    box-shadow: 0 0 0 0 rgba(214, 69, 65, 0.25);
  }
  50% {
    opacity: 0.72;
    box-shadow: 0 0 0 6px rgba(214, 69, 65, 0);
  }
}

.composer-tip {
  padding: 0 16px 12px;
  font-size: 11px;
  color: var(--muted);
}

.drawer-actions {
  margin-bottom: 10px;
}

.session-list.drawer li {
  border: 1px solid var(--border);
  margin-bottom: 6px;
}

@media (max-width: 1023px) {
  .assistant-body {
    grid-template-columns: minmax(0, 1fr);
  }

  .session-panel {
    display: none;
  }

  .assistant-hero {
    flex-direction: column;
    padding: 16px;
  }

  .hero-actions {
    width: 100%;
  }

  .hero-actions .el-button {
    flex: 1;
  }

  .history-btn {
    display: inline-flex;
  }

  .chat-list {
    max-height: none;
    min-height: 320px;
    padding: 14px;
  }

  .suggestion-grid {
    grid-template-columns: 1fr;
  }

  .bubble {
    max-width: 92%;
  }

  /* 手机端：输入框吸附在底部导航上方，长对话里也能随时提问 */
  .chat {
    overflow: visible;
  }

  .quick-prompts {
    flex-wrap: nowrap;
    overflow-x: auto;
    padding: 9px 12px 0;
    scrollbar-width: none;
  }

  .quick-prompts::-webkit-scrollbar {
    display: none;
  }

  .quick-prompts-label {
    display: none;
  }

  .quick-chip {
    flex: 0 0 auto;
    font-size: 11.5px;
  }

  .composer {
    position: sticky;
    bottom: calc(var(--tabbar-h, 60px) + env(safe-area-inset-bottom) + 4px);
    z-index: 6;
    border-radius: 12px;
    box-shadow: 0 -4px 16px rgba(16, 36, 30, 0.08);
  }

  .composer-tip {
    display: none;
  }

  .composer-large {
    padding: 12px 12px 8px;
  }

  .composer-large :deep(.el-textarea__inner) {
    font-size: 14px;
    padding: 12px 14px;
  }

  .composer-large :deep(.el-button) {
    height: 48px;
    padding: 0 18px;
    font-size: 14px;
  }
}

@media (min-width: 1024px) {
  .history-btn {
    display: none;
  }
}

/* ===== 手机端专项（<768px）；桌面端保持原样 ===== */
@media (max-width: 767px) {
  .chat-list {
    /* 输入区已回到文档流，保留适度底部留白即可 */
    padding: 12px 12px 2.5rem;
  }

  .suggestion-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }

  .suggestion {
    width: 100%;
    padding: 12px;
  }

  .suggestion-title {
    font-size: 14px;
    line-height: 1.55;
  }

  .suggestion-cat {
    font-size: 11px;
  }

  .chat {
    overflow: visible;
  }

  /* 手机端取消悬浮，输入区正常跟在聊天列表下方 */
  .composer {
    position: static;
    bottom: auto;
    margin-top: 8px;
    flex-wrap: wrap;
    align-items: stretch;
    gap: 8px;
    padding: 8px 12px 10px;
    box-shadow: none;
  }

  .composer :deep(.el-textarea) {
    flex: 1 1 100%;
    width: 100%;
  }

  /* 手机端输入框更紧凑 */
  .composer :deep(.el-textarea__inner) {
    padding: 8px 13px;
    line-height: 1.5;
  }

  .composer :deep(.voice-button) {
    order: 2;
    flex: 0 0 42px;
    width: 42px;
    height: 40px;
  }

  .composer :deep(.send-btn) {
    order: 3;
    flex: 1 1 0;
    width: auto;
    height: 40px;
    min-width: 0;
    padding: 0 16px;
  }

  .composer-large {
    gap: 8px;
    padding: 10px 12px;
  }

  .composer-large :deep(.el-textarea__inner) {
    padding: 11px 13px;
    font-size: 14px;
  }

  .composer-large :deep(.el-button) {
    height: 40px;
    padding: 0 16px;
    font-size: 13px;
  }
}

</style>
