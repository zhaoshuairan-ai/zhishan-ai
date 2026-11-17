/** 展示层格式化工具。 */

export function formatDate(value?: string | null, withTime = false): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  const base = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
  return withTime ? `${base} ${pad(date.getHours())}:${pad(date.getMinutes())}` : base
}

export function formatRelative(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const diff = Date.now() - date.getTime()
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  if (diff < minute) return '刚刚'
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`
  return formatDate(value)
}

export function formatBytes(bytes?: number | null): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

export function basisLabel(basis?: string): string {
  const map: Record<string, string> = {
    per_100g: '每 100g',
    per_100ml: '每 100mL',
    per_serving: '每份',
    unknown: '基准未知',
  }
  return map[basis || ''] || '基准未知'
}

export function confidenceLabel(confidence?: string): string {
  return { high: '可信度较高', medium: '可信度中等', low: '可信度较低' }[confidence || ''] || '可信度未知'
}

export function evidenceLabel(evidence?: string): string {
  const map: Record<string, string> = {
    knowledge_base: '知识库依据',
    general_knowledge: '通用常识',
    unverified: '未验证推测',
  }
  return map[evidence || ''] || '未标注'
}

export function statusTagType(status?: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    uploaded: 'info',
    ocr_done: 'info',
    corrected: 'warning',
    analyzed: 'success',
    failed: 'danger',
  }
  return map[status || ''] || 'info'
}

export function overallTagType(overall?: string | null): 'success' | 'warning' | 'danger' | 'info' {
  if (overall === 'none_found') return 'success'
  if (overall === 'needs_review') return 'warning'
  if (overall === 'suspected') return 'danger'
  return 'info'
}

export function levelClass(level?: string): string {
  const map: Record<string, string> = {
    pass: 'level-pass',
    info: 'level-info',
    review: 'level-review',
    suspected: 'level-suspected',
    skip: 'level-skip',
  }
  return map[level || ''] || 'level-skip'
}

export function nutritionValue(item: { value: number | null; unit: string }): string {
  if (item.value === null || item.value === undefined) return '未识别'
  const num = Number(item.value)
  const display = Number.isInteger(num) ? String(num) : String(Number(num.toFixed(2)))
  return `${display}${item.unit || ''}`
}
