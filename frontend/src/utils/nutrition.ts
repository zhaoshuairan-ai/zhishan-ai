/**
 * 营养成分表「预览解析」：只用于校正页把文本框里的内容还原成包装格式的表格。
 * 真正的解析以服务端 nutrition_parser 为准，这里的规则刻意保持简单、可读。
 *
 * 重要：数值与 NRV% 只在同一行内匹配，绝不跨行，否则会把下一行的数值错当成 NRV。
 */

export interface NutritionPreviewRow {
  key: string
  name: string
  value: number | null
  unit: string
  nrv_percent: number | null
}

const NUTRIENTS: Array<{ key: string; name: string; unit: string; aliases: string[] }> = [
  { key: 'energy', name: '能量', unit: 'kJ', aliases: ['能量', '热量'] },
  { key: 'protein', name: '蛋白质', unit: 'g', aliases: ['蛋白质'] },
  { key: 'fat', name: '脂肪', unit: 'g', aliases: ['脂肪'] },
  { key: 'saturated_fat', name: '饱和脂肪酸', unit: 'g', aliases: ['饱和脂肪酸', '饱和脂肪'] },
  { key: 'trans_fat', name: '反式脂肪酸', unit: 'g', aliases: ['反式脂肪酸', '反式脂肪'] },
  { key: 'carbohydrate', name: '碳水化合物', unit: 'g', aliases: ['碳水化合物', '碳水'] },
  { key: 'sugar', name: '糖', unit: 'g', aliases: ['糖'] },
  { key: 'fiber', name: '膳食纤维', unit: 'g', aliases: ['膳食纤维'] },
  { key: 'sodium', name: '钠', unit: 'mg', aliases: ['钠'] },
  { key: 'cholesterol', name: '胆固醇', unit: 'mg', aliases: ['胆固醇'] },
  { key: 'calcium', name: '钙', unit: 'mg', aliases: ['钙'] },
  { key: 'iron', name: '铁', unit: 'mg', aliases: ['铁'] },
  { key: 'zinc', name: '锌', unit: 'mg', aliases: ['锌'] },
]

const UNIT_ALIASES: Record<string, string> = {
  kj: 'kJ',
  千焦: 'kJ',
  干焦: 'kJ',
  千售: 'kJ',
  kcal: 'kcal',
  千卡: 'kcal',
  大卡: 'kcal',
  g: 'g',
  克: 'g',
  mg: 'mg',
  毫克: 'mg',
  豪克: 'mg',
}

// 长名字优先，避免「脂肪」先匹配掉「饱和脂肪酸」
const NAME_PATTERN = NUTRIENTS.flatMap((item) => item.aliases)
  .sort((a, b) => b.length - a.length)
  .map((alias) => alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  .join('|')

const NAME_ONLY_RE = new RegExp(`^(${NAME_PATTERN})\\s*[:：]?$`)
const NAME_VALUE_RE = new RegExp(
  `(${NAME_PATTERN})\\s*[:：]?[ \\t]*(\\d+(?:\\.\\d+)?)[ \\t]*(kcal|kJ|KJ|kj|千焦|干焦|千售|千卡|大卡|mg|g|MG|G|克|毫克|豪克)?` +
    `(?:[ \\t]*[（(]?[ \\t]*(\\d+(?:\\.\\d+)?)[ \\t]*[%％])?`,
  'gi'
)
const VALUE_ONLY_RE = /^(\d+(?:\.\d+)?)[ \t]*(kcal|kJ|KJ|kj|千焦|干焦|千售|千卡|大卡|mg|g|MG|G|克|毫克|豪克)?[ \t]*$/
const PERCENT_ONLY_RE = /^[（(]?[ \t]*(\d+(?:\.\d+)?)[ \t]*[%％][)）]?$/
const BASIS_RE = /每\s*(100\s*(?:g|克|ml|毫升)|份|袋|包|支)/i

function normalizeUnit(raw: string | undefined, fallback: string): string {
  if (!raw) return fallback
  return UNIT_ALIASES[raw.toLowerCase()] || UNIT_ALIASES[raw] || fallback
}

export function parseNutritionPreview(text: string): { rows: NutritionPreviewRow[]; basisLabel: string } {
  const lines = (text || '')
    .replace(/\r/g, '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  const found = new Map<string, NutritionPreviewRow>()

  const record = (name: string, value: number, unitRaw: string | undefined, nrv: number | null) => {
    const definition = NUTRIENTS.find((item) => item.aliases.includes(name))
    if (!definition || found.has(definition.key)) return
    if (!Number.isFinite(value)) return
    found.set(definition.key, {
      key: definition.key,
      name: definition.name,
      value,
      unit: normalizeUnit(unitRaw, definition.unit),
      nrv_percent: nrv !== null && Number.isFinite(nrv) ? nrv : null,
    })
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]

    // 1) 同一行：名称 + 数值 (+ NRV%)
    for (const match of line.matchAll(NAME_VALUE_RE)) {
      record(match[1], Number(match[2]), match[3], match[4] ? Number(match[4]) : null)
    }

    // 2) 名称单独一行，数值（可能还有 NRV%）在后续行
    const nameOnly = line.match(NAME_ONLY_RE)
    if (nameOnly) {
      const next = lines[index + 1] || ''
      const valueMatch = next.match(VALUE_ONLY_RE)
      if (valueMatch) {
        let nrv: number | null = null
        const percentMatch = (lines[index + 2] || '').match(PERCENT_ONLY_RE)
        if (percentMatch) nrv = Number(percentMatch[1])
        record(nameOnly[1], Number(valueMatch[1]), valueMatch[2], nrv)
      }
    }
  }

  const basisMatch = (text || '').match(BASIS_RE)
  let basisLabel = ''
  if (basisMatch) {
    const raw = basisMatch[1].replace(/\s+/g, '')
    if (raw.startsWith('100')) {
      basisLabel = raw.includes('ml') || raw.includes('毫升') ? '每 100mL' : '每 100g'
    } else {
      basisLabel = `每${raw}`
    }
  }

  const rows = NUTRIENTS.filter((item) => found.has(item.key)).map((item) => found.get(item.key)!)
  return { rows, basisLabel }
}
