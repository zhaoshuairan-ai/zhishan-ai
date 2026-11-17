<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import { pantryApi, pipelineApi, recordApi } from '@/api'
import {
  API_BASE,
  AUTH_EXPIRED_EVENT,
  ApiError,
  clearSession,
  getToken,
} from '@/api/client'
import type {
  AnalyzeUploadResult,
  DishAnalysisInfo,
  HealthProfile,
  OcrRunResult,
  RecordDetail,
  RecordSummary,
} from '@/api/types'
import AuthImage from '@/components/AuthImage.vue'
import ZoomableImage from '@/components/ZoomableImage.vue'
import PlateIcon from '@/components/PlateIcon.vue'
import { useAppStore } from '@/stores/app'
import { parseNutritionPreview } from '@/utils/nutrition'
import { useDietLog } from '@/composables/useDietLog'

type Step = 'upload' | 'recognizing' | 'correct' | 'analyzing' | 'dish-result'
type Tone = 'ok' | 'warn' | 'muted'

const route = useRoute()
const router = useRouter()
const app = useAppStore()

const step = ref<Step>('upload')
const uploadState = ref<'empty' | 'selected' | 'analyzing'>('empty')
const recordId = ref<number | null>(null)
const record = ref<RecordSummary | null>(null)
const file = ref<File | null>(null)
const previewUrl = ref('')
const uploadProgress = ref(0)
const ocrResult = ref<OcrRunResult | null>(null)
const errorMessage = ref('')
const ocrError = ref('')
const elapsed = ref(0)
const analyzingStage = ref('正在拆分配料表…')
const submitting = ref(false)
const showRawText = ref(false)
const reOcrLoading = ref(false)
/** 网络中断导致的上传/识别/分析失败：提示用户联网后可继续 */
const networkIssue = ref(false)
const pipelineLoadingOpen = ref(false)
const healthProfile = ref<HealthProfile | null>(null)
type AnalysisType = 'package' | 'dish'

const analysisType = ref<AnalysisType>('package')

const dishResult = ref<DishAnalysisInfo | null>(null)
const dishStreamText = ref('')
const dishStreaming = ref(false)
const dishStreamError = ref('')
let dishStreamAbort: AbortController | null = null
const { addDish } = useDietLog()

const ANALYZE_CACHE_KEY = 'fsai_analyze_dish_cache_v1'

type AnalyzeCache = {
  version: 1
  step: 'dish-result'
  stepIndex: 3
  analysisType: 'dish'
  recordId: number
  record: RecordSummary | null
  dishResult: DishAnalysisInfo
  dishStreamText: string
  updatedAt: number
}

function clearAnalyzeCache() {
  try {
    localStorage.removeItem(ANALYZE_CACHE_KEY)
  } catch {
    /* localStorage 不可用时忽略缓存清理 */
  }
}

function saveAnalyzeCache() {
  if (step.value !== 'dish-result' || !dishResult.value) return
  const recordIdValue = Number(recordId.value)
  if (!recordIdValue) return

  const cache: AnalyzeCache = {
    version: 1,
    step: 'dish-result',
    stepIndex: 3,
    analysisType: 'dish',
    recordId: recordIdValue,
    record: record.value,
    dishResult: dishResult.value,
    dishStreamText: dishStreamText.value,
    updatedAt: Date.now(),
  }

  try {
    localStorage.setItem(ANALYZE_CACHE_KEY, JSON.stringify(cache))
  } catch {
    /* 缓存失败不影响当前分析结果展示 */
  }
}

function restoreAnalyzeCache(): boolean {
  let raw = ''
  try {
    raw = localStorage.getItem(ANALYZE_CACHE_KEY) || ''
  } catch {
    return false
  }
  if (!raw) return false

  try {
    const cache = JSON.parse(raw) as Partial<AnalyzeCache>
    if (
      cache.version !== 1 ||
      cache.step !== 'dish-result' ||
      cache.analysisType !== 'dish' ||
      !cache.dishResult ||
      typeof cache.dishResult.dish_name !== 'string'
    ) {
      clearAnalyzeCache()
      return false
    }

    const cachedRecordId = Number(cache.recordId)
    if (!cachedRecordId) {
      clearAnalyzeCache()
      return false
    }

    analysisType.value = 'dish'
    recordId.value = cachedRecordId
    savedRecordId.value = cachedRecordId
    record.value = cache.record || null
    dishResult.value = cache.dishResult
    dishStreamText.value = cache.dishStreamText || ''
    dishStreaming.value = false
    dishStreamError.value = ''
    uploadState.value = 'empty'
    errorMessage.value = ''
    ocrError.value = ''
    resetForm()
    file.value = null
    setPreview(null)
    step.value = 'dish-result'
    return true
  } catch {
    clearAnalyzeCache()
    return false
  }
}

watch(
  [step, dishResult, dishStreamText],
  () => {
    saveAnalyzeCache()
  },
  { flush: 'post' },
)

const ANALYSIS_MODES: Record<
  AnalysisType,
  {
    label: string
    emoji: string
    title: string
    hint: string
    thinking: string
    tips: Array<{ icon: string; title: string; desc: string }>
  }
> = {
  package: {
    label: '识包装',
    emoji: '📦',
    title: '开启 AI 食品透视',
    hint: '请上传清晰的包装背面标签',
    thinking: '从包装标签中提取配料、添加剂与营养信息。',
    tips: [
      { icon: '🎯', title: '正面对象', desc: '标签正对镜头，文字清晰' },
      { icon: '☀️', title: '避开反光', desc: '侧一点拍，减少反光' },
      { icon: '🧩', title: '分区拍摄', desc: '配料、营养表分开拍' },
    ],
  },
  dish: {
    label: '识饭菜',
    emoji: '🍱',
    title: '开启 AI 膳食分析',
    hint: '请上传清晰的菜品俯拍照片',
    thinking: '识别菜品与重量，查库拆解碳水、蛋白质、脂肪，再结合健康目标给出预警。',
    tips: [
      { icon: '📐', title: '俯拍全貌', desc: '菜品完整入镜' },
      { icon: '💡', title: '光线充足', desc: '避免阴影遮挡' },
      { icon: '🍚', title: '主食配菜同框', desc: '方便估算总量' },
    ],
  },
}

const modeMeta = computed(() => ANALYSIS_MODES[analysisType.value])

type ThinkingStep = { title: string; tag?: string; desc: string; color: string }

const THINKING_STEPS: Record<AnalysisType, ThinkingStep[]> = {
  package: [
    { title: '视觉提取', tag: '配料', desc: '精准识别配料表与添加剂', color: '#1f7a5f' },
    { title: '提取红线', tag: '国标', desc: '匹配 GB 2760 与您的健康画像', color: '#2f8d73' },
    { title: '营养测算', desc: '计算热量与宏量营养素', color: '#4a8a6d' },
    { title: '风险拦截', desc: '如：含阿斯巴甜，苯丙酮尿症患者禁忌', color: '#0b3d2e' },
  ],
  dish: [
    { title: '视觉提取', tag: '识别菜品与重量', desc: '识别主要菜名并估算可食用克数', color: '#1f7a5f' },
    { title: '营养拆解', tag: '查库算三大营养素', desc: '检索菜品营养库，换算碳水、蛋白质、脂肪', color: '#2f8d73' },
    { title: '画像匹配', tag: '结合健康目标', desc: '结合减脂、控糖、增肌等目标', color: '#4a8a6d' },
    { title: '营养素预警', tag: '脂肪占比过高', desc: '如脂肪供能占比过高，提示下一餐平衡', color: '#0b3d2e' },
  ],
}

type AnalyzeTab = 'packaging' | 'dish'

/** 模板层用 packaging / dish 命名；请求后端时仍映射为 package / dish。 */
const activeTab = computed<AnalyzeTab>({
  get: () => (analysisType.value === 'dish' ? 'dish' : 'packaging'),
  set: (tab) => selectAnalysisType(tab === 'dish' ? 'dish' : 'package'),
})

const thinkingSteps = computed(() => THINKING_STEPS[analysisType.value])

function selectAnalysisType(type: AnalysisType) {
  if (type === analysisType.value || busy.value || uploadState.value === 'analyzing') return
  analysisType.value = type
  if (uploadState.value === 'empty') return

  // 图片与识别类型不匹配时，清空当前选择，避免用包装图跑菜品分析。
  clearAnalyzeCache()
  recordId.value = null
  savedRecordId.value = null
  record.value = null
  ocrResult.value = null
  file.value = null
  setPreview(null)
  resetForm()
  uploadState.value = 'empty'
  step.value = 'upload'
  ElMessage.info('已切换识别类型，请重新上传图片')
}

const profileCapsule = computed(() => {
  const conditions = (healthProfile.value?.condition_labels || []).filter(Boolean)
  const goals = (healthProfile.value?.goal_labels || []).filter(Boolean)
  const labels = [conditions[0], goals[0], conditions[1]].filter(
    (item, index, list): item is string => Boolean(item) && list.indexOf(item) === index,
  )
  if (!labels.length) return ''
  return `✨ 已同步您的【${labels.slice(0, 2).join('/')}】画像，将进行定制化解析。`
})

const isFatLossMode = computed(
  () =>
    (healthProfile.value?.goals || []).some((goal) => ['weight_loss', 'fat_loss', '减脂', '减重'].includes(goal)) ||
    /减脂|减重|控卡/.test(healthProfile.value?.notes || ''),
)

const dishExerciseTip = computed(() => {
  if (!isFatLossMode.value || !dishResult.value) return ''
  const calories = Number(dishResult.value.totals?.calories || 0)
  if (!calories) return ''
  const minutes = Math.max(1, Math.round(calories / 10))
  return `🏃 减脂提示：消耗这道菜需慢跑约 ${minutes} 分钟`
})

const pipelineStage = ref(0)
let pipelineTimer1: number | undefined
let pipelineTimer2: number | undefined
const cameraOpen = ref(false)
const cameraLoading = ref(false)
const cameraError = ref('')
const cameraVideo = ref<HTMLVideoElement | null>(null)
let cameraStream: MediaStream | null = null

const resumeHint = computed(() =>
  app.online
    ? '网络已恢复：可以点击「保存并开始分析」重试；也可以到「历史记录」中打开该记录继续分析。'
    : '网络已中断：当前校正内容仍在这个页面里。恢复网络后可点击重试；已保存的记录可以到「历史记录」中打开并继续分析。'
)

watch(
  () => app.online,
  (online) => {
    if (online && networkIssue.value) {
      ElMessage.success('网络已恢复，可以继续操作')
    }
  }
)
const savedRecordId = ref<number | null>(null)

const form = reactive<Record<string, string>>({
  food_name: '',
  ingredients_text: '',
  nutrition_text: '',
  net_content: '',
  production_date: '',
  shelf_life: '',
  expiry_date: '',
  storage: '',
  producer: '',
  standard_no: '',
  allergen: '',
})

const currentImageSize = computed(() => imageSize.value || record.value?.image || null)
const lowResolution = computed(() => {
  const size = currentImageSize.value
  return !!size && Math.max(size.width, size.height) < MIN_RECOMMENDED_EDGE
})
/** 识别到了文字，但既没有配料表也没有营养成分表：通常说明只拍到了包装正面 */
const missingLabelSections = computed(
  () =>
    step.value === 'correct' &&
    !!ocr.value &&
    !form.ingredients_text.trim() &&
    !form.nutrition_text.trim()
)

const nutritionPreview = computed(() => {
  const parsed = parseNutritionPreview(form.nutrition_text)
  return { items: parsed.rows, basisLabel: parsed.basisLabel }
})

