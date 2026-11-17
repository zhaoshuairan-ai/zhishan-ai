<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '@/api/client'

interface CaptchaPayload {
  captcha_id: string
  image: string
  question: string
  expires_in: number
}

const props = defineProps<{ disabled?: boolean }>()
const code = defineModel<string>({ default: '' })
const captchaId = defineModel<string>('captchaId', { default: '' })

const image = ref('')
const question = ref('')
const loading = ref(false)
const errorMessage = ref('')

async function refresh() {
  loading.value = true
  errorMessage.value = ''
  code.value = ''
  try {
    const data = await api.get<CaptchaPayload>('/captcha')
    image.value = data.image
    question.value = data.question
    captchaId.value = data.captcha_id
  } catch {
    image.value = ''
    errorMessage.value = '验证码加载失败，点击重试'
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

defineExpose({ refresh })
</script>

<template>
  <div class="captcha-field">
    <div class="captcha-input">
      <el-input
        v-model="code"
        :disabled="disabled"
        maxlength="4"
        placeholder="计算结果"
        inputmode="numeric"
        autocomplete="off"
        aria-label="验证码计算结果"
      />
    </div>
    <button
      type="button"
      class="captcha-image"
      :disabled="loading || disabled"
      title="点击刷新验证码"
      aria-label="刷新验证码"
      @click.prevent.stop="refresh"
    >
      <img v-if="image" :src="image" :alt="`验证码：${question}`" />
      <span v-else class="captcha-placeholder">{{ errorMessage || '加载中…' }}</span>
      <el-icon class="refresh-icon"><Refresh /></el-icon>
    </button>
  </div>
</template>

<style scoped>
.captcha-field {
  display: flex;
  gap: 8px;
  width: 100%;
  align-items: stretch;
}

.captcha-input {
  flex: 1;
  min-width: 0;
}

.captcha-image {
  position: relative;
  width: 132px;
  height: 40px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #f2f8f6;
  cursor: pointer;
  overflow: hidden;
  flex-shrink: 0;
}

.captcha-image img {
  width: 100%;
  height: 100%;
  display: block;
}

.captcha-placeholder {
  font-size: 11px;
  color: var(--muted);
}

.refresh-icon {
  pointer-events: none;
  position: absolute;
  right: 3px;
  bottom: 2px;
  font-size: 11px;
  color: #7aa79d;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 50%;
  padding: 1px;
}

.captcha-image:disabled {
  opacity: 0.7;
  cursor: default;
}
</style>
