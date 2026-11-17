from pathlib import Path

p = Path("src/components/NutritionPanel.vue")
t = p.read_text(encoding="utf-8")
t = t.replace(
    "const warnings = computed(() => props.nutrition?.warnings || [])",
    '''const warnings = computed(() =>
  (props.nutrition?.warnings || []).filter(
    (warning) => !/(计量基准|未在营养成分表|基准待确认)/.test(String(warning.message || '')),
  ),
)
const basisWarnings = computed(() =>
  (props.nutrition?.warnings || []).filter((warning) =>
    /(计量基准|未在营养成分表|基准待确认)/.test(String(warning.message || '')),
  ),
)
const basisIsDefault = computed(() => basisWarnings.value.length > 0 && props.nutrition?.basis === 'per_100g')''',
)
t = t.replace(
    '''      <div class="basis-row">
        <span class="chip">计量基准：{{ basis }}</span>
        <span class="chip chip-muted">来源：{{ nutrition.source === 'ocr' ? '标签识别' : '人工填写' }}</span>
        <span v-if="!hasValues" class="chip chip-warn">未识别到任何数值</span>
      </div>''',
    '''      <div class="basis-row">
        <span class="chip">计量基准：{{ basis }}{{ basisIsDefault ? '（默认）' : '' }}</span>
        <span class="chip chip-muted">来源：{{ nutrition.source === 'ocr' ? '标签识别' : '人工填写' }}</span>
        <span v-if="!hasValues" class="chip chip-warn">未识别到任何数值</span>
      </div>
      <p v-if="basisIsDefault" class="basis-default-note">
        计量基准：默认按每 100g 展示（未识别到表头）
      </p>''',
)
t = t.replace(
    ".table-note {",
    '''.basis-default-note {
  margin: -4px 0 10px;
  color: #8a9e93;
  font-size: 10.5px;
  line-height: 1.6;
}

.table-note {''',
)
p.write_text(t, encoding="utf-8")
print("nutrition basis UI")
