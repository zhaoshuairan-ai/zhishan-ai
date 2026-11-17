<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { reportApi } from '@/api'
import { ApiError } from '@/api/client'
import type { ReportPayload } from '@/api/types'
import AuthImage from '@/components/AuthImage.vue'
import NutritionPanel from '@/components/NutritionPanel.vue'
import CheckPanel from '@/components/CheckPanel.vue'
import BrandMark from '@/components/BrandMark.vue'
import { formatDate } from '@/utils/format'

const route = useRoute()
const router = useRouter()

const report = ref<ReportPayload | null>(null)
const loading = ref(true)
const errorMessage = ref('')

const recordId = computed(() => Number(route.params.id))
const ocr = computed(() => report.value?.ocr || null)
const fields = computed(() => ocr.value?.fields || {})
const fieldLabels = computed(() => ocr.value?.field_labels || {})
const analysis = computed(() => report.value?.ingredient || null)
const nutrition = computed(() => report.value?.nutrition || null)
const check = computed(() => report.value?.check || null)
const health = computed(() => report.value?.health || null)

const isDishReport = computed(
  () =>
    report.value?.record.ocr_provider === 'dish_vision' ||
    ocr.value?.provider === 'dish_vision',
)

const dishRawPayload = computed<Record<string, any>>(() => {
  const raw = String(ocr.value?.raw_text || '')
  try {
    return JSON.parse(raw) as Record<string, any>
  } catch {
    return {}
  }
})

const dishPayload = computed<Record<string, any>>(() => {
  const parsed = dishRawPayload.value
  return parsed?.dish && typeof parsed.dish === 'object' ? parsed.dish : {}
})

const dishConfidenceLabel = computed(() => {
  const confidence = String(
    dishRawPayload.value?.recognition?.confidence ||
    dishPayload.value?.confidence ||
    '',
  ).toLowerCase()
  if (confidence === 'high') return '置信度：高'
  if (confidence === 'low') return '置信度：低'
  if (confidence === 'medium') return '置信度：中'
  return '置信度：待确认'
})

function dishTotal(key: string): number | null {
  const value = dishPayload.value?.totals?.[key]
  return typeof value === 'number' ? value : null
}

const dishFields = computed(() => {
  const dish = dishPayload.value
  const nutritionItems = nutrition.value?.items || []
  const nutritionValue = (key: string) =>
    nutritionItems.find((item) => item.key === key)?.value ?? null

  const weight =
    dish?.estimated_weight_g ??
    dish?.totals?.weight_g ??
    nutrition.value?.basis_note?.match(/([0-9.]+)\s*g/)?.[1]
  const calories = dishTotal('calories') ?? nutritionValue('energy')
  const protein = dishTotal('protein_g') ?? nutritionValue('protein')
  const fat = dishTotal('fat_g') ?? nutritionValue('fat')
  const carbs = dishTotal('carbs_g') ?? nutritionValue('carbohydrate')
  const gi = dish?.gi ?? dish?.glycemic_index ?? null

  return [
    {
      key: 'food_name',
      label: '菜品名称',
      value: report.value?.record.food_name || dish?.dish_name || '',
    },
    {
      key: 'weight',
      label: '估算重量',
      value: weight != null ? `${Math.round(Number(weight))} g` : '',
    },
    {
      key: 'ingredients',
      label: '食材构成',
      value: fields.value.ingredients_text || dish?.category || '',
    },
    {
      key: 'calories',
      label: '本份热量',
      value: calories != null ? `${Math.round(Number(calories))} kcal` : '',
    },
    {
      key: 'protein',
      label: '蛋白质',
      value: protein != null ? `${Number(protein).toFixed(1)} g` : '',
    },
    {
      key: 'fat',
      label: '脂肪',
      value: fat != null ? `${Number(fat).toFixed(1)} g` : '',
    },
    {
      key: 'carbs',
      label: '碳水化合物',
      value: carbs != null ? `${Number(carbs).toFixed(1)} g` : '',
    },
    {
      key: 'gi',
      label: '血糖生成指数（GI）',
      value: gi != null ? String(gi) : '暂未提供',
    },
    {
      key: 'health_tip',
      label: '健康建议',
      value: dish?.health_tip || health.value?.headline || '',
    },
  ]
})

const basicFields = computed(() => {
  if (isDishReport.value) return dishFields.value

  const labels = fieldLabels.value
  const skip = ['ingredients_text', 'nutrition_text']
  return Object.entries(labels)
    .filter(([key]) => !skip.includes(key))
    .map(([key, label]) => ({ key, label, value: (fields.value[key] || '').trim() }))
})

const healthTone = computed(() => {
  const grade = String(health.value?.grade || '').toUpperCase()
  if (grade === 'A') return 'is-green'
  if (grade === 'B') return 'is-amber'
  if (grade === 'C' || grade === 'D') return 'is-red'
  return 'is-muted'
})

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    report.value = await reportApi.get(recordId.value)
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '报告加载失败'
  } finally {
    loading.value = false
  }
}

