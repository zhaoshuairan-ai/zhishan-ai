/** 前端侧的配料文本拆分（仅用于展示「校正后的配料表」，与后端解析逻辑保持一致的直观规则）。 */
export function splitIngredientText(text?: string | null): string[] {
  if (!text) return []
  const cleaned = text.replace(/^配\s*料(?:\s*表)?\s*[:：]?/, '').trim()
  const tokens: string[] = []
  let buffer = ''
  let depth = 0
  for (const char of cleaned) {
    if (char === '(' || char === '（') depth += 1
    if (char === ')' || char === '）') depth = Math.max(0, depth - 1)
    if (depth === 0 && /[、,，;；/\n]/.test(char)) {
      if (buffer.trim()) tokens.push(buffer.trim())
      buffer = ''
      continue
    }
    buffer += char
  }
  if (buffer.trim()) tokens.push(buffer.trim())
  return tokens.map((token) => token.replace(/^[\s\d.、)\]:：]+/, '').replace(/[。.;；,，、]+$/, '')).filter(Boolean)
}
