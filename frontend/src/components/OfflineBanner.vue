<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const visible = ref(false)

onMounted(() => {
  visible.value = !navigator.onLine
  window.addEventListener('online', () => (visible.value = false))
  window.addEventListener('offline', () => (visible.value = true))
})

onBeforeUnmount(() => {
  visible.value = false
})
</script>

<template>
  <transition name="slide-down">
    <div v-if="visible || !app.online" class="offline-banner" role="status">
      <el-icon><WarningFilled /></el-icon>
      <span>当前网络已断开：无法上传图片或查看分析结果。图片和记录保存在服务器，联网后可继续。</span>
    </div>
  </transition>
</template>

<style scoped>
.offline-banner {
  position: sticky;
  top: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  background: #fff5e5;
  color: #8a5a06;
  border-bottom: 1px solid #f3e0bd;
  font-size: 13px;
  line-height: 1.5;
}

.slide-down-enter-active,
.slide-down-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.slide-down-enter-from,
.slide-down-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