async function printReport() {
  // 先让所有 ChartCard 把 ECharts canvas 转成 Base64 PNG
  window.dispatchEvent(new Event('report:prepare-print'))

  // 等待 Vue 渲染出临时 <img> 和图片解码，再打开打印对话框
  await nextTick()
  await new Promise((resolve) => window.setTimeout(resolve, 120))

  // 不弹 ElMessage，避免提示语被浏览器打印进报告
  window.print()
}

onMounted(load)
</script>

<template>
  <div class="report-page">
    <div class="report-toolbar no-print">
      <div class="toolbar-left">
        <el-button text @click="router.push({ name: 'result', params: { id: recordId } })">
          <el-icon><ArrowLeft /></el-icon>
          返回结果页
        </el-button>
        <span class="toolbar-title">分析报告</span>
      </div>
      <div class="toolbar-actions">
        <el-button @click="router.push({ name: 'history' })">历史记录</el-button>
        <el-button type="primary" @click="printReport">
          <el-icon><Printer /></el-icon>
          打印 / 保存 PDF
        </el-button>
      </div>
    </div>

    <div v-if="loading" class="report-shell">
      <div class="loading-block" style="height: 300px" />
    </div>

    <div v-else-if="errorMessage" class="report-shell">
      <div class="card">
        <div class="empty">
          <h4>报告暂时无法生成</h4>
          <p class="empty-desc">{{ errorMessage }}</p>
          <div class="row" style="justify-content: center; margin-top: 14px">
            <el-button type="primary" @click="load">重试</el-button>
            <el-button @click="router.push({ name: 'history' })">返回历史记录</el-button>
          </div>
        </div>
      </div>
    </div>

    <article v-else-if="report" class="report-shell report-document">
      <header class="report-head">
        <div class="head-left">
          <BrandMark compact />
          <div class="head-title">
            <h1>{{ isDishReport ? '菜品营养分析报告' : '食品标签分析报告' }}</h1>
            <p>{{ report.meta.app_subtitle }}</p>
          </div>
        </div>
        <div class="head-right">
          <div class="report-no">报告编号：{{ report.report.report_no }}</div>
          <div class="report-time">生成时间：{{ formatDate(report.report.generated_at, true) }}</div>
          <div v-if="report.meta.public_site_url" class="report-time">来源站点：{{ report.meta.public_site_url }}</div>
        </div>
      </header>

      <div v-if="report.meta.is_demo" class="demo-stamp">演示数据 · 非真实识别结果</div>

      <section class="report-section">
        <h2>一、基本信息</h2>
        <div class="info-grid">
          <div class="info-cell">
            <span class="info-k">食品名称</span>
            <span class="info-v">{{ report.record.food_name || '未填写' }}</span>
          </div>
          <div class="info-cell">
            <span class="info-k">记录编号</span>
            <span class="info-v">#{{ report.record.id }}</span>
          </div>
          <div class="info-cell">
            <span class="info-k">分析模式</span>
            <span class="info-v">
              {{ analysis?.mode_label || '未分析' }}{{ analysis?.model ? `（${analysis.model}）` : '' }}
            </span>
          </div>
          <div class="info-cell">
            <span class="info-k">数据来源</span>
            <span class="info-v">{{ report.meta.is_demo ? '示例数据' : '用户上传的真实图片' }}</span>
          </div>
          <div class="info-cell">
            <span class="info-k">OCR 引擎</span>
            <span class="info-v">{{ ocr?.provider_label || '—' }}</span>
          </div>
          <div class="info-cell">
            <span class="info-k">核查规则集</span>
            <span class="info-v">{{ report.ruleset.version }}（更新于 {{ report.ruleset.updated_at }}）</span>
          </div>
          <div class="info-cell">
            <span class="info-k">分析时间</span>
            <span class="info-v">{{ formatDate(report.record.analyzed_at, true) }}</span>
          </div>
          <div class="info-cell">
            <span class="info-k">整体核查结论</span>
            <span class="info-v">{{ report.check_overall_label || '未核查' }}</span>
          </div>
        </div>
      </section>

      <section class="report-section">
        <h2>{{ isDishReport ? '二、菜品识别字段' : '二、标签字段' }}</h2>
        <div class="report-grid">
          <table class="field-table">
            <tbody>
              <tr v-for="field in basicFields" :key="field.key">
                <th>{{ field.label }}</th>
                <td :class="{ empty: !field.value }">{{ field.value || '未识别' }}</td>
              </tr>
            </tbody>
          </table>
          <div class="report-image">
            <AuthImage v-if="report.record.image_url" :src="report.record.image_url" alt="食品标签照片" ratio="3 / 4" />
            <p class="image-caption">标签照片（原始上传）</p>
          </div>
        </div>
        <p class="section-note">
          {{
            isDishReport
              ? '菜品重量与营养数据由视觉估算和菜品营养库换算，实际以称重为准；GI 未收录时显示“暂未提供”。'
              : '「未识别」表示本次上传的图片中没有读到该字段；这不代表包装上缺少该信息，可能是未拍摄到对应区域或字迹不清。'
          }}
        </p>
      </section>

      <section class="report-section raw-section">
        <h2>三、识别文本</h2>
        <details class="raw-details">
          <summary>展开查看原始技术数据</summary>
          <div class="text-block">
            <h3>原始 OCR 识别文本</h3>
            <pre>{{ ocr?.raw_text || '（无）' }}</pre>
          </div>
          <div class="text-block">
            <h3>校正后的文本</h3>
            <pre>{{ ocr?.corrected_text || '（无）' }}</pre>
          </div>
        </details>
      </section>

      <section class="report-section">
        <h2>{{ isDishReport ? '四、菜品构成分析' : '四、配料分析' }}</h2>
        <div class="mode-line">
          <span class="chip" :class="analysis?.mode === 'ai' ? 'chip-ok' : 'chip-warn'">{{ analysis?.mode_label }}</span>
          <span class="text-small text-muted">提示词版本 {{ analysis?.prompt_version }} · 耗时 {{ analysis?.duration_ms }} ms</span>
        </div>
        <p class="summary-line">{{ analysis?.summary }}</p>
        <table class="ingredient-table desktop-only">
          <thead>
            <tr>
              <th style="width: 34px">#</th>
              <th style="width: 120px">配料</th>
              <th style="width: 110px">类别</th>
              <th>用途与解释</th>
              <th style="width: 92px">依据</th>
              <th style="width: 76px">可信度</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in analysis?.ingredients || []" :key="item.name">
              <td>{{ index + 1 }}</td>
              <td class="strong">{{ item.name }}</td>
              <td>{{ item.category }}</td>
              <td>
                <div v-if="item.purpose" class="item-purpose">{{ item.purpose }}</div>
                <div>{{ item.explanation }}</div>
                <div v-if="item.caution" class="item-caution">注意：{{ item.caution }}</div>
              </td>
              <td>
                {{ item.evidence === 'knowledge_base' ? '知识库' : item.evidence === 'general_knowledge' ? '通用常识' : '未验证' }}
                <div v-if="item.source_refs?.length" class="refs">{{ item.source_refs.join(' ') }}</div>
              </td>
              <td>{{ item.confidence === 'high' ? '较高' : item.confidence === 'medium' ? '中等' : '较低' }}</td>
            </tr>
          </tbody>
        </table>

        <div class="ingredient-cards mobile-only">
          <article v-for="(item, index) in analysis?.ingredients || []" :key="item.name" class="ing-card">
            <div class="ing-head">
              <span class="ing-index">{{ index + 1 }}</span>
              <span class="ing-name">{{ item.name }}</span>
              <span class="chip chip-muted">{{ item.category }}</span>
            </div>
            <div class="ing-meta">
              <span>依据：{{ item.evidence === 'knowledge_base' ? '知识库' : item.evidence === 'general_knowledge' ? '通用常识' : '未验证' }}</span>
              <span v-if="item.source_refs?.length">{{ item.source_refs.join(' ') }}</span>
              <span>可信度：{{ item.confidence === 'high' ? '较高' : item.confidence === 'medium' ? '中等' : '较低' }}</span>
            </div>
            <div v-if="item.purpose" class="item-purpose">{{ item.purpose }}</div>
            <p class="ing-explain">{{ item.explanation }}</p>
            <p v-if="item.caution" class="item-caution">注意：{{ item.caution }}</p>
          </article>
        </div>
        <div v-if="analysis?.unknown_items?.length" class="sub-note">
          <strong>未收录成分：</strong>{{ analysis?.unknown_items.join('、') }}
        </div>
        <div v-if="analysis?.unconfirmed?.length" class="sub-note">
          <strong>待确认事项：</strong>
          <ul>
            <li v-for="(item, index) in analysis?.unconfirmed" :key="index">{{ item }}</li>
          </ul>
        </div>
        <p class="disclaimer-line">{{ analysis?.disclaimer }}</p>
      </section>

      <section class="report-section">
        <h2>五、营养成分</h2>
        <NutritionPanel
          :nutrition="nutrition"
          :notes="analysis?.nutrition_notes || []"
          :notes-label="analysis?.mode_label"
        />
      </section>

      <section class="report-section">
        <h2>六、健康评估（自建参考模型）</h2>
        <template v-if="health">
          <div class="health-top">
            <div class="health-score" :class="healthTone">
              <strong>{{ health.score === null ? '—' : health.score }}</strong>
              <span>健康分</span>
            </div>
            <div class="health-meta">
              <p class="health-grade">{{ health.grade === 'NA' ? '数据不足' : `${health.grade} · ${health.grade_label}` }}</p>
              <p class="health-headline">{{ health.headline }}</p>
            </div>
          </div>
          <ul class="health-findings">
            <li v-for="item in health.findings" :key="item.key">
              <div class="health-finding-head">
                <strong>{{ item.title }}</strong>
                <span class="health-level">{{ item.level_label }}</span>
              </div>
              <p class="health-finding-summary">{{ item.summary }}</p>
              <p class="health-finding-detail">{{ item.detail }}</p>
              <p class="health-finding-basis">依据：{{ item.basis }} · 置信度 {{ item.confidence }}</p>
            </li>
          </ul>
          <p v-if="health.additives.count" class="section-note">
            识别到 {{ health.additives.count }} 种常见添加剂：{{ health.additives.items.map((item) => item.name).join('、') }}。
            添加剂是否合规需要具体品类、用量与适用范围，本报告无法判定，需以官方标准与检测结果为准。
          </p>
          <p class="health-disclaimer">{{ health.disclaimer }}</p>
        </template>
        <p v-else class="section-note">该记录未生成健康评估。</p>
      </section>

      <section class="report-section">
        <h2>
          {{
            isDishReport
              ? '七、AI 视觉估算说明与置信度'
              : '七、标签辅助核查'
          }}
        </h2>

        <template v-if="isDishReport">
          <div class="dish-estimate-card">
            <div class="dish-estimate-head">
              <span class="dish-estimate-icon">💡</span>
              <strong>视觉估算提示</strong>
              <span class="dish-estimate-confidence">{{ dishConfidenceLabel }}</span>
            </div>
            <p>
              AI 视觉模型基于图片为您估算了食物的份量与营养，可能存在一定误差，实际请以称重为准。
            </p>
            <div class="dish-estimate-meta">
              <span>识别菜品：{{ report.record.food_name }}</span>
              <span v-if="dishFields.find((item) => item.key === 'weight')?.value">
                估算份量：{{ dishFields.find((item) => item.key === 'weight')?.value }}
              </span>
              <span>营养来源：菜品营养库</span>
            </div>
          </div>
        </template>

        <CheckPanel
          v-else
          :check="check"
          :expand-all="true"
          :filterable="false"
          :compact-pass="true"
        />
      </section>

      <section class="report-section">
        <h2>八、资料来源</h2>
        <div v-if="report.sources.length" class="source-list">
          <div v-for="(source, index) in report.sources" :key="`${source.title}-${index}`" class="source-item">
            <div class="source-title">{{ source.title }}</div>
            <div class="source-meta">
              来源：{{ source.source_name }}
              <span v-if="source.version">· 版本 {{ source.version }}</span>
              <span v-if="source.verification_status">· {{ source.verification_status === 'verified' ? '已核对' : '待核验' }}</span>
            </div>
            <div v-if="source.claim" class="source-claim">{{ source.claim }}</div>
            <a v-if="source.source_url" :href="source.source_url" target="_blank" rel="noopener" class="source-url">
              {{ source.source_url }}
            </a>
          </div>
        </div>
        <p v-else-if="!isDishReport" class="section-note">本次分析未匹配到知识库条目。</p>

        <h3 class="rule-source-title">核查规则依据（名称引用，未收录原文）</h3>
        <ul class="rule-source-list">
          <li v-for="source in report.rule_sources" :key="source.name">
            <span class="rule-source-name">{{ source.name }}</span>
            <span class="rule-source-note">{{ source.note }}</span>
          </li>
        </ul>
      </section>

      <section class="report-section disclaimer-section">
        <h2>九、声明与边界</h2>
        <ul class="boundary-list">
          <li>本报告由「{{ report.meta.app_name }}」自动生成，属于信息理解辅助，不构成食品安全性判定、合规认定或医疗建议。</li>
          <li>系统只读取包装上可见的文字，不进行任何实验检测，无法发现微生物、农药残留、重金属、真菌毒素或非法添加物。</li>
          <li>OCR 与 AI 结果可能存在误差，标签内容的真实性仍需以产品实物与官方信息为准。</li>
          <li>图片未拍到某字段，不等于包装上实际缺少该字段；核查结论中的「需要进一步核实」表示需要人工确认。</li>
          <li>规则依据仅以标准名称级别引用，系统未收录标准原文，具体条款请查阅现行有效的官方文本。</li>
          <li>报告内容可由浏览器打印或另存为 PDF，保存的版本以打印时刻的页面内容为准。</li>
        </ul>
      </section>

      <footer class="report-footer">
        <span>{{ report.meta.app_name }} v{{ report.meta.app_version }}</span>
        <span>报告编号 {{ report.report.report_no }}</span>
        <span>生成于 {{ formatDate(report.report.generated_at, true) }}</span>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.health-top {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 10px;
}

