<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dishApi, knowledgeApi } from '@/api'
import { ApiError } from '@/api/client'
import type { DishInfo, KnowledgeEntry } from '@/api/types'
import { formatDate } from '@/utils/format'
import { useDietLog } from '@/composables/useDietLog'

type TabKey = 'all' | 'ingredient' | 'dishes' | 'risk' | 'terms' | 'science'
type SourceKind = 'knowledge' | 'merged_dish'

interface KnowledgeItem {
  type: 'knowledge'
  key: string
  title: string
  description: string
  entry: KnowledgeEntry
}

interface DishCard {
  type: 'dish'
  key: string
  title: string
  description: string
  dish?: DishInfo
  entry?: KnowledgeEntry
}

type HubItem = KnowledgeItem | DishCard

interface KnowledgeAiItem {
  id?: number
  title: string
  category: string
  category_label: string
  summary?: string
  source_name?: string
}

function knowledgeAiQuestion(item: KnowledgeAiItem): string {
  const name = item.title

  switch (item.category) {
    case 'dish':
      return `请帮我分析一下【${name}】的营养价值、热量，并结合我的健康画像看看适不适合我吃？`
    case 'ingredient':
      return `请帮我解读一下【${name}】的作用`
    case 'additive':
      return `请帮我评估一下【${name}】这个添加剂安全吗？`
    case 'nutrition':
      return `请用大白话解释【${name}】`
    case 'safety':
      return `请帮我详细科普一下关于【${name}】的食品安全知识。`
    default:
      return `请帮我解读一下【${name}】的科学含义，并结合日常饮食给我一些建议。`
  }
}

function askGlobalAi(item: KnowledgeAiItem) {
  const context = {
    context_type: 'knowledge',
    entry_id: item.id ?? null,
    title: item.title,
    name: item.title,
    category: item.category,
    category_label: item.category_label,
    summary: item.summary || '',
    source: item.source_name || '',
  }

  window.dispatchEvent(
    new CustomEvent('fsai:ask', {
      detail: {
        question: knowledgeAiQuestion(item),
        context,
      },
    }),
  )
}

interface SourceConfig {
  key: string
  label: string
  kind: SourceKind
  category?: string
}

interface SourceState extends SourceConfig {
  page: number
  pages: number
  total: number
  items: HubItem[]
  hasMore: boolean
}

interface TabConfig {
  key: TabKey
  label: string
}

const PAGE_SIZE = 12

/**
 * 后端 knowledge category 编码：
 * ingredient=常见配料，additive=食品添加剂，nutrition=营养术语，
 * safety=食品安全常识，label_rule=标签与核查规则。
 *
 * 「菜品」来自独立菜品营养库（/dishes），与知识库的「常见配料」一起
 * 组成膳食营养 Tab；所有内容都由接口返回，不再使用前端假数据。
 */
const tabSources: Record<TabKey, SourceConfig[]> = {
  // 全库概览：按分类分别取数，避免第一页被单一分类占满
  all: [
    // C 端只查 knowledge 表；不合并菜品库等其他表
    { key: 'all-dish', label: '🥗 常见菜品', kind: 'knowledge', category: 'dish' },
    { key: 'all-additive', label: '🧪 食品添加剂', kind: 'knowledge', category: 'additive' },
    { key: 'all-ingredient', label: '🥩 常见配料', kind: 'knowledge', category: 'ingredient' },
    { key: 'all-label-rule', label: '📋 标签与核查规则', kind: 'knowledge', category: 'label_rule' },
    { key: 'all-nutrition', label: '📖 营养术语', kind: 'knowledge', category: 'nutrition' },
    { key: 'all-safety', label: '🛡️ 食品安全常识', kind: 'knowledge', category: 'safety' },
  ],
  ingredient: [
    { key: 'ingredient', label: '🥩 常见配料', kind: 'knowledge', category: 'ingredient' },
  ],
  dishes: [
    // 只读取 knowledge 表中 category=dish 的已发布且已核验条目
    { key: 'dishes', label: '🥗 常见菜品', kind: 'knowledge', category: 'dish' },
  ],
  risk: [
    { key: 'additive', label: '🧪 食品添加剂', kind: 'knowledge', category: 'additive' },
  ],
  terms: [
    { key: 'nutrition', label: '📖 营养术语', kind: 'knowledge', category: 'nutrition' },
  ],
  science: [
    { key: 'safety', label: '🛡️ 食品安全常识', kind: 'knowledge', category: 'safety' },
    { key: 'label_rule', label: '📋 标签与核查规则', kind: 'knowledge', category: 'label_rule' },
  ],
}

const tabs: TabConfig[] = [
  { key: 'all', label: '全库概览' },
  { key: 'ingredient', label: '常见配料' },
  { key: 'dishes', label: '常见菜品' },
  { key: 'risk', label: '成分风险筛查' },
  { key: 'terms', label: '营养术语' },
  { key: 'science', label: '食安科普' },
]

const route = useRoute()
const router = useRouter()
const { addDish } = useDietLog()

const activeTab = ref<TabKey>('all')
const query = ref('')
const sections = ref<SourceState[]>([])
const loading = ref(true)
const loadingMore = ref(false)
const errorMessage = ref('')
const searchInvalid = ref(false)

const drawerVisible = ref(false)
const detailLoading = ref(false)
const current = ref<KnowledgeEntry | null>(null)
const related = ref<KnowledgeEntry[]>([])

const dishDrawerVisible = ref(false)
const dishCurrent = ref<DishInfo | null>(null)
const dishNutritionLoading = ref(false)
const dishNutritionError = ref('')

const searchPlaceholder = '搜索食物、菜品、配料或食安术语'
const normalizedQuery = computed(() => query.value.trim().toLowerCase())

const isSearchQueryValid = computed(() => {
  const keyword = normalizedQuery.value
  if (!keyword) return true

  const hasChinese = /[\u4e00-\u9fa5]/.test(keyword)
  const englishCount = (keyword.match(/[a-z]/g) || []).length

  return hasChinese || englishCount >= 2
})

const totalVisible = computed(() =>
  sections.value.reduce((sum, section) => sum + section.total, 0),
)

const isEmpty = computed(
  () =>
    !loading.value &&
    !searchInvalid.value &&
    sections.value.every((section) => section.items.length === 0),
)

const hasMore = computed(() =>
  sections.value.some((section) => section.hasMore),
)

