<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { pantryApi } from '@/api'
import { ApiError } from '@/api/client'
import type { PantryParseItem } from '@/api/types'

const emit = defineEmits<{ imported: []; close: [] }>()

const dialogOpen = ref(false)
const mode = ref<'receipt' | 'voice'>('receipt')
const busy = ref(false)
const progress = ref(0)
const busyText = ref('')
const errorMessage = ref('')
const warnings = ref<string[]>([])
const draft = ref<PantryParseItem[]>([])
const rawText = ref('')
const sourceMode = ref('')

const voiceText = ref('')
const listening = ref(false)
const speechSupported = ref(false)
const recognitionRef = ref<any>(null)
const fileInput = ref<HTMLInputElement | null>(null)


const today = () => new Date().toISOString().slice(0, 10)

const title = computed(() => {
  if (mode.value === 'receipt') return '拍照 / 小票录入'
  return '语音录入'
})

function resetVoiceState() {
  stopListening()
  voiceText.value = ''
  draft.value = []
  rawText.value = ''
  warnings.value = []
  errorMessage.value = ''
  sourceMode.value = ''
  progress.value = 0
  busyText.value = ''
}

function open(next: 'receipt' | 'voice' = 'receipt') {
  // 每次打开都从全新状态开始，避免上一次语音/解析结果残留
  resetVoiceState()

  mode.value = next
  dialogOpen.value = true

  if (next === 'voice') setupSpeech()
}

function close() {
  stopListening()
  resetVoiceState()
  dialogOpen.value = false
  emit('close')
}

function setupSpeech() {
  const w = window as any
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition
  speechSupported.value = Boolean(Ctor)
  if (!Ctor) return
  const recognition = new Ctor()
  recognition.lang = 'zh-CN'
  recognition.continuous = false
  recognition.interimResults = false
  recognition.onresult = (event: any) => {
    const text = event.results?.[0]?.[0]?.transcript || ''
    if (text) voiceText.value = text
  }
  recognition.onend = () => {
    listening.value = false
  }
  recognition.onerror = () => {
    listening.value = false
    ElMessage.warning('语音识别失败，可以改用文字输入')
  }
  recognitionRef.value = recognition
}

function startListening() {
  if (!recognitionRef.value) {
    ElMessage.info('当前浏览器不支持语音识别，请直接输入文字')
    return
  }
  listening.value = true
  try {
    recognitionRef.value.start()
  } catch {
    listening.value = false
  }
}

function stopListening() {
  listening.value = false
  try {
    recognitionRef.value?.abort?.()
  } catch {
    /* ignore */
  }
}

function applyParsed(data: Awaited<ReturnType<typeof pantryApi.importText>>) {
  draft.value = data.items
  warnings.value = data.warnings || []
  sourceMode.value = data.mode
  if (data.ocr?.raw_text) rawText.value = data.ocr.raw_text
}

function onFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file) return
  uploadReceipt(file)
}

async function compressImage(file: File): Promise<File> {
  // 手机原图往往 5–10MB，先缩到 1800px 再上传，显著缩短 OCR 等待时间
  if (!file.type.startsWith('image/') || file.size < 1.2 * 1024 * 1024) return file
  try {
    const bitmap = await createImageBitmap(file)
    const maxEdge = 1800
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const context = canvas.getContext('2d')
    if (!context) return file
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.84))
    if (!blob) return file
    return new File([blob], 'receipt.jpg', { type: 'image/jpeg' })
  } catch {
    return file
  }
}

async function uploadReceipt(file: File) {
  busy.value = true
  progress.value = 0
  busyText.value = '正在上传小票…'
  errorMessage.value = ''
  try {
    const prepared = await compressImage(file)
    busyText.value = '正在上传小票…'
    const data = await pantryApi.importReceipt(prepared, (value) => {
      progress.value = value
      if (value >= 100) busyText.value = '上传完成，正在识别文字…'
    })
    applyParsed(data)
    busyText.value = ''
    if (data.ocr?.is_demo) {
      warnings.value = [...warnings.value, '当前使用演示 OCR 文本，识别结果仅用于流程演示。']
    }
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '小票识别失败，请换一张更清晰的照片'
  } finally {
    busy.value = false
    busyText.value = ''
  }
}

