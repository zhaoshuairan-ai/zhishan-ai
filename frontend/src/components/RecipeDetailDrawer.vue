<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AssistantSection, RecipeSummary, RecipeVersionKey, RecipeVersions } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  title: string
  summary?: RecipeSummary | null
  sections: AssistantSection[]
  versions?: RecipeVersions | null
  defaultVersion?: RecipeVersionKey
  saved?: boolean
  saving?: boolean
  nutrition?: Record<string, number> | null
  ingredients?: Array<{ name: string; amount: string }>
  missing?: Array<{ name: string; amount: string }>
  consuming?: boolean
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'save', version: RecipeVersionKey): void
  (event: 'consume'): void
  (event: 'add-to-shopping'): void
}>()

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const activeVersion = ref<RecipeVersionKey>(props.defaultVersion || 'novice')
const currentVersion = computed(() => props.versions?.[activeVersion.value] || null)

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) activeVersion.value = props.defaultVersion || 'novice'
  },
)

watch(
  () => props.defaultVersion,
  (version) => {
    if (version) activeVersion.value = version
  },
)

function lines(text: string): string[] {
  return (text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

function stripBullet(text: string): string {
  return text.replace(/^[·\-]\s*/, '')
}

function stripStepNumber(text: string): string {
  return text.replace(/^\d+[.、]\s*/, '')
}

function sectionLines(section: AssistantSection): string[] {
  return lines(section.text)
}

const orderedSections = computed(() => {
  const priority = ['intro', 'ingredients', 'steps', 'tips', 'safety', 'source']
  return [...props.sections]
    .filter((section) => {
      if (!currentVersion.value) return true
      return section.key !== 'steps' && section.key !== 'tips'
    })
    .sort((a, b) => {
    const ai = priority.indexOf(a.key)
    const bi = priority.indexOf(b.key)
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi)
  })
})
const nutritionRows = computed(() => {
  const data = props.nutrition || {}
  return [
    { label: '热量', value: data.energy_kcal, unit: 'kcal' },
    { label: '蛋白质', value: data.protein_g, unit: 'g' },
    { label: '脂肪', value: data.fat_g, unit: 'g' },
    { label: '碳水', value: data.carbs_g, unit: 'g' },
    { label: '钠', value: data.sodium_mg, unit: 'mg' },
    { label: '糖', value: data.sugar_g, unit: 'g' },
  ].filter((item) => item.value !== undefined && item.value !== null)
})

const missingText = computed(() =>
  (props.missing || []).map((item) => `${item.name}${item.amount ? ` ${item.amount}` : ''}`).join('、'),
)
</script>

<template>
  <el-drawer
    v-model="open"
    :with-header="false"
    direction="rtl"
    size="min(94vw, 720px)"
    class="recipe-detail-drawer"
  >
    <div class="detail-panel">
      <header class="detail-hero">
        <button type="button" class="detail-close" aria-label="关闭详细步骤" @click="open = false">×</button>
        <span class="detail-emoji">🥘</span>
        <div>
          <span class="detail-kicker">详细做法 · 边看边做</span>
          <h2>{{ summary?.title || title }}</h2>
          <p v-if="summary" class="detail-meta">
            <span>⏱ {{ summary.time }}</span>
            <span>难度 · {{ summary.difficulty }}</span>
          </p>
        </div>
      </header>

      <div v-if="versions" class="detail-version-tabs">
        <button type="button" :class="{ active: activeVersion === 'novice' }" @click="activeVersion = 'novice'">
          新手版
        </button>
        <button type="button" :class="{ active: activeVersion === 'chef' }" @click="activeVersion = 'chef'">
          大厨版
        </button>
        <span>{{ currentVersion?.steps.length || 0 }} 步</span>
      </div>

      <div class="detail-body">
        <section v-if="currentVersion" class="detail-version-section">
          <h3>{{ activeVersion === 'chef' ? '大厨版步骤' : '新手版步骤' }}</h3>
          <div class="detail-steps">
            <div v-for="(step, index) in currentVersion.steps" :key="index" class="detail-step">
              <span>{{ index + 1 }}</span>
              <p>{{ stripStepNumber(step) }}</p>
            </div>
          </div>
          <div v-if="currentVersion.tips.length" class="version-tips">
            <h4>{{ activeVersion === 'chef' ? '大厨提升点' : '新手易错点' }}</h4>
            <ul class="detail-notes">
              <li v-for="tip in currentVersion.tips" :key="tip">{{ tip }}</li>
            </ul>
          </div>
        </section>

        <section v-for="section in orderedSections" :key="section.key" class="detail-section">
          <h3>{{ section.label }}</h3>

          <template v-if="section.key === 'steps'">
            <div class="detail-steps">
              <div v-for="(step, index) in sectionLines(section)" :key="index" class="detail-step">
                <span>{{ index + 1 }}</span>
                <p>{{ stripStepNumber(step) }}</p>
              </div>
            </div>
          </template>

          <template v-else-if="section.key === 'ingredients'">
            <div class="detail-ingredients">
              <span v-for="item in sectionLines(section)" :key="item">{{ stripBullet(item) }}</span>
            </div>
          </template>

          <template v-else-if="section.key === 'tips' || section.key === 'safety'">
            <ul class="detail-notes" :class="{ danger: section.key === 'safety' }">
              <li v-for="item in sectionLines(section)" :key="item">{{ stripBullet(item) }}</li>
            </ul>
          </template>

          <p v-else class="detail-text">{{ section.text }}</p>
        </section>

        <div v-if="!orderedSections.length" class="detail-empty">暂时没有可展示的详细步骤。</div>

        <section v-if="nutritionRows.length" class="detail-section nutrition-section">
          <h3>营养数据 · 每份估算</h3>
          <div class="nutrition-grid">
            <div v-for="item in nutritionRows" :key="item.label" class="nutrition-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}<small>{{ item.unit }}</small></strong>
            </div>
          </div>
          <el-button
            type="success"
            size="large"
            class="consume-btn"
            :loading="consuming"
            :disabled="Boolean(missing?.length)"
            :title="missing?.length ? '还有主食材未补齐，请先采购' : '按食材用量扣减库存'"
            @click="emit('consume')"
          >
            {{ missing?.length ? '缺主料，先去采购' : '🍳 烹饪完成，扣减库存' }}
          </el-button>
        </section>

        <div v-if="missing?.length" class="detail-missing">
          <div class="detail-missing-copy">
            <strong>这道菜还需要补购</strong>
            <span>{{ missingText }}</span>
          </div>
          <el-button type="warning" size="small" class="shopping-missing-btn" @click="emit('add-to-shopping')">
            🛒 去采购/加入清单
          </el-button>
        </div>
      </div>

      <footer class="detail-footer">
        <span v-if="summary?.safety" class="detail-safety-tip">⚠️ {{ summary.safety }}</span>
        <el-button @click="open = false">关闭</el-button>
        <el-button
          type="success"
          :loading="saving"
          @click="emit('save', activeVersion)"
        >
          {{ saved ? '更新食谱版本' : '📅 加入食谱规划' }}
        </el-button>
        <el-tag v-if="saved" type="success" effect="plain">已加入</el-tag>
      </footer>
    </div>
  </el-drawer>
</template>

<style scoped>
.recipe-detail-drawer :deep(.el-drawer__body) {
  padding: 0;
  overflow: hidden;
}

.detail-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.detail-hero {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 28px 30px 22px;
  color: #fff;
  background:
    radial-gradient(circle at 92% 4%, rgba(255, 255, 255, 0.24), transparent 34%),
    linear-gradient(135deg, #1e6f57, #2c9271);
}

.detail-close {
  position: absolute;
  top: 14px;
  right: 16px;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  font-size: 23px;
  line-height: 1;
  cursor: pointer;
}

.detail-emoji {
  flex: none;
  width: 72px;
  height: 72px;
  display: grid;
  place-items: center;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.24);
  font-size: 38px;
}

.detail-kicker {
  font-size: 11.5px;
  opacity: 0.82;
  letter-spacing: 0.06em;
}

.detail-hero h2 {
  margin: 5px 0 7px;
  font-size: 26px;
  line-height: 1.25;
}

.detail-meta {
  margin: 0;
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

.detail-meta span {
  font-size: 11.5px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
}

.detail-version-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 30px 0;
  border-bottom: 1px solid #edf2ef;
}

.detail-version-tabs button {
  border: 0;
  background: transparent;
  padding: 7px 14px;
  border-radius: 9px 9px 0 0;
  color: #7a9187;
  font-size: 13px;
  cursor: pointer;
}

.detail-version-tabs button.active {
  color: #1f7a5f;
  background: #e8f5ee;
  font-weight: 700;
}

.detail-version-tabs span {
  margin-left: auto;
  color: #98aaa1;
  font-size: 11px;
}

.version-tips {
  margin-top: 14px;
}

.version-tips h4 {
  margin: 0 0 7px;
  color: #4d6d5e;
  font-size: 13px;
}

.detail-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 24px 30px 112px;
}