function formatCalories(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function dishMacros(dish: DishInfo) {
  const energy = {
    carbs: dish.carbs_per_100g * 4,
    protein: dish.protein_per_100g * 4,
    fat: dish.fat_per_100g * 9,
  }
  const total = energy.carbs + energy.protein + energy.fat || 1
  return [
    {
      key: 'carbs',
      label: '碳水',
      percent: Math.round((energy.carbs / total) * 100),
      grams: dish.carbs_per_100g,
    },
    {
      key: 'protein',
      label: '蛋白质',
      percent: Math.round((energy.protein / total) * 100),
      grams: dish.protein_per_100g,
    },
    {
      key: 'fat',
      label: '脂肪',
      percent: Math.round((energy.fat / total) * 100),
      grams: dish.fat_per_100g,
    },
  ]
}

function portionCalories(dish: DishInfo): number {
  return Math.round((dish.calories_per_100g * dish.typical_portion_g) / 100)
}

function dishCalories(item: DishCard): string {
  const value =
    item.dish?.calories_per_100g ??
    item.entry?.calories_per_100g ??
    0

  return value > 0 ? formatCalories(value) : '--'
}

function dishMacroItems(item: DishCard) {
  const format = (value: number) =>
    value > 0 ? `${value.toFixed(1)}g` : '--'

  if (item.dish) {
    return [
      {
        key: 'carbs',
        label: '碳水',
        percent: format(item.dish.carbs_per_100g),
      },
      {
        key: 'protein',
        label: '蛋白质',
        percent: format(item.dish.protein_per_100g),
      },
      {
        key: 'fat',
        label: '脂肪',
        percent: format(item.dish.fat_per_100g),
      },
    ]
  }

  const entry = item.entry
  return [
    {
      key: 'carbs',
      label: '碳水',
      percent: format(entry?.carbs_per_100g || entry?.carbs || 0),
    },
    {
      key: 'protein',
      label: '蛋白质',
      percent: format(entry?.protein_per_100g || entry?.protein || 0),
    },
    {
      key: 'fat',
      label: '脂肪',
      percent: format(entry?.fat_per_100g || entry?.fat || 0),
    },
  ]
}

function toKnowledgeItem(entry: KnowledgeEntry): HubItem {
  // 全库概览里也把菜品统一成菜品卡片，避免同一个“菜品”出现两种样式
  if (entry.category === 'dish') {
    return {
      type: 'dish',
      key: `dish-knowledge-${entry.id}`,
      title: entry.title,
      description: entry.summary || '暂无描述',
      entry,
    }
  }

  return {
    type: 'knowledge',
    key: `knowledge-${entry.id}`,
    title: entry.title,
    description: entry.summary,
    entry,
  }
}

function normalizeDishKey(value: string): string {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s()（）【】\[\],，、;；:：。.\-_]/g, '')
}

function mergeDishCards(
  entries: KnowledgeEntry[],
  dishes: DishInfo[],
): DishCard[] {
  const index = new Map<string, KnowledgeEntry>()

  entries.forEach((entry) => {
    [entry.title, ...(entry.aliases || [])].forEach((name) => {
      const key = normalizeDishKey(name)
      if (key && !index.has(key)) index.set(key, entry)
    })
  })

  const usedEntries = new Set<number>()
  const cards: DishCard[] = []

  dishes.forEach((dish) => {
    const matched = [dish.dish_name, ...(dish.aliases || [])]
      .map((name) => index.get(normalizeDishKey(name)))
      .find(Boolean)

    if (matched) usedEntries.add(matched.id)

    cards.push({
      type: 'dish',
      key: `dish-${dish.slug}`,
      title: dish.dish_name,
      description: matched?.summary || dish.health_tip || '暂无描述',
      dish,
      entry: matched,
    })
  })

  // 后台手动新增、但菜品热量库尚未收录的菜品
  entries.forEach((entry) => {
    if (usedEntries.has(entry.id)) return

    cards.push({
      type: 'dish',
      key: `dish-knowledge-${entry.id}`,
      title: entry.title,
      description: entry.summary || '暂无描述',
      entry,
    })
  })

  return cards
}

function cardBadgeLabel(item: HubItem): string {
  if (item.type === 'dish') return '菜品已收录'

  switch (item.entry.category) {
    case 'additive':
      return '国标溯源'
    case 'nutrition':
      return '术语已收录'
    case 'safety':
    case 'label_rule':
      return '科普已发布'
    case 'ingredient':
      return '配料已收录'
    case 'dish':
      return '菜品已收录'
    default:
      return '知识已发布'
  }
}

function cardBadgeClass(item: HubItem): string {
  if (item.type === 'dish') return 'kb-card-badge--dish'
  return `kb-card-badge--${item.entry.category || 'knowledge'}`
}

function dishSummaryNeedsImprovement(entry: KnowledgeEntry): boolean {
  const summary = (entry.summary || '').trim()
  const title = (entry.title || '').trim()
  return !summary || summary === title || summary.length < 12
}

function dishNeedsNutrition(dish: DishInfo): boolean {
  return [
    dish.calories_per_100g,
    dish.carbs_per_100g,
    dish.protein_per_100g,
    dish.fat_per_100g,
  ].some((value) => !Number.isFinite(Number(value)) || Number(value) <= 0)
}

async function hydrateDishNutrition(
  entry: KnowledgeEntry,
  dish: DishInfo,
) {
  if (
    !entry.id ||
    (!dishNeedsNutrition(dish) &&
      !dishSummaryNeedsImprovement(entry))
  ) {
    return
  }

  dishNutritionLoading.value = true
  dishNutritionError.value = ''

  try {
    const result = await knowledgeApi.estimateNutrition({
      entry_id: entry.id,
      title: entry.title,
      description: entry.summary || entry.content || '',
    })

    if (result.entry) {
      Object.assign(entry, result.entry)
    } else {
      entry.calories_per_100g = result.nutrition.calories_per_100g
      entry.carbs_per_100g = result.nutrition.carbs_per_100g
      entry.protein_per_100g = result.nutrition.protein_per_100g
      entry.fat_per_100g = result.nutrition.fat_per_100g
      entry.typical_portion_g = result.nutrition.typical_portion_g
    }

    const updated = dishFromKnowledgeEntry(entry, entry.title)
    Object.assign(dish, updated)

    if (dishCurrent.value?.slug === dish.slug) {
      dishCurrent.value = { ...updated }
    }

    if (result.nutrition_ai?.status === 'failed') {
      dishNutritionError.value =
        result.nutrition_ai.message || 'AI 营养补全失败，请稍后重试'
    }
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0
    dishNutritionError.value =
      status === 401
        ? '登录后可自动补全营养数据'
        : (error as ApiError).message || 'AI 营养补全失败，请稍后重试'
  } finally {
    dishNutritionLoading.value = false
  }
}