const fieldDefs = [
  { key: 'food_name', label: '食品名称', placeholder: '例如：原味苏打饼干', span: 1 },
  { key: 'net_content', label: '净含量', placeholder: '例如：200g', span: 1 },
  { key: 'production_date', label: '生产日期', placeholder: 'YYYY-MM-DD', span: 1 },
  { key: 'shelf_life', label: '保质期', placeholder: '例如：12个月 / 21天', span: 1 },
  { key: 'expiry_date', label: '到期日期（可选）', placeholder: '包装上直接印有到期日期时填写', span: 1 },
  { key: 'standard_no', label: '产品标准号', placeholder: '例如：GB/T 20980', span: 1 },
]

const longFieldDefs = [
  { key: 'storage', label: '贮存条件', rows: 2 },
  { key: 'producer', label: '生产者 / 制造商', rows: 2 },
  { key: 'allergen', label: '致敏物质提示', rows: 2 },
]

let timer: number | undefined

const stepIndex = computed(() => ({ upload: 0, recognizing: 1, correct: 2, analyzing: 3, 'dish-result': 3 }[step.value]))
const hasRecord = computed(() => Boolean(recordId.value))
const ocr = computed(() => ocrResult.value?.ocr || null)
const isDemoOcr = computed(() => Boolean(ocr.value?.is_demo || record.value?.is_demo))
const busy = computed(() => step.value === 'recognizing' || step.value === 'analyzing')

const canAnalyze = computed(() => Boolean(form.ingredients_text.trim() || form.nutrition_text.trim()))

const fieldState = computed<Record<string, { tone: Tone; text: string }>>(() => {
  const confidence = ocr.value?.field_confidence || {}
  const flags = ocr.value?.field_flags || {}
  const result: Record<string, { tone: Tone; text: string }> = {}
  for (const key of Object.keys(form)) {
    const value = (form[key] || '').trim()
    const conf = Number(confidence[key] ?? 0)
    const flag = flags[key]?.status
    if (!value) {
      result[key] = { tone: 'muted', text: flag === 'missing' ? '未识别，可手动填写' : '未填写' }
    } else if (flag === 'inferred') {
      result[key] = { tone: 'warn', text: '推断值，请确认' }
    } else if (conf > 0 && conf < 0.8) {
      result[key] = { tone: 'warn', text: `低置信度 ${Math.round(conf * 100)}%` }
    } else if (flag === 'format_suspect') {
      result[key] = { tone: 'warn', text: '格式待确认' }
    } else {
      result[key] = { tone: 'ok', text: conf > 0 ? `置信度 ${Math.round(conf * 100)}%` : '已填写' }
    }
  }
  return result
})

function resetForm() {
  for (const key of Object.keys(form)) form[key] = ''
}

function setPreview(fileObj: File | null) {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = fileObj ? URL.createObjectURL(fileObj) : ''
}

function startTimer() {
  elapsed.value = 0
  window.clearInterval(timer)
  timer = window.setInterval(() => {
    elapsed.value += 1
  }, 1000)
}

function stopTimer() {
  window.clearInterval(timer)
  timer = undefined
}

function isHeic(fileObj: File): boolean {
  return /heic|heif/i.test(fileObj.type) || /\.(heic|heif)$/i.test(fileObj.name)
}

function validateFile(fileObj: File): string {
  const allowed = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
  const name = fileObj.name.toLowerCase()
  const extOk = /\.(jpe?g|png|webp|heic|heif)$/.test(name)
  if (!allowed.includes(fileObj.type) && !extOk && !isHeic(fileObj)) {
    return '仅支持 JPG / JPEG / PNG / WEBP 格式的图片（iPhone 的 HEIC 会自动转换）'
  }
  if (fileObj.size > 10 * 1024 * 1024) return '图片超过 10MB，请压缩后再上传'
  if (fileObj.size < 1024) return '图片文件过小，可能已损坏'
  return ''
}

/**
 * 手机端兼容处理：
 * 1. iPhone 常拍 HEIC，直接在浏览器里解码后转成 JPEG；
 * 2. 大图等比缩到长边 2400 再上传，减少失败率与等待时间；
 * 3. 浏览器无法解码（如安卓 Chrome 遇到 HEIC）时保留原文件，由上传接口给出明确提示。
 */
async function prepareImage(fileObj: File): Promise<File> {
  const needResize = fileObj.size > 4 * 1024 * 1024
  if (!isHeic(fileObj) && !needResize) return fileObj
  try {
    const bitmap = await createImageBitmap(fileObj)
    const maxEdge = 2400
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const context = canvas.getContext('2d')
    if (!context) return fileObj
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    if (!blob) return fileObj
    const baseName = fileObj.name.replace(/\.[^.]+$/, '') || 'label'
    return new File([blob], `${baseName}.jpg`, { type: 'image/jpeg', lastModified: Date.now() })
  } catch {
    return fileObj
  }
}

const imageSize = ref<{ width: number; height: number } | null>(null)
/** 图片长边低于该值时，标签文字通常糊到无法识别 */
const MIN_RECOMMENDED_EDGE = 900

function readImageSize(fileObj: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(fileObj)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(url)
      resolve({ width: image.naturalWidth, height: image.naturalHeight })
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('无法读取图片尺寸'))
    }
    image.src = url
  })
}

async function handleFile(source: File) {
  const invalid = validateFile(source)
  if (invalid) {
    ElMessage.error(invalid)
    return
  }
  const fileObj = await prepareImage(source)
  if (isHeic(fileObj)) {
    ElMessage.error('这支浏览器无法转换 HEIC 格式：请在手机「设置 → 相机 → 格式」选择「兼容性最佳」，或先把照片导出为 JPG 再上传')
    return
  }
  try {
    imageSize.value = await readImageSize(fileObj)
  } catch {
    imageSize.value = null
  }
  if (imageSize.value && Math.max(imageSize.value.width, imageSize.value.height) < MIN_RECOMMENDED_EDGE) {
    const proceed = await ElMessageBox.confirm(
      `这张图片只有 ${imageSize.value.width}×${imageSize.value.height} 像素，标签上的小字很可能识别不出来。` +
        '建议用相机直接拍摄包装背面的配料表 / 营养成分表，或上传原图（长边建议 ≥ 1000 像素）。',
      '图片分辨率偏低',
      { confirmButtonText: '仍然上传', cancelButtonText: '重新选择', type: 'warning' }
    )
      .then(() => true)
      .catch(() => false)
    if (!proceed) {
      imageSize.value = null
      return
    }
  }
  clearAnalyzeCache()
  file.value = fileObj
  setPreview(fileObj)
  errorMessage.value = ''
  ocrError.value = ''
  ocrResult.value = null
  resetForm()
  uploadState.value = 'selected'
  step.value = 'upload'
}

function wait(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms))
}

/**
 * 读取图片为 data URL。
 * 例如：data:image/jpeg;base64,/9j/4AAQ...
 */
function readFileAsDataUrl(fileToRead: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string' && reader.result.startsWith('data:')) {
        resolve(reader.result)
      } else {
        reject(new ApiError('图片读取失败：没有得到有效的 Base64 数据', 0, 0))
      }
    }
    reader.onerror = () => {
      reject(new ApiError('图片读取失败，请重新选择图片', 0, 0))
    }
    reader.readAsDataURL(fileToRead)
  })
}

/**
 * Base64 JSON 上传：完全不经过 Axios / FormData。
 *
 * 请求体：
 * {
 *   "image_base64": "data:image/jpeg;base64,xxxxx...",
 *   "mode": "packaging" | "dish"
 * }
 *
 * Content-Type 必须是 application/json。
 * image_base64 保留 data URL 前缀，由后端负责剥离。
 */
async function uploadImageForAnalysis(
  fileToUpload: File,
  mode: 'packaging' | 'dish',
): Promise<AnalyzeUploadResult> {
  const imageBase64 = await readFileAsDataUrl(fileToUpload)

  // 本项目使用 Bearer Token 鉴权；Authorization 与 Content-Type 互不影响。
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) headers.Authorization = `Bearer ${token}`

  let response: Response
  try {
    response = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        image_base64: imageBase64,
        mode,
      }),
    })
  } catch {
    throw new ApiError('无法连接服务器：请检查网络连接，并确认后端服务已启动。', 0, 0)
  }

  let rawBody: unknown = null
  try {
    rawBody = await response.json()
  } catch {
    rawBody = null
  }

  const envelope = rawBody as
    | {
        success?: boolean
        message?: string
        code?: number
        details?: unknown
        request_id?: string
        data?: AnalyzeUploadResult
      }
    | null

  if (response.status === 401) {
    clearSession()
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
  }

  if (!response.ok || !envelope || envelope.success === false) {
    let message = envelope?.message || '上传失败，请稍后重试'
    if (response.status === 413) message = '图片过大，请压缩后重试。'
    throw new ApiError(
      message,
      response.status,
      Number(envelope?.code) || 0,
      envelope?.details,
      envelope?.request_id,
    )
  }

  // 兼容 { success, data } 包装和直接返回对象两种后端格式
  return (envelope.data ?? envelope) as AnalyzeUploadResult
}

async function startAnalysis() {
  if (!file.value || uploadState.value === 'analyzing') return
  clearAnalyzeCache()
  const startedAt = Date.now()
  uploadState.value = 'analyzing'
  errorMessage.value = ''
  ocrError.value = ''
  uploadProgress.value = 0
  step.value = 'upload'
  try {
    // Base64 JSON 单次请求：图片 + 当前模式（packaging / dish）。
    // 不使用 FormData，也不使用 Axios，彻底避开 multipart 格式冲突。
    const uploaded = await uploadImageForAnalysis(file.value, activeTab.value)
    uploadProgress.value = 100
    recordId.value = uploaded.record.id
    record.value = uploaded.record
    savedRecordId.value = uploaded.record.id

    // 识饭菜：上传请求已经完成视觉分析，直接进入结果页并消费 SSE。
    if (uploaded.mode === 'dish') {
      const dish = (uploaded.result as { dish?: DishAnalysisInfo } | undefined)?.dish || null
      if (!dish) {
        throw new ApiError('没有拿到菜品营养结果，请重试', 500)
      }
      uploadState.value = 'empty'
      dishResult.value = dish
      dishStreamText.value = ''
      dishStreamError.value = ''
      stopTimer()
      step.value = 'dish-result'
      await startDishStream(recordId.value, uploaded.stream_url)
      return
    }

    // 识包装：上传请求已完成 OCR，接下来进入文字核对，保留人工校正环节。
    if (!uploaded.ocr || !uploaded.provider) {
      throw new ApiError('图片已上传，但没有拿到文字识别结果，请重试', 500)
    }
    ocrResult.value = {
      record: uploaded.record,
      ocr: uploaded.ocr,
      fields: uploaded.fields || {},
      field_order: uploaded.field_order,
      demo_warning: uploaded.demo_warning ?? null,
      ocr_warning: uploaded.ocr_warning ?? null,
      provider: uploaded.provider,
    }
    for (const key of Object.keys(form)) {
      form[key] = (uploaded.fields?.[key] || '') as string
    }

    const remaining = 2000 - (Date.now() - startedAt)
    if (remaining > 0) await wait(remaining)
    uploadState.value = 'empty'

    if (uploaded.demo_warning) {
      ElMessage.warning('当前识别基于示例数据，请核对字段后再使用')
    } else if (uploaded.ocr_warning) {
      ElMessage.info(uploaded.ocr_warning)
    }

    if (canAnalyze.value) {
      await startAnalyze()
      return
    }
    step.value = 'correct'
  } catch (error) {
    uploadState.value = 'selected'
    step.value = 'upload'
    networkIssue.value = (error as ApiError).status === 0
    errorMessage.value = (error as ApiError).message || '上传失败'
    ElMessage.error(errorMessage.value)
  } finally {
    stopTimer()
  }
}