.detail-section {
  margin-bottom: 24px;
}

.detail-section h3 {
  margin: 0 0 10px;
  font-size: 17px;
  color: #173d30;
}

.detail-text {
  margin: 0;
  color: #567066;
  line-height: 1.8;
  font-size: 14px;
}

.detail-ingredients {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-ingredients span {
  padding: 5px 10px;
  border: 1px solid #e2ece7;
  border-radius: 999px;
  background: #f8fbf9;
  color: #355c4c;
  font-size: 12.5px;
}

.detail-steps {
  display: grid;
  gap: 2px;
}

.detail-step {
  display: flex;
  gap: 13px;
  padding: 12px 0;
  border-bottom: 1px solid #edf2ef;
}

.detail-step:last-child {
  border-bottom: 0;
}

.detail-step > span {
  flex: none;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: #e8f5ee;
  color: #1f7a5f;
  font-weight: 700;
  font-size: 15px;
}

.detail-step p {
  margin: 1px 0 0;
  font-size: 16px;
  line-height: 1.8;
  color: #253f35;
}

.detail-notes {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 7px;
}

.detail-notes li {
  position: relative;
  padding: 8px 10px 8px 26px;
  border-radius: 8px;
  background: #fbf8ef;
  color: #76551b;
  font-size: 13px;
  line-height: 1.65;
}

.detail-notes li::before {
  content: '·';
  position: absolute;
  left: 11px;
  font-weight: 800;
}

.detail-notes.danger li {
  background: #fdf1ee;
  color: #91452e;
}

.detail-empty {
  padding: 24px;
  border-radius: 10px;
  background: #f7faf8;
  color: #7b9188;
  text-align: center;
}

.nutrition-section {
  padding: 15px;
  border: 1px solid #dcebe2;
  border-radius: 12px;
  background: #fbfdfb;
}

.nutrition-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin-bottom: 14px;
}