.health-score {
  width: 86px;
  height: 86px;
  border: 2px solid #0f7b6c;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.health-score strong {
  font-size: 26px;
  line-height: 1;
  color: #0f7b6c;
}

.health-score span {
  font-size: 10px;
  color: #666;
}

.health-meta {
  min-width: 0;
}

.health-grade {
  margin: 0 0 4px;
  font-weight: 700;
  color: #0f7b6c;
  font-size: 14px;
}

.health-headline {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: #444;
}

.health-findings {
  margin: 0 0 10px;
  padding-left: 16px;
  display: grid;
  gap: 8px;
}

.health-finding-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.health-level {
  font-size: 10px;
  border: 1px solid #d8e3df;
  border-radius: 999px;
  padding: 1px 7px;
  color: #555;
  flex-shrink: 0;
}

.health-finding-summary {
  margin: 3px 0;
  font-size: 11.5px;
  line-height: 1.7;
}

.health-finding-detail,
.health-finding-basis {
  margin: 0;
  font-size: 10.5px;
  color: #666;
  line-height: 1.7;
}

.health-disclaimer {
  margin: 8px 0 0;
  padding: 7px 10px;
  border: 1px dashed #e0cba8;
  background: #fdf8ef;
  color: #7a5a1e;
  font-size: 10.5px;
  line-height: 1.7;
}