function dishFromKnowledgeEntry(
  entry: KnowledgeEntry,
  fallbackTitle: string,
): DishInfo {
  const number = (value: unknown) => {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
  }

  return {
    slug: entry.slug,
    dish_name: entry.title || fallbackTitle,
    aliases: entry.aliases || [],
    category: entry.category_label || '常见菜品',
    calories_per_100g: number(
      entry.calories_per_100g ?? entry.calories,
    ),
    protein_per_100g: number(
      entry.protein_per_100g ?? entry.protein,
    ),
    fat_per_100g: number(entry.fat_per_100g ?? entry.fat),
    carbs_per_100g: number(entry.carbs_per_100g ?? entry.carbs),
    typical_portion_g: Math.max(
      1,
      Number(entry.typical_portion_g || 200),
    ),
    health_tip:
      entry.summary?.trim() ||
      '菜品营养数据按常见做法估算，实际热量会因用油和份量有所差异。',
    source: entry.source_name || '平台菜品资料整理',
  }
}

function openCard(item: HubItem, event?: Event) {
  if (item.type === 'dish') {
    const dish =
      item.dish ||
      (item.entry
        ? dishFromKnowledgeEntry(item.entry, item.title)
        : null)

    if (!dish) return

    openDish(dish, event)

    if (
      item.entry &&
      (dishNeedsNutrition(dish) ||
        dishSummaryNeedsImprovement(item.entry))
    ) {
      void hydrateDishNutrition(item.entry, dish)
    }
    return
  }

  openEntry(item.entry.id, event)
}

function cardActionLabel(item: HubItem): string {
  if (item.type === 'dish') return 'AI 营养拆解'
  if (item.entry.category === 'additive') return 'AI 风险评估'
  return 'AI 解读'
}

function runCardAction(item: HubItem, event: Event) {
  event.stopPropagation()

  if (item.type === 'dish') {
    askDish(item)
  } else {
    askNutritionist(item.entry)
  }
}

function cardNote(item: HubItem): string {
  if (item.type === 'dish') {
    const calories =
      item.dish?.calories_per_100g ??
      item.entry?.calories_per_100g ??
      0
    const portion =
      item.dish?.typical_portion_g ??
      item.entry?.typical_portion_g ??
      200

    if (!calories) return '常见菜品 · -- kcal / 100g'
    return `常见一份 ${portion}g · ${Math.round((calories * portion) / 100)} kcal`
  }
  return `${item.entry.category_label} · 来源可追溯`
}

/**
 * 后端公开接口已经只返回 published，这里再做一次前端防御，
 * 确保草稿 / 下架条目永远不会进入 C 端列表。
 */
function publishedOnly(entries: KnowledgeEntry[]): KnowledgeEntry[] {
  return entries.filter((entry) => entry.status === 'published')
}

async function searchKnowledgePage(
  source: SourceState,
  page: number,
): Promise<void> {
  const data = await knowledgeApi.list({
    page,
    per_page: PAGE_SIZE,
    category: source.category,
    query: query.value.trim() || undefined,
  })

  const items = publishedOnly(data.items).map(toKnowledgeItem)
  const known = new Set(source.items.map((item) => item.key))

  source.items.push(...items.filter((item) => !known.has(item.key)))
  source.page = data.page
  source.pages = data.pages
  source.total = data.total
  source.hasMore = source.page < source.pages
}

async function loadMergedDishPage(source: SourceState): Promise<void> {
  const keyword = query.value.trim() || undefined

  const [knowledgeData, dishData] = await Promise.all([
    knowledgeApi.list({
      page: 1,
      per_page: 50,
      category: 'dish',
      query: keyword,
    }),
    dishApi.list({
      page: 1,
      per_page: 60,
      query: keyword,
    }),
  ])

  const entries = publishedOnly(knowledgeData.items)
  const cards = mergeDishCards(entries, dishData.items)

  source.items = cards
  source.total = cards.length
  source.page = 1
  source.pages = 1
  source.hasMore = false
}

async function loadSourcePage(
  source: SourceState,
  page: number,
  token: number,
): Promise<void> {
  if (token !== requestVersion) return

  if (source.kind === 'knowledge') {
    await searchKnowledgePage(source, page)
  } else {
    await loadMergedDishPage(source)
  }
}

let requestVersion = 0
let searchTimer: number | undefined

async function loadFirstPage() {
  if (searchInvalid.value) return

  const token = ++requestVersion
  const configs = tabSources[activeTab.value]

  sections.value = configs.map((config) => ({
    ...config,
    page: 0,
    pages: 0,
    total: 0,
    items: [],
    hasMore: true,
  }))

  loading.value = true
  loadingMore.value = false
  errorMessage.value = ''

  try {
    const results = await Promise.allSettled(
      sections.value.map((source) =>
        loadSourcePage(source, 1, token),
      ),
    )

    if (token !== requestVersion) return

    const failed = results.find(
      (result): result is PromiseRejectedResult =>
        result.status === 'rejected',
    )

    if (failed) {
      const reason = failed.reason as ApiError
      errorMessage.value = reason?.message || '智膳智库加载失败'
    }
  } finally {
    if (token === requestVersion) loading.value = false
  }
}

async function loadNextPage() {
  if (loading.value || loadingMore.value || !hasMore.value) return

  const token = requestVersion
  const targets = sections.value.filter((source) => source.hasMore)
  if (!targets.length) return

  loadingMore.value = true

  try {
    const results = await Promise.allSettled(
      targets.map((source) =>
        loadSourcePage(source, source.page + 1, token),
      ),
    )

    if (token !== requestVersion) return

    const failed = results.find(
      (result): result is PromiseRejectedResult =>
        result.status === 'rejected',
    )

    if (failed) {
      const reason = failed.reason as ApiError
      errorMessage.value = reason?.message || '加载更多失败'
    }
  } finally {
    if (token === requestVersion) loadingMore.value = false
  }
}

