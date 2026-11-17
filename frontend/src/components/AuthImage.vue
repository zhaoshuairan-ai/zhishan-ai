<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { api } from '@/api/client'

/**
 * 需要登录才能访问的图片：
 * 通过带 Authorization 头的请求取回二进制，再转成 objectURL 显示，
 * 避免把登录令牌拼进 URL（防止令牌出现在浏览记录/Referer 中）。
 */
const props = defineProps<{
  src: string
  alt?: string
  ratio?: string
  rounded?: boolean
}>()

const objectUrl = ref('')
const loading = ref(false)
const error = ref('')
const previewVisible = ref(false)

let currentUrl = ''

async function load() {
  if (!props.src) return
  loading.value = true
  error.value = ''
  try {
    const blob = await api.blob(props.src)
    if (currentUrl) URL.revokeObjectURL(currentUrl)
    currentUrl = URL.createObjectURL(blob)
    objectUrl.value = currentUrl
  } catch (err) {
    error.value = (err as Error).message || '图片加载失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.src,
  () => load(),
  { immediate: true }
)

onBeforeUnmount(() => {
  if (currentUrl) URL.revokeObjectURL(currentUrl)
})
</script>

<template>
  <div class="auth-image" :style="{ aspectRatio: ratio || '4 / 3' }" :class="{ rounded }">
    <div v-if="loading" class="state">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>图片加载中…</span>
    </div>
    <div v-else-if="error" class="state error">
      <el-icon><PictureRounded /></el-icon>
      <span>{{ error }}</span>
    </div>
    <template v-else>
      <img :src="objectUrl" :alt="alt || '食品标签照片'" class="image" @click="previewVisible = true" />
      <button type="button" class="zoom-btn" @click="previewVisible = true">
        <el-icon><ZoomIn /></el-icon>
        查看大图
      </button>
    </template>
  </div>

  <el-image-viewer
    v-if="previewVisible"
    :url-list="[objectUrl]"
    :initial-index="0"
    :hide-on-click-modal="true"
    :z-index="4000"
    :zoom-rate="1.4"
    :min-scale="0.2"
    :max-scale="8"
    teleported
    @close="previewVisible = false"
  />
</template>

<style scoped>
.auth-image {
  position: relative;
  width: 100%;
  background: #f3f6f5;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  display: grid;
  place-items: center;
}

.auth-image.rounded {
  border-radius: 16px;
}

.image {
  width: 100%;
  height: 100%;
  object-fit: contain; /* 保持比例，不拉伸 */
  cursor: zoom-in;
  display: block;
  background: var(--surface-2);
}

.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 13px;
  padding: 14px;
  text-align: center;
}

.state.error {
  color: var(--danger);
}

.zoom-btn {
  position: absolute;
  right: 10px;
  bottom: 10px;
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

.preview-wrap {
  max-height: 72vh;
  overflow: auto;
  display: grid;
  place-items: center;
}

.preview-wrap img {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
}

.preview-tip {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--muted);
  text-align: center;
}
</style>