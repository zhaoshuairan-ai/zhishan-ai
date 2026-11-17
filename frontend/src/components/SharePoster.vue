<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

type PosterWarning = {
  level?: string
  title?: string
  message?: string
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    foodName: string
    score: number | null
    grade: string
    gradeLabel: string
    summary: string
    warning?: PosterWarning | null
    tags?: Array<{ name: string; label: string; value?: string; status?: string }>
  }>(),
  {
    warning: null,
    tags: () => [],
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const posterUrl = ref('')
const generating = ref(false)
const canvasRef = ref<HTMLCanvasElement | null>(null)

function updateOpen(value: boolean) {
  emit('update:modelValue', value)
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const r = Math.min(radius, width / 2, height / 2)
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + width, y, x + width, y + height, r)
  ctx.arcTo(x + width, y + height, x, y + height, r)
  ctx.arcTo(x, y + height, x, y, r)
  ctx.arcTo(x, y, x + width, y, r)
  ctx.closePath()
}

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines = 4,
): number {
  const chars = Array.from(String(text || ''))
  let line = ''
  let lines = 0
  for (const char of chars) {
    const next = line + char
    if (ctx.measureText(next).width > maxWidth && line) {
      ctx.fillText(line, x, y + lines * lineHeight)
      line = char
      lines += 1
      if (lines >= maxLines) return y + lines * lineHeight
    } else {
      line = next
    }
  }
  if (line && lines < maxLines) {
    ctx.fillText(line, x, y + lines * lineHeight)
    lines += 1
  }
  return y + lines * lineHeight
}

function scoreColor(score: number | null): string {
  if (score === null) return '#9aa9a2'
  if (score >= 80) return '#2f9e6f'
  if (score >= 60) return '#2f7f9e'
  if (score >= 40) return '#d8952a'
  return '#cf4237'
}

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => resolve(image)
    image.onerror = () => resolve(null)
    image.src = src
  })
}

