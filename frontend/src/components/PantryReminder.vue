<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElNotification } from 'element-plus'
import { feedbackApi, pantryApi } from '@/api'
import { API_BASE, getToken } from '@/api/client'
import type { PantryReminder } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const data = ref<PantryReminder | null>(null)
const loading = ref(false)
const connected = ref(false)
const lastSignature = ref('')
const feedbackUnread = ref(0)

let controller: AbortController | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

const count = computed(() => (data.value ? data.value.counts.expiring + data.value.counts.expired : 0))
const items = computed(() => [...(data.value?.expired || []), ...(data.value?.expiring || [])].slice(0, 8))

function goPantry() {
  router.push({ name: 'pantry' })
}

function goFeedback() {
  router.push({ name: 'settings', query: { feedback: 'mine' } })
}

function notify(result: PantryReminder) {
  if (!result.counts.expiring && !result.counts.expired) return
  const signature = [
    result.counts.expired,
    result.counts.expiring,
    ...(result.urgent || []).map((item) => item.id),
  ].join('-')
  if (signature === lastSignature.value) return
  lastSignature.value = signature
  const today = new Date().toISOString().slice(0, 10)
  const key = `fsai_pantry_reminder_${today}_${signature}`
  if (sessionStorage.getItem(key)) return
  sessionStorage.setItem(key, '1')
  ElNotification({
    title: '食安卫士 · 食材临期提醒',
    message: result.message + ((result.urgent || []).length ? ' 可点击铃铛生成临期拯救食谱。' : ''),
    type: result.counts.expired ? 'warning' : 'info',
    duration: 9000,
    offset: 70,
    onClick: goPantry,
  })
}

function handleReminder(result: PantryReminder, withNotify = true) {
  data.value = result
  window.dispatchEvent(new CustomEvent('pantry:reminder', { detail: result }))
  if (withNotify) notify(result)
}

async function loadFeedbackUnread() {
  if (!auth.isAuthenticated) {
    feedbackUnread.value = 0
    return
  }
  try {
    const data = await feedbackApi.mine()
    let readIds: number[] = []
    try {
      readIds = JSON.parse(
        localStorage.getItem('fsai_feedback_read_ids') || '[]',
      ) as number[]
    } catch {
      readIds = []
    }
    feedbackUnread.value = (data.items || []).filter(
      (item) =>
        item.status === 'resolved' &&
        Boolean((item.reply || item.reply_content || '').trim()) &&
        !readIds.includes(item.id),
    ).length
  } catch {
    feedbackUnread.value = 0
  }
}

function handleFeedbackRead(event: Event) {
  const detail = (event as CustomEvent<{ unread?: number }>).detail
  feedbackUnread.value = Math.max(0, Number(detail?.unread || 0))
}

async function load(withNotify = true) {
  if (!auth.isAuthenticated) {
    data.value = null
    feedbackUnread.value = 0
    return
  }
  loading.value = true
  try {
    handleReminder(await pantryApi.reminders(), withNotify)
    await loadFeedbackUnread()
  } catch {
    /* 提醒失败不影响主流程 */
  } finally {
    loading.value = false
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    if (auth.isAuthenticated) load(true)
  }, 60000)
}

function disconnect() {
  controller?.abort()
  controller = null
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  connected.value = false
}

async function connect() {
  if (!auth.isAuthenticated) return
  disconnect()
  controller = new AbortController()
  try {
    const response = await fetch(`${API_BASE}/pantry/stream`, {
      headers: { Authorization: `Bearer ${getToken()}` },
      signal: controller.signal,
    })
    if (!response.ok || !response.body) {
      await load()
      return
    }
    connected.value = true
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let index = buffer.indexOf('\n\n')
      while (index >= 0) {
        const chunk = buffer.slice(0, index)
        buffer = buffer.slice(index + 2)
        const line = chunk.split('\n').find((item) => item.startsWith('data:'))
        if (line) {
          try {
            handleReminder(JSON.parse(line.slice(5).trim()) as PantryReminder)
          } catch {
            /* 忽略坏事件 */
          }
        }
        index = buffer.indexOf('\n\n')
      }
    }
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === 'AbortError'
    if (!aborted) {
      await load()
    }
  } finally {
    connected.value = false
    if (controller && !controller.signal.aborted) {
      reconnectTimer = setTimeout(connect, 5000)
    }
  }
}

