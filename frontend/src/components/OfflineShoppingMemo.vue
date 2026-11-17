<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

interface MemoItem {
  id: string
  name: string
  detail: string
}

const props = defineProps<{
  modelValue: boolean
  items: MemoItem[]
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
}>()

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const checkedIds = ref<string[]>([])

watch(
  () => [props.modelValue, props.items] as const,
  ([visible]) => {
    if (visible) checkedIds.value = []
  },
  { deep: true },
)

const doneCount = computed(() => props.items.filter((item) => checkedIds.value.includes(item.id)).length)
const progress = computed(() => {
  if (!props.items.length) return 0
  return Math.round((doneCount.value / props.items.length) * 100)
})

function toggle(id: string) {
  if (checkedIds.value.includes(id)) {
    checkedIds.value = checkedIds.value.filter((value) => value !== id)
  } else {
    checkedIds.value = [...checkedIds.value, id]
  }
}

function memoText(): string {
  return props.items
    .map((item) => `${checkedIds.value.includes(item.id) ? '☑' : '☐'} ${item.name} ${item.detail}`)
    .join('\n')
}

async function copyText() {
  const text = memoText()
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
  ElMessage.success('线下采购清单已复制')
}

function openMap() {
  // 演示模式：不调用真实地图 SDK，也不离开当前弹窗。
  ElMessage.success('已模拟唤起地图：搜索附近的超市、生鲜店')
}
</script>

<template>
  <el-dialog
    v-model="open"
    title="线下采购备忘录"
    width="min(94vw, 520px)"
    append-to-body
    class="offline-memo-dialog"
  >
    <div class="memo-hero">
      <div class="memo-emoji">🏪</div>
      <div>
        <span class="memo-kicker">OFFLINE SHOPPING</span>
        <h3>附近超市 · 边走边买</h3>
        <p>看到一样勾一样，买完再回来线上补。</p>
      </div>
    </div>

    <div class="memo-progress">
      <div class="memo-progress-head">
        <span>采购进度</span>
        <strong>{{ doneCount }} / {{ items.length }}</strong>
      </div>
      <el-progress :percentage="progress" :show-text="false" :stroke-width="7" color="#2f9b78" />
    </div>

    <div v-if="items.length" class="memo-list">
      <div v-for="item in items" :key="item.id" class="memo-row" :class="{ done: checkedIds.includes(item.id) }">
        <el-checkbox
          :model-value="checkedIds.includes(item.id)"
          @update:model-value="toggle(item.id)"
        />
        <div class="memo-main">
          <strong>{{ item.name }}</strong>
          <span>{{ item.detail }}</span>
        </div>
        <span class="memo-state">{{ checkedIds.includes(item.id) ? '已买' : '待买' }}</span>
      </div>
    </div>
    <p v-else class="memo-empty">当前没有需要线下采购的食材。</p>

    <p class="memo-note">这是线下采购备忘录，勾选不会扣库存，也不会触发线上结算。</p>

    <template #footer>
      <el-button text @click="openMap">🗺️ 唤起地图导航（模拟）</el-button>
      <el-button @click="open = false">关闭</el-button>
      <el-button type="primary" @click="copyText">复制清单文本</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.offline-memo-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}

.memo-hero {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 13px 14px;
  border-radius: 12px;
  background: linear-gradient(135deg, #f0f7f2, #fbf8ef);
  border: 1px solid #e1eee6;
}

.memo-emoji {
  flex: none;
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 13px;
  background: #fff;
  font-size: 27px;
  box-shadow: 0 4px 12px rgba(37, 91, 67, 0.08);
}

.memo-kicker {
  font-size: 9.5px;
  letter-spacing: 0.12em;
  color: #7b9b8d;
}

.memo-hero h3 {
  margin: 2px 0 3px;
  font-size: 17px;
  color: #1f3e31;
}

.memo-hero p {
  margin: 0;
  font-size: 11.5px;
  color: #728a7e;
}

.memo-progress {
  margin: 14px 2px 10px;
}

.memo-progress-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
  color: #6e8579;
  font-size: 11.5px;
}

.memo-progress-head strong {
  color: #2f7a60;
  font-size: 12.5px;
}

.memo-list {
  display: grid;
  gap: 7px;
  max-height: 42vh;
  overflow: auto;
  padding-right: 2px;
}

.memo-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: #fff;
  transition: background 0.15s, border-color 0.15s;
}

.memo-row.done {
  background: #f5faf7;
  border-color: #d8ebe0;
}

.memo-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.memo-main strong {
  font-size: 13px;
  color: #263f33;
}

.memo-row.done .memo-main strong {
  color: #8ba296;
  text-decoration: line-through;
}

.memo-main span {
  font-size: 10.5px;
  color: #8b9f95;
  line-height: 1.5;
}

.memo-state {
  margin-left: auto;
  flex: none;
  font-size: 10px;
  color: #8da196;
  background: #f5f8f6;
  border-radius: 999px;
  padding: 2px 7px;
}

.memo-row.done .memo-state {
  color: #2f7a60;
  background: #e7f4ec;
}

.memo-empty {
  margin: 20px 0;
  color: var(--muted);
  text-align: center;
}

.memo-note {
  margin: 12px 0 0;
  color: #93a49b;
  font-size: 11px;
  line-height: 1.6;
}
</style>
