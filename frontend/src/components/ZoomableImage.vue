<script setup lang="ts">
import { ref } from 'vue'

/**
 * 可放大的图片：点击后打开 Element Plus 图片查看器，
 * 支持滚轮/按钮缩放（最高 8 倍）、拖拽平移、旋转，方便看清配料表小字。
 */
withDefaults(
  defineProps<{
    src: string
    alt?: string
    maxHeight?: string
    rounded?: boolean
    hint?: string
  }>(),
  { alt: '图片', maxHeight: '320px', rounded: false, hint: '点击放大' }
)

const visible = ref(false)
</script>

<template>
  <div class="zoomable" :class="{ rounded }" @click="visible = true">
    <img :src="src" :alt="alt" :style="{ maxHeight }" />
    <button type="button" class="zoom-tip" @click.stop="visible = true">
      <el-icon><ZoomIn /></el-icon>
      {{ hint }}
    </button>
  </div>

  <el-image-viewer
    v-if="visible"
    :url-list="[src]"
    :initial-index="0"
    :hide-on-click-modal="true"
    :z-index="4000"
    :zoom-rate="1.4"
    :min-scale="0.2"
    :max-scale="8"
    teleported
    @close="visible = false"
  />
</template>

<style scoped>
.zoomable {
  position: relative;
  width: 100%;
  background: var(--surface-2);
  border-radius: 10px;
  overflow: hidden;
  cursor: zoom-in;
  display: grid;
  place-items: center;
}

.zoomable.rounded {
  border-radius: 14px;
}

.zoomable img {
  display: block;
  width: 100%;
  object-fit: contain;
}

.zoom-tip {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: rgba(20, 34, 30, 0.72);
  color: #fff;
  font-size: 12px;
  padding: 5px 10px;
  border-radius: 999px;
  cursor: pointer;
  backdrop-filter: blur(4px);
}

.zoom-tip:active {
  background: rgba(20, 34, 30, 0.9);
}
</style>