.nutrition-item {
  padding: 8px 9px;
  border-radius: 8px;
  background: #f2f8f4;
}

.nutrition-item span {
  display: block;
  color: #789087;
  font-size: 10.5px;
}

.nutrition-item strong {
  display: block;
  margin-top: 2px;
  color: #28533f;
  font-size: 16px;
}

.nutrition-item small {
  margin-left: 2px;
  color: #7e968a;
  font-size: 10px;
  font-weight: 400;
}

.consume-btn {
  width: 100%;
  font-weight: 700;
  box-shadow: 0 7px 16px rgba(31, 122, 95, 0.16);
}

.detail-missing {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #f0d9b0;
  border-radius: 10px;
  background: #fffbf1;
}

.detail-missing-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-missing-copy strong {
  color: #9a6a16;
  font-size: 12px;
}

.detail-missing-copy span {
  color: #a9874c;
  font-size: 11.5px;
}

.shopping-missing-btn {
  flex: none;
  font-weight: 700;
  box-shadow: 0 5px 12px rgba(196, 132, 30, 0.18);
}

.detail-footer {
  flex: none;
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  padding: 13px 24px;
  border-top: 1px solid #e8efeb;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(8px);
}

.detail-safety-tip {
  min-width: 200px;
  flex: 1;
  color: #8a5a12;
  font-size: 11.5px;
  line-height: 1.5;
}

@media (max-width: 640px) {
  .detail-hero {
    padding: 22px 18px 18px;
  }

  .detail-emoji {
    width: 56px;
    height: 56px;
    font-size: 30px;
  }

  .detail-hero h2 {
    font-size: 21px;
  }

  .detail-version-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 30px 0;
  border-bottom: 1px solid #edf2ef;
}

.detail-version-tabs button {
  border: 0;
  background: transparent;
  padding: 7px 14px;
  border-radius: 9px 9px 0 0;
  color: #7a9187;
  font-size: 13px;
  cursor: pointer;
}

.detail-version-tabs button.active {
  color: #1f7a5f;
  background: #e8f5ee;
  font-weight: 700;
}

.detail-version-tabs span {
  margin-left: auto;
  color: #98aaa1;
  font-size: 11px;
}

.version-tips {
  margin-top: 14px;
}

.version-tips h4 {
  margin: 0 0 7px;
  color: #4d6d5e;
  font-size: 13px;
}

.detail-body {
    padding: 18px 18px 120px;
  }

  .detail-step p {
    font-size: 15px;
  }

  .nutrition-section {
  padding: 15px;
  border: 1px solid #dcebe2;
  border-radius: 12px;
  background: #fbfdfb;
}

.nutrition-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin-bottom: 14px;
}

.nutrition-item {
  padding: 8px 9px;
  border-radius: 8px;
  background: #f2f8f4;
}

.nutrition-item span {
  display: block;
  color: #789087;
  font-size: 10.5px;
}

.nutrition-item strong {
  display: block;
  margin-top: 2px;
  color: #28533f;
  font-size: 16px;
}

.nutrition-item small {
  margin-left: 2px;
  color: #7e968a;
  font-size: 10px;
  font-weight: 400;
}

.consume-btn {
  width: 100%;
  font-weight: 700;
  box-shadow: 0 7px 16px rgba(31, 122, 95, 0.16);
}

.detail-missing {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #f0d9b0;
  border-radius: 10px;
  background: #fffbf1;
}

.detail-missing-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-missing-copy strong {
  color: #9a6a16;
  font-size: 12px;
}

.detail-missing-copy span {
  color: #a9874c;
  font-size: 11.5px;
}

.shopping-missing-btn {
  flex: none;
  font-weight: 700;
  box-shadow: 0 5px 12px rgba(196, 132, 30, 0.18);
}

.detail-footer {
  flex: none;
    padding: 12px 16px;
  }

  .detail-safety-tip {
    flex-basis: 100%;
  }
}
</style>
