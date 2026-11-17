<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { favoriteApi } from '@/api'
import { ApiError } from '@/api/client'
import type { FavoriteRecipe } from '@/api/types'

type RecipeData = Record<string, unknown> & {
  ingredients?: Array<{ name?: string; amount?: string } | string>
  main_ingredients?: Array<{ name?: string; amount?: string } | string>
  nutrition?: { energy_kcal?: number; [key: string]: unknown }
  steps?: string[]
  tips?: string
  versions?: Record<string, { steps?: string[]; tips?: string }>
}

const router = useRouter()
const items = ref<FavoriteRecipe[]>([])
const loading = ref(true)
const errorMessage = ref('')
const scheduling = ref<number | null>(null)
const removing = ref<number | null>(null)
const detailOpen = ref(false)
const detailItem = ref<FavoriteRecipe | null>(null)

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await favoriteApi.list()
    items.value = result.items
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '收藏加载失败'
  } finally {
    loading.value = false
  }
}

function dataOf(item: FavoriteRecipe): RecipeData {
  return (item.recipe_data || {}) as RecipeData
}

function energyOf(item: FavoriteRecipe): number {
  const direct = Number(item.energy_kcal || 0)
  if (Number.isFinite(direct) && direct > 0) return Math.round(direct)
  const data = dataOf(item)
  const value = Number(data.nutrition?.energy_kcal || 0)
  return Number.isFinite(value) && value > 0 ? Math.round(value) : 0
}

function energyText(item: FavoriteRecipe): string {
  const energy = energyOf(item)
  return energy > 0 ? `🔥 ${energy} kcal` : '🔥 热量待估算'
}

function mainIngredients(item: FavoriteRecipe): Array<{ name: string; amount: string }> {
  if (item.main_ingredients?.length) return item.main_ingredients
  const data = dataOf(item)
  const raw = data.main_ingredients || data.ingredients || []
  return raw
    .map((entry) => {
      if (typeof entry === 'string') {
        const [name, ...rest] = entry.split(/\s+/)
        return { name: name || entry, amount: rest.join(' ') }
      }
      return { name: String(entry.name || ''), amount: String(entry.amount || '') }
    })
    .filter((entry) => entry.name)
}

function stepList(item: FavoriteRecipe | null): string[] {
  if (!item) return []
  const data = dataOf(item)
  const direct = Array.isArray(data.steps) ? data.steps : []
  if (direct.length) return direct.map(String)
  const versions = data.versions || {}
  return (versions.novice?.steps || versions.chef?.steps || []).map(String)
}

function tipsOf(item: FavoriteRecipe | null): string {
  if (!item) return ''
  const data = dataOf(item)
  return String(data.tips || data.versions?.novice?.tips || '')
}

const detailSteps = computed(() => stepList(detailItem.value))
const detailTips = computed(() => tipsOf(detailItem.value))
const detailIngredients = computed(() => (detailItem.value ? mainIngredients(detailItem.value) : []))

function openDetail(item: FavoriteRecipe) {
  detailItem.value = item
  detailOpen.value = true
}

async function schedule(item: FavoriteRecipe) {
  scheduling.value = item.id
  try {
    const result = await favoriteApi.schedule(item.id)
    ElMessage.success(result.message)

    let goPurchase = false
    if (item.missing.length > 0) {
      try {
        await ElMessageBox.confirm(
          `⚠️ 您缺少 ${item.missing.length} 种主食材，已为您加入计划，请及时采购。`,
          '缺少主食材',
          { type: 'warning', confirmButtonText: '去采购', cancelButtonText: '稍后处理' },
        )
        goPurchase = true
      } catch {
        goPurchase = false
      }
    }

    router.push({
      name: 'pantry',
      query: {
        tab: 'plan',
        ...(goPurchase && item.missing[0]
          ? { purchase: item.missing[0].name, favorite_id: String(item.id) }
          : {}),
      },
    })
  } catch (error) {
    ElMessage.error((error as ApiError).message || '加入排期失败')
  } finally {
    scheduling.value = null
  }
}

async function remove(item: FavoriteRecipe) {
  removing.value = item.id
  try {
    await favoriteApi.remove(item.id)
    items.value = items.value.filter((entry) => entry.id !== item.id)
    if (detailItem.value?.id === item.id) detailOpen.value = false
    ElMessage.success('已取消收藏')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '取消收藏失败')
  } finally {
    removing.value = null
  }
}

function goPurchase(name: string, favoriteId?: number) {
  router.push({
    name: 'pantry',
    query: {
      tab: 'plan',
      purchase: name,
      ...(favoriteId ? { favorite_id: String(favoriteId) } : {}),
    },
  })
}

