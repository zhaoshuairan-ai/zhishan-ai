<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { assistantApi } from '@/api'
import { ApiError } from '@/api/client'

type ChatBubble = {
  id: number
  role: 'user' | 'assistant'
  content: string
}

const route = useRoute()
const router = useRouter()
const rootRef = ref<HTMLElement | null>(null)
const open = ref(false)
const modalHidden = ref(false)
const question = ref('')
const asking = ref(false)
const error = ref('')
const thread = ref<ChatBubble[]>([])
const sessionId = ref<number | null>(null)
const threadRef = ref<HTMLElement | null>(null)
const context = ref<Record<string, unknown> | null>(null)
let ignoreDocumentClick = false
let bubbleSeed = 0

const raised = computed(() => route.name === 'health-profile')
const position = ref<{ x: number; y: number } | null>(null)
const positionStyle = computed(() =>
  position.value
    ? {
        left: `${position.value.x}px`,
        top: `${position.value.y}px`,
        right: 'auto',
        bottom: 'auto',
      }
    : undefined,
)
const popoverLeft = computed(() => (position.value ? position.value.x < 380 : false))
const popoverBelow = computed(() => (position.value ? position.value.y < 400 : false))

let drag: {
  pointerId: number
  startX: number
  startY: number
  originX: number
  originY: number
  width: number
  height: number
  moved: boolean
} | null = null
let suppressClick = false

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  const element = event.currentTarget as HTMLElement
  const rect = element.getBoundingClientRect()
  position.value = { x: rect.left, y: rect.top }
  drag = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: rect.left,
    originY: rect.top,
    width: rect.width,
    height: rect.height,
    moved: false,
  }
  element.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', onPointerMove, { passive: false })
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

function onPointerMove(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  const dx = event.clientX - drag.startX
  const dy = event.clientY - drag.startY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) drag.moved = true
  position.value = {
    x: clamp(drag.originX + dx, 8, window.innerWidth - drag.width - 8),
    y: clamp(drag.originY + dy, 8, window.innerHeight - drag.height - 8),
  }
  event.preventDefault()
}

function onPointerUp() {
  if (!drag) return
  const moved = drag.moved
  drag = null
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
  if (moved) {
    suppressClick = true
    window.setTimeout(() => {
      suppressClick = false
    }, 250)
  }
}

function onFabClick() {
  if (suppressClick) {
    suppressClick = false
    return
  }
  toggleOpen()
}

function onWindowResize() {
  if (!position.value || !rootRef.value) return
  const rect = rootRef.value.getBoundingClientRect()
  position.value = {
    x: clamp(position.value.x, 8, window.innerWidth - rect.width - 8),
    y: clamp(position.value.y, 8, window.innerHeight - rect.height - 8),
  }
}

function nextBubbleId() {
  bubbleSeed += 1
  return bubbleSeed
}

async function scrollThread() {
  await nextTick()
  if (threadRef.value) {
    threadRef.value.scrollTop = threadRef.value.scrollHeight
  }
}

async function toggleOpen() {
  open.value = !open.value
  if (open.value) {
    await nextTick()
    await scrollThread()
  }
}

async function ask() {
  const text = question.value.trim()
  if (!text || asking.value) return

  error.value = ''
  thread.value.push({ id: nextBubbleId(), role: 'user', content: text })
  question.value = ''
  asking.value = true
  await scrollThread()

  try {
    const data = await assistantApi.ask(
      text,
      sessionId.value,
      context.value,
      null,
    )
    sessionId.value = data.session_id
    thread.value.push({
      id: nextBubbleId(),
      role: 'assistant',
      content: data.answer,
    })
    await scrollThread()
  } catch (err) {
    error.value = (err as ApiError).message || '提问失败，请稍后重试'
    await scrollThread()
  } finally {
    asking.value = false
  }
}

function resetChat() {
  thread.value = []
  sessionId.value = null
  question.value = ''
  error.value = ''
  context.value = null
}

type ExternalAskDetail = {
  question?: string
  context?: Record<string, unknown> | null
}

