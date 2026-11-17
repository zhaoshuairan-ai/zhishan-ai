<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dishApi } from '@/api'
import { ApiError } from '@/api/client'
import type { DishInfo } from '@/api/types'
import { useDietLog } from '@/composables/useDietLog'

const props = defineProps<{
  query: string
  openSlug?: string
}>()

const emit = defineEmits<{
  (event: 'total', total: number): void
  (event: 'open', slug: string): void
  (event: 'close'): void
}>()

const PAGE_SIZE = 12
const items = ref<DishInfo[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(true)
const errorMessage = ref('')

const drawerVisible = ref(false)
const detailLoading = ref(false)
const current = ref<DishInfo | null>(null)
const related = ref<DishInfo[]>([])

const { entries, totals, addDish, removeEntry, clearToday } = useDietLog()

const macroList = [
  { key: 'carbs_per_100g', label: '碳水', color: '#d99a2b' },
  { key: 'protein_per_100g', label: '蛋白质', color: '#d45f5f' },
  { key: 'fat_per_100g', label: '脂肪', color: '#3f8d86' },
] as const

const detailPortionCalories = computed(() => {
  if (!current.value) return 0
  return Math.round(
    (current.value.calories_per_100g * current.value.typical_portion_g) / 100,
  )
})

const detailMacros = computed(() => {
  if (!current.value) return []
  return macroList.map((macro) => ({
    label: macro.label,
    value: current.value?.[macro.key] || 0,
    color: macro.color,
  }))
})

function macroRows(dish: DishInfo) {
  const max = Math.max(
    dish.carbs_per_100g,
    dish.protein_per_100g,
    dish.fat_per_100g,
    1,
  )
  return macroList.map((macro) => ({
    label: macro.label,
    value: dish[macro.key],
    color: macro.color,
    width: `${Math.max(10, Math.round((dish[macro.key] / max) * 100))}%`,
  }))
}

function portionCalories(dish: DishInfo) {
  return Math.round((dish.calories_per_100g * dish.typical_portion_g) / 100)
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await dishApi.list({
      page: page.value,
      per_page: PAGE_SIZE,
      query: props.query.trim(),
    })
    items.value = data.items
    total.value = data.total
    emit('total', data.total)
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '菜品营养库加载失败'
  } finally {
    loading.value = false
  }
}