function syncTransport() {
  if (!auth.isAuthenticated) {
    disconnect()
    stopPolling()
    data.value = null
    return
  }
  if (route.name === 'pantry') {
    stopPolling()
    connect()
  } else {
    disconnect()
    startPolling()
  }
}

watch(() => auth.token, () => { lastSignature.value = ''; syncTransport() })
watch(() => route.name, () => syncTransport())

onMounted(() => {
  window.addEventListener('feedback:read', handleFeedbackRead)
  if (auth.isAuthenticated) {
    load(true)
    syncTransport()
  }
})

onUnmounted(() => {
  window.removeEventListener('feedback:read', handleFeedbackRead)
  disconnect()
  stopPolling()
})
</script>

<template>
  <el-popover v-if="auth.isAuthenticated" placement="bottom-end" :width="300" trigger="click" @show="load(false)">
    <template #reference>
      <button
        type="button"
        class="pantry-bell"
        :aria-label="feedbackUnread ? '您的反馈有新回复' : '食材临期提醒'"
        :title="feedbackUnread ? '您的反馈有新回复' : '食材临期提醒'"
      >
        <el-badge :value="count" :hidden="count === 0" :max="99">
          <el-icon><Bell /></el-icon>
        </el-badge>
        <span v-if="feedbackUnread" class="feedback-dot" />
      </button>
    </template>
    <div class="pantry-popover">
      <div class="popover-head">
        <strong>食材临期提醒</strong>
        <span class="stream-state" :class="{ live: connected }">{{ connected ? '实时' : '轮询' }}</span>
        <el-button text size="small" :loading="loading" @click="load(false)">刷新</el-button>
      </div>
      <button
        v-if="feedbackUnread"
        type="button"
        class="feedback-notice"
        @click="goFeedback"
      >
        <span>您的反馈有新回复</span>
        <strong>{{ feedbackUnread }} 条</strong>
      </button>
      <p v-if="!count" class="popover-empty">没有过期或临期食材。</p>
      <template v-else>
        <p class="popover-message">{{ data?.message }}</p>
        <ul class="popover-list">
          <li v-for="item in items" :key="item.id">
            <span>{{ item.name }}</span>
            <span class="popover-status" :class="item.status">{{ item.status_text }}</span>
          </li>
        </ul>
        <el-button type="primary" size="small" class="popover-btn" @click="goPantry">去食材管家处理</el-button>
      </template>
    </div>
  </el-popover>
</template>

<style scoped>
.pantry-bell {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-2);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  cursor: pointer;
}

.pantry-bell:hover {
  background: var(--surface-2);
}

.pantry-popover {
  font-size: 12.5px;
}

.stream-state {
  font-size: 10px;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0 6px;
}

.stream-state.live {
  color: #1d8a5c;
  border-color: #9ed3ba;
}

.popover-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.popover-message {
  margin: 0 0 8px;
  color: var(--muted);
  line-height: 1.6;
}

.popover-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 5px;
}

.popover-list li {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--border);
}

.popover-status {
  color: var(--muted);
  flex-shrink: 0;
}

.popover-status.expired {
  color: var(--danger);
}

.popover-status.expiring {
  color: var(--warn);
}

.popover-empty {
  margin: 0;
  color: var(--muted);
}

.popover-btn {
  width: 100%;
  margin-top: 10px;
}

.pantry-bell {
  position: relative;
}

.feedback-dot {
  position: absolute;
  top: 6px;
  right: 5px;
  width: 7px;
  height: 7px;
  border: 1.5px solid #fff;
  border-radius: 50%;
  background: #e05252;
}

.feedback-notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 8px;
  padding: 8px 10px;
  border: 1px solid #f0c9c5;
  border-radius: 8px;
  background: #fff6f4;
  color: #b34a40;
  font-family: inherit;
  font-size: 11.5px;
  text-align: left;
  cursor: pointer;
}

.feedback-notice strong {
  font-size: 11px;
}

</style>