function onExternalAsk(event: Event) {
  const detail = (event as CustomEvent<ExternalAskDetail>).detail || {}

  // 卡片按钮触发的打开事件会继续冒泡到 document，先忽略这一次外部点击
  ignoreDocumentClick = true
  window.setTimeout(() => {
    ignoreDocumentClick = false
  }, 0)

  resetChat()
  question.value = String(detail.question || '')
  context.value = detail.context || null
  open.value = true
  void nextTick().then(scrollThread)
}

function openAssistant() {
  open.value = false
  router.push({ name: 'assistant' })
}

function onDocumentClick(event: MouseEvent) {
  if (ignoreDocumentClick) return
  if (!open.value) return
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) {
    open.value = false
  }
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

function onModalToggle(event: Event) {
  const detail = (event as CustomEvent<{ open?: boolean }>).detail
  modalHidden.value = Boolean(detail?.open)
  if (modalHidden.value) open.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
  window.addEventListener('resize', onWindowResize)
  window.addEventListener('fsai:modal', onModalToggle)
  window.addEventListener('fsai:ask', onExternalAsk)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('fsai:modal', onModalToggle)
  window.removeEventListener('fsai:ask', onExternalAsk)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
})
</script>

<template>
  <div
    v-show="!modalHidden"
    ref="rootRef"
    class="ai-launcher fixed bottom-8 right-8 z-50"
    :class="{ 'is-raised': raised, 'is-open': open, 'is-left': popoverLeft, 'is-below': popoverBelow }"
    :style="positionStyle"
  >
    <Transition name="ai-pop">
      <section
        v-if="open"
        class="ai-popover"
        role="dialog"
        aria-modal="false"
        aria-label="问问智膳 AI"
      >
        <header class="ai-popover-head">
          <div class="ai-popover-head-main">
            <span class="ai-popover-mark">AI</span>
            <div>
              <strong>问问智膳 AI</strong>
              <p>食品安全、配料解读、营养建议，直接问。</p>
            </div>
          </div>
          <button
            type="button"
            class="ai-popover-close"
            aria-label="关闭快捷提问"
            @click="open = false"
          >
            ×
          </button>
        </header>

        <div class="ai-popover-body">
          <div
            v-if="thread.length || asking"
            ref="threadRef"
            class="ai-chat-thread"
          >
            <div
              v-for="bubble in thread"
              :key="bubble.id"
              class="ai-chat-row"
              :class="bubble.role"
            >
              <span v-if="bubble.role === 'assistant'" class="ai-chat-avatar">AI</span>
              <div class="ai-chat-bubble">{{ bubble.content }}</div>
            </div>

            <div v-if="asking" class="ai-chat-row assistant">
              <span class="ai-chat-avatar">AI</span>
              <div class="ai-chat-bubble ai-chat-typing">
                <i /><i /><i />
                <span>正在检索知识库…</span>
              </div>
            </div>
          </div>

          <div v-else class="ai-mini-empty">
            <span class="ai-mini-empty-icon">✦</span>
            <strong>有什么想确认的？</strong>
            <p>问配料、问营养、问忌口，智膳 AI 会带着来源回答你。</p>
          </div>

          <div class="ai-dialog-input">
            <el-input
              v-model="question"
              type="textarea"
              :rows="2"
              maxlength="200"
              show-word-limit
              resize="none"
              placeholder="例如：隔夜菜到底能不能吃？"
              @keydown.ctrl.enter.prevent="ask"
            />

            <div class="ai-dialog-actions">
              <span>Ctrl + Enter 快速提问</span>
              <div class="ai-dialog-action-buttons">
                <el-button
                  v-if="thread.length"
                  text
                  class="ai-dialog-reset"
                  @click="resetChat"
                >
                  新对话
                </el-button>
                <el-button
                  type="primary"
                  class="ai-dialog-submit"
                  :loading="asking"
                  :disabled="!question.trim()"
                  @click="ask"
                >
                  提问
                </el-button>
              </div>
            </div>
          </div>

          <div v-if="error" class="ai-dialog-error">{{ error }}</div>

          <el-button
            v-if="thread.length"
            text
            class="ai-open-full"
            @click="openAssistant"
          >
            打开完整对话 →
          </el-button>
        </div>
      </section>
    </Transition>

    <button
      v-show="!open"
      type="button"
      class="ai-launcher-fab"
      :class="{ 'is-open': open }"
      :aria-expanded="open"
      aria-label="打开智膳 AI 快捷提问"
      title="问问智膳 AI"
      @pointerdown="onPointerDown"
      @click="onFabClick"
    >
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 2.8 14.1 9l6.2 2.1-6.2 2.1L12 19.4l-2.1-6.2L3.7 11.1 9.9 9 12 2.8Z"
          fill="currentColor"
        />
        <path
          d="M18.5 16.5 19.4 19l2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9.9-2.5Z"
          fill="currentColor"
          opacity="0.72"
        />
      </svg>
      <span class="ai-launcher-label">AI</span>
    </button>
  </div>