.report-page {
  background: #eef2f1;
  min-height: 100vh;
  padding-bottom: 40px;
}

.report-toolbar {
  position: sticky;
  top: 0;
  z-index: 12;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 20px;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.toolbar-title {
  font-size: 15px;
  font-weight: 650;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.report-shell {
  width: 100%;
  max-width: 900px;
  margin: 18px auto;
  background: var(--card);
  border-radius: 6px;
  box-shadow: 0 10px 30px rgba(16, 36, 30, 0.1);
  padding: 34px 38px 26px;
  position: relative;
}

.report-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--brand);
  flex-wrap: wrap;
}

.head-left {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
}

.head-title h1 {
  font-size: 22px;
  letter-spacing: 0.4px;
}

.head-title p {
  font-size: 11.5px;
  color: var(--muted);
  margin-top: 2px;
}

.head-right {
  text-align: right;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.8;
}

.report-no {
  font-weight: 700;
  color: var(--text);
  font-size: 12.5px;
}

.demo-stamp {
  margin-top: 12px;
  display: inline-block;
  border: 1.5px solid var(--danger);
  color: var(--danger);
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
  transform: rotate(-1.2deg);
}

.report-section {
  margin-top: 22px;
}

.report-section h2 {
  font-size: 15px;
  padding-left: 9px;
  border-left: 3px solid var(--brand);
  margin-bottom: 10px;
  line-height: 1.4;
}

