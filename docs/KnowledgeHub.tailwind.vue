<script setup lang="ts">
/**
 * 食安百科：添加剂 + 菜品热量综合页（Vue 3 + TailwindCSS 完整示例）
 *
 * 使用前确认：
 * 1. 项目已安装 tailwindcss / postcss / autoprefixer；
 * 2. Vue 3 + Element Plus 已安装；
 * 3. 使用项目现有的 @/api、@/api/types、@/composables/useDietLog。
 *
 * 当前主仓库未安装 Tailwind，因此实际页面使用等价的 scoped CSS 实现；
 * 本文件是可直接迁移到 Tailwind 项目的完整组件版本。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dishApi, knowledgeApi } from '@/api'
import type { DishInfo, KnowledgeEntry } from '@/api/types'
import { useDietLog } from '@/composables/useDietLog'

type TabKey = 'all' | 'additive' | 'food'

interface AdditiveItem {
  type: 'additive'
  key: string
  title: string
  description: string
  entry: KnowledgeEntry
}

interface FoodItem {
  type: 'food'
  key: string
  title: string
  dish: DishInfo
}

type HubItem = AdditiveItem | FoodItem

const route = useRoute()
const router = useRouter()
const { addDish } = useDietLog()

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'additive', label: '添加剂避雷' },
  { key: 'food', label: '热量图鉴（菜品）' },
]

const activeTab = ref<TabKey>('all')
const query = ref('')
const rawItems = ref<HubItem[]>([])
const loading = ref(true)
const errorMessage = ref('')

const additiveDrawer = ref(false)
const currentEntry = ref<KnowledgeEntry | null>(null)
const related = ref<KnowledgeEntry[]>([])
const entryLoading = ref(false)

const dishDrawer = ref(false)
const currentDish = ref<DishInfo | null>(null)

const filteredItems = computed(() => {
  let items =
    activeTab.value === 'all'
      ? rawItems.value
      : rawItems.value.filter((item) => item.type === activeTab.value)

  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return items

  return items.filter((item) => {
    const haystack =
      item.type === 'additive'
        ? [item.title, item.description, ...item.entry.aliases, ...item.entry.keywords]
        : [item.title, ...item.dish.aliases, item.dish.category, item.dish.health_tip]
    return haystack.join(' ').toLowerCase().includes(keyword)
  })
})

const isEmpty = computed(() => !loading.value && filteredItems.value.length === 0)

function formatCalories(value: number) {
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

function portionCalories(dish: DishInfo) {
  return Math.round((dish.calories_per_100g * dish.typical_portion_g) / 100)
}

async function loadData() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [firstAdditives, dishes] = await Promise.all([
      knowledgeApi.list({ category: 'additive', page: 1, per_page: 50 }),
      dishApi.list({ page: 1, per_page: 60 }),
    ])

    let entries = [...firstAdditives.items]
    if (firstAdditives.total > entries.length) {
      const rest = await knowledgeApi.list({
        category: 'additive',
        page: 2,
        per_page: 50,
      })
      entries = entries.concat(rest.items)
    }

    const additives: AdditiveItem[] = entries.map((entry) => ({
      type: 'additive',
      key: `additive-${entry.id}`,
      title: entry.title,
      description: entry.summary,
      entry,
    }))

    const foods: FoodItem[] = dishes.items.map((dish) => ({
      type: 'food',
      key: `food-${dish.slug}`,
      title: dish.dish_name,
      dish,
    }))

    // 「全部」中交错排列，避免菜品全部排在添加剂后面。
    const merged: HubItem[] = []
    const length = Math.max(additives.length, foods.length)
    for (let index = 0; index < length; index += 1) {
      if (additives[index]) merged.push(additives[index])
      if (foods[index]) merged.push(foods[index])
    }
    rawItems.value = merged
  } catch (error) {
    errorMessage.value = (error as Error).message || '食安百科加载失败'
  } finally {
    loading.value = false
  }
}

function categoryQuery(): Record<string, string> {
  return activeTab.value === 'all' ? {} : { category: activeTab.value }
}

function selectTab(key: TabKey) {
  activeTab.value = key
  router.replace({ query: categoryQuery() })
}

async function openEntry(id: number) {
  additiveDrawer.value = true
  entryLoading.value = true
  currentEntry.value =
    rawItems.value.find(
      (item): item is AdditiveItem =>
        item.type === 'additive' && item.entry.id === id,
    )?.entry || null

  router.replace({ query: { ...categoryQuery(), entry: String(id) } })

  try {
    const data = await knowledgeApi.detail(id)
    currentEntry.value = data.entry
    related.value = data.related
  } finally {
    entryLoading.value = false
  }
}

function openDish(dish: DishInfo) {
  currentDish.value = dish
  dishDrawer.value = true
  router.replace({ query: { ...categoryQuery(), dish: dish.slug } })
}

function closeEntryDrawer() {
  additiveDrawer.value = false
  router.replace({ query: categoryQuery() })
}

function closeDishDrawer() {
  dishDrawer.value = false
  currentDish.value = null
  router.replace({ query: categoryQuery() })
}

function askNutritionist(entry: KnowledgeEntry) {
  router.push({
    name: 'assistant',
    query: {
      prompt: `请帮我判断一下「${entry.title}」我能不能吃？`,
      context: JSON.stringify({
        title: entry.title,
        name: entry.title,
        category: entry.category_label,
        summary: entry.summary,
        source: entry.source_name,
        context_type: 'knowledge',
      }),
    },
  })
}

function addDishToToday() {
  if (!currentDish.value) return
  const entry = addDish(currentDish.value)
  ElMessage.success(
    `已加入今日饮食：${currentDish.value.dish_name} · ${entry.calories} 大卡`,
  )
}

onMounted(async () => {
  await loadData()

  const category = String(route.query.category || 'all')
  if (category === 'additive') activeTab.value = 'additive'
  else if (category === 'food' || category === 'dish') activeTab.value = 'food'

  const slug = String(route.query.dish || '')
  if (slug) {
    const food = rawItems.value.find(
      (item): item is FoodItem =>
        item.type === 'food' && item.dish.slug === slug,
    )
    if (food) openDish(food.dish)
  }

  const entryId = Number(route.query.entry)
  if (entryId) await openEntry(entryId)
})
</script>

<template>
  <div class="min-h-screen bg-[#f6faf7] px-4 pb-24 pt-6 md:px-8">
    <div class="mx-auto max-w-[1400px]">
      <!-- 页头 -->
      <header class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 class="text-2xl font-extrabold tracking-tight text-slate-900 md:text-3xl">
            食安百科
          </h1>
          <p class="mt-2 text-sm leading-6 text-slate-500">
            查成分、算热量、识谣言。AI为您解读每一口食物背后的健康真相。
          </p>
        </div>
        <span class="rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
          共 {{ filteredItems.length }} 条
        </span>
      </header>

      <!-- Tab -->
      <div class="mt-6 flex w-fit max-w-full items-center gap-1 overflow-x-auto rounded-2xl bg-emerald-50 p-1">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="shrink-0 rounded-xl px-4 py-2 text-sm font-medium transition"
          :class="activeTab === tab.key
            ? 'bg-white text-emerald-700 shadow-sm ring-1 ring-emerald-100'
            : 'text-slate-500 hover:text-emerald-700'"
          @click="selectTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- 搜索 -->
      <div class="mt-4 rounded-2xl border border-emerald-100/70 bg-white p-3 shadow-sm">
        <el-input v-model="query" size="large" clearable
          placeholder="搜索食物、菜品或添加剂（如：红烧肉、阿斯巴甜）">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <p class="mt-2 pl-1 text-[11px] text-slate-400">
          输入即筛选 · 支持菜名、别名与添加剂名称
        </p>
      </div>

      <!-- 错误 -->
      <div v-if="errorMessage" class="mt-4 rounded-2xl border border-red-100 bg-red-50 p-4 text-sm text-red-600">
        {{ errorMessage }}
        <button type="button" class="ml-2 font-semibold underline" @click="loadData">重试</button>
      </div>

      <!-- 骨架 -->
      <div v-if="loading" class="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div v-for="i in 6" :key="i" class="h-56 animate-pulse rounded-2xl bg-emerald-50/70" />
      </div>

      <!-- 空状态 -->
      <div v-else-if="isEmpty" class="mt-5 rounded-2xl border border-emerald-100 bg-white p-12 text-center">
        <p class="text-lg font-semibold text-slate-700">没有找到相关食物或添加剂</p>
        <p class="mt-1 text-sm text-slate-400">试试更短的关键词，或切换到「全部」分类。</p>
      </div>

      <!-- 卡片列表 -->
      <div v-else class="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="item in filteredItems"
          :key="item.key"
          class="cursor-pointer transition duration-200 hover:-translate-y-0.5 hover:shadow-lg"
          :class="item.type === 'food'
            ? 'rounded-[22px] border border-orange-100 bg-gradient-to-br from-orange-50/80 via-white to-white p-5 shadow-sm'
            : 'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:border-emerald-300'"
          @click="item.type === 'additive' ? openEntry(item.entry.id) : openDish(item.dish)"
        >
          <!-- 添加剂卡片 -->
          <template v-if="item.type === 'additive'">
            <div class="flex items-center justify-between gap-2">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">食品添加剂</span>
              <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                权威已收录
              </span>
            </div>
            <h3 class="mt-3 text-[17px] font-bold leading-6 text-slate-800">{{ item.title }}</h3>
            <p class="mt-2 line-clamp-3 min-h-[66px] text-[13px] leading-6 text-slate-500">
              {{ item.description }}
            </p>
            <div class="mt-4 flex items-center justify-between gap-2 border-t border-dashed border-slate-200 pt-3">
              <span class="text-[11px] text-slate-400">依据 GB 2760</span>
              <el-button size="small" type="primary" plain @click.stop="askNutritionist(item.entry)">
                问营养师
              </el-button>
            </div>
          </template>

          <!-- 菜品卡片 -->
          <template v-else>
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <span class="block truncate text-[10px] font-bold tracking-wide text-amber-700/70">
                  {{ item.dish.category }}
                </span>
                <h3 class="mt-1 text-xl font-extrabold leading-7 tracking-tight text-stone-800">
                  {{ item.title }}
                </h3>
              </div>
              <span class="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                热量图鉴
              </span>
            </div>

            <div class="mt-3 flex items-baseline gap-2">
              <strong class="text-5xl font-black tracking-[-0.08em] text-red-500">
                {{ formatCalories(item.dish.calories_per_100g) }}
              </strong>
              <span class="text-[11px] font-semibold text-stone-400">kcal / 100g</span>
            </div>

            <div class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="macro in dishMacros(item.dish)"
                :key="macro.key"
                class="rounded-full px-2 py-1 text-[10.5px] font-semibold"
                :class="{
                  'bg-amber-50 text-amber-800': macro.key === 'carbs',
                  'bg-red-50 text-red-700': macro.key === 'protein',
                  'bg-emerald-50 text-emerald-700': macro.key === 'fat',
                }"
                :title="`${macro.label} ${macro.grams}g / 100g`"
              >
                {{ macro.label }} {{ macro.percent }}%
              </span>
            </div>

            <div class="mt-4 flex items-center justify-between gap-2 border-t border-dashed border-orange-100 pt-3">
              <span class="text-[10.5px] leading-4 text-stone-400">
                常见一份 {{ item.dish.typical_portion_g }}g · {{ portionCalories(item.dish) }} kcal
              </span>
              <button
                type="button"
                class="shrink-0 rounded-lg bg-stone-800 px-3 py-2 text-[11px] font-semibold text-white transition hover:bg-red-500"
                @click.stop="openDish(item.dish)"
              >
                查看营养建议
              </button>
            </div>
          </template>
        </article>
      </div>

      <p class="mt-6 rounded-2xl border border-emerald-100 bg-emerald-50/50 p-4 text-xs leading-6 text-slate-500">
        添加剂内容依据 GB 2760 与权威公开资料整理；菜品热量参考《中国食物成分表》与常见做法估算，
        不同餐厅会有差异。本页不构成合规或安全性判定依据。
      </p>
    </div>

    <!-- 添加剂详情 -->
    <el-drawer v-model="additiveDrawer" :title="currentEntry?.title || '添加剂详情'"
      size="min(560px, 92vw)" direction="rtl" @closed="closeEntryDrawer">
      <div v-if="currentEntry" class="space-y-4 px-5 pb-6">
        <div class="flex flex-wrap gap-2">
          <span class="rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700">添加剂避雷</span>
          <span class="rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">权威已收录</span>
          <span class="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500">版本 {{ currentEntry.version }}</span>
        </div>
        <p class="rounded-xl bg-emerald-50 p-3 text-sm leading-7 text-emerald-800">{{ currentEntry.summary }}</p>
        <div class="space-y-2 text-sm leading-7 text-slate-600">
          <p v-for="(paragraph, index) in (currentEntry.content || '').split('\n')" :key="index">
            {{ paragraph }}
          </p>
        </div>
        <div v-if="currentEntry.usage_note" class="rounded-xl border border-amber-100 bg-amber-50 p-3">
          <p class="text-xs font-bold text-amber-800">怎么理解这条信息</p>
          <p class="mt-1 text-sm leading-7 text-amber-900/80">{{ currentEntry.usage_note }}</p>
        </div>
        <div class="rounded-xl border border-slate-200 p-3 text-xs leading-6 text-slate-500">
          <p>来源：{{ currentEntry.source_name }}</p>
          <p>类型：{{ currentEntry.source_type_label }}</p>
        </div>
      </div>
      <div v-else-if="entryLoading" class="h-40 animate-pulse rounded-xl bg-slate-100" />
    </el-drawer>

    <!-- 菜品营养建议 -->
    <el-drawer v-model="dishDrawer" :title="currentDish?.dish_name || '营养建议'"
      size="min(560px, 92vw)" direction="rtl" @closed="closeDishDrawer">
      <div v-if="currentDish" class="space-y-4 px-5 pb-6">
        <div class="flex gap-2">
          <span class="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-700">{{ currentDish.category }}</span>
          <span class="rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">热量图鉴</span>
        </div>
        <div class="rounded-2xl bg-gradient-to-br from-orange-50 to-white p-4">
          <strong class="text-5xl font-black tracking-tighter text-red-500">
            {{ formatCalories(currentDish.calories_per_100g) }}
          </strong>
          <span class="ml-2 text-xs font-semibold text-stone-400">kcal / 100g</span>
          <p class="mt-2 text-xs text-stone-500">
            常见一份 {{ currentDish.typical_portion_g }}g ≈ {{ portionCalories(currentDish) }} kcal
          </p>
        </div>
        <div class="grid grid-cols-3 gap-2">
          <div v-for="macro in dishMacros(currentDish)" :key="macro.key" class="rounded-xl border border-slate-200 p-3">
            <p class="text-[11px] text-slate-400">{{ macro.label }} {{ macro.percent }}%</p>
            <p class="mt-1 text-sm font-bold text-slate-700">{{ macro.grams }}g</p>
          </div>
        </div>
        <div class="rounded-xl border border-amber-100 bg-amber-50 p-3">
          <p class="text-xs font-bold text-amber-800">💡 营养建议</p>
          <p class="mt-1 text-sm leading-7 text-amber-900/80">{{ currentDish.health_tip }}</p>
        </div>
        <p class="text-xs leading-6 text-slate-400">{{ currentDish.source }}</p>
        <el-button type="primary" class="w-full" @click="addDishToToday">加入今日饮食记录</el-button>
      </div>
    </el-drawer>
  </div>
</template>