async function openDetail(slug: string) {
  if (!slug) return
  drawerVisible.value = true
  detailLoading.value = true
  current.value = items.value.find((dish) => dish.slug === slug) || null
  try {
    const data = await dishApi.detail(slug)
    current.value = data.dish
    related.value = data.related
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '菜品详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  drawerVisible.value = false
  current.value = null
  related.value = []
  emit('close')
}

function add(dish: DishInfo) {
  const entry = addDish(dish)
  ElMessage.success(
    `已加入今日饮食：${dish.dish_name} · ${entry.calories} 大卡`,
  )
}

async function clearAll() {
  if (!entries.value.length) return
  try {
    await ElMessageBox.confirm('确定清空今天已记录的菜品吗？', '清空今日饮食', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  clearToday()
}

let searchTimer: number | undefined

watch(
  () => props.query,
  () => {
    window.clearTimeout(searchTimer)
    searchTimer = window.setTimeout(() => {
      page.value = 1
      load()
    }, 320)
  },
)

onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
})

watch(
  () => props.openSlug,
  (slug) => {
    if (slug) openDetail(slug)
  },
)

onMounted(async () => {
  await load()
  if (props.openSlug) openDetail(props.openSlug)
})
</script>

<template>
  <section class="dish-library">
    <div class="dish-toolbar card">
      <div>
        <div class="dish-toolbar-title">
          常见菜品热量字典
          <span>每 100g 营养数据</span>
        </div>
        <p>食堂、外卖常见菜品，拍完照也能来这里查一查。</p>
      </div>
      <div v-if="entries.length" class="diet-summary">
        <span>今日已记录 <b>{{ entries.length }}</b> 道</span>
        <strong>{{ Math.round(totals.calories) }} 大卡</strong>
        <button type="button" @click="clearAll">清空</button>
      </div>
    </div>

    <div v-if="errorMessage" class="notice notice-danger mt">
      <el-icon><WarningFilled /></el-icon>
      <div>
        {{ errorMessage }}
        <el-button text type="primary" @click="load">重试</el-button>
      </div>
    </div>

    <div v-if="loading" class="dish-grid">
      <div v-for="index in 6" :key="index" class="loading-block" style="height: 260px" />
    </div>

    <div v-else-if="!items.length" class="card">
      <div class="empty">
        <el-icon class="empty-icon"><Search /></el-icon>
        <h4>没有找到相关菜品</h4>
        <p class="empty-desc">试试更短的菜名，比如「西红柿」「鸡丁」「面」。</p>
      </div>
    </div>

    <div v-else class="dish-grid">
      <article
        v-for="dish in items"
        :key="dish.slug"
        class="dish-card"
        @click="openDetail(dish.slug)"
      >
        <div class="dish-card-top">
          <span class="dish-category">{{ dish.category }}</span>
          <span class="dish-alias" :title="dish.aliases.join('、')">
            {{ dish.aliases.slice(0, 2).join(' / ') }}
          </span>
        </div>
        <h3 class="dish-name">{{ dish.dish_name }}</h3>
        <div class="dish-calorie">
          <strong>{{ dish.calories_per_100g }}</strong>
          <span>大卡 / 100g</span>
        </div>
        <div class="macro-list">
          <div v-for="macro in macroRows(dish)" :key="macro.label" class="macro-row">
            <div class="macro-head">
              <span>{{ macro.label }}</span>
              <b>{{ macro.value }}g</b>
            </div>
            <div class="macro-track">
              <span :style="{ width: macro.width, background: macro.color }" />
            </div>
          </div>
        </div>
        <div class="dish-card-foot">
          <span>常见一份 {{ dish.typical_portion_g }}g · {{ portionCalories(dish) }} 大卡</span>
          <el-button
            class="dish-add"
            size="small"
            type="primary"
            plain
            @click.stop="add(dish)"
          >
            加入今日饮食记录
          </el-button>
        </div>
      </article>
    </div>

    <div v-if="!loading && total > PAGE_SIZE" class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="PAGE_SIZE"
        :total="total"
        layout="prev, pager, next"
        background
        small
        @current-change="load"
      />
    </div>

    <div v-if="entries.length" class="diet-today">
      <div class="diet-today-head">
        <strong>今日饮食记录</strong>
        <span>{{ Math.round(totals.calories) }} 大卡 · 蛋白质 {{ totals.protein_g.toFixed(1) }}g · 碳水 {{ totals.carbs_g.toFixed(1) }}g · 脂肪 {{ totals.fat_g.toFixed(1) }}g</span>
      </div>
      <div class="diet-today-list">
        <span v-for="entry in entries" :key="entry.id" class="diet-chip">
          {{ entry.dish_name }} {{ entry.weight_g }}g / {{ entry.calories }} 大卡
          <button type="button" aria-label="移除" @click="removeEntry(entry.id)">×</button>
        </span>
      </div>
    </div>

    <el-drawer
      v-model="drawerVisible"
      :title="current?.dish_name || '菜品详情'"
      :size="'min(560px, 92vw)'"
      direction="rtl"
      @closed="closeDetail"
    >
      <div v-if="current" class="dish-detail">
        <div class="dish-detail-tags">
          <span class="chip">{{ current.category }}</span>
          <span class="chip chip-ok">热量字典已收录</span>
          <span v-if="current.aliases.length" class="chip chip-muted">
            别名：{{ current.aliases.slice(0, 3).join('、') }}
          </span>
        </div>

        <div class="detail-calorie">
          <strong>{{ current.calories_per_100g }}</strong>
          <span>大卡 / 100g</span>
          <em>常见一份 {{ current.typical_portion_g }}g ≈ {{ detailPortionCalories }} 大卡</em>
        </div>

        <div class="detail-macro-grid">
          <div v-for="macro in detailMacros" :key="macro.label" class="detail-macro">
            <span>{{ macro.label }}</span>
            <strong>{{ macro.value }}g</strong>
            <i :style="{ background: macro.color }" />
          </div>
        </div>

        <div class="detail-tip">
          <span>💡 健康建议</span>
          <p>{{ current.health_tip }}</p>
        </div>

        <div class="detail-portion">
          <span>按 100g 数据换算</span>
          <p>如果实际吃了 {{ current.typical_portion_g }}g，约摄入 {{ detailPortionCalories }} 大卡；具体以称重和实际做法为准。</p>
        </div>

        <div class="detail-source">
          <span>数据来源</span>
          <p>{{ current.source }}</p>
        </div>

        <el-button class="detail-add" type="primary" size="large" @click="add(current)">
          加入今日饮食记录
        </el-button>

        <div v-if="related.length" class="detail-related">
          <div class="related-title">同类菜品</div>
          <button
            v-for="item in related"
            :key="item.slug"
            type="button"
            class="related-item"
            @click="openDetail(item.slug)"
          >
            {{ item.dish_name }} · {{ item.calories_per_100g }} 大卡/100g
          </button>
        </div>

        <p class="detail-note">
          营养数据参考《中国食物成分表》与常见食堂做法估算，不同餐厅的油盐用量会造成差异。
        </p>
      </div>
      <div v-else-if="detailLoading" class="loading-block" style="height: 220px; margin: 16px" />
    </el-drawer>
  </section>
</template>

<style scoped>
.dish-library {
  margin-top: 4px;
}

.dish-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  margin-bottom: 14px;
}

