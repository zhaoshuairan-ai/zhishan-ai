<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { RecipeSummary, RecipeVersionKey, RecipeVersions } from '@/api/types'

const props = defineProps<{
  summary: RecipeSummary
  versions?: RecipeVersions | null
  saved?: boolean
  saving?: boolean
  favorite?: boolean
  favoriting?: boolean
}>()

const emit = defineEmits<{
  (event: 'view', version: RecipeVersionKey): void
  (event: 'save', version: RecipeVersionKey): void
  (event: 'favorite'): void
}>()

const activeVersion = ref<RecipeVersionKey>('novice')
const currentVersion = computed(() => props.versions?.[activeVersion.value] || null)

watch(
  () => props.versions,
  (versions) => {
    if (!versions) activeVersion.value = 'novice'
  },
)
</script>

<template>
  <article class="recipe-summary-card">
    <div class="recipe-card-top">
      <div class="recipe-emoji">🍳</div>
      <div class="recipe-title-wrap">
        <span class="recipe-kicker">选好的做法</span>
        <h3>{{ summary.title }}</h3>
      </div>
      <div class="recipe-top-actions">
        <span class="recipe-ready">可以开做</span>
        <button
          type="button"
          class="recipe-favorite"
          :class="{ active: favorite }"
          :disabled="favoriting"
          @click="emit('favorite')"
        >
          {{ favorite ? '⭐ 已收藏' : '☆ 收藏' }}
        </button>
      </div>
    </div>

    <div class="recipe-meta">
      <span>⏱ {{ summary.time }}</span>
      <span>难度 · {{ summary.difficulty }}</span>
    </div>

    <div class="recipe-block">
      <span class="recipe-label">主要食材</span>
      <div class="recipe-ingredients">
        <span v-for="item in summary.main_ingredients" :key="item">{{ item }}</span>
      </div>
    </div>

    <div v-if="summary.safety" class="recipe-safety">
      <span>⚠️</span>
      <p>{{ summary.safety }}</p>
    </div>

    <div v-if="versions" class="recipe-version-block">
      <div class="version-tabs">
        <button
          type="button"
          :class="{ active: activeVersion === 'novice' }"
          @click="activeVersion = 'novice'"
        >
          新手版
        </button>
        <button
          type="button"
          :class="{ active: activeVersion === 'chef' }"
          @click="activeVersion = 'chef'"
        >
          大厨版
        </button>
        <span class="version-count">{{ currentVersion?.steps.length || 0 }} 步</span>
      </div>
      <div v-if="currentVersion?.steps.length" class="version-preview">
        <div v-for="(step, index) in currentVersion.steps.slice(0, 3)" :key="index" class="version-step">
          <span>{{ index + 1 }}</span>
          <p>{{ step.replace(/^\d+[.、]\s*/, '') }}</p>
        </div>
        <p v-if="currentVersion.steps.length > 3" class="version-more">
          还有 {{ currentVersion.steps.length - 3 }} 步，点「查看详细步骤」继续
        </p>
      </div>
    </div>

    <footer class="recipe-card-footer">
      <el-button type="primary" round @click="emit('view', activeVersion)">查看详细步骤</el-button>
      <el-button
        plain
        type="success"
        :loading="saving"
        @click="emit('save', activeVersion)"
      >
        {{ saved ? '更新食谱版本' : '📅 加入食谱规划' }}
      </el-button>
      <el-tag v-if="saved" size="small" type="success" effect="plain">已加入</el-tag>
    </footer>
  </article>
</template>

<style scoped>
.recipe-summary-card {
  margin-top: 12px;
  border: 1px solid #dce8e1;
  border-radius: 16px;
  background: linear-gradient(180deg, #fbfdfb 0%, #ffffff 55%);
  box-shadow: 0 10px 28px rgba(31, 90, 71, 0.08);
  overflow: hidden;
}

.recipe-card-top {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px 10px;
}

.recipe-emoji {
  flex: none;
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: #e8f5ee;
  font-size: 26px;
}

.recipe-title-wrap {
  min-width: 0;
}

.recipe-kicker {
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: #5d8a77;
}

.recipe-title-wrap h3 {
  margin: 2px 0 0;
  font-size: 19px;
  line-height: 1.3;
  color: #183c30;
}

.recipe-top-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.recipe-favorite {
  border: 1px solid #f0dca8;
  background: #fffaf0;
  color: #a97812;
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.recipe-favorite.active {
  background: #fff4cf;
  border-color: #e8c96d;
}

.recipe-favorite:disabled {
  opacity: 0.6;
  cursor: wait;
}

.recipe-ready {
  margin-left: auto;
  flex: none;
  font-size: 10.5px;
  color: #1f7a5f;
  background: #e8f5ee;
  border-radius: 999px;
  padding: 3px 8px;
}

.recipe-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0 18px 12px;
  color: #6f857c;
  font-size: 12px;
}

.recipe-meta span {
  background: #f4f8f6;
  border-radius: 999px;
  padding: 3px 9px;
}

.recipe-block {
  padding: 0 18px 12px;
}

.recipe-label {
  display: block;
  margin-bottom: 6px;
  font-size: 11px;
  color: #7b9188;
}

.recipe-ingredients {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.recipe-ingredients span {
  padding: 4px 9px;
  border-radius: 999px;
  border: 1px solid #e2ece7;
  background: #fff;
  color: #355c4c;
  font-size: 12px;
}

.recipe-safety {
  display: flex;
  gap: 8px;
  margin: 0 18px 14px;
  padding: 9px 11px;
  border-radius: 10px;
  background: #fdf8ef;
  border: 1px solid #f1dfc3;
  color: #865c16;
  font-size: 12px;
  line-height: 1.65;
}

.recipe-safety p {
  margin: 0;
}

.recipe-version-block {
  margin: 0 18px 12px;
  padding-top: 10px;
  border-top: 1px solid #edf3ef;
}

.version-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
}

.version-tabs button {
  border: 0;
  background: transparent;
  padding: 4px 10px;
  border-radius: 999px;
  color: #7a9187;
  font-size: 12px;
  cursor: pointer;
}

.version-tabs button.active {
  color: #1f7a5f;
  background: #e8f5ee;
  font-weight: 700;
}

.version-count {
  margin-left: auto;
  color: #9aaca3;
  font-size: 10.5px;
}

.version-preview {
  display: grid;
  gap: 5px;
}

.version-step {
  display: flex;
  gap: 7px;
  align-items: flex-start;
}

.version-step > span {
  flex: none;
  width: 19px;
  height: 19px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: #f1f7f3;
  color: #4e7d68;
  font-size: 10px;
  font-weight: 700;
}

.version-step p {
  margin: 0;
  color: #62796e;
  font-size: 11.5px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.version-more {
  margin: 3px 0 0;
  color: #98aaa1;
  font-size: 10.5px;
}

.recipe-card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px 18px;
  border-top: 1px solid #edf3ef;
  background: rgba(248, 251, 249, 0.8);
}

@media (max-width: 480px) {
  .recipe-title-wrap h3 {
    font-size: 17px;
  }

  .recipe-top-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.recipe-favorite {
  border: 1px solid #f0dca8;
  background: #fffaf0;
  color: #a97812;
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.recipe-favorite.active {
  background: #fff4cf;
  border-color: #e8c96d;
}

.recipe-favorite:disabled {
  opacity: 0.6;
  cursor: wait;
}

.recipe-ready {
    display: none;
  }
}
</style>
