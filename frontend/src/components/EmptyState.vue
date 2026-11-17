<script setup lang="ts">
defineProps<{
  icon?: string
  title: string
  description?: string
  actionText?: string
}>()

defineEmits<{ (e: 'action'): void }>()
</script>

<template>
  <div class="empty">
    <el-icon class="empty-icon"><component :is="icon || 'Files'" /></el-icon>
    <h4>{{ title }}</h4>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <el-button v-if="actionText" type="primary" plain class="empty-action" @click="$emit('action')">
      {{ actionText }}
    </el-button>
  </div>
</template>

<style scoped>
.empty h4 {
  font-size: 15px;
  margin-bottom: 4px;
}

.empty-desc {
  font-size: 13px;
  color: var(--muted);
  max-width: 420px;
  margin: 0 auto;
  line-height: 1.7;
}

.empty-action {
  margin-top: 14px;
}
</style>