async function runOcr(options: { advance?: boolean } = {}) {
  if (!recordId.value) return
  step.value = options.advance === false ? 'upload' : 'recognizing'
  ocrError.value = ''
  if (!timer) startTimer()
  try {
    const result = await pipelineApi.ocr(recordId.value)
    ocrResult.value = result
    record.value = result.record
    for (const key of Object.keys(form)) {
      form[key] = (result.fields[key] || '') as string
    }
    if (options.advance !== false) step.value = 'correct'
    if (result.demo_warning) {
      ElMessage.warning('当前识别基于示例数据，请核对字段后再使用')
    } else if (result.ocr_warning) {
      ElMessage.info(result.ocr_warning)
    } else {
      ElMessage.success('识别完成，请核对并修正文字')
    }
  } catch (error) {
    ocrError.value = (error as ApiError).message || '识别失败'
    networkIssue.value = (error as ApiError).status === 0
  } finally {
    stopTimer()
  }
}

function stopCamera() {
  cameraStream?.getTracks().forEach((track) => track.stop())
  cameraStream = null
  if (cameraVideo.value) cameraVideo.value.srcObject = null
}

function cameraErrorMessage(error: unknown): string {
  const name = (error as { name?: string })?.name || ''
  if (name === 'NotAllowedError') return '摄像头权限被拒绝，请在浏览器地址栏允许摄像头后重试。'
  if (name === 'NotFoundError') return '没有找到可用摄像头，请改用系统拍照或选择图片。'
  if (name === 'NotReadableError') return '摄像头被其他程序占用，请关闭占用摄像头的程序后重试。'
  if (name === 'SecurityError') return '当前页面不是安全连接。手机局域网访问请使用 HTTPS，或改用系统拍照。'
  return '摄像头调用失败，请确认浏览器支持并已授权，或改用系统拍照。'
}

function closeCamera() {
  cameraOpen.value = false
  stopCamera()
}

async function openCameraScan() {
  cameraError.value = ''
  if (!navigator.mediaDevices?.getUserMedia) {
    ElMessage.warning('当前浏览器不支持网页直接调用摄像头，已打开系统拍照/图片选择')
    cameraInput.value?.click()
    return
  }
  cameraOpen.value = true
  cameraLoading.value = true
  await nextTick()
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: 'environment' },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
    })
    if (cameraVideo.value) {
      cameraVideo.value.srcObject = cameraStream
      await cameraVideo.value.play().catch(() => undefined)
    }
  } catch (error) {
    cameraError.value = cameraErrorMessage(error)
  } finally {
    cameraLoading.value = false
  }
}

function captureCamera() {
  const video = cameraVideo.value
  if (!video || !video.videoWidth || !video.videoHeight) {
    cameraError.value = '摄像头画面还没准备好，请稍等一秒再试。'
    return
  }
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  const context = canvas.getContext('2d')
  if (!context) {
    cameraError.value = '当前浏览器无法截取摄像头画面，请改用系统拍照。'
    return
  }
  context.drawImage(video, 0, 0, canvas.width, canvas.height)
  canvas.toBlob(
    (blob) => {
      if (!blob) {
        cameraError.value = '照片生成失败，请重试。'
        return
      }
      const picked = new File([blob], `camera_${Date.now()}.jpg`, { type: 'image/jpeg' })
      closeCamera()
      handleFile(picked)
    },
    'image/jpeg',
    0.92,
  )
}

function useSystemCamera() {
  closeCamera()
  cameraInput.value?.click()
}

function showPipelineLoading() {
  pipelineLoadingOpen.value = true
  pipelineStage.value = 0
  window.clearTimeout(pipelineTimer1)
  window.clearTimeout(pipelineTimer2)
  return new Promise<void>((resolve) => {
    pipelineTimer1 = window.setTimeout(() => {
      pipelineStage.value = 1
    }, 900)
    pipelineTimer2 = window.setTimeout(() => {
      pipelineLoadingOpen.value = false
      resolve()
    }, 2000)
  })
}

function onUploadChange(uploadFile: UploadFile) {
  if (uploadFile.raw) handleFile(uploadFile.raw)
}

function onCameraPick(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = input.files?.[0]
  if (picked) handleFile(picked)
  input.value = ''
}

const cameraInput = ref<HTMLInputElement | null>(null)
const galleryInput = ref<HTMLInputElement | null>(null)

/** 移动端优先走系统相机；桌面端走 getUserMedia，浏览器不支持时回退到文件选择。 */
function isMobileDevice(): boolean {
  const ua = navigator.userAgent || ''
  return (
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Windows Phone/i.test(ua) ||
    (navigator.maxTouchPoints > 1 && /Macintosh/i.test(ua)) ||
    window.matchMedia('(max-width: 767px)').matches
  )
}

function pickCamera() {
  if (isMobileDevice()) {
    cameraInput.value?.click()
    return
  }
  void openCameraScan()
}

function pickGallery() {
  galleryInput.value?.click()
}

