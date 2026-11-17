<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  label: string
  value: number | string
  unit?: string
  hint?: string
  icon?: string
  tone?: 'brand' | 'ok' | 'warn' | 'danger' | 'info'
  loading?: boolean
  clickable?: boolean
}>()

const toneClass = computed(() => `tone-${props.tone || 'brand'}`)
</script>

<template>
  <div class="stat-card" :class="[toneClass, { clickable }]">
    <div class="stat-top">
      <span class="stat-label">{{ label }}</span>
      <el-icon v-if="icon" class="stat-icon"><component :is="icon" /></el-icon>
    </div>
    <div class="stat-value">
      <span v-if="!loading">{{ value }}</span>
      <span v-else class="stat-skeleton" />
      <span v-if="unit && !loading" class="stat-unit">{{ unit }}</span>
    </div>
    <div v-if="hint" class="stat-hint">{{ hint }}</div>
  </div>
</template>

<style scoped>
.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 15px 16px;
  box-shadow: var(--shadow);
  position: relative;
  overflow: hidden;
  min-width: 0;
}

.stat-card::after {
  content: '';
  position: absolute;
  right: -18px;
  top: -18px;
  width: 62px;
  height: 62px;
  border-radius: 50%;
  opacity: 0.12;
  background: var(--brand);
}

.tone-ok::after {
  background: var(--ok);
}

.tone-warn::after {
  background: var(--accent);
}

.tone-danger::after {
  background: var(--danger);
}

.tone-info::after {
  background: var(--info);
}

.stat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.stat-label {
  font-size: 13px;
  color: var(--muted);
}

.stat-icon {
  color: var(--brand);
  font-size: 16px;
  opacity: 0.85;
}

.stat-value {
  margin-top: 6px;
  font-size: 27px;
  font-weight: 720;
  letter-spacing: -0.4px;
  color: var(--text);
  display: flex;
  align-items: baseline;
  gap: 3px;
  line-height: 1.2;
}

.stat-unit {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--muted);
}

.stat-hint {
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.45;
}

.stat-skeleton {
  display: inline-block;
  width: 42px;
  height: 26px;
  border-radius: 6px;
  background: #eef2f0;
}

.clickable {
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.clickable:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-hover);
}

@media (max-width: 560px) {
  .stat-card {
    padding: 12px 13px;
  }
  .stat-value {
    font-size: 23px;
  }
  .stat-label {
    font-size: 12px;
  }
}
</style>