.dish-toolbar-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 16px;
  font-weight: 750;
  color: var(--text-1);
}

.dish-toolbar-title span {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted);
}

.dish-toolbar p {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--muted);
}

.diet-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
  padding: 7px 10px 7px 12px;
  border-radius: 999px;
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 12px;
}

.diet-summary strong {
  font-size: 14px;
}

.diet-summary button {
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}

.dish-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.dish-card {
  display: flex;
  flex-direction: column;
  gap: 9px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--card);
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
}

.dish-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
  border-color: var(--brand);
}

.dish-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.dish-category {
  display: inline-flex;
  align-items: center;
  width: max-content;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 11px;
  font-weight: 650;
}

.dish-alias {
  overflow: hidden;
  color: var(--muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dish-name {
  overflow-wrap: anywhere;
  color: var(--text-1);
  font-size: 17px;
  font-weight: 750;
  line-height: 1.35;
}

.dish-calorie {
  display: flex;
  align-items: baseline;
  gap: 7px;
  padding: 4px 0 2px;
}

.dish-calorie strong {
  color: var(--brand-700);
  font-size: 38px;
  font-weight: 800;
  letter-spacing: -1.4px;
  line-height: 1;
}

.dish-calorie span {
  color: var(--muted);
  font-size: 11.5px;
}

.macro-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 8px 0 4px;
  border-top: 1px dashed var(--border);
}

.macro-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.macro-head {
  display: flex;
  justify-content: space-between;
  color: var(--text-2);
  font-size: 11.5px;
}

.macro-head b {
  font-weight: 700;
}

.macro-track {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #f0f3f2;
}

.macro-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  transition: width 0.3s ease;
}

.dish-card-foot {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
}

.dish-card-foot > span {
  color: var(--muted);
  font-size: 11px;
}

.dish-add {
  width: 100%;
  border-radius: 9px;
  font-size: 12px;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.mt {
  margin-top: 12px;
}

.diet-today {
  margin-top: 18px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: linear-gradient(135deg, #f7fbf8, #ffffff);
}

.diet-today-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-2);
  font-size: 11.5px;
}

.diet-today-head strong {
  color: var(--brand-700);
  font-size: 13px;
}

.diet-today-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 9px;
}

.diet-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--card);
  border: 1px solid var(--border);
  color: var(--text-2);
  font-size: 11px;
}

.diet-chip button {
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  padding: 0 2px;
}

.dish-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 0 22px 26px;
}

.dish-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-calorie {
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #eef8f3, #fbfdfb);
}

.detail-calorie strong {
  color: var(--brand-700);
  font-size: 42px;
  font-weight: 800;
  letter-spacing: -1.5px;
}

.detail-calorie > span {
  margin-left: 8px;
  color: var(--muted);
  font-size: 12px;
}

.detail-calorie em {
  display: block;
  margin-top: 6px;
  color: var(--text-2);
  font-size: 12px;
  font-style: normal;
}

.detail-macro-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.detail-macro {
  position: relative;
  overflow: hidden;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
}

.detail-macro span {
  display: block;
  color: var(--muted);
  font-size: 11px;
}

.detail-macro strong {
  display: block;
  margin-top: 4px;
  font-size: 18px;
}

.detail-macro i {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3px;
}

.detail-tip,
.detail-portion,
.detail-source {
  padding: 11px 13px;
  border-radius: 10px;
  background: #fbf7ee;
  border: 1px solid #f0e2c8;
}

.detail-tip > span,
.detail-portion > span,
.detail-source > span {
  color: #7a5a17;
  font-size: 12px;
  font-weight: 700;
}

.detail-tip p,
.detail-portion p,
.detail-source p {
  margin-top: 4px;
  color: #6b5320;
  font-size: 13px;
  line-height: 1.7;
}

.detail-portion,
.detail-source {
  background: #f7f9f8;
  border-color: var(--border);
}

.detail-portion > span,
.detail-source > span {
  color: var(--muted);
}

.detail-portion p,
.detail-source p {
  color: var(--text-2);
}

.detail-add {
  width: 100%;
  border-radius: 10px;
}

.detail-related {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.related-title {
  color: var(--muted);
  font-size: 12.5px;
  font-weight: 650;
}

.related-item {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  color: var(--text-2);
  cursor: pointer;
  font-size: 13px;
  text-align: left;
}

.related-item:hover {
  border-color: var(--brand);
  color: var(--brand-700);
}

.detail-note {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}

@media (max-width: 1024px) {
  .dish-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .dish-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .diet-summary {
    width: 100%;
    justify-content: space-between;
  }

  .dish-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .dish-detail {
    padding: 0 16px 22px;
  }
}
</style>