<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { assistantApi } from '@/api'
import { ApiError } from '@/api/client'
import type { AssistantAnswer } from '@/api/types'

interface KnowledgeAiItem {
  id?: number
  title: string
  category: string
  category_label?: string
  summary?: string
  source_name?: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const props = defineProps<{
  modelValue: boolean
  item: KnowledgeAiItem | null
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const messages = ref<ChatMessage[]>([])
const question = ref('')
const sending = ref(false)
const sessionId = ref<number | null>(null)
const messagesEl = ref<HTMLElement | null>(null)

function buildQuestion(item: KnowledgeAiItem): string {
  const name = item.title

  switch (item.category) {
    case 'dish':
    case 'ingredient':
      return `请帮我分析一下【${name}】的营养价值、热量，并结合我的健康画像看看适不适合我吃？`
    case 'additive':
      return `请帮我评估一下【${name}】这个添加剂安全吗？吃了有什么潜在风险？`
    case 'nutrition':
      return `请用通俗易懂的大白话帮我解释一下什么是【${name}】？在日常生活中我该怎么看这个指标？`
    case 'safety':
      return `请帮我详细科普一下关于【${name}】的食品安全知识。`
    default:
      return `请帮我解读一下【${name}】的科学含义，并结合日常饮食给我一些建议。`
  }
}

function resetConversation() {
  messages.value = []
  sessionId.value = null
  question.value = props.item ? buildQuestion(props.item) : ''
}

function closeDrawer() {
  visible.value = false
}

async function scrollToBottom() {
  await nextTick()
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

async function send() {
  const text = question.value.trim()
  if (!text || sending.value || !props.item) return

  const item = props.item
  messages.value.push({ role: 'user', content: text })
  question.value = ''
  sending.value = true
  await scrollToBottom()

  try {
    const context = {
      context_type: 'knowledge',
      entry_id: item.id ?? null,
      title: item.title,
      name: item.title,
      category: item.category,
      category_label: item.category_label || '',
      summary: item.summary || '',
      source: item.source_name || '',
    }

    // 标准 POST Body：question / session_id / context 全部放在 body 中
    const answer: AssistantAnswer = await assistantApi.ask(
      text,
      sessionId.value,
      context,
      null,
    )

    sessionId.value = answer.session_id
    const content =
      answer.answer?.trim() ||
      answer.evidence?.trim() ||
      'AI 暂时没有生成有效回答，请换一种问法再试一次。'

    messages.value.push({ role: 'assistant', content })
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0
    const message =
      status === 401
        ? '登录后即可使用 AI 解读，登录状态不会影响当前浏览位置。'
        : (error as ApiError).message || '请求失败，请稍后重试'

    messages.value.push({
      role: 'assistant',
      content: message,
    })
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) resetConversation()
  },
  { immediate: true },
)

watch(
  () => props.item,
  () => {
    if (props.modelValue) resetConversation()
  },
)
</script>

<template>
  <el-drawer
    v-model="visible"
    direction="rtl"
    :size="'min(520px, 96vw)'"
    :with-header="false"
    class="knowledge-ai-drawer"
  >
    <div class="kai-shell">
      <header class="kai-head">
        <div class="kai-head-copy">
          <span class="kai-eyebrow">智膳智库 · AI 营养师</span>
          <strong>{{ item?.title || 'AI 解读' }}</strong>
          <small v-if="item?.category_label">
            {{ item.category_label }}
          </small>
        </div>
        <button
          type="button"
          class="kai-close"
          aria-label="关闭 AI 解读"
          title="关闭"
          @click="closeDrawer"
        >
          ×
        </button>
      </header>

      <div ref="messagesEl" class="kai-messages">
        <div v-if="!messages.length" class="kai-empty">
          <div class="kai-empty-icon" aria-hidden="true">🌿</div>
          <p>已根据这条知识准备好问题。</p>
          <p class="kai-empty-hint">
            可以直接发送，也可以修改成你更关心的问题。
          </p>
        </div>

        <div
          v-for="(message, index) in messages"
          :key="index"
          class="kai-message"
          :class="`is-${message.role}`"
        >
          <span class="kai-role">{{ message.role === 'user' ? '你' : 'AI' }}</span>
          <div class="kai-bubble">{{ message.content }}</div>
        </div>

        <div v-if="sending" class="kai-message is-assistant">
          <span class="kai-role">AI</span>
          <div class="kai-bubble kai-typing">
            <i></i><i></i><i></i>
          </div>
        </div>
      </div>

      <form class="kai-composer" @submit.prevent="send">
        <el-input
          v-model="question"
          type="textarea"
          :rows="3"
          resize="none"
          maxlength="500"
          placeholder="输入你的问题，AI 营养师在线解答…"
          @keydown.enter.exact.prevent="send"
        />
        <div class="kai-composer-foot">
          <span>Enter 发送 · Shift + Enter 换行</span>
          <el-button
            type="primary"
            native-type="submit"
            :loading="sending"
            :disabled="!question.trim()"
          >
            发送
          </el-button>
        </div>
      </form>
    </div>
  </el-drawer>
</template>

<style scoped>
.kai-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  color: #173b2e;
}

.kai-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 2px 14px;
  border-bottom: 1px solid #e3eee8;
}

.kai-head-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.kai-eyebrow {
  color: #2d8061;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.kai-head-copy strong {
  overflow: hidden;
  color: #123c2d;
  font-size: 17px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kai-head-copy small {
  color: #7b9489;
  font-size: 11.5px;
}

.kai-close {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: #f1f7f3;
  color: #4c6e5e;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.kai-close:hover {
  background: #e3efe8;
  color: #1c5b43;
}

.kai-messages {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 2px;
}

.kai-empty {
  margin: auto;
  padding: 24px 12px;
  color: #668174;
  text-align: center;
}

.kai-empty-icon {
  margin-bottom: 8px;
  font-size: 30px;
}

.kai-empty p {
  margin: 4px 0;
  font-size: 13px;
}

.kai-empty-hint {
  color: #95a99f;
  font-size: 11.5px !important;
}

.kai-message {
  display: flex;
  flex-direction: column;
  gap: 5px;
  max-width: 92%;
}

.kai-message.is-user {
  align-self: flex-end;
  align-items: flex-end;
}

.kai-message.is-assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.kai-role {
  color: #94a99e;
  font-size: 10.5px;
  font-weight: 700;
}

.kai-bubble {
  padding: 10px 13px;
  border-radius: 14px;
  background: #f3f8f5;
  color: #274a3b;
  font-size: 13px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.kai-message.is-user .kai-bubble {
  border-bottom-right-radius: 4px;
  background: #0f6b52;
  color: #fff;
}

.kai-message.is-assistant .kai-bubble {
  border: 1px solid #e2eee7;
  border-bottom-left-radius: 4px;
  background: #fff;
}

.kai-typing {
  display: flex;
  gap: 4px;
  align-items: center;
  min-height: 38px;
}

.kai-typing i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #74a48d;
  animation: kai-blink 1.2s infinite ease-in-out;
}

.kai-typing i:nth-child(2) {
  animation-delay: 0.15s;
}

.kai-typing i:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes kai-blink {
  0%,
  80%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

.kai-composer {
  padding-top: 12px;
  border-top: 1px solid #e3eee8;
}

.kai-composer-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 8px;
}

.kai-composer-foot span {
  color: #94a99e;
  font-size: 10.5px;
}

@media (max-width: 767px) {
  .kai-messages {
    padding-top: 12px;
  }

  .kai-composer-foot span {
    display: none;
  }

  .kai-composer-foot {
    justify-content: flex-end;
  }
}
</style>
