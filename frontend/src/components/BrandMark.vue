<script setup lang="ts">
import { useId } from 'vue'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })

// 页面里可能有多个 BrandMark；打印时重复的 gradient id 会让 Logo 变透明
const gradientId = `zhishan-brand-grad-${useId().replace(/:/g, '')}`
</script>

<template>
  <div class="brand" :class="{ compact }">
    <div class="mark">
      <svg viewBox="0 0 24 24" width="100%" height="100%" aria-hidden="true">
        <defs>
          <linearGradient :id="gradientId" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#12a08b" />
            <stop offset="100%" stop-color="#0b6558" />
          </linearGradient>
        </defs>
        <rect
          width="24"
          height="24"
          rx="7"
          :fill="`url(#${gradientId})`"
        />
        <g
          fill="none"
          stroke="#ffffff"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2" />
          <path d="M7 2v20" />
          <path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Z" />
          <path d="M21 15v7" />
        </g>
      </svg>
    </div>
    <div v-if="!compact" class="brand-text">
      <div class="brand-name">智膳 <span>AI</span></div>
      <div class="brand-sub">AI 全场景健康膳食管家</div>
    </div>
    <div v-else class="brand-text">
      <div class="brand-name">智膳 AI</div>
      <div class="brand-sub">AI 全场景健康膳食管家</div>
    </div>
  </div>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.mark {
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 6px 14px rgba(11, 101, 88, 0.24);
}

.compact .mark {
  width: 34px;
  height: 34px;
  border-radius: 10px;
}

.brand-text {
  min-width: 0;
}

.brand-name {
  font-size: 17px;
  font-weight: 750;
  letter-spacing: 0.2px;
  color: var(--brand-700);
  line-height: 1.25;
  white-space: nowrap;
}

.brand-name span {
  font-size: 12px;
  font-weight: 700;
  color: var(--brand);
  background: var(--brand-100);
  padding: 1px 5px;
  border-radius: 6px;
  vertical-align: 2px;
  margin-left: 2px;
}

.brand-sub {
  font-size: 11.5px;
  color: #9aa8a1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.compact .brand-name {
  font-size: 15px;
}

.compact .brand-sub {
  font-size: 10.5px;
}
<
/* 打印时给 Logo 一个实色兜底，避免 SVG gradient 在部分浏览器打印引擎中丢失 */
@media print {
  .brand .mark {
    background: #0f7b6c !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .brand,
  .brand .mark,
  .brand svg {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
  }
}
</style>