function resolveTab(value: string): TabKey {
  const aliases: Record<string, TabKey> = {
    all: 'all',
    全库概览: 'all',
    全库知识: 'all',
    ingredient: 'ingredient',
    常见配料: 'ingredient',
    food: 'dishes',
    diet: 'dishes',
    dish: 'dishes',
    dishes: 'dishes',
    膳食营养: 'dishes',
    膳食热量图谱: 'dishes',
    菜品: 'dishes',
    菜品知识: 'dishes',
    菜品热量库: 'dishes',
    常见菜品: 'dishes',
    risk: 'risk',
    additive: 'risk',
    成分风险: 'risk',
    食品添加剂: 'risk',
    terms: 'terms',
    nutrition: 'terms',
    营养术语: 'terms',
    science: 'science',
    safety: 'science',
    label_rule: 'science',
    食安科普: 'science',
    食品安全常识: 'science',
    标签与核查规则: 'science',
  }

  return aliases[value] || 'all'
}

function categoryQuery(): Record<string, string> {
  // 全库概览不带 category，让 /api/knowledge 返回全部已发布条目
  return activeTab.value === 'all' ? {} : { category: activeTab.value }
}

async function selectTab(key: TabKey) {
  if (activeTab.value === key) return

  activeTab.value = key
  await router.replace({ query: categoryQuery() })
  void loadFirstPage()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

watch(query, (value) => {
  if (searchTimer) window.clearTimeout(searchTimer)

  const keyword = value.trim()

  if (keyword && !isSearchQueryValid.value) {
    requestVersion += 1
    searchInvalid.value = true
    sections.value = []
    loading.value = false
    loadingMore.value = false
    errorMessage.value = ''
    return
  }

  searchInvalid.value = false
  searchTimer = window.setTimeout(() => {
    void loadFirstPage()
  }, 320)
})

const loadMoreSentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

function observeSentinel() {
  if (!observer || !loadMoreSentinel.value) return

  observer.disconnect()
  observer.observe(loadMoreSentinel.value)
}

onMounted(async () => {
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        void loadNextPage()
      }
    },
    { rootMargin: '320px 0px' },
  )

  activeTab.value = resolveTab(String(route.query.category || ''))
  await loadFirstPage()

  const dishSlug = String(route.query.dish || '')
  if (dishSlug) {
    const found = sections.value
      .flatMap((section) => section.items)
      .find(
        (item): item is DishCard =>
          item.type === 'dish' && item.dish?.slug === dishSlug,
      )

    if (found?.dish) {
      openDish(found.dish)
    } else {
      try {
        const data = await dishApi.detail(dishSlug)
        openDish(data.dish)
      } catch {
        /* 深链失效时保持列表页 */
      }
    }
  }

  const entryId = Number(route.query.entry)
  if (entryId) openEntry(entryId)

  await nextTick()
  observeSentinel()
})

watch([loading, loadingMore, hasMore, isEmpty], async () => {
  await nextTick()
  observeSentinel()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  if (searchTimer) window.clearTimeout(searchTimer)
})

let savedKnowledgeScrollY = 0

function rememberKnowledgeScroll() {
  if (!drawerVisible.value && !dishDrawerVisible.value) {
    savedKnowledgeScrollY = window.scrollY
  }
}

function restoreKnowledgeScroll() {
  window.requestAnimationFrame(() => {
    window.scrollTo(0, savedKnowledgeScrollY)
  })
}

function findKnowledgeItem(id: number): KnowledgeItem | undefined {
  for (const section of sections.value) {
    const found = section.items.find(
      (item): item is KnowledgeItem =>
        item.type === 'knowledge' && item.entry.id === id,
    )
    if (found) return found
  }
  return undefined
}

function openEntry(id: number, event?: Event) {
  event?.preventDefault()
  rememberKnowledgeScroll()
  drawerVisible.value = true
  detailLoading.value = true

  const found = findKnowledgeItem(id)
  current.value = found?.entry || null

  knowledgeApi
    .detail(id)
    .then((data) => {
      // 菜品统一走营养卡片，即使是从相关条目进入
      if (data.entry.category === 'dish') {
        drawerVisible.value = false
        current.value = null
        openDish(dishFromKnowledgeEntry(data.entry, data.entry.title))
        return
      }

      current.value = data.entry
      related.value = data.related
    })
    .catch((error) => {
      if (!current.value) {
        errorMessage.value = (error as ApiError).message || '条目加载失败'
      }
    })
    .finally(() => {
      detailLoading.value = false
    })
}

function closeDrawer() {
  drawerVisible.value = false
  restoreKnowledgeScroll()
}

function openDish(dish: DishInfo, event?: Event) {
  event?.preventDefault()
  rememberKnowledgeScroll()
  dishCurrent.value = dish
  dishDrawerVisible.value = true
}

function closeDishDrawer() {
  dishDrawerVisible.value = false
  dishCurrent.value = null
  restoreKnowledgeScroll()
}

function askNutritionist(entry: KnowledgeEntry) {
  askGlobalAi({
    id: entry.id,
    title: entry.title,
    category: entry.category,
    category_label: entry.category_label,
    summary: entry.summary,
    source_name: entry.source_name,
  })
}

function askDish(item: DishCard) {
  if (item.entry) {
    askNutritionist(item.entry)
    return
  }

  askGlobalAi({
    title: item.title,
    category: 'dish',
    category_label: '菜品',
    summary: item.description,
    source_name: '菜品营养库',
  })
}

function addDishToToday() {
  if (!dishCurrent.value) return
  const entry = addDish(dishCurrent.value)
  ElMessage.success(
    `已加入今日饮食：${dishCurrent.value.dish_name} · ${entry.calories} 大卡`,
  )
}
</script>

