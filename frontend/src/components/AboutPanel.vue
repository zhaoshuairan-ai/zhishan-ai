<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import BrandMark from '@/components/BrandMark.vue'

const router = useRouter()
const app = useAppStore()
const currentVersion = computed(() => app.settings?.app.version || '1.0.0')

const features = [
  { icon: 'Camera', title: '多模态食安检测', desc: '拍照识别配料表与营养成分，快速测算热量并给出标签解读。' },
  { icon: 'Document', title: 'OCR 健康建档', desc: '解析体检单与健康信息，自动构建可持续更新的个人健康画像。' },
  { icon: 'MagicStick', title: '智能配餐 Agent', desc: '结合家庭库存、健康目标与预算，生成可执行的一日三餐食谱。' },
  { icon: 'Reading', title: 'RAG 智询官', desc: '基于国标与权威知识库检索增强问答，答案可溯源、防幻觉。' },
]

const stack = [
  { group: '前端', items: ['Vue 3', 'Vite', 'TypeScript', 'Element Plus', 'Vue Router', 'Pinia', 'Axios', 'ECharts'] },
  { group: '后端', items: ['Python 3.12', 'Flask', 'Flask-CORS', 'SQLAlchemy', 'SQLite', 'Pydantic v2'] },
  { group: '识别与 AI', items: ['RapidOCR（本地 ONNX）', 'OpenAI 兼容视觉模型', 'OpenAI 兼容大语言模型', 'JSON Schema 校验'] },
  { group: '工程化', items: ['pytest', 'Playwright 响应式测试', 'PWA / Service Worker', 'Gunicorn / Waitress'] },
]

const innovations = [
  {
    title: '「识别—校正—解读—核查」四段式闭环',
    desc: '把 OCR 不确定性显式暴露给用户：原始文本与校正文本同时入库，低置信度字段高亮，保证后续分析建立在可核对的数据之上。',
  },
  {
    title: '零 Key 可运行的真实 OCR',
    desc: '内置本地 OCR 引擎，离线即可真实识别中文标签；未配置大模型时自动降级为知识库规则模式，并在全站显著标注模式，绝不伪装。',
  },
  {
    title: '可追溯的证据链',
    desc: '每条配料解释都带知识库编号、来源名称与核验状态；每条核查结论都带规则版本、依据与待确认事项。',
  },
  {
    title: '审慎的核查结论体系',
    desc: '只使用「未发现明显问题 / 需要进一步核实 / 发现疑似问题」三档，并明确说明无法从图片判断的内容，避免过度结论。',
  },
]

const boundaries = [
  '只读取包装上可见的文字，不做实验检测，无法判断微生物、农药残留、重金属、真菌毒素等指标。',
  '图片未拍到某字段 ≠ 包装上缺少该字段；「需要进一步核实」不等于「食品不安全」。',
  '食品添加剂只解释用途，不做「有毒/有害」判断；合规性取决于品种、范围与用量，需要检测与监管数据。',
  'AI 结果可能存在误差或幻觉，系统会做结构校验与引用过滤，但仍不能作为安全性或合规性结论。',
  '规则依据以标准名称级别引用，系统未收录标准原文，不构成合规认定。',
]
</script>

<template>
  <div class="about-panel">
    <div class="about-hero">
      <BrandMark />
      <p class="hero-sub">面向大众消费者与慢病人群的全场景 AI 健康膳食管家</p>
      <div class="hero-tags">
        <span class="chip">真实 OCR</span>
        <span class="chip">可追溯知识库</span>
        <span class="chip">响应式 + PWA</span>
        <span class="chip chip-muted">v{{ currentVersion }}</span>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="router.push({ name: 'analyze' })">
          <el-icon><Camera /></el-icon>
          立即体验
        </el-button>
        <el-button @click="router.push({ name: 'knowledge' })">浏览知识库</el-button>
      </div>
    </div>

    <section class="about-section">
      <h3>项目定位</h3>
      <p>
        面向大众消费者与慢病人群的全场景 AI 健康膳食管家。结合多模态视觉识别、健康画像构建与 RAG 检索增强技术，
        提供从食品标签解读、热量测算到个性化食谱规划的完整闭环解决方案。
      </p>
    </section>

    <section class="about-section">
      <h3>核心功能</h3>
      <div class="feature-grid">
        <div v-for="feature in features" :key="feature.title" class="feature-item">
          <span class="feature-icon"><el-icon><component :is="feature.icon" /></el-icon></span>
          <div>
            <strong>{{ feature.title }}</strong>
            <p>{{ feature.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="about-section">
      <h3>技术栈</h3>
      <div class="stack-grid">
        <div v-for="group in stack" :key="group.group" class="stack-group">
          <div class="stack-title">{{ group.group }}</div>
          <div class="stack-items">
            <span v-for="item in group.items" :key="item" class="stack-chip">{{ item }}</span>
          </div>
        </div>
      </div>
    </section>

    <section class="about-section">
      <h3>项目创新点</h3>
      <ol class="innovation-list">
        <li v-for="item in innovations" :key="item.title">
          <strong>{{ item.title }}</strong>
          <p>{{ item.desc }}</p>
        </li>
      </ol>
    </section>

    <section class="about-section">
      <h3>功能边界</h3>
      <ul class="boundary-list">
        <li v-for="item in boundaries" :key="item">{{ item }}</li>
      </ul>
    </section>

    <p class="about-footer">
      智膳 AI v{{ currentVersion }} · 本项目为比赛作品，不构成医疗诊断或官方检测结论
    </p>
  </div>
</template>

<style scoped>
.about-panel {
  color: var(--text-1);
}

.about-hero {
  text-align: center;
  padding: 4px 0 16px;
  border-bottom: 1px dashed var(--border);
  margin-bottom: 14px;
}

.about-hero :deep(.brand) {
  justify-content: center;
}

.hero-sub {
  margin: 10px 0 8px;
  font-size: 13px;
  color: var(--muted);
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  margin-bottom: 12px;
}

.chip {
  font-size: 11.5px;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--brand-50);
  color: var(--brand-700);
}

.chip-muted {
  background: #f3f6f5;
  color: var(--muted);
}

.hero-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}

.about-section {
  margin-bottom: 18px;
}

.about-section h3 {
  margin: 0 0 8px;
  font-size: 14.5px;
}

.about-section p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--text-2);
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 8px;
}

.feature-item {
  display: flex;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
}

.feature-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: var(--brand-50);
  color: var(--brand-700);
  flex-shrink: 0;
}

.feature-item strong {
  font-size: 12.5px;
}

.feature-item p {
  margin: 3px 0 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--muted);
}

.stack-grid {
  display: grid;
  gap: 8px;
}

.stack-title {
  font-size: 11.5px;
  color: var(--muted);
  margin-bottom: 4px;
}

.stack-items {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.stack-chip {
  font-size: 11.5px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--surface-2);
  color: var(--text-2);
}

.innovation-list {
  margin: 0;
  padding-left: 18px;
}

.innovation-list li {
  margin-bottom: 8px;
}

.innovation-list strong {
  font-size: 12.5px;
}

.innovation-list p {
  margin: 2px 0 0;
  font-size: 11.5px;
}

.boundary-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.9;
  color: var(--text-2);
}

.about-footer {
  margin: 4px 0 0;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
  text-align: center;
  font-size: 11px;
  color: var(--muted);
}

@media (max-width: 767px) {
  .feature-grid {
    grid-template-columns: 1fr;
  }
}
</style>