async function replaceImage() {
  try {
    await ElMessageBox.confirm(
      '重新选择图片会创建一条新的分析记录，当前记录仍然保留在历史记录中。',
      '更换图片',
      { confirmButtonText: '继续更换', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  recordId.value = null
  savedRecordId.value = null
  ocrResult.value = null
  file.value = null
  setPreview(null)
  resetForm()
  step.value = 'upload'
}

async function discardRecord() {
  if (recordId.value && !ocrResult.value) {
    try {
      await recordApi.remove(recordId.value)
    } catch {
      /* 清理失败不阻塞用户 */
    }
  }
  recordId.value = null
  savedRecordId.value = null
  record.value = null
  ocrResult.value = null
  file.value = null
  setPreview(null)
  resetForm()
  step.value = 'upload'
}

async function saveCorrection(silent = false) {
  if (!recordId.value) return false
  submitting.value = true
  try {
    await pipelineApi.correct(recordId.value, { ...form })
    if (!silent) ElMessage.success('识别结果已保存')
    return true
  } catch (error) {
    ElMessage.error((error as ApiError).message || '保存失败')
    return false
  } finally {
    submitting.value = false
  }
}

function buildDishStreamText(dish: DishAnalysisInfo | null): string {
  if (!dish) return ''
  const totals = dish.totals
  const format = (value: number) => String(Math.round(value * 10) / 10)
  return [
    `识别到：${dish.dish_name}（约${format(totals.weight_g)}克）。`,
    '依据《中国食物成分表》：',
    `🔥 总热量：${format(totals.calories)} 大卡`,
    `🍞 碳水：${format(totals.carbs_g)}g | 🥩 蛋白质：${format(totals.protein_g)}g | 🧈 脂肪：${format(totals.fat_g)}g`,
    `💡 健康建议：${dish.health_tip}`,
  ].join('\n')
}

/**
 * 使用 Fetch + ReadableStream 消费 SSE。
 * 不依赖 EventSource，因此可以携带 Authorization，并支持 AbortController。
 */
async function readSseStream(
  response: Response,
  onEvent: (payload: Record<string, unknown>) => void,
): Promise<void> {
  if (!response.ok || !response.body) {
    throw new Error(`SSE ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const packets = buffer.split(/\r?\n\r?\n/)
      buffer = packets.pop() || ''

      for (const packet of packets) {
        const data = packet
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n')
        if (!data) continue
        try {
          onEvent(JSON.parse(data) as Record<string, unknown>)
        } catch {
          /* 忽略单条坏事件，继续读后续内容 */
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

let dishTypeBuffer = ''
let dishTypePromise: Promise<void> | null = null
let dishTypeGeneration = 0

function resetDishTypewriter() {
  dishTypeGeneration += 1
  dishTypeBuffer = ''
  dishTypePromise = null
}

function enqueueDishText(text: string) {
  if (!text) return
  dishTypeBuffer += text
  if (dishTypePromise) return

  const generation = dishTypeGeneration
  dishTypePromise = (async () => {
    try {
      while (generation === dishTypeGeneration && dishTypeBuffer.length) {
        const [char] = Array.from(dishTypeBuffer)
        dishTypeBuffer = dishTypeBuffer.slice(char.length)
        dishStreamText.value += char
        await wait(14)
      }
    } finally {
      if (generation === dishTypeGeneration) dishTypePromise = null
    }
  })()
}

async function startDishStream(id: number, streamUrl?: string) {
  dishStreamAbort?.abort()
  const controller = new AbortController()
  dishStreamAbort = controller
  resetDishTypewriter()
  dishStreaming.value = true
  dishStreamError.value = ''
  dishStreamText.value = ''

  try {
    const endpoint = streamUrl || `/analyze/dish/${id}/stream`
    const response = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        Accept: 'text/event-stream',
        Authorization: `Bearer ${getToken()}`,
      },
      signal: controller.signal,
    })

    await readSseStream(response, (payload) => {
      if (typeof payload.text === 'string') enqueueDishText(payload.text)
    })

    // 等打字机把最后一个字符显示完，再结束“正在输出”状态。
    if (dishTypePromise) await dishTypePromise
    if (!dishStreamText.value) throw new Error('empty stream')
  } catch (error) {
    if ((error as Error).name === 'AbortError') return
    resetDishTypewriter()
    dishStreamError.value = '流式输出中断，已切换为完整结果展示'
    dishStreamText.value = buildDishStreamText(dishResult.value)
  } finally {
    if (dishStreamAbort === controller) {
      dishStreaming.value = false
      dishStreamAbort = null
    }
  }
}

function viewDishWiki() {
  if (!dishResult.value?.slug) return
  router.push({
    name: 'knowledge',
    query: { category: 'dish', dish: dishResult.value.slug },
  })
}

function addDishToToday() {
  if (!dishResult.value) return
  const entry = addDish(dishResult.value, dishResult.value.totals.weight_g)
  ElMessage.success(
    `已加入今日饮食：${dishResult.value.dish_name} · ${entry.calories} 大卡`,
  )
}

function newDishAnalysis() {
  clearAnalyzeCache()
  dishStreamAbort?.abort()
  dishStreamAbort = null
  resetDishTypewriter()
  dishStreaming.value = false
  dishResult.value = null
  dishStreamText.value = ''
  dishStreamError.value = ''
  recordId.value = null
  record.value = null
  file.value = null
  setPreview(null)
  resetForm()
  uploadState.value = 'empty'
  step.value = 'upload'
}

async function startAnalyze(options: { skipCorrection?: boolean } = {}) {
  if (!recordId.value) return
  const skipCorrection = Boolean(options.skipCorrection)
  if (!skipCorrection && !canAnalyze.value) {
    ElMessage.warning('配料表与营养成分表都为空，请至少填写其中一项后再分析')
    return
  }
  step.value = 'analyzing'
  startTimer()
  try {
    if (!skipCorrection) {
      analyzingStage.value = '正在保存校正后的文字…'
      const saved = await saveCorrection(true)
      if (!saved) {
        step.value = 'correct'
        stopTimer()
        return
      }
      analyzingStage.value = '正在拆分配料并检索知识库…'
    } else {
      analyzingStage.value = '正在识别菜品与估算分量…'
    }

    const result = await pipelineApi.analyze(recordId.value, analysisType.value)

    if (analysisType.value === 'dish') {
      const dish = (result.result as { dish?: DishAnalysisInfo }).dish || null
      if (!dish) {
        throw new ApiError('没有拿到菜品营养结果，请重试', 500)
      }
      dishResult.value = dish
      dishStreamText.value = ''
      dishStreamError.value = ''
      stopTimer()
      step.value = 'dish-result'
      await startDishStream(recordId.value)
      return
    }

    analyzingStage.value = '分析完成，正在打开结果页…'
    if (result.result.errors?.length) {
      ElMessage.warning('大模型调用失败，已自动使用基础规则模式')
    }
    stopTimer()
    router.replace({ name: 'result', params: { id: recordId.value } })
  } catch (error) {
    stopTimer()
    step.value = skipCorrection ? 'upload' : 'correct'
    if (skipCorrection) uploadState.value = 'selected'
    networkIssue.value = (error as ApiError).status === 0
    ElMessage.error((error as ApiError).message || '分析失败，请重试')
  }
}

function backToUpload() {
  step.value = 'upload'
  stopTimer()
}

/** 对同一张图片重新执行 OCR：用于识别质量不佳、或解析规则升级后想重新识别的场景 */
async function rerunOcr() {
  if (!recordId.value) return
  try {
    await ElMessageBox.confirm(
      '重新识别会再次读取这张图片，并用新的识别结果覆盖当前表单内容（未保存的修改会丢失）。是否继续？',
      '重新识别',
      { type: 'warning', confirmButtonText: '重新识别', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  reOcrLoading.value = true
  step.value = 'recognizing'
  startTimer()
  ocrError.value = ''
  try {
    const result = await pipelineApi.ocr(recordId.value)
    ocrResult.value = result
    record.value = result.record
    for (const key of Object.keys(form)) {
      form[key] = (result.fields[key] || '') as string
    }
    step.value = 'correct'
    ElMessage.success('已重新识别，请核对结果')
  } catch (error) {
    ocrError.value = (error as ApiError).message || '重新识别失败'
    step.value = 'correct'
    ElMessage.error(ocrError.value)
  } finally {
    stopTimer()
    reOcrLoading.value = false
  }
}

async function loadExisting(id: number) {
  step.value = 'recognizing'
  startTimer()
  try {
    const detail: RecordDetail = await recordApi.detail(id)
    record.value = detail.record
    recordId.value = id
    savedRecordId.value = id
    if (detail.record.status === 'analyzed') {
      router.replace({ name: 'result', params: { id } })
      return
    }
    if (!detail.ocr) {
      await runOcr()
      return
    }
    ocrResult.value = {
      record: detail.record,
      ocr: detail.ocr,
      fields: detail.ocr.fields,
      field_order: Object.keys(detail.ocr.fields),
      demo_warning: null,
      provider: {
        key: detail.ocr.provider,
        label: detail.ocr.provider_label,
        version: detail.ocr.engine_version,
        is_demo: detail.ocr.is_demo,
        duration_ms: detail.ocr.duration_ms,
      },
    }
    for (const key of Object.keys(form)) form[key] = detail.ocr.fields[key] || ''
    step.value = 'correct'
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '记录加载失败'
    step.value = 'upload'
  } finally {
    stopTimer()
  }
}

onMounted(async () => {
  const queryId = Number(route.query.record)
  if (queryId) {
    // 从历史记录进入时，历史记录优先级最高，不恢复本地缓存
    loadExisting(queryId)
  } else {
    // 先同步恢复结果页，避免页面先闪一下上传界面
    restoreAnalyzeCache()
  }

  try {
    healthProfile.value = await pantryApi.profile()
  } catch {
    healthProfile.value = null
  }
})

onBeforeUnmount(() => {
  saveAnalyzeCache()
  dishStreamAbort?.abort()
  resetDishTypewriter()
  stopCamera()
  stopTimer()
  window.clearTimeout(pipelineTimer1)
  window.clearTimeout(pipelineTimer2)
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>

<template>
  <div class="page analyze-page page-narrow">
    <header class="page-head analyze-head">
      <div class="head-copy">
        <span class="analyze-eyebrow">AI NUTRITION ENGINE</span>
        <h1 class="page-title">AI 营养解析与评估</h1>
        <p class="page-sub">拍一拍，让 AI 营养师看懂你吃的是什么。支持包装配料表、食堂饭菜、外卖甜点。</p>
      </div>
      <button type="button" class="history-button" @click="router.push({ name: 'history' })">
        <el-icon><Tickets /></el-icon>
        历史记录
      </button>
    </header>

    <!-- 步骤条 -->
    <div class="stepper">
      <div v-for="(label, index) in ['上传图片', '识别文字', '核对校正', '分析结果']" :key="label" class="step-item" :class="{ active: stepIndex === index, done: stepIndex > index }">
        <span class="step-dot">{{ index + 1 }}</span>
        <span class="step-label">{{ label }}</span>
      </div>
    </div>

    <div v-if="errorMessage" class="notice notice-danger mb">
      <el-icon><WarningFilled /></el-icon>
      <div>{{ errorMessage }}</div>
    </div>

    <!-- 步骤 1：上传 -->
    <template v-if="step === 'upload'">
      <div class="grid grid-side upload-layout">
        <section class="card upload-card">
          <span class="upload-aurora" aria-hidden="true" />

          <div class="analysis-tabs" role="tablist" aria-label="选择识别类型">
            <button
              type="button"
              class="analysis-tab"
              :class="{ active: activeTab === 'packaging' }"
              :disabled="busy"
              @click="activeTab = 'packaging'"
            >
              <span class="analysis-tab-emoji">📦</span>
              识包装
            </button>
            <button
              type="button"
              class="analysis-tab"
              :class="{ active: activeTab === 'dish' }"
              :disabled="busy"
              @click="activeTab = 'dish'"
            >
              <span class="analysis-tab-emoji">🍱</span>
              识饭菜
            </button>
          </div>

          <el-upload
            drag
            action="#"
            :auto-upload="false"
            :show-file-list="false"
            accept="image/*"
            :disabled="busy || uploadState !== 'empty'"
            :on-change="onUploadChange"
            class="uploader"
          >
            <div v-if="uploadState === 'empty'" class="upload-inner" @click.stop="pickCamera">
              <div class="vision-orb">
                <span class="vision-orb-ring" aria-hidden="true" />
                <PlateIcon v-if="analysisType === 'dish'" class="vision-plate" />
                <span v-else class="vision-emoji" aria-hidden="true">{{ modeMeta.emoji }}</span>
              </div>
              <span class="vision-kicker">AI FOOD VISION</span>
              <h3>{{ modeMeta.title }}</h3>
              <p class="upload-mode-hint">{{ modeMeta.hint }}</p>

              <div class="upload-action-row">
                <div class="upload-actions">
                  <el-button class="primary-action" @click.stop="pickCamera">
                    📷 {{ isMobileDevice() ? '拍照/上传图片' : '打开摄像头' }}
                  </el-button>
                  <el-button class="primary-action" @click.stop="pickGallery">
                    📁 从相册选择
                  </el-button>
                </div>
                <button type="button" class="scan-link" @click.stop="openCameraScan">
                  扫码检测
                  <el-icon><ArrowRight /></el-icon>
                </button>
              </div>

              <p class="upload-note">
                支持 JPG / PNG / WEBP · 单张不超过 10MB · 图片仅用于本次分析<span v-if="!isMobileDevice()"> · 可直接拖拽图片</span>
              </p>
            </div>

            <div v-else class="upload-selected" @click.stop>
              <div class="selected-preview">
                <img v-if="previewUrl" :src="previewUrl" :alt="analysisType === 'dish' ? '已选择的菜品照片' : '已选择的食品标签照片'" />
                <span v-else class="selected-placeholder">🖼️</span>
              </div>
              <div class="selected-copy">
                <span class="selected-kicker">已选图片待提交</span>
                <strong>{{ file?.name || (analysisType === 'dish' ? '菜品照片' : '食品标签图片') }}</strong>
                <p>确认图片清晰后，点击下方按钮开始 AI 智能分析。</p>
              </div>
              <el-button
                v-if="uploadState === 'selected'"
                class="start-analysis"
                @click.stop="startAnalysis"
              >
                {{ analysisType === 'dish' ? '🚀 开始 AI 膳食分析' : '🚀 开始 AI 营养解析' }}
              </el-button>
              <el-button
                v-else
                class="start-analysis"
                loading
              >
                {{ analysisType === 'dish' ? '正在识别菜品…' : '正在提取标签文字…' }}
              </el-button>
              <el-button
                v-if="uploadState === 'selected'"
                text
                class="reselect"
                @click.stop="pickGallery"
              >
                重新选择
              </el-button>
              <div v-if="uploadState === 'analyzing'" class="upload-progress-line">
                <el-progress :percentage="uploadProgress" :show-text="false" :stroke-width="5" />
                <span>{{ uploadProgress < 100 ? '正在上传图片…' : analysisType === 'dish' ? '正在识别菜品…' : '正在提取标签文字…' }}</span>
              </div>
            </div>
          </el-upload>

          <input
            ref="galleryInput"
            type="file"
            accept="image/*"
            class="native-file-input"
            tabindex="-1"
            aria-hidden="true"
            @change="onCameraPick"
          />
          <input
            ref="cameraInput"
            type="file"
            accept="image/*"
            capture="environment"
            class="native-file-input"
            tabindex="-1"
            aria-hidden="true"
            @change="onCameraPick"
          />

          <div class="shot-guide">
            <div class="shot-guide-head">
              <span>拍摄小技巧</span>
              <small>3 个细节，让 AI 读得更准</small>
            </div>
            <div class="shot-guide-grid">
              <div v-for="tip in modeMeta.tips" :key="tip.title" class="shot-tip">
                <span class="shot-tip-icon">{{ tip.icon }}</span>
                <strong>{{ tip.title }}</strong>
                <p>{{ tip.desc }}</p>
              </div>
            </div>
          </div>
        </section>

        <aside class="card side-card ai-thinking-card">
          <div class="thinking-head">
            <span class="thinking-kicker">AI THINKING</span>
            <h3>AI 的思考过程</h3>
            <p>{{ modeMeta.thinking }}</p>
          </div>

          <el-timeline class="ai-timeline">
            <el-timeline-item
              v-for="(item, index) in thinkingSteps"
              :key="item.title"
              :color="item.color"
            >
              <div class="timeline-copy">
                <strong>
                  <span class="timeline-index">{{ index + 1 }}.</span>{{ item.title }}
                  <span v-if="item.tag" class="timeline-tag">({{ item.tag }})</span>
                </strong>
                <p>{{ item.desc }}</p>
              </div>
            </el-timeline-item>
          </el-timeline>

          <div class="ai-thinking-note">
            <el-icon><InfoFilled /></el-icon>
            <span>AI 解读仅供日常饮食参考，不能替代医生诊断。</span>
          </div>
        </aside>
      </div>

      <div v-if="profileCapsule" class="profile-capsule">
        <span class="capsule-shine" aria-hidden="true" />
        <span class="capsule-dot" aria-hidden="true" />
        {{ profileCapsule }}
      </div>
    </template>

    <!-- 步骤 2：识别中 -->
    <template v-if="step === 'recognizing'">
      <div class="card progress-card">
        <div class="progress-head">
          <div class="progress-title">
            <el-icon class="is-loading"><Loading /></el-icon>
            {{ uploadProgress > 0 && uploadProgress < 100 ? '正在上传图片…' : ocrError ? '识别未完成' : '正在识别标签文字…' }}
          </div>
          <span class="progress-time">已用时 {{ elapsed }} 秒</span>
        </div>
        <el-progress
          v-if="uploadProgress < 100 && !ocrError"
          :percentage="uploadProgress"
          :stroke-width="10"
          status="success"
        />
        <div v-else class="ocr-waiting">
          <div class="waiting-bar"><span /></div>
          <p class="waiting-text">
            本地 OCR 通常需要 3-8 秒（首次加载模型会稍慢）。识别期间请保持页面打开。
          </p>
        </div>

        <div v-if="ocrError" class="ocr-error">
          <el-alert type="error" :title="ocrError" :closable="false" show-icon />
          <p class="error-tip">
            常见原因：图片模糊 / 反光 / 文字太小，或本地 OCR 引擎未安装。你可以重试、换一张图片，或直接手动填写配料表。
          </p>
          <div class="error-actions">
            <el-button type="primary" @click="runOcr">重试识别</el-button>
            <el-button @click="replaceImage">换一张图片</el-button>
            <el-button plain @click="step = 'correct'">手动填写配料表</el-button>
            <el-button text @click="discardRecord">放弃本次记录</el-button>
          </div>
        </div>

        <div v-if="previewUrl || record?.image_url" class="progress-preview">
          <ZoomableImage v-if="previewUrl" :src="previewUrl" alt="待识别的标签照片" max-height="360px" />
          <AuthImage v-else-if="record?.image_url" :src="record.image_url" alt="待识别的标签照片" ratio="16 / 10" />
          <div class="preview-meta">
            <span v-if="file">{{ file.name }} · {{ (file.size / 1024).toFixed(0) }} KB</span>
            <span v-else-if="record">记录 #{{ record.id }}</span>
            <span v-if="currentImageSize" class="mono">{{ currentImageSize.width }}×{{ currentImageSize.height }}</span>
            <el-tag v-if="lowResolution" type="warning" size="small" effect="light">
              分辨率偏低，可能影响识别
            </el-tag>
          </div>
        </div>
      </div>
    </template>

    <!-- 步骤 3：校正 -->
    <template v-if="step === 'correct'">
      <div v-if="isDemoOcr" class="notice notice-danger mb">
        <el-icon><WarningFilled /></el-icon>
        <div>
          本次识别基于示例数据，请核对字段后再使用。
          如需真实识别，请安装本地 OCR 依赖或配置视觉模型（见 README / 设置页）。
        </div>
      </div>
      <div v-else-if="ocr" class="notice notice-brand mb">
        <el-icon><Cpu /></el-icon>
        <div>
          OCR 引擎：{{ ocr.provider_label }}（{{ ocr.engine_version }}，耗时 {{ ocr.duration_ms }}ms）。
          识别结果仅供参考，请对照实物逐字核对；标为「低置信度」的字段更容易出错。
          <template v-if="ocr.meta?.preprocess?.mode === 'enhanced' || ocr.meta?.warning">
            <br />
            <span class="ocr-hint">
              已自动增强处理（灰度 / 对比度 / 锐化{{ ocr.meta?.preprocess?.mode === 'enhanced' ? ' / 放大' : '' }}）。
              {{ ocr.meta?.warning || '' }}
            </span>
          </template>
        </div>
      </div>

      <div v-if="networkIssue" class="notice mb" :class="app.online ? 'notice-brand' : 'notice-danger'">
        <el-icon><CircleCheck v-if="app.online" /><WarningFilled v-else /></el-icon>
        <div>{{ resumeHint }}</div>
      </div>

      <div v-if="missingLabelSections" class="notice notice-warn mb">
        <el-icon><WarningFilled /></el-icon>
        <div>
          这张照片里没有找到「配料表」和「营养成分表」——很可能只拍到了包装正面，或者文字太小/太糊。
          请补拍包装背面（配料表、营养成分表、日期喷码），也可以直接手动填写关键字段。
          <div class="row mt-s">
            <el-button size="small" type="primary" plain @click="replaceImage">重新拍一张</el-button>
            <el-button size="small" plain :loading="reOcrLoading" @click="rerunOcr">再识别一次</el-button>
          </div>
        </div>
      </div>

      <div v-if="lowResolution" class="notice notice-warn mb">
        <el-icon><WarningFilled /></el-icon>
        <div>
          这张图片只有 {{ currentImageSize?.width }}×{{ currentImageSize?.height }} 像素，标签小字基本无法识别。
          建议用相机直接拍摄包装背面，或上传长边 ≥ 1000 像素的原图。
        </div>
      </div>

      <div class="grid grid-side">
        <div class="card">
          <div class="card-title">
            <h3>核对识别结果</h3>
            <div class="row">
              <el-button v-if="ocr?.raw_text" text @click="showRawText = !showRawText">
                {{ showRawText ? '隐藏原始文本' : '查看原始 OCR 文本' }}
              </el-button>
              <el-button v-if="recordId" :loading="reOcrLoading" plain size="small" @click="rerunOcr">
                <el-icon><Refresh /></el-icon>
                重新识别
              </el-button>
            </div>
          </div>

          <el-collapse-transition>
            <div v-show="showRawText" class="raw-text-box">
              <div class="raw-text-head">原始 OCR 识别文本（未修改，已入库）</div>
              <pre class="raw-text">{{ ocr?.raw_text || '（空）' }}</pre>
            </div>
          </el-collapse-transition>

          <el-form label-position="top" class="correct-form">
            <div class="form-grid">
              <el-form-item v-for="def in fieldDefs" :key="def.key" class="form-item">
                <template #label>
                  <span class="field-label">
                    {{ def.label }}
                    <span class="conf-tag" :class="`conf-${fieldState[def.key].tone}`">
                      {{ fieldState[def.key].text }}
                    </span>
                  </span>
                </template>
                <el-input
                  v-model="form[def.key]"
                  :placeholder="def.placeholder"
                  clearable
                  maxlength="200"
                />
              </el-form-item>
            </div>

            <el-form-item class="form-item">
              <template #label>
                <span class="field-label">
                  配料表 <span class="required-mark">（分析核心字段）</span>
                  <span class="conf-tag" :class="`conf-${fieldState.ingredients_text.tone}`">
                    {{ fieldState.ingredients_text.text }}
                  </span>
                </span>
              </template>
              <el-input
                v-model="form.ingredients_text"
                type="textarea"
                :rows="5"
                resize="vertical"
                placeholder="例如：小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母…"
              />
              <div class="field-tip">配料之间用「、」或逗号分隔，括号内的内容会保留在原文中。</div>
            </el-form-item>

            <el-form-item class="form-item">
              <template #label>
                <span class="field-label">
                  营养成分表
                  <span class="conf-tag" :class="`conf-${fieldState.nutrition_text.tone}`">
                    {{ fieldState.nutrition_text.text }}
                  </span>
                </span>
              </template>
              <el-input
                v-model="form.nutrition_text"
                type="textarea"
                :rows="4"
                resize="vertical"
                placeholder="例如：能量 1980kJ 24%，蛋白质 8.5g 14%，脂肪 18.2g 30%，碳水化合物 65.4g 22%，钠 480mg 24%"
              />
              <div class="field-tip">保留原始数值与单位即可，系统会自动识别项目、数值、单位与 NRV%。</div>

              <div v-if="nutritionPreview.items.length" class="nutrition-preview">
                <div class="nutrition-preview__head">
                  识别结果预览（按包装格式）
                  <span v-if="nutritionPreview.basisLabel" class="chip">{{ nutritionPreview.basisLabel }}</span>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>项目</th>
                      <th>含量</th>
                      <th>NRV%</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in nutritionPreview.items" :key="item.key">
                      <td>{{ item.name }}</td>
                      <td :class="{ missing: item.value === null }">
                        {{ item.value === null ? '未识别' : `${item.value}${item.unit}` }}
                      </td>
                      <td>{{ item.nrv_percent === null ? '—' : `${item.nrv_percent}%` }}</td>
                    </tr>
                  </tbody>
                </table>
                <div class="field-tip">这里只展示营养成分表的行；若识别串到了配料文字，可在上方文本框中删掉。</div>
              </div>
            </el-form-item>

            <el-form-item v-for="def in longFieldDefs" :key="def.key" class="form-item">
              <template #label>
                <span class="field-label">
                  {{ def.label }}
                  <span class="conf-tag" :class="`conf-${fieldState[def.key].tone}`">
                    {{ fieldState[def.key].text }}
                  </span>
                </span>
              </template>
              <el-input v-model="form[def.key]" type="textarea" :rows="def.rows" resize="vertical" />
            </el-form-item>
          </el-form>

          <div v-if="!canAnalyze" class="notice notice-info mt">
            <el-icon><InfoFilled /></el-icon>
            <div>配料表与营养成分表都为空。你可以手动输入配料表后继续分析，系统不会凭空生成成分。</div>
          </div>

          <div class="form-actions">
            <el-button type="primary" size="large" :loading="submitting" :disabled="!canAnalyze" @click="startAnalyze">
              <el-icon><MagicStick /></el-icon>
              保存并开始分析
            </el-button>
            <el-button size="large" :loading="submitting" @click="saveCorrection()">仅保存校正</el-button>
            <el-button size="large" plain @click="replaceImage">换一张图片</el-button>
            <el-button text @click="backToUpload">返回上传页</el-button>
          </div>
        </div>

        <aside class="card side-card">
          <h3 class="side-title">参考图片</h3>
          <ZoomableImage v-if="previewUrl" :src="previewUrl" alt="已上传的标签照片" max-height="300px" />
          <AuthImage v-else-if="record?.image_url" :src="record.image_url" alt="已上传的标签照片" ratio="4 / 3" />
          <div class="side-meta">
            <div class="row-between">
              <span class="text-small text-muted">记录编号</span>
              <span class="text-small mono">#{{ record?.id }}</span>
            </div>
            <div class="row-between">
              <span class="text-small text-muted">当前状态</span>
              <span class="text-small">{{ record?.status_label }}</span>
            </div>
            <div v-if="ocr?.provider" class="row-between">
              <span class="text-small text-muted">OCR 驱动</span>
              <span class="text-small">{{ ocr.provider }}</span>
            </div>
            <div class="row-between">
              <span class="text-small text-muted">未识别字段</span>
              <span class="text-small">{{ ocr?.missing_fields?.length ?? 0 }} 个</span>
            </div>
          </div>
          <div class="divider" />
          <div class="side-note">
            <el-icon><Warning /></el-icon>
            <span>照片只反映包装的一个面，未识别到不等于包装上没有该信息。</span>
          </div>
          <el-button class="side-link" text type="primary" @click="router.push({ name: 'knowledge' })">
            不确定某种配料是什么？查知识库 →
          </el-button>
        </aside>
      </div>
    </template>

    <!-- 步骤 4：分析中 -->
    <template v-if="step === 'analyzing'">
      <div class="card analyzing-card">
        <div class="analyzing-anim">
          <span class="pulse-ring" />
          <el-icon class="is-loading"><MagicStick /></el-icon>
        </div>
        <h3>正在生成分析结果</h3>
        <p class="analyzing-stage">{{ analyzingStage }}</p>
        <ul class="analyzing-steps">
          <li class="done">保存校正后的识别文本</li>
          <li :class="{ done: elapsed > 1 }">拆分配料并匹配知识库</li>
          <li :class="{ done: elapsed > 3 }">生成配料解释（AI 或规则模式）</li>
          <li :class="{ done: elapsed > 5 }">执行标签逻辑核查</li>
        </ul>
        <p class="analyzing-time">已用时 {{ elapsed }} 秒，请勿关闭页面</p>
      </div>
    </template>
    <!-- 识饭菜：流式营养结果 -->
    <template v-if="step === 'dish-result'">
      <div class="grid grid-side dish-result-layout">
        <section class="card dish-result-card">
          <div class="dish-result-head">
            <div>
              <span class="dish-result-kicker">AI 营养师 · 菜品营养库</span>
              <h3>{{ dishResult?.dish_name || '菜品营养分析' }}</h3>
              <p>已按菜品营养库完成份量换算，下面是本份的估算结果。</p>
            </div>
            <span class="dish-result-status" :class="{ streaming: dishStreaming }">
              <span class="status-dot" />
              {{ dishStreaming ? '正在流式输出' : '分析完成' }}
            </span>
          </div>

          <div class="dish-stream-box">
            <div class="dish-stream-text">
              {{ dishStreamText }}<span v-if="dishStreaming" class="stream-cursor" aria-hidden="true" />
            </div>
            <p v-if="dishStreamError" class="dish-stream-error">{{ dishStreamError }}</p>
          </div>

          <div class="dish-result-actions">
            <el-button type="primary" @click="viewDishWiki">
              查看百科
            </el-button>
            <el-button plain @click="addDishToToday">
              加入今日饮食记录
            </el-button>
            <el-button text @click="router.push({ name: 'result', params: { id: recordId } })">
              查看完整报告 →
            </el-button>
            <el-button text @click="newDishAnalysis">
              再识别一张
            </el-button>
          </div>
        </section>

        <aside v-if="dishResult" class="card dish-nutrition-card">
          <div class="dish-nutrition-kicker">本份营养看板</div>
          <div class="dish-nutrition-name">{{ dishResult.dish_name }}</div>
          <div class="dish-nutrition-portion">约 {{ dishResult.totals.weight_g }}g / 份</div>
          <div class="dish-nutrition-calorie">
            <strong>{{ Math.round(dishResult.totals.calories) }}</strong>
            <span>大卡</span>
          </div>

          <div class="dish-nutrition-macros">
            <div>
              <span>碳水</span>
              <strong>{{ dishResult.totals.carbs_g }}g</strong>
            </div>
            <div>
              <span>蛋白质</span>
              <strong>{{ dishResult.totals.protein_g }}g</strong>
            </div>
            <div>
              <span>脂肪</span>
              <strong>{{ dishResult.totals.fat_g }}g</strong>
            </div>
          </div>

          <div class="dish-nutrition-tip">
            <span>💡 健康建议</span>
            <p>{{ dishResult.health_tip }}</p>
          </div>

          <div class="dish-nutrition-source">
            每 100g {{ dishResult.calories_per_100g }} 大卡 · 数据来自菜品营养库
          </div>

          <div v-if="dishExerciseTip" class="dish-exercise-tip">
            {{ dishExerciseTip }}
          </div>
        </aside>
      </div>
    </template>

    <el-dialog
      v-model="cameraOpen"
      :title="analysisType === 'dish' ? '拍摄菜品' : '拍摄包装标签'"
      width="min(94vw, 620px)"
      align-center
      class="camera-dialog"
      @closed="stopCamera"
    >
      <div class="camera-shell">
        <video
          v-show="!cameraError"
          ref="cameraVideo"
          class="camera-video"
          autoplay
          playsinline
          muted
        />
        <div v-if="cameraLoading" class="camera-state">
          <el-icon class="is-loading"><Loading /></el-icon>
          正在调用摄像头…
        </div>
        <div v-else-if="cameraError" class="camera-state camera-error">
          <span>📷</span>
          <p>{{ cameraError }}</p>
        </div>
        <p v-else class="camera-tip">
          {{ analysisType === 'dish'
            ? '把整盘菜放在画面中央，保持光线充足，尽量让主食和配菜同框。'
            : '把食品包装上的配料表、营养成分表或条码对准画面，保持文字清晰。' }}
        </p>
      </div>
      <template #footer>
        <el-button @click="closeCamera">取消</el-button>
        <el-button @click="useSystemCamera">使用系统拍照</el-button>
        <el-button type="primary" :disabled="cameraLoading || Boolean(cameraError)" @click="captureCamera">
          拍照并继续
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="pipelineLoadingOpen"
      width="min(90vw, 420px)"
      :show-close="false"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      align-center
      class="pipeline-loading-dialog"
    >
      <div class="pipeline-loading">
        <div class="pipeline-spinner">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <h3>{{ pipelineStage === 0 ? '正在提取文字…' : '正在分析配料表…' }}</h3>
        <p>{{ pipelineStage === 0 ? '识别包装上的配料表与营养成分表' : '整理识别结果，准备下一步核对' }}</p>
        <el-progress :percentage="pipelineStage === 0 ? 45 : 85" :show-text="false" :stroke-width="8" />
        <div class="pipeline-steps">
          <span :class="{ active: pipelineStage === 0, done: pipelineStage > 0 }">1 提取文字</span>
          <span :class="{ active: pipelineStage === 1 }">2 分析配料表</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.analyze-page {
  max-width: 1120px;
  padding-top: 30px;
  padding-bottom: 96px;
  border-radius: 24px;
  background:
    radial-gradient(760px 300px at 10% -10%, rgba(70, 164, 138, 0.14), transparent 72%),
    linear-gradient(180deg, #f7f9fc 0%, #ffffff 74%);
}

.analyze-head {
  align-items: flex-start;
  margin-bottom: 22px;
}

.head-copy {
  min-width: 0;
}

.analyze-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  color: #6f8b7e;
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.17em;
}

.analyze-eyebrow::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2f9578;
  box-shadow: 0 0 0 4px rgba(47, 149, 120, 0.12);
}

.analyze-page :deep(.card) {
  background: #fff;
  border: 1px solid rgba(19, 58, 43, 0.06);
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.04);
}

.analyze-page .page-title {
  color: #102a20;
  font-size: clamp(29px, 3.1vw, 38px);
  font-weight: 800;
  letter-spacing: -1.2px;
  line-height: 1.16;
}

.analyze-page .page-sub {
  max-width: 650px;
  margin-top: 9px;
  color: #74877e;
  font-size: 14px;
  line-height: 1.72;
}

.history-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  margin-top: 19px;
  padding: 9px 15px;
  border: 1px solid rgba(19, 58, 43, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 5px 16px rgba(0, 0, 0, 0.035);
  color: #536d61;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 650;
  cursor: pointer;
  transition: border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.history-button:hover {
  border-color: rgba(31, 122, 95, 0.28);
  color: #1f7a5f;
  transform: translateY(-1px);
}

.mb {
  margin-bottom: 14px;
}

.mt {
  margin-top: 14px;
}

/* 步骤条 */
.stepper {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 20px;
  padding: 10px 16px;
  overflow-x: auto;
  border: 1px solid rgba(19, 58, 43, 0.06);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.76);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.035);
  backdrop-filter: blur(12px);
}

.step-item {
  display: flex;
  align-items: center;
  gap: 7px;
  flex: 0 0 auto;
  margin-right: 8px;
  color: #9aaba3;
  font-size: 12px;
  font-weight: 550;
}

.step-item:not(:last-child)::after {
  content: '';
  width: 18px;
  height: 1px;
  margin-left: 7px;
  background: #e5ece8;
}

.step-dot {
  display: grid;
  place-items: center;
  width: 23px;
  height: 23px;
  border: 1px solid #e9efec;
  border-radius: 50%;
  background: #f5f8f6;
  color: #91a49a;
  font-size: 10.5px;
  font-weight: 750;
  transition: background 0.18s ease, box-shadow 0.18s ease, color 0.18s ease;
}

.step-item.active {
  color: #194b38;
  font-weight: 700;
}

.step-item.active .step-dot {
  border-color: #0b3d2e;
  background: #0b3d2e;
  color: #fff;
  box-shadow: 0 0 0 4px rgba(31, 122, 95, 0.1);
}

.step-item.done .step-dot {
  border-color: #d5e9df;
  background: #eef8f3;
  color: #1f7a5f;
}

/* 上传 */
.upload-layout {
  gap: 20px;
}

.upload-card {
  position: relative;
  overflow: hidden;
  padding: 26px;
}

.upload-aurora {
  position: absolute;
  top: -170px;
  left: 50%;
  width: 540px;
  height: 330px;
  transform: translateX(-50%);
  background: radial-gradient(closest-side, rgba(65, 171, 143, 0.2), rgba(65, 171, 143, 0.04) 58%, transparent 78%);
  pointer-events: none;
}

.analysis-tabs {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 4px;
  width: max-content;
  margin: 0 auto 8px;
  padding: 4px;
  border: 1px solid #e9f0ec;
  border-radius: 999px;
  background: #f2f6f4;
}

.analysis-tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 100px;
  padding: 8px 16px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #7b8e84;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.analysis-tab-emoji {
  font-size: 15px;
  line-height: 1;
}

.analysis-tab.active {
  background: #fff;
  color: #0b3d2e;
  box-shadow: 0 4px 12px rgba(15, 50, 37, 0.08);
}

.analysis-tab:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.uploader {
  position: relative;
  z-index: 1;
}

:deep(.uploader .el-upload) {
  width: 100%;
}

:deep(.uploader .el-upload-dragger) {
  width: 100%;
  padding: 8px;
  border: 0;
  border-radius: 16px;
  background: transparent;
  transition: background 0.2s ease, box-shadow 0.2s ease;
}

:deep(.uploader .el-upload-dragger:hover) {
  border: 0;
  background: rgba(243, 249, 246, 0.6);
}

:deep(.uploader .el-upload-dragger.is-dragover) {
  background: rgba(236, 248, 242, 0.9);
  box-shadow: inset 0 0 0 1.5px rgba(31, 122, 95, 0.32);
}

.upload-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 26px 12px 18px;
  text-align: center;
}

.vision-orb {
  position: relative;
  display: grid;
  place-items: center;
  width: 102px;
  height: 102px;
  margin-bottom: 15px;
  border-radius: 32px;
  background: linear-gradient(145deg, #0b3d2e 0%, #14684f 54%, #42a98b 100%);
  box-shadow:
    0 20px 42px rgba(11, 61, 46, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
  color: #fff;
  font-size: 43px;
  transform: rotate(-3deg);
}

.vision-orb::after {
  content: '';
  position: absolute;
  inset: 1px;
  border-radius: 31px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.16), transparent 45%);
  pointer-events: none;
}

.vision-emoji {
  position: relative;
  z-index: 1;
  font-size: 47px;
  line-height: 1;
  filter: drop-shadow(0 6px 10px rgba(0, 0, 0, 0.16));
}

.vision-plate {
  position: relative;
  z-index: 1;
  width: 78px;
  height: 78px;
  filter: drop-shadow(0 8px 14px rgba(11, 61, 46, 0.2));
}

.timeline-index {
  margin-right: 2px;
  color: var(--brand);
  font-variant-numeric: tabular-nums;
}

.timeline-tag {
  margin-left: 4px;
  color: var(--muted);
  font-size: 11.5px;
  font-weight: 500;
}

.vision-orb-ring {
  position: absolute;
  inset: -13px;
  border: 1px solid rgba(45, 137, 111, 0.2);
  border-radius: 42px;
  animation: orb-breathe 3.8s ease-in-out infinite;
  pointer-events: none;
}

@keyframes orb-breathe {
  0%,
  100% {
    transform: scale(0.97);
    opacity: 0.55;
  }
  50% {
    transform: scale(1.04);
    opacity: 0.22;
  }
}

.vision-kicker {
  color: #92a69b;
  font-size: 9.5px;
  font-weight: 750;
  letter-spacing: 0.18em;
}

.upload-inner h3 {
  margin: 1px 0 0;
  color: #102a20;
  font-size: clamp(26px, 3vw, 34px);
  font-weight: 800;
  letter-spacing: -1px;
  line-height: 1.25;
}

.upload-mode-hint {
  max-width: 430px;
  margin: 8px 0 0;
  color: #49675a;
  font-size: 13.5px;
  font-weight: 650;
  line-height: 1.7;
}

.upload-lead {
  max-width: 430px;
  margin: 5px 0 0;
  color: #7a8e84;
  font-size: 13.5px;
  line-height: 1.7;
}

.upload-action-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 22px;
}

.upload-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  justify-content: center;
}

.primary-action.el-button {
  --el-button-bg-color: #0b3d2e;
  --el-button-border-color: #0b3d2e;
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: #145e47;
  --el-button-hover-border-color: #145e47;
  --el-button-hover-text-color: #fff;
  --el-button-active-bg-color: #092f23;
  --el-button-active-border-color: #092f23;
  height: 50px;
  padding: 0 21px;
  border: 1px solid #0b3d2e;
  border-radius: 14px;
  background: linear-gradient(135deg, #0b3d2e 0%, #145e47 100%);
  box-shadow: 0 11px 24px rgba(11, 61, 46, 0.18);
  color: #fff;
  font-size: 13.5px;
  font-weight: 700;
  transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.primary-action.el-button:hover {
  background: linear-gradient(135deg, #0e4a37 0%, #1a7055 100%);
  box-shadow: 0 14px 30px rgba(11, 61, 46, 0.24);
  transform: translateY(-1px);
}

.primary-action.el-button:active {
  transform: translateY(0);
}

.scan-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 9px 2px;
  border: 0;
  background: transparent;
  color: #1f7a5f;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  transition: color 0.18s ease, gap 0.18s ease;
}

.scan-link:hover {
  gap: 7px;
  color: #0b3d2e;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.upload-note {
  margin-top: 14px;
  color: #a0afa7;
  font-size: 11px;
  line-height: 1.6;
}

/* iOS 不允许对 display:none 的 input 触发文件选择，这里用移出屏幕的方式隐藏 */
.native-file-input {
  position: fixed;
  left: -9999px;
  top: 0;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

/* 拍摄小技巧 */
.shot-guide {
  position: relative;
  z-index: 1;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #eef3f0;
}

.shot-guide-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.shot-guide-head span {
  color: #4b6559;
  font-size: 12.5px;
  font-weight: 720;
}

.shot-guide-head small {
  color: #9caca4;
  font-size: 10.5px;
}

.shot-guide-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.shot-tip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  min-height: 104px;
  padding: 13px 13px 12px;
  border: 1px solid #edf1ef;
  border-radius: 14px;
  background: #f7f8fa;
}

.shot-tip-icon {
  margin-bottom: 4px;
  font-size: 20px;
  line-height: 1;
  filter: saturate(0.72);
}

.shot-tip strong {
  color: #3d574b;
  font-size: 12.5px;
  font-weight: 700;
}

.shot-tip p {
  margin: 0;
  color: #8d9e96;
  font-size: 10.5px;
  line-height: 1.55;
}

/* 侧栏 */
.side-card {
  background: #fff;
}

.side-title {
  margin-bottom: 12px;
  color: #173d2e;
  font-size: 15px;
  font-weight: 750;
}

.ai-thinking-card {
  position: relative;
  overflow: hidden;
  padding: 24px;
}

.ai-thinking-card::before {
  content: '';
  position: absolute;
  top: -80px;
  right: -70px;
  width: 190px;
  height: 190px;
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(58, 166, 137, 0.14), transparent 72%);
  pointer-events: none;
}

.thinking-head {
  position: relative;
  z-index: 1;
}

.thinking-kicker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 7px;
  color: #8aa096;
  font-size: 9.5px;
  font-weight: 750;
  letter-spacing: 0.16em;
}

.thinking-kicker::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #2f9578;
  box-shadow: 0 0 0 4px rgba(47, 149, 120, 0.1);
}

.thinking-head h3 {
  margin: 0;
  color: #173d2e;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.thinking-head p {
  margin: 5px 0 0;
  color: #84968d;
  font-size: 12px;
  line-height: 1.65;
}

.ai-timeline {
  position: relative;
  z-index: 1;
  margin-top: 22px;
  padding-left: 2px;
}

.ai-timeline :deep(.el-timeline-item) {
  padding-bottom: 20px;
}

.ai-timeline :deep(.el-timeline-item:last-child) {
  padding-bottom: 6px;
}

.ai-timeline :deep(.el-timeline-item__tail) {
  left: 6px;
  border-left: 1px dashed #d4e4dd;
}

.ai-timeline :deep(.el-timeline-item__node) {
  left: 1px;
  width: 10px;
  height: 10px;
  border: 0;
  box-shadow: 0 0 0 4px rgba(31, 122, 95, 0.07);
}

.ai-timeline :deep(.el-timeline-item__wrapper) {
  top: -7px;
  padding-left: 20px;
}

.timeline-copy strong {
  display: block;
  color: #2a4c3d;
  font-size: 13px;
  font-weight: 700;
}

.timeline-copy p {
  margin: 2px 0 0;
  color: #8b9c94;
  font-size: 11.5px;
  line-height: 1.55;
}

.ai-thinking-note {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 16px;
  padding-top: 13px;
  border-top: 1px solid #eef3f0;
  color: #98a79f;
  font-size: 11px;
  line-height: 1.6;
}

.ai-thinking-note .el-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  color: #7aa394;
}

/* 已同步画像胶囊 */
.profile-capsule {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: max-content;
  max-width: 100%;
  margin: 20px auto 0;
  padding: 11px 20px;
  overflow: hidden;
  border: 1px solid rgba(31, 122, 95, 0.17);
  border-radius: 999px;
  background: linear-gradient(135deg, #ffffff 0%, #f1fbf6 100%);
  box-shadow:
    0 0 0 4px rgba(47, 149, 120, 0.04),
    0 8px 24px rgba(31, 122, 95, 0.08);
  color: #1b6048;
  font-size: 12.5px;
  font-weight: 650;
  line-height: 1.5;
  text-align: center;
}

.capsule-shine {
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 22%, rgba(255, 255, 255, 0.9) 48%, transparent 72%);
  transform: translateX(-120%);
  animation: capsule-sheen 4.8s ease-in-out infinite;
  pointer-events: none;
}

.capsule-dot {
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2f9578;
  box-shadow: 0 0 0 4px rgba(47, 149, 120, 0.12);
}

@keyframes capsule-sheen {
  0%,
  38% {
    transform: translateX(-120%);
  }
  62%,
  100% {
    transform: translateX(120%);
  }
}

/* 识别中 */
.progress-card {
  padding: 22px;
}

.progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15.5px;
  font-weight: 650;
}

.progress-time {
  font-size: 12.5px;
  color: var(--muted);
}

.ocr-waiting {
  margin-top: 8px;
}

.waiting-bar {
  height: 6px;
  border-radius: 999px;
  background: #eef2f0;
  overflow: hidden;
  position: relative;
}

.waiting-bar span {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 35%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--brand), #35bfa7);
  animation: slide 1.5s ease-in-out infinite;
}

@keyframes slide {
  0% {
    left: -35%;
  }
  100% {
    left: 100%;
  }
}

.waiting-text {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--muted);
}

.ocr-error {
  margin-top: 12px;
}

.error-tip {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.7;
}

.error-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.progress-preview {
  margin-top: 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  background: var(--surface-2);
}

.progress-preview img {
  width: 100%;
  max-height: 320px;
  object-fit: contain;
  border-radius: 8px;
  display: block;
}

.preview-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
  text-align: center;
  overflow-wrap: anywhere;
}

/* 校正 */
.ocr-hint {
  color: var(--brand-700);
  font-size: 12px;
  opacity: 0.85;
}

.raw-text-box {
  margin-bottom: 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--surface-2);
}

.raw-text-head {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  background: #f4f8f6;
}

.raw-text {
  margin: 0;
  padding: 12px;
  font-family: 'Cascadia Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow: auto;
  color: var(--text-2);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
}

.form-item {
  margin-bottom: 14px;
}

.field-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-2);
  font-weight: 600;
  flex-wrap: wrap;
}

.required-mark {
  font-weight: 400;
  color: var(--brand);
  font-size: 11.5px;
}

.conf-tag {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--muted);
  white-space: nowrap;
}

.conf-ok {
  background: var(--ok-bg);
  border-color: #c9e8d9;
  color: var(--ok);
}

.conf-warn {
  background: var(--warn-bg);
  border-color: #f3e0bd;
  color: var(--warn);
}

.field-tip {
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.6;
}

.form-actions {
  display: flex;
  gap: 9px;
  flex-wrap: wrap;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.side-image {
  width: 100%;
  border-radius: 10px;
  border: 1px solid var(--border);
  display: block;
  object-fit: contain;
  max-height: 260px;
  background: var(--surface-2);
}

.side-meta {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.side-note {
  display: flex;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.7;
}

.side-link {
  margin-top: 10px;
  padding-left: 0;
}

/* 识饭菜流式结果 */
.dish-result-layout {
  align-items: start;
}

.dish-result-card {
  padding: 24px;
}

.dish-result-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.dish-result-kicker {
  color: #6f8b7e;
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.dish-result-head h3 {
  margin-top: 6px;
  color: #102a20;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.5px;
}

.dish-result-head p {
  margin-top: 5px;
  color: #7a8e84;
  font-size: 12.5px;
  line-height: 1.65;
}

.dish-result-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 5px 10px;
  border-radius: 999px;
  background: #edf7f2;
  color: #1f7a5f;
  font-size: 11px;
  font-weight: 650;
}

.dish-result-status.streaming {
  background: #fbf4e5;
  color: #9a6b18;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.dish-result-status.streaming .status-dot {
  animation: status-blink 1s ease-in-out infinite;
}

@keyframes status-blink {
  50% {
    opacity: 0.25;
  }
}

.dish-stream-box {
  margin-top: 18px;
  padding: 20px;
  border-radius: 16px;
  background:
    radial-gradient(420px 200px at 90% 0%, rgba(70, 164, 138, 0.16), transparent 70%),
    linear-gradient(145deg, #0b3d2e, #10533f);
  box-shadow: 0 18px 36px rgba(11, 61, 46, 0.18);
}

.dish-stream-text {
  min-height: 150px;
  color: #f4fbf7;
  font-size: 14px;
  line-height: 2;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.dish-stream-error {
  margin-top: 10px;
  color: #ffd9a8;
  font-size: 11.5px;
}

.stream-cursor {
  display: inline-block;
  width: 2px;
  height: 15px;
  margin-left: 2px;
  vertical-align: -2px;
  background: #8fe0c4;
  animation: cursor-blink 0.8s steps(2, start) infinite;
}

@keyframes cursor-blink {
  50% {
    opacity: 0;
  }
}

.dish-result-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.dish-result-actions .el-button {
  border-radius: 9px;
}

.dish-nutrition-card {
  padding: 22px;
  background:
    radial-gradient(300px 180px at 100% 0%, rgba(70, 164, 138, 0.12), transparent 72%),
    #fff;
}

.dish-nutrition-kicker {
  color: #6f8b7e;
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.dish-nutrition-name {
  margin-top: 8px;
  color: #102a20;
  font-size: 17px;
  font-weight: 750;
  line-height: 1.4;
}

.dish-nutrition-portion {
  margin-top: 3px;
  color: #8a9a92;
  font-size: 11.5px;
}

.dish-nutrition-calorie {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin-top: 14px;
  padding-bottom: 14px;
  border-bottom: 1px dashed rgba(19, 58, 43, 0.12);
}

.dish-nutrition-calorie strong {
  color: #0b3d2e;
  font-size: 50px;
  font-weight: 800;
  letter-spacing: -2px;
  line-height: 1;
}

.dish-nutrition-calorie span {
  color: #7a8e84;
  font-size: 12px;
}

.dish-nutrition-macros {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}

.dish-nutrition-macros > div {
  padding: 9px;
  border-radius: 10px;
  background: #f6faf8;
}

.dish-nutrition-macros span {
  display: block;
  color: #7a8e84;
  font-size: 10.5px;
}

.dish-nutrition-macros strong {
  display: block;
  margin-top: 3px;
  color: #173f30;
  font-size: 15px;
}

.dish-nutrition-tip {
  margin-top: 14px;
  padding: 11px 12px;
  border: 1px solid #f0e2c8;
  border-radius: 10px;
  background: #fbf7ee;
}

.dish-nutrition-tip span {
  color: #7a5a17;
  font-size: 11.5px;
  font-weight: 700;
}

.dish-nutrition-tip p {
  margin-top: 4px;
  color: #6b5320;
  font-size: 12.5px;
  line-height: 1.7;
}

.dish-nutrition-source {
  margin-top: 12px;
  color: #94a39b;
  font-size: 10.5px;
  line-height: 1.6;
}

.dish-exercise-tip {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  margin-top: 12px;
  padding: 6px 10px;
  border: 1px solid #f6dfbd;
  border-radius: 999px;
  background: #fff5e8;
  color: #a9650a;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
}

/* 分析中 */
.analyzing-card {
  text-align: center;
  padding: 40px 24px;
}

.analyzing-anim {
  position: relative;
  width: 66px;
  height: 66px;
  margin: 0 auto 16px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--brand-100);
  color: var(--brand);
  font-size: 28px;
}

.pulse-ring {
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 2px solid rgba(15, 123, 108, 0.25);
  animation: pulse-ring 1.8s ease-out infinite;
}

@keyframes pulse-ring {
  0% {
    transform: scale(0.9);
    opacity: 0.9;
  }
  100% {
    transform: scale(1.35);
    opacity: 0;
  }
}

.analyzing-card h3 {
  font-size: 18px;
}

.analyzing-stage {
  margin-top: 6px;
  color: var(--brand-700);
  font-size: 13.5px;
  font-weight: 600;
}

.analyzing-steps {
  list-style: none;
  padding: 0;
  margin: 20px auto 0;
  max-width: 320px;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.analyzing-steps li {
  font-size: 13px;
  color: var(--muted);
  padding-left: 22px;
  position: relative;
}

.analyzing-steps li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid var(--border-strong);
}

.analyzing-steps li.done {
  color: var(--text-2);
}

.analyzing-steps li.done::before {
  border-color: var(--ok);
  background: var(--ok);
  box-shadow: inset 0 0 0 2px #fff;
}

.analyzing-time {
  margin-top: 18px;
  font-size: 12px;
  color: var(--muted);
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .upload-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .dish-result-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .ai-thinking-card {
    padding: 22px;
  }
}

@media (max-width: 560px) {
  .dish-result-card {
    padding: 18px;
  }

  .dish-result-head {
    flex-direction: column;
  }

  .dish-result-head h3 {
    font-size: 21px;
  }

  .dish-stream-box {
    padding: 16px;
  }

  .dish-stream-text {
    font-size: 13px;
  }

  .dish-result-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .dish-result-actions .el-button {
    width: 100%;
    margin-left: 0;
  }

  .analyze-page {
    padding: 18px 14px 90px;
    border-radius: 18px;
  }

  .analyze-head {
    gap: 10px;
    margin-bottom: 16px;
  }

  .analyze-eyebrow {
    margin-bottom: 6px;
  }

  .analyze-page .page-title {
    font-size: 28px;
    letter-spacing: -0.9px;
  }

  .analyze-page .page-sub {
    font-size: 12.5px;
    line-height: 1.65;
  }

  .history-button {
    margin-top: 0;
    padding: 8px 12px;
    font-size: 11.5px;
  }

  .upload-card {
    padding: 17px 13px;
  }

  :deep(.uploader .el-upload-dragger) {
    padding: 2px;
  }

  .upload-inner {
    padding: 16px 2px 12px;
  }

  .analysis-tabs {
    width: 100%;
    gap: 3px;
  }

  .analysis-tab {
    flex: 1;
    min-width: 0;
    padding: 8px 10px;
  }

  .vision-orb {
    width: 84px;
    height: 84px;
    margin-bottom: 13px;
    border-radius: 26px;
    font-size: 36px;
  }

  .vision-emoji {
    font-size: 38px;
  }

  .vision-orb::after {
    border-radius: 25px;
  }

  .vision-orb-ring {
    inset: -10px;
    border-radius: 34px;
  }

  .upload-inner h3 {
    font-size: 27px;
    letter-spacing: -0.8px;
  }

  .upload-lead {
    max-width: 290px;
    font-size: 12.5px;
  }

  .upload-action-row {
    flex-direction: column;
    gap: 2px;
    width: 100%;
    margin-top: 18px;
  }

  .upload-actions {
    flex-direction: column;
    width: 100%;
    gap: 8px;
  }

  .upload-actions :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }

  .primary-action.el-button {
    height: 48px;
    border-radius: 13px;
    font-size: 13px;
  }

  .scan-link {
    padding-top: 10px;
    font-size: 12px;
  }

  .upload-note {
    margin-top: 11px;
    font-size: 10px;
  }

  .shot-guide {
    margin-top: 16px;
    padding-top: 13px;
  }

  .shot-guide-head small {
    display: none;
  }

  .shot-guide-grid {
    gap: 7px;
  }

  .shot-tip {
    min-height: 100px;
    padding: 10px 9px;
    border-radius: 12px;
  }

  .shot-tip-icon {
    font-size: 17px;
  }

  .shot-tip strong {
    font-size: 11.5px;
  }

  .shot-tip p {
    font-size: 9.5px;
  }

  .ai-thinking-card {
    padding: 18px;
  }

  .thinking-head h3 {
    font-size: 17px;
  }

  .ai-timeline {
    margin-top: 19px;
  }

  .profile-capsule {
    width: auto;
    margin-top: 16px;
    padding: 10px 14px;
    gap: 6px;
    font-size: 11px;
    line-height: 1.6;
  }

  .form-actions :deep(.el-button) {
    flex: 1 1 100%;
    margin-left: 0;
  }

  .stepper {
    padding: 8px;
    gap: 0;
  }

  .step-item {
    margin-right: 0;
    gap: 4px;
    font-size: 10.5px;
  }

  .step-item:not(:last-child)::after {
    width: 6px;
    margin-left: 4px;
    margin-right: 4px;
  }

  .step-dot {
    width: 18px;
    height: 18px;
    font-size: 9.5px;
  }

  .progress-card {
    padding: 16px;
  }
}

.pipeline-loading-dialog :deep(.el-dialog__header) {
  display: none;
}

.pipeline-loading {
  padding: 12px 10px 8px;
  text-align: center;
}

.pipeline-spinner {
  width: 58px;
  height: 58px;
  margin: 0 auto 14px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  background: #e8f5ee;
  color: #1f7a5f;
  font-size: 28px;
}

.pipeline-loading h3 {
  margin: 0 0 7px;
  font-size: 19px;
  color: #1d3c30;
}

.pipeline-loading p {
  margin: 0 0 16px;
  color: #7b9188;
  font-size: 12px;
}

.pipeline-steps {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
  color: #9aaca3;
  font-size: 11px;
}

.pipeline-steps span.active {
  color: #1f7a5f;
  font-weight: 700;
}

.pipeline-steps span.done {
  color: #4d8e72;
}

.upload-selected {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 11px;
  padding: 22px 14px;
  border: 1px solid #edf3f0;
  border-radius: 16px;
  background: linear-gradient(180deg, #fbfdfc 0%, #f4f9f6 100%);
  cursor: default;
}

.selected-preview {
  display: grid;
  place-items: center;
  width: min(100%, 240px);
  height: 160px;
  overflow: hidden;
  border: 1px solid rgba(24, 68, 50, 0.08);
  border-radius: 14px;
  background: #f4f8f5;
  box-shadow: 0 8px 20px rgba(15, 50, 37, 0.06);
}

.selected-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.selected-placeholder {
  font-size: 40px;
}

.selected-copy {
  text-align: center;
}

.selected-kicker {
  display: block;
  color: #8ca096;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.selected-copy strong {
  display: block;
  max-width: 360px;
  margin: 4px 0;
  overflow: hidden;
  color: #173d2e;
  font-size: 14.5px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected-copy p {
  margin: 0;
  color: #84968d;
  font-size: 11.5px;
}

.start-analysis.el-button {
  --el-button-bg-color: #0b3d2e;
  --el-button-border-color: #0b3d2e;
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: #145e47;
  --el-button-hover-border-color: #145e47;
  --el-button-hover-text-color: #fff;
  min-width: 230px;
  height: 48px;
  border-radius: 13px;
  background: linear-gradient(135deg, #0b3d2e 0%, #145e47 100%);
  box-shadow: 0 10px 22px rgba(11, 61, 46, 0.2);
  font-size: 13.5px;
  font-weight: 700;
}

.start-analysis.el-button:hover {
  background: linear-gradient(135deg, #0e4a37 0%, #1a7055 100%);
  box-shadow: 0 14px 28px rgba(11, 61, 46, 0.25);
}

.reselect {
  color: #8a9c92;
}

.upload-progress-line {
  display: flex;
  align-items: center;
  gap: 8px;
  width: min(100%, 300px);
  color: #7b9188;
  font-size: 10.5px;
}

.upload-progress-line :deep(.el-progress) {
  flex: 1;
}

.camera-shell {
  position: relative;
  min-height: 260px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 12px;
  background: #0f1f18;
}

.camera-video {
  width: 100%;
  max-height: 62vh;
  display: block;
  object-fit: contain;
  background: #0f1f18;
}

.camera-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: #e6f4ec;
  background: rgba(15, 31, 24, 0.88);
  text-align: center;
  font-size: 13px;
}

.camera-state .el-icon {
  font-size: 26px;
}

.camera-error span {
  font-size: 34px;
}

.camera-error p {
  max-width: 420px;
  margin: 0;
  line-height: 1.7;
}

.camera-tip {
  position: absolute;
  left: 50%;
  bottom: 12px;
  transform: translateX(-50%);
  width: max-content;
  max-width: 90%;
  margin: 0;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(8, 24, 16, 0.7);
  color: #dceee3;
  font-size: 11px;
  text-align: center;
}

/* 手机端紧凑上传区：确保「拍照/上传」按钮位于底部 Tab 栏上方 */
@media (max-width: 767px) {
  .analyze-head {
    margin-bottom: 8px;
    justify-content: flex-end;
  }

  .analyze-head .head-copy {
    display: none;
  }

  .stepper {
    margin-bottom: 10px;
  }

  .upload-inner {
    padding-top: 8px;
  }

  .vision-orb {
    width: 68px;
    height: 68px;
    margin-bottom: 8px;
    border-radius: 21px;
    font-size: 30px;
  }

  .vision-orb-ring {
    inset: -8px;
    border-radius: 28px;
  }

  .vision-kicker {
    display: none;
  }

  .upload-inner h3 {
    font-size: 23px;
    letter-spacing: -0.5px;
  }

  .upload-mode-hint {
    margin: 4px 0 8px;
  }
}

</style>