function goGenerate() {
  router.push({ name: 'pantry', query: { tab: 'plan' } })
}

onMounted(load)
</script>

<template>
  <div class="page favorites-page">
    <header class="favorites-hero">
      <div class="favorites-hero-copy">
        <span class="favorites-eyebrow">MY RECIPE COLLECTION</span>
        <h1 class="favorites-title">我的收藏</h1>
        <p class="favorites-subtitle">把喜欢的味道收进口袋，随时加入今日三餐。</p>
      </div>
      <div class="favorites-hero-side">
        <div class="hero-dish">
          <div class="hero-dish-thumb" aria-hidden="true">🍖</div>
          <div class="hero-dish-meta">
            <span>今日灵感</span>
            <strong>红烧肉</strong>
          </div>
        </div>
        <div class="hero-actions">
          <el-button class="today-menu-btn" @click="goGenerate">今日菜谱</el-button>
          <el-button :loading="loading" plain class="refresh-btn" @click="load">刷新</el-button>
        </div>
      </div>
    </header>

    <div v-if="errorMessage" class="notice notice-danger">{{ errorMessage }}</div>

    <div v-if="loading" class="favorite-loading">
      <el-skeleton v-for="i in 3" :key="i" animated :rows="3" />
    </div>

    <div v-else-if="!items.length" class="favorite-empty">
      <div class="empty-illustration">🍽️</div>
      <h2>还没有收藏任何菜谱</h2>
      <p>您还没有收藏任何菜谱，快去让 AI 为您规划吧~</p>
      <el-button type="primary" size="large" @click="goGenerate">去生成食谱</el-button>
    </div>

    <div v-else class="favorite-grid">
      <article v-for="item in items" :key="item.id" class="favorite-card">
        <div class="favorite-card-head">
          <div class="recipe-icon">🍲</div>
          <div class="favorite-head-right">
            <span class="energy-chip">{{ energyText(item) }}</span>
            <button type="button" class="favorite-badge" title="已收藏">
              ⭐ 已收藏
            </button>
          </div>
        </div>

        <h2>{{ item.recipe_name }}</h2>

        <div class="ingredient-block">
          <span class="main-label">主要食材</span>
          <div class="ingredient-tags">
            <el-tag
              v-for="ingredient in mainIngredients(item).slice(0, 5)"
              :key="`${ingredient.name}-${ingredient.amount}`"
              size="small"
              effect="plain"
              class="ingredient-tag"
            >
              {{ ingredient.name }}<span v-if="ingredient.amount"> {{ ingredient.amount }}</span>
            </el-tag>
            <span v-if="!mainIngredients(item).length" class="muted-text">主料信息待补充</span>
          </div>
        </div>

        <div v-if="item.missing.length" class="missing-line">
          <span class="missing-badge">⚠️ 缺少 {{ item.missing.length }} 种食材</span>
          <button type="button" class="purchase-link" @click="goPurchase(item.missing[0].name, item.id)">
            去采购
          </button>
        </div>
        <p v-else class="ready-line">✅ 家庭库存主料已齐，可以直接安排</p>

        <div class="favorite-actions">
          <el-button
            type="primary"
            class="schedule-btn"
            :loading="scheduling === item.id"
            @click="schedule(item)"
          >
            📅 加入今日排期
          </el-button>
          <el-button class="detail-btn" @click="openDetail(item)">查看详细步骤</el-button>
          <el-button
            text
            type="danger"
            class="remove-btn"
            :loading="removing === item.id"
            @click="remove(item)"
          >
            🗑️ 取消收藏
          </el-button>
        </div>
      </article>
    </div>

    <el-drawer v-model="detailOpen" :title="detailItem?.recipe_name || '菜谱详情'" size="min(94vw, 560px)">
      <div v-if="detailItem" class="recipe-detail">
        <div class="detail-top">
          <div class="recipe-icon large">🍲</div>
          <div>
            <h3>{{ detailItem.recipe_name }}</h3>
            <div class="detail-meta">
              <span>{{ energyText(detailItem) }}</span>
              <span>{{ mainIngredients(detailItem).length }} 样主料</span>
            </div>
          </div>
        </div>

        <section class="detail-section">
          <h4>主要食材</h4>
          <div class="detail-ingredients">
            <div v-for="ingredient in detailIngredients" :key="`${ingredient.name}-${ingredient.amount}`" class="detail-ingredient">
              <span>{{ ingredient.name }}</span>
              <strong>{{ ingredient.amount || '适量' }}</strong>
            </div>
          </div>
        </section>

        <section class="detail-section">
          <h4>详细步骤</h4>
          <ol v-if="detailSteps.length" class="detail-steps">
            <li v-for="(step, index) in detailSteps" :key="index">{{ step }}</li>
          </ol>
          <p v-else class="muted-text">这条收藏暂时没有步骤，重新让 AI 生成一份即可查看。</p>
        </section>

        <section v-if="detailTips" class="detail-section">
          <h4>小贴士</h4>
          <p class="detail-tips">{{ detailTips }}</p>
        </section>

        <div class="detail-footer">
          <el-button type="primary" :loading="scheduling === detailItem.id" @click="schedule(detailItem)">
            📅 加入今日排期
          </el-button>
          <el-button text type="danger" :loading="removing === detailItem.id" @click="remove(detailItem)">
            🗑️ 取消收藏
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.favorites-page {
  min-height: calc(100vh - 90px);
  padding-bottom: 48px;
  background: #f3f8f5;
}