async function generate() {
  if (generating.value) return
  generating.value = true
  try {
    await nextTick()
    const canvas = canvasRef.value || document.createElement('canvas')
    canvas.width = 900
    canvas.height = 1240
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // 背景与顶部品牌区
    ctx.fillStyle = '#f4fae7'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = '#ffffff'
    roundedRect(ctx, 38, 38, 824, 1164, 30)
    ctx.fill()

    const logo = await loadImage('/icons/icon-192.png')
    if (logo) {
      ctx.save()
      roundedRect(ctx, 72, 72, 64, 64, 16)
      ctx.clip()
      ctx.drawImage(logo, 72, 72, 64, 64)
      ctx.restore()
    } else {
      ctx.fillStyle = '#0f7b6c'
      roundedRect(ctx, 72, 72, 64, 64, 16)
      ctx.fill()
      ctx.fillStyle = '#ffffff'
      ctx.font = 'bold 28px sans-serif'
      ctx.fillText('AI', 89, 113)
    }
    ctx.fillStyle = '#173e32'
    ctx.font = '700 25px "Microsoft YaHei", sans-serif'
    ctx.fillText('智膳 AI', 152, 104)
    ctx.fillStyle = '#78928a'
    ctx.font = '16px "Microsoft YaHei", sans-serif'
    ctx.fillText('全场景健康膳食 · 家庭决策海报', 152, 130)

    ctx.strokeStyle = '#e6eee9'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(72, 168)
    ctx.lineTo(828, 168)
    ctx.stroke()

    // 食品名称
    ctx.fillStyle = '#7d938a'
    ctx.font = '600 18px "Microsoft YaHei", sans-serif'
    ctx.fillText('本次检测食品', 72, 218)
    ctx.fillStyle = '#173e32'
    ctx.font = '700 42px "Microsoft YaHei", sans-serif'
    wrapText(ctx, props.foodName || '未命名食品', 72, 274, 570, 52, 2)

    // 健康分圆环
    const ringX = 735
    const ringY = 300
    const ringR = 76
    ctx.strokeStyle = '#edf2ee'
    ctx.lineWidth = 14
    ctx.beginPath()
    ctx.arc(ringX, ringY, ringR, -Math.PI / 2, Math.PI * 1.5)
    ctx.stroke()
    if (props.score !== null) {
      ctx.strokeStyle = scoreColor(props.score)
      ctx.lineCap = 'round'
      ctx.beginPath()
      ctx.arc(
        ringX,
        ringY,
        ringR,
        -Math.PI / 2,
        -Math.PI / 2 + (Math.PI * 2 * Math.max(0, Math.min(100, props.score))) / 100,
      )
      ctx.stroke()
    }
    ctx.fillStyle = '#173e32'
    ctx.textAlign = 'center'
    ctx.font = '700 44px "Microsoft YaHei", sans-serif'
    ctx.fillText(props.score === null ? '—' : String(props.score), ringX, ringY + 14)
    ctx.fillStyle = '#7d938a'
    ctx.font = '15px "Microsoft YaHei", sans-serif'
    ctx.fillText('分', ringX, ringY + 39)
    ctx.fillStyle = scoreColor(props.score)
    ctx.font = '700 20px "Microsoft YaHei", sans-serif'
    ctx.fillText(`${props.grade} 级`, ringX, ringY + 112)
    ctx.fillStyle = '#7d938a'
    ctx.font = '14px "Microsoft YaHei", sans-serif'
    ctx.fillText(props.gradeLabel, ringX, ringY + 135)
    ctx.textAlign = 'left'

    // AI 个性化预警
    let cursorY = 455
    if (props.warning && props.warning.level && props.warning.level !== 'none') {
      ctx.fillStyle = props.warning.level === 'warning' ? '#fff8e8' : '#fff0ec'
      roundedRect(ctx, 72, cursorY, 756, 150, 16)
      ctx.fill()
      ctx.strokeStyle = props.warning.level === 'warning' ? '#f0d7a5' : '#f2c8bc'
      ctx.stroke()
      ctx.fillStyle = props.warning.level === 'warning' ? '#946b1d' : '#a74432'
      ctx.font = '700 19px "Microsoft YaHei", sans-serif'
      const warningTitle = String(props.warning.title || '个性化健康预警').replace(/^⚠️\s*/, '')
      ctx.fillText(`⚠️ ${warningTitle}`, 96, cursorY + 36)
      ctx.font = '17px "Microsoft YaHei", sans-serif'
      wrapText(ctx, props.warning.message || '', 96, cursorY + 70, 700, 27, 2)
      cursorY += 174
    }

    // AI 总结
    ctx.fillStyle = '#7d938a'
    ctx.font = '600 18px "Microsoft YaHei", sans-serif'
    ctx.fillText('AI 健康总结', 72, cursorY + 6)
    ctx.fillStyle = '#263f35'
    ctx.font = '23px "Microsoft YaHei", sans-serif'
    cursorY = wrapText(ctx, props.summary || '暂无总结', 72, cursorY + 44, 756, 36, 4)

    // 标签胶囊
    const tagStart = Math.max(cursorY + 24, 760)
    let tagX = 72
    let tagY = tagStart
    for (const tag of (props.tags || []).slice(0, 3)) {
      const label = `${tag.name} ${tag.label}`.trim()
      ctx.font = '600 15px "Microsoft YaHei", sans-serif'
      const width = Math.min(250, ctx.measureText(label).width + 30)
      if (tagX + width > 828) {
        tagX = 72
        tagY += 42
      }
      ctx.fillStyle = tag.status === 'high' ? '#fff0ec' : '#eef8f2'
      roundedRect(ctx, tagX, tagY, width, 32, 16)
      ctx.fill()
      ctx.fillStyle = tag.status === 'high' ? '#a74432' : '#2f6e54'
      ctx.fillText(label, tagX + 14, tagY + 21)
      tagX += width + 10
    }

    // 页脚二维码
    const footerY = 1000
    ctx.strokeStyle = '#e6eee9'
    ctx.beginPath()
    ctx.moveTo(72, footerY)
    ctx.lineTo(828, footerY)
    ctx.stroke()
    const qr = await loadImage('/share-qr.png')
    if (qr) {
      ctx.fillStyle = '#ffffff'
      roundedRect(ctx, 72, footerY + 28, 164, 164, 12)
      ctx.fill()
      ctx.drawImage(qr, 78, footerY + 34, 152, 152)
    }
    ctx.fillStyle = '#173e32'
    ctx.font = '700 24px "Microsoft YaHei", sans-serif'
    ctx.fillText('微信扫码体验', 268, footerY + 78)
    ctx.fillStyle = '#7d938a'
    ctx.font = '16px "Microsoft YaHei", sans-serif'
    ctx.fillText('拍一张标签，读懂配料与营养', 268, footerY + 110)
    ctx.fillStyle = '#93a69d'
    ctx.font = '13px "Microsoft YaHei", sans-serif'
    wrapText(ctx, '本海报基于标签识别与 AI 解读生成，仅作健康参考，不构成医学诊断或官方检测结论。', 268, footerY + 145, 540, 21, 2)

    posterUrl.value = canvas.toDataURL('image/png')
  } catch {
    ElMessage.error('海报生成失败，请重试')
  } finally {
    generating.value = false
  }
}

function download() {
  if (!posterUrl.value) return
  const link = document.createElement('a')
  link.href = posterUrl.value
  link.download = `${props.foodName || '智膳'}-健康海报.png`
  link.click()
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) void generate()
  },
)
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    width="min(92vw, 520px)"
    top="4vh"
    class="share-poster-dialog"
    @update:model-value="updateOpen"
  >
    <template #header>
      <div class="poster-dialog-title">🖼️ 生成分享海报</div>
    </template>
    <div v-loading="generating" class="poster-preview">
      <img v-if="posterUrl" :src="posterUrl" alt="智膳分享海报" class="poster-image" />
      <div v-else class="poster-placeholder">正在绘制健康海报…</div>
    </div>
    <p class="poster-hint">长按保存图片，分享给家人朋友避雷</p>
    <canvas ref="canvasRef" class="poster-canvas" aria-hidden="true" />
    <template #footer>
      <el-button @click="updateOpen(false)">关闭</el-button>
      <el-button type="primary" :disabled="!posterUrl" @click="download">下载海报</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.share-poster-dialog :deep(.el-dialog__body) {
  padding-top: 4px;
}

.poster-dialog-title {
  font-size: 16px;
  font-weight: 700;
  color: #173e32;
}

.poster-preview {
  min-height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: #f5f9f6;
  overflow: hidden;
}

.poster-image {
  display: block;
  width: 100%;
  max-height: 68vh;
  object-fit: contain;
}

.poster-placeholder {
  color: #8a9e93;
  font-size: 13px;
}

.poster-hint {
  margin: 10px 0 0;
  text-align: center;
  color: #6d8278;
  font-size: 12px;
}

.poster-canvas {
  position: fixed;
  left: -9999px;
  top: 0;
  width: 900px;
  height: 1240px;
  pointer-events: none;
}
</style>