</template>

<style scoped>
.ai-launcher {
  position: fixed;
  right: 32px;
  bottom: 32px;
  z-index: 50;
}

.ai-launcher.is-raised {
  bottom: 104px;
}

.ai-launcher-fab {
  position: relative;
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: linear-gradient(135deg, #12a08b, #0b6558);
  color: #ffffff;
  cursor: grab;
  touch-action: none;
  user-select: none;
  box-shadow:
    0 12px 28px rgba(11, 101, 88, 0.3),
    0 0 0 6px rgba(18, 160, 139, 0.08);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.ai-launcher-fab:active {
  cursor: grabbing;
}

.ai-launcher-fab::before {
  position: absolute;
  inset: -7px;
  border: 2px solid rgba(18, 160, 139, 0.38);
  border-radius: 50%;
  content: '';
  pointer-events: none;
  animation: ai-fab-breathe 2.6s ease-out infinite;
}

.ai-launcher-fab:hover,
.ai-launcher-fab.is-open {
  transform: translateY(-3px) scale(1.03);
  box-shadow:
    0 18px 34px rgba(11, 101, 88, 0.34),
    0 0 0 8px rgba(18, 160, 139, 0.1);
}

.ai-launcher-fab svg {
  width: 24px;
  height: 24px;
}

.ai-launcher-label {
  position: absolute;
  right: -2px;
  bottom: -1px;
  padding: 2px 5px;
  border: 2px solid #ffffff;
  border-radius: 999px;
  background: #0f6b52;
  color: #ffffff;
  font-size: 8px;
  font-weight: 800;
  line-height: 1.2;
  letter-spacing: 0.02em;
}

@keyframes ai-fab-breathe {
  0% {
    opacity: 0.72;
    transform: scale(0.88);
  }
  70% {
    opacity: 0;
    transform: scale(1.28);
  }
  100% {
    opacity: 0;
    transform: scale(1.28);
  }
}

.ai-popover {
  position: absolute;
  right: 0;
  bottom: calc(100% + 16px);
  display: flex;
  width: min(380px, calc(100vw - 32px));
  max-height: min(620px, calc(100vh - 140px));
  flex-direction: column;
  border: 1px solid #e3eee8;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 20px 48px rgba(23, 55, 44, 0.18);
}

.ai-popover::after {
  position: absolute;
  right: 21px;
  bottom: -7px;
  width: 14px;
  height: 14px;
  border-right: 1px solid #e3eee8;
  border-bottom: 1px solid #e3eee8;
  border-radius: 0 0 2px 0;
  background: #ffffff;
  content: '';
  transform: rotate(45deg);
}

.ai-launcher.is-left .ai-popover {
  right: auto;
  left: 0;
}

.ai-launcher.is-left .ai-popover::after {
  right: auto;
  left: 21px;
}

.ai-launcher.is-below .ai-popover {
  top: calc(100% + 16px);
  bottom: auto;
}

.ai-launcher.is-below .ai-popover::after {
  top: -7px;
  bottom: auto;
  border-top: 1px solid #e3eee8;
  border-right: 0;
  border-bottom: 0;
  border-left: 1px solid #e3eee8;
  border-radius: 2px 0 0 0;
}

.ai-popover-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex: 0 0 auto;
  padding: 14px 16px 12px;
  border-bottom: 1px solid #eef4f0;
}

.ai-popover-head-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-popover-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  border-radius: 10px;
  background: #eaf5ef;
  color: #0f6b52;
  font-size: 12px;
  font-weight: 800;
}

.ai-popover-head strong {
  display: block;
  color: #203a2e;
  font-size: 15px;
}

.ai-popover-head p {
  margin: 2px 0 0;
  color: #8a9e93;
  font-size: 11px;
  line-height: 1.5;
}