.favorites-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  width: 100%;
  margin-bottom: 24px;
  padding: 26px 30px;
  border: 1px solid #e4eee8;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 10px 30px rgba(31, 61, 50, 0.06);
}

.favorites-eyebrow {
  color: #91a79c;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.favorites-title {
  margin: 6px 0 6px;
  color: #1d3a2e;
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.favorites-subtitle {
  margin: 0;
  color: #7b9188;
  font-size: 13px;
  line-height: 1.7;
}

.favorites-hero-side {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
}

.hero-dish {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px 8px 8px;
  border: 1px solid #f1e1d1;
  border-radius: 16px;
  background: #fffbf6;
}

.hero-dish-thumb {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: radial-gradient(circle at 35% 30%, #ffe0be, #f6b77a);
  font-size: 26px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6);
}

.hero-dish-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.hero-dish-meta span {
  color: #b08a63;
  font-size: 10px;
}

.hero-dish-meta strong {
  color: #6b432b;
  font-size: 13px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.today-menu-btn {
  border: 1px solid #dce8e1 !important;
  border-radius: 999px !important;
  background: #f7fbf9 !important;
  color: #1f7a5f !important;
  font-weight: 600;
}

.today-menu-btn:hover {
  border-color: #b9d2c6 !important;
  background: #eef8f3 !important;
  color: #0f6b52 !important;
}

.refresh-btn {
  border-color: #dce8e1 !important;
  border-radius: 999px !important;
  background: #ffffff !important;
  color: #4b6b5d !important;
}

.refresh-btn:hover {
  border-color: #bcd4c8 !important;
  background: #f8fcfa !important;
  color: #1f7a5f !important;
}

.favorite-loading {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

.favorite-loading :deep(.el-skeleton) {
  padding: 18px;
  border: 1px solid #edf1f3;
  border-radius: 16px;
  background: #fff;
}

.favorite-empty {
  max-width: 580px;
  margin: 54px auto;
  padding: 48px 28px;
  border: 1px solid #eef2f4;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 8px 28px rgba(35, 61, 51, 0.06);
  text-align: center;
}

.empty-illustration {
  width: 82px;
  height: 82px;
  display: grid;
  place-items: center;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: #fff4e7;
  font-size: 42px;
}

.favorite-empty h2 {
  margin: 0 0 8px;
  color: #294d3e;
  font-size: 20px;
}

.favorite-empty p {
  margin: 0 0 22px;
  color: #7b9188;
  font-size: 13px;
  line-height: 1.7;
}

.favorite-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
  gap: 20px;
  align-items: stretch;
}

.favorite-card {
  display: flex;
  flex-direction: column;
  min-height: 350px;
  padding: 20px;
  border: 1px solid #e6eee9;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(31, 61, 50, 0.06);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.favorite-card:hover {
  transform: translateY(-4px);
  border-color: #d4e5dc;
  box-shadow: 0 20px 42px rgba(31, 61, 50, 0.12);
}

.favorite-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px dashed #eef4f0;
}

.recipe-icon {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  border-radius: 16px;
  background: linear-gradient(145deg, #fff3e6, #ffe3c7);
  font-size: 28px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7), 0 6px 14px rgba(190, 130, 67, 0.1);
}

.recipe-icon.large {
  width: 54px;
  height: 54px;
  font-size: 28px;
}

.favorite-head-right {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.energy-chip {
  padding: 5px 9px;
  border-radius: 999px;
  background: #f4f8f5;
  color: #4e7662;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.favorite-badge {
  padding: 5px 8px;
  border: 0;
  border-radius: 999px;
  background: #fff8e8;
  color: #b07a16;
  font-size: 10.5px;
  cursor: default;
  white-space: nowrap;
}

.favorite-card h2 {
  margin: 0 0 12px;
  color: #203a2e;
  font-size: 19px;
  font-weight: 700;
  line-height: 1.4;
}

.ingredient-block {
  min-height: 76px;
}

.main-label {
  display: block;
  margin-bottom: 6px;
  color: #8a9e93;
  font-size: 10.5px;
}

.ingredient-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ingredient-tag {
  border-color: #e5eee8 !important;
  background: #f8fbf9 !important;
  color: #587568 !important;
  font-size: 11px !important;
}

.muted-text {
  color: #9aaba2;
  font-size: 11.5px;
}

.missing-line {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  margin: 13px 0 10px;
  padding: 5px 10px;
  border: 1px solid #ffe1dd;
  border-radius: 999px;
  background: #fff1f0;
}

.missing-badge {
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: #d9534f;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.purchase-link {
  padding: 0;
  border: 0;
  background: none;
  color: #d9534f;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.purchase-link:hover {
  text-decoration: underline;
  text-underline-offset: 2px;
}

.ready-line {
  margin: 13px 0 10px;
  color: #4b8c6c;
  font-size: 11.5px;
}

.favorite-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: auto;
  padding-top: 18px;
  border-top: 1px solid #f2f5f3;
}

.schedule-btn {
  flex: 1 1 100%;
  height: 42px;
  border: 0 !important;
  border-radius: 10px !important;
  background: #0f6b52 !important;
  color: #fff !important;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 6px 14px rgba(15, 107, 82, 0.18);
}

.schedule-btn:hover {
  background: #0b5a45 !important;
  box-shadow: 0 8px 18px rgba(15, 107, 82, 0.24);
}

.detail-btn {
  flex: 1;
  height: 36px;
  border: 0 !important;
  border-radius: 9px !important;
  background: transparent !important;
  color: #4b6b5d !important;
  font-size: 12px;
  font-weight: 500;
}

.detail-btn:hover {
  background: #f4f9f6 !important;
  color: #1f7a5f !important;
}

.remove-btn {
  flex: 0 0 auto;
  height: 36px;
  margin-left: 0 !important;
  padding: 0 6px;
  color: #95a69d !important;
  font-size: 12px;
}

.remove-btn:hover {
  background: transparent !important;
  color: #c14936 !important;
}

.recipe-detail {
  padding: 0 2px;
}

.detail-top {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 15px;
  border-bottom: 1px solid #edf2ef;
}

.detail-top h3 {
  margin: 0 0 6px;
  color: #203a2e;
  font-size: 20px;
}

.detail-meta {
  display: flex;
  gap: 12px;
  color: #7d938a;
  font-size: 11.5px;
}

.detail-section {
  padding: 16px 0;
  border-bottom: 1px solid #f1f5f2;
}

.detail-section h4 {
  margin: 0 0 10px;
  color: #294d3e;
  font-size: 13px;
}

.detail-ingredients {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.detail-ingredient {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f7faf8;
  color: #587568;
  font-size: 12px;
}

.detail-ingredient strong {
  color: #294d3e;
  font-weight: 600;
}

.detail-steps {
  margin: 0;
  padding-left: 20px;
  color: #536b60;
  font-size: 13px;
  line-height: 1.85;
}

.detail-steps li {
  margin-bottom: 7px;
}

.detail-tips {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff9ee;
  color: #806735;
  font-size: 12px;
  line-height: 1.7;
}

.detail-footer {
  display: flex;
  gap: 8px;
  padding-top: 16px;
}

.detail-footer .el-button--primary {
  border-color: #0f6b52;
  background: #0f6b52;
}

.detail-footer .el-button--primary:hover {
  border-color: #0b5a45;
  background: #0b5a45;
}

@media (max-width: 760px) {
  .favorites-page {
    background: #f3f8f5;
  }

  .favorites-hero {
    flex-direction: column;
    align-items: flex-start;
    padding: 20px;
  }

  .favorites-title {
    font-size: 26px;
  }

  .favorites-hero-side {
    width: 100%;
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .hero-actions {
    justify-content: flex-end;
  }

  .favorite-grid,
  .favorite-loading {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .favorite-card {
    min-height: 0;
    padding: 16px;
  }

  .favorite-badge {
    font-size: 10px;
  }

  .detail-ingredients {
    grid-template-columns: 1fr;
  }

  .detail-footer {
    flex-direction: column;
  }

  .detail-footer .el-button {
    width: 100%;
    margin-left: 0;
  }
}
</style>