<template>
  <div
    class="page knowledge-page"
    style="background-color: #f4f7f9; min-height: 100vh;"
  >
    <header class="page-head">
      <div>
        <h1 class="page-title">智膳智库</h1>
        <p class="page-sub">
          分类与后台知识库同步，只展示“已发布 + 已核验”内容；科普问答在 AI 食安智询官中单独统计。
        </p>
      </div>
      <span
        class="kb-count"
        title="仅统计 /api/knowledge 返回的已发布且已核验知识；科普问答在 AI 食安智询官中单独统计"
      >
        共 {{ searchInvalid ? 0 : totalVisible }} 条已发布且已核验数据
      </span>
    </header>

    <div class="kb-tabs mt-4" role="tablist" aria-label="智膳智库分类">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        role="tab"
        class="kb-tab"
        :class="{ 'is-active': activeTab === tab.key }"
        :aria-selected="activeTab === tab.key"
        @click="selectTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="kb-search mt-3">
      <el-input
        v-model="query"
        class="kb-search-input"
        :placeholder="searchPlaceholder"
        size="large"
        clearable
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <p class="kb-search-hint">
        输入即搜索当前分类 · 支持菜名、配料、添加剂与营养术语
      </p>
    </div>

    <div v-if="errorMessage" class="notice notice-danger mt">
      <el-icon><WarningFilled /></el-icon>
      <div>
        {{ errorMessage }}
        <el-button text type="primary" @click="loadFirstPage">重试</el-button>
      </div>
    </div>

    <div
      v-if="searchInvalid"
      class="mt-4 rounded-xl border border-solid border-gray-100 bg-white p-10 text-center shadow-sm"
    >
      <div class="flex flex-col items-center gap-2 text-gray-500">
        <el-icon class="text-2xl text-gray-300"><Search /></el-icon>
        <h4 class="text-base font-semibold text-gray-700">搜索关键词太短</h4>
        <p class="text-sm text-gray-400">
          请输入至少 1 个汉字或 2 个英文字母，并尝试菜名、配料或营养术语。
        </p>
      </div>
    </div>

    <div
      v-else-if="loading"
      class="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3"
    >
      <div
        v-for="index in 6"
        :key="index"
        class="h-[280px] animate-pulse rounded-xl border border-solid border-gray-100 bg-white shadow-sm"
      />
    </div>

    <div
      v-else-if="isEmpty"
      class="mt-4 rounded-xl border border-solid border-gray-100 bg-white p-10 text-center shadow-sm"
    >
      <div class="flex flex-col items-center gap-2 text-gray-500">
        <el-icon class="text-2xl text-gray-300"><Search /></el-icon>
        <h4 class="text-base font-semibold text-gray-700">
          {{ normalizedQuery ? '没有找到相关条目' : '该分类暂时没有已发布内容' }}
        </h4>
        <p class="text-sm text-gray-400">
          {{ normalizedQuery
            ? '请换一个关键词，或切换上方分类继续浏览。'
            : '后台发布相关内容后会自动出现在这里。' }}
        </p>
      </div>
    </div>

    <div v-else class="knowledge-sections">
      <section
        v-for="section in sections"
        v-show="section.items.length"
        :key="section.key"
        class="kb-section"
      >
        <div class="mb-4 flex items-end justify-between gap-3">
          <h2 class="m-0 text-lg font-bold text-gray-800">
            {{ section.label }}
          </h2>
          <span class="text-xs font-medium text-gray-400">
            已发布 {{ section.total }} 条 · 已加载 {{ section.items.length }} 条
          </span>
        </div>

        <div
          class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 items-stretch"
          style="grid-auto-rows: 1fr; gap: 16px;"
        >
          <div
            v-for="item in section.items"
            :key="item.key"
            class="kb-card flex flex-col h-full"
            :class="item.type === 'dish'
              ? 'kb-card--food bg-gradient-to-br from-white to-orange-50/40'
              : 'kb-card--knowledge bg-white'"
            @click="openCard(item, $event)"
          >
            <div class="flex-grow">
              <div class="flex justify-between items-center mb-4">
                <span class="kb-category-label">
                  {{ item.type === 'dish' ? '常见菜品' : item.entry.category_label }}
                </span>

                <span
                  class="kb-card-badge"
                  :class="cardBadgeClass(item)"
                >
                  {{ cardBadgeLabel(item) }}
                </span>
              </div>

              <h3 class="kb-card-title">
                {{ item.title }}
              </h3>

              <template v-if="item.type === 'dish'">
                <div class="kb-calorie-row">
                  <span class="kb-calories">
                    {{ dishCalories(item) }}
                  </span>
                  <span class="kb-calorie-unit">kcal / 100g</span>
                </div>

                <div class="kb-macro-row">
                  <span
                    v-for="macro in dishMacroItems(item)"
                    :key="macro.key"
                    class="kb-macro"
                    :class="`kb-macro--${macro.key}`"
                  >
                    {{ macro.label }} {{ macro.percent }}
                  </span>
                </div>
              </template>

              <div class="kb-card-desc">
                <p class="kb-desc">
                  {{ item.description || '暂无描述' }}
                </p>
              </div>
            </div>

            <div class="kb-card-footer mt-auto pt-4 flex items-center justify-between border-t border-gray-100">
              <span class="kb-card-note">
                {{ cardNote(item) }}
              </span>

              <button
                type="button"
                class="kb-card-action"
                :class="item.type === 'dish'
                  ? 'kb-card-action--primary'
                  : 'kb-card-action--ghost'"
                @click.stop="runCardAction(item, $event)"
              >
                {{ cardActionLabel(item) }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <div
      v-if="!loading && !searchInvalid && !isEmpty"
      ref="loadMoreSentinel"
      class="kb-load-more"
      aria-live="polite"
    >
      <span v-if="loadingMore">正在加载更多…</span>
      <span v-else-if="hasMore">继续下滑加载更多</span>
      <span v-else>已经到底了</span>
    </div>

    <div class="notice notice-info mt-6">
      <el-icon><InfoFilled /></el-icon>
      <div>
        内容来自后台知识库的已发布条目与菜品营养库；待审核、下架内容不会出现在本页。
        菜品热量参考《中国食物成分表》与常见做法估算，不同餐厅会有差异。
        本页不构成合规或安全性判定依据。
      </div>
    </div>

    <el-drawer
      v-model="drawerVisible"
      :title="current?.title || '添加剂详情'"
      :size="'min(560px, 92vw)'"
      direction="rtl"
      @closed="closeDrawer"
    >
      <div v-if="current" class="flex flex-col gap-4 px-1 pb-4">
        <div class="flex flex-wrap gap-2">
          <span class="rounded-full bg-white border border-gray-200 px-2.5 py-1 text-[11px] text-gray-600">成分风险筛查</span>
          <span class="rounded-full bg-white border border-gray-200 px-2.5 py-1 text-[11px] text-gray-600">国标溯源</span>
          <span class="rounded-full bg-white border border-gray-200 px-2.5 py-1 text-[11px] text-gray-500">版本 {{ current.version }}</span>
        </div>

        <p class="rounded-lg bg-white border border-gray-200 px-4 py-3 text-sm leading-7 text-gray-700">
          {{ current.summary }}
        </p>

        <div class="space-y-2 text-sm leading-7 text-gray-600">
          <template v-for="(paragraph, index) in (current.content || '').split('\n')" :key="index">
            <p v-if="paragraph.trim()">{{ paragraph }}</p>
          </template>
        </div>

        <div v-if="current.usage_note" class="rounded-lg border border-solid border-gray-200 bg-white p-4">
          <div class="text-sm font-semibold text-gray-800">怎么理解这条信息</div>
          <p class="mt-1 text-sm leading-7 text-gray-600">{{ current.usage_note }}</p>
        </div>

        <div class="rounded-lg border border-solid border-gray-200 bg-white p-4 text-xs text-gray-500">
          <div class="flex justify-between gap-3 py-1">
            <span class="text-gray-400">来源</span>
            <span class="text-right text-gray-700">{{ current.source_name }}</span>
          </div>
          <div class="flex justify-between gap-3 py-1">
            <span class="text-gray-400">来源类型</span>
            <span class="text-right text-gray-700">{{ current.source_type_label }}</span>
          </div>
          <div class="flex justify-between gap-3 py-1">
            <span class="text-gray-400">更新时间</span>
            <span class="text-right text-gray-700">{{ formatDate(current.updated_at, true) }}</span>
          </div>
          <a
            v-if="current.source_url"
            :href="current.source_url"
            target="_blank"
            rel="noopener"
            class="mt-2 inline-flex text-gray-700 hover:underline"
          >
            打开官方查询入口 →
          </a>
        </div>

        <div v-if="related.length">
          <div class="mb-2 text-sm font-semibold text-gray-700">相关条目</div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="item in related"
              :key="item.id"
              type="button"
              class="rounded-full border border-solid border-gray-200 bg-white px-3 py-1 text-xs text-gray-600 hover:border-gray-300 hover:text-gray-800"
              @click="openEntry(item.id, $event)"
            >
              {{ item.title }}
            </button>
          </div>
        </div>

        <p class="text-xs leading-6 text-gray-400">
          本条目为概述性内容，未收录标准原文；涉及法规判定请以官方发布文本为准。
        </p>
      </div>
      <div v-else-if="detailLoading" class="mx-4 my-4 h-48 animate-pulse rounded-xl bg-gray-100" />
    </el-drawer>

    <el-drawer
      v-model="dishDrawerVisible"
      :with-header="false"
      :size="'min(560px, 94vw)'"
      direction="rtl"
      class="dish-detail-drawer"
      modal-class="dish-drawer-overlay"
      @closed="closeDishDrawer"
    >
      <div v-if="dishCurrent" class="dish-sheet">
        <header class="dish-sheet-head">
          <div class="dish-sheet-head-copy">
            <span class="dish-sheet-kicker">AI 营养拆解</span>
            <h2 class="dish-sheet-title">{{ dishCurrent.dish_name }}</h2>
            <div class="dish-sheet-tags">
              <span class="dish-sheet-tag dish-sheet-tag--green">{{ dishCurrent.category }}</span>
              <span class="dish-sheet-tag dish-sheet-tag--blue">数据已收录</span>
            </div>
          </div>
          <button type="button" class="dish-sheet-close" aria-label="关闭" @click="closeDishDrawer">
            ×
          </button>
        </header>

        <div class="dish-sheet-scroll">
          <div class="dish-calorie-card">
            <div class="dish-calorie-main">
              <strong>{{ formatCalories(dishCurrent.calories_per_100g) }}</strong>
              <span>kcal / 100g</span>
            </div>
            <p>常见一份 {{ dishCurrent.typical_portion_g }}g ≈ {{ portionCalories(dishCurrent) }} kcal</p>
            <div class="dish-calorie-glow" aria-hidden="true" />
          </div>

          <p v-if="dishNutritionLoading" class="dish-nutrition-status">
            AI 正在补全营养数据…
          </p>
          <p v-else-if="dishNutritionError" class="dish-nutrition-status is-error">
            {{ dishNutritionError }}
          </p>

          <div class="dish-macro-section">
            <div class="dish-section-head">
              <strong>三大营养素</strong>
              <span>每 100g</span>
            </div>
            <div class="dish-macro-list">
              <div
                v-for="macro in dishMacros(dishCurrent)"
                :key="macro.key"
                class="dish-macro"
              >
                <div class="dish-macro-row">
                  <span class="dish-macro-name">{{ macro.label }}</span>
                  <strong class="dish-macro-grams">{{ macro.grams }}g</strong>
                  <span class="dish-macro-percent">{{ macro.percent }}%</span>
                </div>
                <div class="dish-macro-track">
                  <span
                    class="dish-macro-fill"
                    :class="`dish-macro-fill--${macro.key}`"
                    :style="{ width: `${Math.min(100, Math.max(3, macro.percent))}%` }"
                  />
                </div>
              </div>
            </div>
          </div>

          <div class="dish-tip-card">
            <div class="dish-tip-title">💡 营养建议</div>
            <p>{{ dishCurrent.health_tip }}</p>
          </div>

          <div class="dish-source-card">
            <span>数据来源</span>
            <strong>{{ dishCurrent.source }}</strong>
          </div>
        </div>

        <footer class="dish-sheet-footer">
          <button type="button" class="dish-sheet-add" @click="addDishToToday">
            加入今日饮食记录
          </button>
        </footer>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>

.knowledge-page {
  padding-bottom: 96px;
}

/* 顶部计数 */
.kb-count {
  color: #6b7280;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

/* 顶部筛选胶囊按钮组 */
.kb-tabs {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  width: 100%;
  max-width: 100%;
  padding: 4px;
  overflow-x: auto;
  overflow-y: hidden;
  white-space: nowrap;
  scrollbar-width: none;
  -ms-overflow-style: none;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior-x: contain;
  touch-action: pan-x;
  border-radius: 999px;
  background: #ebf0f4;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.kb-tabs::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}

.kb-tabs::-webkit-scrollbar-track,
.kb-tabs::-webkit-scrollbar-thumb {
  display: none;
}

.kb-tab {
  flex: 0 0 auto;
  border: 0;
  border-radius: 999px;
  background: #ffffff;
  color: #6b7280;
  padding: 8px 18px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.kb-tab:hover {
  background: #f8fafb;
  color: #0f5f4c;
}

.kb-tab.is-active {
  background: #0f5f4c;
  color: #ffffff;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(15, 95, 76, 0.18);
}

/* 搜索框：胶囊形、无边框 */
.kb-search {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
}

.kb-search-input :deep(.el-input__wrapper) {
  min-height: 48px;
  border: 0;
  border-radius: 999px;
  background: #ebf0f4;
  box-shadow: none !important;
  padding: 8px 18px;
}

.kb-search-input :deep(.el-input__wrapper:hover),
.kb-search-input :deep(.el-input__wrapper.is-focus) {
  background: #ebf0f4;
  box-shadow: none !important;
}

.kb-search-input :deep(.el-input__inner::placeholder) {
  color: #7c8b96;
}

.kb-search-input :deep(.el-input__inner) {
  background: transparent;
}

.kb-search-hint {
  margin-top: 8px;
  padding-left: 4px;
  color: #8a98a3;
  font-size: 11px;
}

/* 分类区块 */
.kb-section {
  margin-bottom: 28px;
}

.kb-section:last-child {
  margin-bottom: 0;
}

/* 卡片 */
.kb-card,
.kb-card.kb-card--food,
.kb-card.kb-card--knowledge {
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  min-height: 0;
  padding: 20px;
  border: 0;
  border-radius: 16px;
  /* 强制纯白底，清除任何继承的透明/渐变/毛玻璃 */
  background: #ffffff !important;
  opacity: 1 !important;
  filter: none !important;
  backdrop-filter: none !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.04);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.kb-card:hover {
  background: #ffffff !important;
  transform: translateY(-4px) !important;
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.06);
}

/* 内容区吃掉剩余高度，底部操作栏固定在卡片底部 */
.kb-card > .flex-grow {
  flex: 1 1 auto !important;
  min-height: 0;
}

.kb-card-footer {
  margin-top: auto !important;
  padding-top: 16px !important;
  border-top: 1px solid #eef1ef;
  background: #ffffff;
}

/* 知识卡片文字强制为清晰的深灰，禁止半透明 */
.kb-card--knowledge .kb-card-title,
.kb-card--knowledge .kb-desc,
.kb-card--knowledge .kb-category-label,
.kb-card--knowledge .kb-card-note,
.kb-card--knowledge .kb-calorie-unit {
  color: #1f2937 !important;
  opacity: 1 !important;
}

.kb-card--knowledge .kb-card-note {
  color: #6b7280 !important;
}

/* 左上角分类文字 */
.kb-category-label {
  color: #6b7280;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.6;
}

/* 右上角状态小标签 */
.kb-card-badge {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.6;
}

.kb-card-badge--food {
  background: #fff7ed;
  border: 1px solid #f3e1cc;
  color: #a15c1a;
}

/* 新增分类统一使用浅绿色「已收录 / 已发布」标签 */
.kb-card-badge--additive,
.kb-card-badge--ingredient,
.kb-card-badge--dish,
.kb-card-badge--nutrition,
.kb-card-badge--safety,
.kb-card-badge--label_rule,
.kb-card-badge--knowledge {
  background: #edf8f2;
  border: 1px solid #d5ecdf;
  color: #2f7659;
}

/* 卡片标题与热量 */
.kb-card-title {
  color: #1f2937;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.4;
  margin-bottom: 8px;
}

.kb-calorie-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-top: 12px;
  margin-bottom: 12px;
}

.kb-calories {
  color: #a94442;
  font-size: 32px;
  font-weight: 800;
  line-height: 1.1;
}



.kb-calorie-unit {
  color: #999999;
  font-size: 12px;
}

.kb-card-desc {
  min-height: 44px;
  margin-bottom: 16px;
}

.kb-desc {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  margin: 0;
  overflow: hidden;
  color: #6b7280;
  font-size: 14px;
  line-height: 1.75;
  max-height: 3.5em;
}

.kb-macro-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

/* 营养成分胶囊 */
.kb-macro {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #eef3f7;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 11px;
  line-height: 1.5;
  white-space: nowrap;
  background: #f7fafc;
  color: #6b7f8f;
}

.kb-macro--carbs {
  background: #f7fafc;
  border-color: #eef3f7;
  color: #6b7f8f;
}

.kb-macro--protein {
  background: #f7fbf8;
  border-color: #edf4ef;
  color: #6e8777;
}

.kb-macro--fat {
  background: #fbf9f6;
  border-color: #f2ece4;
  color: #8a7a68;
}

/* 卡片底部 */
.kb-card-footer {
  margin-top: auto;
}

.kb-card-note {
  color: #9ca3af;
  font-size: 12px;
  line-height: 1.5;
}

.kb-card-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 14px;
  margin-top: auto;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.kb-card-action--primary {
  background: #0f5f4c;
  border: 1px solid #0f5f4c;
  color: #ffffff;
}

.kb-card-action--primary:hover {
  background: #0b4a3b;
  border-color: #0b4a3b;
}

.kb-card-action--ghost {
  background: #ffffff;
  border: 1px solid #cfe3da;
  color: #3f7d68;
}

.kb-card-action--ghost:hover {
  background: #f2f8f5;
}

.knowledge-page :deep(.el-drawer__body) {
  padding-top: 4px;
}


.kb-load-more {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 44px;
  padding: 22px 0 6px;
  color: #8a98a3;
  font-size: 12px;
  letter-spacing: 0.02em;
}

@media (max-width: 560px) {
  .knowledge-page {
    padding-bottom: 84px;
  }

  .kb-tabs {
    gap: 6px;
  }

  .kb-tab {
    flex: 0 0 auto;
    padding: 8px 14px;
    font-size: 13px;
    white-space: nowrap;
  }
}


/* ===== AI 营养拆解抽屉 ===== */
:global(.dish-drawer-overlay) {
  background: rgba(8, 20, 16, 0.42) !important;
  backdrop-filter: blur(2px);
}

:global(.dish-detail-drawer.el-drawer) {
  overflow: hidden;
  border-radius: 24px 0 0 24px;
  background: #f8fbf9;
  box-shadow: -28px 0 70px rgba(7, 28, 20, 0.28), -2px 0 0 rgba(255, 255, 255, 0.5) inset;
}

:global(.dish-detail-drawer .el-drawer__body) {
  display: flex;
  min-height: 0;
  padding: 0;
}

.dish-sheet {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: linear-gradient(180deg, #f4faf6 0%, #fbfcfb 34%, #ffffff 100%);
}

.dish-sheet-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 26px 26px 20px;
  border-bottom: 1px solid rgba(24, 74, 55, 0.08);
  background:
    radial-gradient(circle at 88% 0%, rgba(177, 226, 204, 0.52), transparent 42%),
    linear-gradient(135deg, #eff9f3 0%, #f8fcfa 72%);
}

.dish-sheet-head-copy {
  min-width: 0;
}

.dish-sheet-kicker {
  display: block;
  margin-bottom: 7px;
  color: #6f9686;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.dish-sheet-title {
  margin: 0;
  color: #102f23;
  font-size: clamp(25px, 3vw, 32px);
  font-weight: 850;
  line-height: 1.2;
  letter-spacing: -0.04em;
}

.dish-sheet-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 13px;
}

.dish-sheet-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 650;
  line-height: 1.3;
}

.dish-sheet-tag--green {
  border-color: #cfe9dd;
  background: #e9f8f0;
  color: #2c7659;
}

.dish-sheet-tag--blue {
  border-color: #d9e8f3;
  background: #eef7fc;
  color: #46758c;
}

.dish-sheet-close {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  padding: 0 0 2px;
  border: 1px solid rgba(22, 70, 52, 0.1);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  color: #6a8a7c;
  font-family: inherit;
  font-size: 23px;
  font-weight: 300;
  line-height: 1;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease, transform 0.16s ease;
}

.dish-sheet-close:hover {
  background: #ffffff;
  color: #1e6049;
  transform: rotate(3deg);
}

.dish-sheet-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 26px 24px;
  scrollbar-width: thin;
  scrollbar-color: #c7d7cf transparent;
}