.ai-popover-close {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #9aaba2;
  font-size: 19px;
  line-height: 1;
  cursor: pointer;
}

.ai-popover-close:hover {
  background: #f3f8f5;
  color: #315b49;
}

.ai-popover-body {
  display: grid;
  gap: 11px;
  min-height: 0;
  padding: 12px 16px 15px;
  overflow-y: auto;
}

.ai-chat-thread {
  display: flex;
  max-height: 300px;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  padding: 1px 2px 1px;
}

.ai-chat-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.ai-chat-row.user {
  justify-content: flex-end;
}

.ai-chat-avatar {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  border-radius: 8px;
  background: #0f6b52;
  color: #ffffff;
  font-size: 8px;
  font-weight: 800;
}

.ai-chat-bubble {
  max-width: 82%;
  padding: 9px 12px;
  border-radius: 12px;
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.ai-chat-row.user .ai-chat-bubble {
  border-bottom-right-radius: 4px;
  background: #0f6b52;
  color: #ffffff;
}

.ai-chat-row.assistant .ai-chat-bubble {
  border: 1px solid #e3eee8;
  border-top-left-radius: 4px;
  background: #f7fbf9;
  color: #4b6359;
}

.ai-chat-typing {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #7b9188;
  font-size: 11.5px;
}

.ai-chat-typing i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #91b7a7;
  animation: ai-typing-dot 1.2s ease-in-out infinite;
}

.ai-chat-typing i:nth-child(2) {
  animation-delay: 0.15s;
}

.ai-chat-typing i:nth-child(3) {
  animation-delay: 0.3s;
}

.ai-chat-typing span {
  margin-left: 4px;
}

@keyframes ai-typing-dot {
  0%,
  60%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

.ai-mini-empty {
  padding: 17px 14px;
  border: 1px dashed #dce9e2;
  border-radius: 12px;
  background: #f8fcfa;
  text-align: center;
}

.ai-mini-empty-icon {
  display: block;
  margin-bottom: 5px;
  color: #1f7a5f;
  font-size: 20px;
}

.ai-mini-empty strong {
  color: #315b49;
  font-size: 13px;
}

.ai-mini-empty p {
  margin: 4px 0 0;
  color: #8a9e93;
  font-size: 11.5px;
  line-height: 1.6;
}

.ai-dialog-input {
  display: grid;
  gap: 8px;
}

.ai-dialog-input :deep(.el-textarea__inner) {
  padding: 10px 12px;
  border: 1px solid #dce8e2;
  border-radius: 12px;
  box-shadow: 0 3px 10px rgba(31, 61, 50, 0.04);
}

.ai-dialog-input :deep(.el-textarea__inner:focus) {
  border-color: #91c6b1;
  box-shadow: 0 0 0 3px rgba(15, 123, 108, 0.1);
}

.ai-dialog-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #9aaba2;
  font-size: 10.5px;
}

.ai-dialog-action-buttons {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ai-dialog-reset {
  padding: 0 4px;
  color: #8a9e93;
  font-size: 11px;
}

.ai-dialog-submit {
  border: 0 !important;
  border-radius: 10px !important;
  background: #0f6b52 !important;
  color: #ffffff !important;
  font-weight: 700;
}

.ai-dialog-error {
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff1f0;
  color: #c14936;
  font-size: 12px;
}

.ai-open-full {
  justify-self: flex-start;
  padding: 0;
  color: #1f7a5f;
}

.ai-pop-enter-active,
.ai-pop-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.ai-pop-enter-from,
.ai-pop-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.98);
}

@media (max-width: 767px) {
  .ai-launcher {
    right: 16px;
    bottom: calc(var(--tabbar-h, 60px) + 24px);
  }

  .ai-launcher.is-raised {
    bottom: calc(var(--tabbar-h, 60px) + 96px);
  }

  .ai-launcher-fab {
    width: 52px;
    height: 52px;
  }

  .ai-popover {
    width: calc(100vw - 32px);
    max-height: min(560px, calc(100vh - 160px));
  }

  .ai-chat-bubble {
    max-width: 86%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ai-launcher-fab::before,
  .ai-chat-typing i {
    animation: none;
  }
}
</style>