.report-section h3 {
  font-size: 13px;
  margin: 12px 0 6px;
  color: var(--text-2);
}

.info-table,
.field-table,
.ingredient-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.info-table th,
.info-table td,
.field-table th,
.field-table td,
.ingredient-table th,
.ingredient-table td {
  border: 1px solid #e6ebe9;
  padding: 7px 9px;
  text-align: left;
  vertical-align: top;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

/* 基本信息：用网格代替四列表格，移动端自动堆叠 */
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: #e6ebe9;
  border: 1px solid #e6ebe9;
  border-radius: 6px;
  overflow: hidden;
}

.info-cell {
  background: var(--card);
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.info-k {
  font-size: 10.5px;
  color: var(--muted);
  letter-spacing: 0.2px;
}

.info-v {
  font-size: 12.5px;
  color: var(--text);
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.desktop-only {
  display: table;
}

.mobile-only {
  display: none;
}

.ingredient-cards {
  display: none;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.ing-card {
  border: 1px solid #e6ebe9;
  border-radius: 8px;
  padding: 10px 11px;
}

.ing-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.ing-index {
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: var(--brand-100);
  color: var(--brand-700);
  display: inline-grid;
  place-items: center;
  font-size: 10px;
  font-weight: 700;
}

.ing-name {
  font-size: 13.5px;
  font-weight: 700;
}

.ing-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 10.5px;
  color: var(--muted);
  margin-top: 4px;
}

.ing-explain {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.75;
  color: var(--text-2);
}

.info-table th,
.field-table th {
  background: var(--surface-2);
  color: var(--muted);
  font-weight: 600;
  width: 92px;
  white-space: nowrap;
}

.field-table td.empty {
  color: var(--muted);
}

.report-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 210px;
  gap: 16px;
  align-items: start;
}

.report-image {
  text-align: center;
}

.image-caption {
  margin-top: 5px;
  font-size: 10.5px;
  color: var(--muted);
}

.section-note {
  margin-top: 7px;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}

.text-block pre {
  margin: 0;
  padding: 10px 12px;
  background: var(--surface-2);
  border: 1px solid #e6ebe9;
  border-radius: 6px;
  font-family: 'Cascadia Mono', Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow: auto;
}

.mode-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.summary-line {
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--text-2);
  background: var(--brand-50);
  border-left: 3px solid var(--brand);
  padding: 8px 11px;
  border-radius: 4px;
}

.ingredient-table {
  margin-top: 10px;
}

.ingredient-table th {
  background: var(--surface-2);
  color: var(--muted);
  font-weight: 600;
  font-size: 11.5px;
}

.ingredient-table td {
  font-size: 12px;
}

.strong {
  font-weight: 700;
  color: var(--text);
}

.item-purpose {
  font-weight: 600;
  color: var(--brand-700);
  margin-bottom: 2px;
}

.item-caution {
  color: var(--warn);
  margin-top: 3px;
  font-size: 11.5px;
}

.refs {
  font-size: 10.5px;
  color: var(--muted);
  margin-top: 2px;
}

.sub-note {
  margin-top: 9px;
  font-size: 11.5px;
  color: var(--text-2);
  line-height: 1.75;
}