async function parseVoice() {
  if (!voiceText.value.trim()) {
    ElMessage.info('请先说话或输入一句话')
    return
  }
  busy.value = true
  errorMessage.value = ''
  try {
    const data = await pantryApi.importText(voiceText.value.trim(), 'voice')
    applyParsed(data)
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '解析失败'
  } finally {
    busy.value = false
  }
}

function addDaysFrom(value: string | null | undefined, days: number): string {
  const base = value ? new Date(`${value}T00:00:00`) : new Date()
  const date = new Date(base.getTime())
  date.setDate(date.getDate() + days)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function setDraftExpiry(item: PantryParseItem, days: number) {
  item.expires_at = addDaysFrom(item.purchased_at, days)
}

function isSuggestedExpiry(item: PantryParseItem, days: number): boolean {
  return item.expires_at === addDaysFrom(item.purchased_at, days)
}

function confidenceClass(item: PantryParseItem): string {
  if (!item.shelf_life_days) return 'unknown'
  if (item.shelf_life_confidence >= 80) return 'high'
  if (item.shelf_life_confidence >= 60) return 'medium'
  return 'low'
}

function removeDraft(index: number) {
  draft.value.splice(index, 1)
}

async function confirmImport() {
  if (!draft.value.length) {
    ElMessage.info('待导入列表为空')
    return
  }
  busy.value = true
  errorMessage.value = ''
  try {
    const items = draft.value.map((item) => ({
      name: item.name,
      category: item.category || 'other',
      quantity: item.quantity,
      unit: item.unit,
      purchased_at: item.purchased_at,
      expires_at: item.expires_at,
      note: item.note,
    }))
    const result = await pantryApi.batch(items)
    ElMessage.success(`已导入 ${result.count} 项食材`)

    // 导入成功后彻底清空，下一次打开不会带出旧语音和旧预览
    resetVoiceState()
    dialogOpen.value = false
    emit('imported')
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '导入失败'
  } finally {
    busy.value = false
  }
}

async function handleFileClick() {
  await nextTick()
  fileInput.value?.click()
}

defineExpose({ open })
</script>

<template>
  <el-dialog v-model="dialogOpen" :title="title" width="min(96vw, 760px)" @close="close">
    <el-tabs v-model="mode">
      <el-tab-pane label="小票 / 拍照" name="receipt">
        <div class="drop-zone" @click="handleFileClick">
          <el-icon><Camera /></el-icon>
          <p>{{ busy ? busyText || "正在处理，请稍候…" : "拍一张超市小票或商品包装照片" }}</p>
          <span>自动识别名称与数量，并按内置常识表估算保质期；导入前可逐项确认。</span>
          <el-button type="primary" :loading="busy" @click.stop="handleFileClick">{{ busy ? busyText || "正在处理…" : "选择 / 拍摄图片" }}</el-button>
          <input ref="fileInput" type="file" accept="image/*" capture="environment" hidden @click.stop @change="onFile" />
        </div>
        <el-progress v-if="progress > 0 && progress < 100" :percentage="progress" class="mt" />
      </el-tab-pane>

      <el-tab-pane label="语音" name="voice">
        <div class="voice-box">
          <el-button :type="listening ? 'danger' : 'primary'" round @click="listening ? stopListening() : startListening()">
            <el-icon><Microphone /></el-icon>
            {{ listening ? '正在听，点击停止' : '按住/点击说话' }}
          </el-button>
          <p class="hint">
            {{ speechSupported ? '说完后会自动转成文字，也可以直接输入。' : '当前浏览器不支持语音识别，请直接输入文字。' }}
          </p>
        </div>
        <el-input
          v-model="voiceText"
          type="textarea"
          :rows="3"
          placeholder="例如：今天买了3个西红柿、2斤排骨，放冷藏"
        />
        <el-button type="primary" class="mt" :loading="busy" @click="parseVoice">解析这句话</el-button>
      </el-tab-pane>

    </el-tabs>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mt" />
    <el-alert
      v-for="(warning, index) in warnings"
      :key="index"
      :title="warning"
      type="warning"
      show-icon
      :closable="false"
      class="mt"
    />

    <div v-if="draft.length" class="draft-block">
      <div class="draft-head">
        <strong>待导入 {{ draft.length }} 项</strong>
        <span v-if="sourceMode" class="hint">解析方式：{{ sourceMode === 'ai' ? '大模型' : '规则' }}</span>
      </div>
      <div class="draft-list">
        <div v-for="(item, index) in draft" :key="`${item.name}-${index}`" class="draft-item">
          <div class="draft-row">
            <el-input v-model="item.name" placeholder="名称" />
            <el-input v-model.number="item.quantity" type="number" min="0.1" step="0.1" class="qty" />
            <el-input v-model="item.unit" placeholder="单位" class="unit" />
            <el-button text type="danger" @click="removeDraft(index)">移除</el-button>
          </div>
          <div class="estimate-line">
            <span
              class="estimate-badge"
              :class="confidenceClass(item)"
              :title="item.shelf_life_basis || item.shelf_life_note || item.note"
            >
              {{
                item.shelf_life_days
                  ? `AI智能估算：${item.shelf_life_days}天（置信度 ${item.shelf_life_confidence}%）`
                  : '未估算：请手动选择到期日'
              }}
            </span>
            <span v-if="item.shelf_life_days" class="estimate-storage">{{ item.storage }}</span>
            <button
              v-for="day in item.shelf_life_alternatives"
              :key="day"
              type="button"
              class="estimate-chip"
              :class="{ active: isSuggestedExpiry(item, day) }"
              @click="setDraftExpiry(item, day)"
            >
              {{ day }}天
            </button>
            <label class="custom-date">
              自定义
              <input v-model="item.expires_at" type="date" />
            </label>
          </div>
        </div>
      </div>
      <p class="hint">
        保质期是规则表估算值，不是包装标注；可点快捷天数或「自定义」修改，未估算的食材必须手动选择。
      </p>
    </div>

    <details v-if="rawText" class="raw-block">
      <summary>查看 OCR 原始文本</summary>
      <pre>{{ rawText }}</pre>
    </details>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :disabled="!draft.length" :loading="busy" @click="confirmImport">
        确认导入 {{ draft.length ? `（${draft.length} 项）` : '' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.drop-zone {
  border: 1px dashed var(--border);
  border-radius: 12px;
  padding: 24px 16px;
  text-align: center;
  cursor: pointer;
  background: var(--surface-2);
}

.drop-zone .el-icon {
  font-size: 30px;
  color: var(--brand-700);
}

.drop-zone p {
  margin: 8px 0 4px;
  font-weight: 600;
  font-size: 14px;
}

.drop-zone span {
  display: block;
  color: var(--muted);
  font-size: 11.5px;
  line-height: 1.8;
  margin-bottom: 10px;
}

.voice-box {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.hint {
  margin: 0;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}

.mt {
  margin-top: 10px;
}

.draft-block {
  margin-top: 14px;
  border-top: 1px solid var(--border);
  padding-top: 10px;
}

.draft-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.draft-list {
  display: grid;
  gap: 6px;
  max-height: 300px;
  overflow: auto;
}

.draft-item {
  border-bottom: 1px dashed var(--border);
  padding: 6px 0;
}

.draft-row {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) 76px 72px auto;
  gap: 6px;
  align-items: center;
}

.draft-row .qty,
.draft-row .unit {
  width: 100%;
}

.estimate-line {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 5px;
  font-size: 11px;
}

.estimate-badge {
  border-radius: 999px;
  padding: 1px 8px;
  background: var(--surface-2);
  color: var(--muted);
}

.estimate-badge.high {
  color: #1d7a4f;
  background: #e8f5ee;
}

.estimate-badge.medium {
  color: #8a5a0a;
  background: #fdf3e2;
}

.estimate-badge.low,
.estimate-badge.unknown {
  color: #a33b2b;
  background: #fcebe8;
}

.estimate-storage {
  color: var(--muted);
}

.estimate-chip {
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text-2);
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 11px;
  cursor: pointer;
}

.estimate-chip.active,
.estimate-chip:hover {
  border-color: var(--brand);
  color: var(--brand-700);
}

.custom-date {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
  font-size: 11px;
}

.custom-date input {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px 5px;
  background: var(--card);
  color: var(--text-2);
  font-size: 11px;
  max-width: 125px;
}

.raw-block {
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--muted);
}

.raw-block pre {
  margin: 6px 0 0;
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  background: var(--surface-2);
  border-radius: 6px;
  padding: 8px;
}

@media (max-width: 767px) {
  .draft-row {
    grid-template-columns: 1fr 1fr;
  }

  .draft-row .el-button {
    justify-self: start;
  }
}
</style>