.dish-sheet-scroll::-webkit-scrollbar {
  width: 7px;
}

.dish-sheet-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: #c7d7cf;
}

.dish-nutrition-status {
  margin: -2px 0 14px;
  padding: 8px 12px;
  border-radius: 10px;
  background: #eef8f2;
  color: #277154;
  font-size: 12px;
  line-height: 1.6;
}

.dish-nutrition-status.is-error {
  background: #fff2f0;
  color: #b23b32;
}

.dish-calorie-card {
  position: relative;
  overflow: hidden;
  padding: 22px 24px;
  border: 1px solid #d6ebdf;
  border-radius: 20px;
  background:
    linear-gradient(135deg, #e8f7ee 0%, #f3fbf6 55%, #ecf7f3 100%);
  box-shadow: 0 12px 30px rgba(35, 103, 73, 0.08);
}

.dish-calorie-main {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.dish-calorie-main strong {
  color: #143f2e;
  font-size: 42px;
  font-weight: 850;
  line-height: 1;
  letter-spacing: -0.055em;
}

.dish-calorie-main span {
  color: #5f8876;
  font-size: 11.5px;
  font-weight: 650;
}

.dish-calorie-card p {
  position: relative;
  z-index: 1;
  margin: 10px 0 0;
  color: #658576;
  font-size: 12px;
  line-height: 1.6;
}

.dish-calorie-glow {
  position: absolute;
  right: -34px;
  bottom: -48px;
  width: 170px;
  height: 170px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(112, 199, 157, 0.28), transparent 68%);
  pointer-events: none;
}

.dish-macro-section {
  margin-top: 24px;
}

.dish-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.dish-section-head strong {
  color: #173d2e;
  font-size: 13px;
  font-weight: 800;
}

.dish-section-head span {
  color: #91a69c;
  font-size: 10.5px;
}

.dish-macro-list {
  display: grid;
  gap: 13px;
  padding: 16px;
  border: 1px solid #e5efe9;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 6px 18px rgba(24, 64, 48, 0.035);
}

.dish-macro-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
}