.sub-note ul {
  margin: 3px 0 0;
  padding-left: 18px;
}

.disclaimer-line {
  margin-top: 10px;
  font-size: 10.5px;
  color: var(--muted);
  line-height: 1.7;
  border-top: 1px dashed #e6ebe9;
  padding-top: 7px;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.source-item {
  border: 1px solid #e6ebe9;
  border-radius: 6px;
  padding: 8px 10px;
}

.source-title {
  font-size: 12.5px;
  font-weight: 650;
}

.source-meta {
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
}

.source-claim {
  font-size: 11.5px;
  color: var(--text-2);
  margin-top: 3px;
  line-height: 1.65;
}

.source-url {
  font-size: 10.5px;
  color: var(--brand);
  word-break: break-all;
}

.rule-source-title {
  margin-top: 16px !important;
}

.rule-source-list {
  margin: 0;
  padding-left: 18px;
  font-size: 11.5px;
  color: var(--text-2);
  line-height: 1.8;
}

.rule-source-name {
  font-weight: 600;
}

.rule-source-note {
  color: var(--muted);
  margin-left: 5px;
  font-size: 10.5px;
}

.boundary-list {
  margin: 0;
  padding-left: 18px;
  font-size: 11.5px;
  color: var(--text-2);
  line-height: 1.9;
}

.disclaimer-section {
  background: #fbfcfb;
  border: 1px solid #e6ebe9;
  border-radius: 6px;
  padding: 12px 14px;
}

.report-footer {
  margin-top: 24px;
  padding-top: 10px;
  border-top: 1px solid #e6ebe9;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 10.5px;
  color: var(--muted);
}

@media (max-width: 768px) {
  .report-shell {
    margin: 10px auto;
    width: auto;
    padding: 20px 16px 18px;
    border-radius: 10px;
  }
  .report-head {
    flex-direction: column;
    gap: 10px;
  }
  .head-right {
    text-align: left;
  }
  .head-title h1 {
    font-size: 18px;
  }
  .info-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .desktop-only {
    display: none !important;
  }
  .mobile-only {
    display: block !important;
  }
  .ingredient-cards.mobile-only {
    display: flex !important;
  }
  .report-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .report-image {
    max-width: 260px;
  }
  .info-table th {
    width: 76px;
    font-size: 11.5px;
  }
  .info-table td,
  .field-table td {
    font-size: 12px;
  }
  .field-table th {
    width: 84px;
    font-size: 11.5px;
  }
  .toolbar-actions :deep(.el-button) {
    flex: 1 1 auto;
  }
}

/* 打印样式统一放在文件末尾的全局 @media print 中 */

/* 原始技术数据折叠 */
.raw-details {
  border: 1px solid #e5eee8;
  border-radius: 10px;
  background: #fafcfb;
  overflow: hidden;
}

.raw-details > summary {
  padding: 11px 14px;
  color: #34775e;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.raw-details > summary::-webkit-details-marker {
  display: none;
}

.raw-details > summary::before {
  content: '▸';
  display: inline-block;
  margin-right: 7px;
  transition: transform 0.16s ease;
}

.raw-details[open] > summary::before {
  transform: rotate(90deg);
}

.raw-details .text-block {
  margin: 0 12px 12px;
}

/* 健康评分等级色 */
.health-score.is-green {
  border-color: #2f9b6f;
  background: #effaf4;
}

.health-score.is-green strong {
  color: #22845b;
}

.health-score.is-amber {
  border-color: #d99a2b;
  background: #fff9ec;
}

.health-score.is-amber strong {
  color: #b87817;
}

.health-score.is-red {
  border-color: #d9534f;
  background: #fff3f1;
}

.health-score.is-red strong {
  color: #bf4a43;
}


/* 识饭菜：视觉估算说明卡 */
.dish-estimate-card {
  padding: 18px 20px;
  border: 1px solid #dcecf3;
  border-radius: 14px;
  background: linear-gradient(135deg, #f4fafc 0%, #f8fbfa 100%);
}

.dish-estimate-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.dish-estimate-icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: #e8f4fa;
  font-size: 15px;
}

.dish-estimate-head strong {
  color: #2f5f73;
  font-size: 14px;
}

.dish-estimate-confidence {
  margin-left: auto;
  padding: 3px 9px;
  border: 1px solid #d1e6ef;
  border-radius: 999px;
  background: #ffffff;
  color: #558297;
  font-size: 10.5px;
  font-weight: 650;
}

.dish-estimate-card > p {
  margin: 10px 0 0;
  color: #4d6b78;
  font-size: 12.5px;
  line-height: 1.8;
}

.dish-estimate-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #dceaf0;
  color: #78939e;
  font-size: 10.5px;
}

</style>


<style>
/*
 * 报告打印专用样式：
 * 全部规则只在 @media print 生效，网页端视觉完全不变。
 */
@page {
  size: A4;
  margin: 15mm;
}

@media print {
  html,
  body,
  #app,
  .app-shell {
    width: auto !important;
    height: auto !important;
    min-height: 0 !important;
    overflow: visible !important;
    background: #fff !important;
  }

  body {
    margin: 0 !important;
    padding: 0 !important;
    color: #111 !important;
    font-size: 11pt;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  /* 网页端所有导航、操作、悬浮球、提示条 */
  .app-sidebar,
  .app-header,
  .mobile-header,
  .mobile-tabbar,
  .ai-launcher,
  .offline-banner,
  .report-toolbar,
  .no-print,
  .el-message,
  .el-message-box__wrapper,
  .el-notification,
  .el-overlay,
  .el-drawer__wrapper,
  .el-backtop {
    display: none !important;
  }

  .app-main,
  .page,
  .report-page {
    width: 100% !important;
    max-width: none !important;
    height: auto !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
    background: #fff !important;
  }

  .report-page {
    color: #111 !important;
    font-size: 11pt !important;
  }

  .report-shell {
    width: 100% !important;
    max-width: none !important;
    height: auto !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: #fff !important;
    box-shadow: none !important;
  }

  /* 打印报告一律单列，不再继承网页端 Grid / Flex 两栏 */
  .report-head,
  .head-left,
  .head-right,
  .info-grid,
  .info-cell,
  .report-grid,
  .health-top,
  .health-meta,
  .health-finding-head,
  .mode-line,
  .dish-estimate-head,
  .chart-grid {
    display: block !important;
    width: 100% !important;
    max-width: none !important;
    grid-template-columns: none !important;
    flex-direction: column !important;
    align-items: stretch !important;
    text-align: left !important;
  }

  .head-left {
    margin-bottom: 8px !important;
  }

  .head-right {
    margin-top: 8px !important;
    text-align: left !important;
    line-height: 1.6 !important;
  }

  .report-head {
    padding-bottom: 10px !important;
    border-bottom: 1.5px solid #000 !important;
  }

  .head-title h1 {
    margin: 0 !important;
    font-size: 20pt !important;
    color: #111 !important;
  }

  .head-title p,
  .report-time,
  .report-no {
    color: #333 !important;
  }

  .demo-stamp {
    margin: 8px 0 0 !important;
    color: #b00020 !important;
    border-color: #b00020 !important;
  }

  /* 取消高度限制、滚动条和 overflow 裁切 */
  .report-page *,
  .report-shell * {
    max-height: none !important;
  }

  .report-page .report-section,
  .report-page .report-grid,
  .report-page .info-grid,
  .report-page .raw-details,
  .report-page .text-block,
  .report-page .text-block pre,
  .report-page .table-wrap,
  .report-page .auth-image,
  .report-page .card {
    overflow: visible !important;
  }

  .report-section {
    margin-top: 14px !important;
    break-inside: auto !important;
    page-break-inside: auto !important;
    color: #111 !important;
  }

  .report-section h2 {
    margin: 0 0 8px !important;
    padding-left: 8px !important;
    border-left: 3px solid #000 !important;
    color: #111 !important;
    font-size: 13pt !important;
    break-after: avoid !important;
    page-break-after: avoid !important;
  }

  .report-section h3 {
    color: #111 !important;
    break-after: avoid !important;
    page-break-after: avoid !important;
  }

  .report-page p,
  .report-page li,
  .report-page span,
  .report-page div,
  .report-page td,
  .report-page th,
  .report-page strong,
  .report-page small,
  .report-page h1,
  .report-page h2,
  .report-page h3 {
    color: #111 !important;
  }

  /* 基本信息：单列堆叠，字段不再被两栏或 overflow 截断 */
  .info-grid {
    border: 1px solid #000 !important;
    border-radius: 0 !important;
    background: #fff !important;
  }

  .info-cell {
    display: block !important;
    padding: 5px 8px !important;
    border: 0 !important;
    border-bottom: 1px solid #999 !important;
    background: #fff !important;
  }

  .info-cell:last-child {
    border-bottom: 0 !important;
  }

  .info-k {
    display: block !important;
    width: auto !important;
    margin-bottom: 2px !important;
    color: #333 !important;
    font-size: 9.5pt !important;
    font-weight: 700 !important;
  }

  .report-page .detail-label {
    display: inline !important;
    width: auto !important;
    margin-right: 5px !important;
  }

  .report-page .detail-text {
    display: inline !important;
    width: auto !important;
  }

  .info-v {
    display: block !important;
    color: #111 !important;
    font-size: 10.5pt !important;
    line-height: 1.6 !important;
    overflow-wrap: anywhere !important;
  }

  /* 所有表格统一黑框、内边距与标题列宽度 */
  .report-page table {
    width: 100% !important;
    max-width: 100% !important;
    margin: 8px 0 !important;
    border: 1px solid #000 !important;
    border-collapse: collapse !important;
    table-layout: fixed !important;
    font-size: 9.5pt !important;
    page-break-inside: auto !important;
  }

  .report-page thead {
    display: table-header-group !important;
  }

  .report-page table th,
  .report-page table td {
    border: 1px solid #000 !important;
    padding: 8px !important;
    color: #111 !important;
    background: #fff !important;
    text-align: left !important;
    vertical-align: top !important;
    line-height: 1.5 !important;
    overflow-wrap: anywhere !important;
    word-break: break-word !important;
  }

  .report-page table th {
    font-weight: 700 !important;
    background: #f2f2f2 !important;
  }

  .report-page table tr {
    break-inside: avoid !important;
    page-break-inside: avoid !important;
  }

  /* 标签字段表：标题列固定宽度 */
  .report-page .field-table th {
    width: 34mm !important;
  }

  .report-page .ingredient-table th:nth-child(1) {
    width: 10mm !important;
  }

  .report-page .ingredient-table th:nth-child(2) {
    width: 25mm !important;
  }

  .report-page .ingredient-table th:nth-child(3) {
    width: 22mm !important;
  }

  .report-page .ingredient-table th:nth-child(5) {
    width: 20mm !important;
  }

  .report-page .ingredient-table th:nth-child(6) {
    width: 16mm !important;
  }

  .report-page .nutri-table th:first-child {
    width: 38mm !important;
  }

  .report-page .table-wrap {
    overflow: visible !important;
  }

  .report-page .nutri-table {
    min-width: 0 !important;
  }

  /* 图片限宽 50%，居中，避免一整页只放一张图 */
  .report-grid {
    display: block !important;
  }

  .report-image {
    display: block !important;
    width: 50% !important;
    max-width: 50% !important;
    margin: 10px auto 0 !important;
    text-align: center !important;
    break-inside: avoid !important;
    page-break-inside: avoid !important;
  }

  .report-image .auth-image {
    display: block !important;
    width: 100% !important;
    height: auto !important;
    aspect-ratio: auto !important;
    overflow: visible !important;
    border: 0 !important;
    background: #fff !important;
  }

  .report-image img {
    display: block !important;
    width: auto !important;
    max-width: 100% !important;
    height: auto !important;
    max-height: 100mm !important;
    margin: 0 auto !important;
    object-fit: contain !important;
  }

  .report-image .zoom-btn {
    display: none !important;
  }

  .image-caption {
    margin-top: 3px !important;
    color: #333 !important;
    font-size: 9pt !important;
  }

  /* 图表打印时单列，使用打印前生成的 Base64 图片替代 canvas */
  .report-page .chart-grid {
    display: block !important;
  }

  .report-page .chart-box {
    height: 48mm !important;
    min-height: 0 !important;
  }

  .report-page .chart-print-image {
    display: block !important;
    width: 100% !important;
    height: auto !important;
    max-height: 48mm !important;
    object-fit: contain !important;
    margin: 0 auto !important;
  }

  .report-page .chart-box.is-print-ready .chart-canvas {
    display: none !important;
  }

  /* 没有成功生成图片的图表不打印，避免只剩坐标轴/大白块 */
  .report-page .chart-box:not(.is-print-ready),
  .report-page .chart-box.is-empty,
  .report-page .chart-block:has(.chart-box.is-empty) {
    display: none !important;
  }

  .report-page .chart-grid:not(:has(.chart-box.is-print-ready)) {
    display: none !important;
  }

  /* 左上角 Logo：SVG 之外再给实色底，确保打印引擎不会丢图 */
  .report-head .brand {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
  }

  .report-head .brand .mark {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    background: #0f7b6c !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .report-head .brand .mark svg {
    display: block !important;
    visibility: visible !important;
    width: 100% !important;
    height: 100% !important;
  }

  .chart-block,
  .health-top,
  .health-findings li,
  .dish-estimate-card,
  .source-item,
  .report-footer {
    break-inside: avoid !important;
    page-break-inside: avoid !important;
  }

  /* 核查规则条目可能很长，允许跨页，避免整段被推到下一页产生空白 */
  .report-page .rule-item {
    break-inside: auto !important;
    page-break-inside: auto !important;
  }

  .report-page canvas {
    max-width: 100% !important;
    height: auto !important;
  }

  .report-page .chart-block {
    display: block !important;
    width: 100% !important;
    margin-bottom: 10px !important;
  }

  /* 打印时不需要的交互元素 */
  .report-page button,
  .report-page .zoom-btn,
  .report-page .filter-row,
  .report-page .detail-toggle,
  .report-page .mobile-only {
    display: none !important;
  }

  .report-page .desktop-only {
    display: table !important;
  }

  /* 原始技术文本默认折叠，纸质报告不展开，避免出现空标题 */
  .report-page .raw-section {
    display: none !important;
  }

  .report-page .text-block pre {
    white-space: pre-wrap !important;
    word-break: break-word !important;
    page-break-inside: auto !important;
  }

  .report-page .summary-line,
  .report-page .section-note,
  .report-page .disclaimer-line,
  .report-page .health-disclaimer {
    border-radius: 0 !important;
    box-shadow: none !important;
  }

  .report-page a[href]::after {
    content: '' !important;
  }

  .report-footer {
    margin-top: 14px !important;
    padding-top: 8px !important;
    border-top: 1px solid #000 !important;
    color: #333 !important;
    font-size: 9pt !important;
  }
}
</style>