.dish-macro-name {
  color: #44685a;
  font-size: 12px;
  font-weight: 650;
}

.dish-macro-grams {
  color: #1d4837;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.dish-macro-percent {
  width: 32px;
  color: #9aafa5;
  font-size: 10.5px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.dish-macro-track {
  height: 6px;
  margin-top: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf3ef;
}

.dish-macro-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  transition: width 0.35s ease;
}

.dish-macro-fill--carbs {
  background: linear-gradient(90deg, #e7b85d, #d99a2b);
}

.dish-macro-fill--protein {
  background: linear-gradient(90deg, #63c59b, #2f9c72);
}

.dish-macro-fill--fat {
  background: linear-gradient(90deg, #e49a70, #d57848);
}

.dish-tip-card {
  margin-top: 18px;
  padding: 16px 17px;
  border: 1px solid #e5efe9;
  border-radius: 16px;
  background: #ffffff;
}

.dish-tip-title {
  color: #244d3c;
  font-size: 12px;
  font-weight: 800;
}

.dish-tip-card p {
  margin: 7px 0 0;
  color: #607d70;
  font-size: 12.5px;
  line-height: 1.8;
}

.dish-source-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-top: 14px;
  padding: 11px 3px;
  border-top: 1px dashed #e3ece7;
  color: #96a89f;
  font-size: 10.5px;
  line-height: 1.6;
}

.dish-source-card strong {
  max-width: 70%;
  color: #678174;
  font-weight: 500;
  text-align: right;
}

.dish-sheet-footer {
  flex: 0 0 auto;
  padding: 14px 26px 22px;
  border-top: 1px solid rgba(24, 74, 55, 0.08);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 -12px 28px rgba(24, 64, 48, 0.06);
  backdrop-filter: blur(8px);
}

.dish-sheet-add {
  width: 100%;
  min-height: 48px;
  padding: 0 20px;
  border: 0;
  border-radius: 14px;
  background: #0f6b52;
  color: #ffffff;
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 750;
  letter-spacing: 0.01em;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(15, 107, 82, 0.28);
  transition: background 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;
}

.dish-sheet-add:hover {
  background: #0b5a45;
  box-shadow: 0 13px 28px rgba(15, 107, 82, 0.34);
  transform: translateY(-1px);
}

.dish-sheet-add:active {
  transform: translateY(0);
}

</style>
