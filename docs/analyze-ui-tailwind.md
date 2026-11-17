# 拍照识别页 UI 改造：TailwindCSS 版本

> 当前仓库是 **Vue 3 + Element Plus + scoped CSS**，`package.json` 中没有安装 Tailwind。
> 为了避免为了一个页面引入整套构建链，实际页面使用等价的 scoped CSS 实现；
> 下面给出可直接迁移到 Tailwind 的类名、状态与组件结构。

## 1. 状态管理

```ts
// useAnalyzeTab.ts
import { computed, ref } from 'vue'

export type AnalyzeTab = 'packaging' | 'dish'

export interface AnalyzeMode {
  label: string
  title: string
  hint: string
  thinking: string
  tips: Array<{ icon: string; title: string; desc: string }>
  steps: Array<{ title: string; tag?: string; desc: string }>
}

export const ANALYZE_MODES: Record<AnalyzeTab, AnalyzeMode> = {
  packaging: {
    label: '识包装',
    title: '开启 AI 食品透视',
    hint: '请上传清晰的包装背面标签',
    thinking: '从包装标签中提取配料、添加剂与营养信息。',
    tips: [
      { icon: '🎯', title: '正面对象', desc: '标签正对镜头，文字清晰' },
      { icon: '☀️', title: '避开反光', desc: '侧一点拍，减少反光' },
      { icon: '🧩', title: '分区拍摄', desc: '配料、营养表分开拍' },
    ],
    steps: [
      { title: '视觉提取', tag: '配料', desc: '精准识别配料表与添加剂' },
      { title: '提取红线', tag: '国标', desc: '匹配 GB 2760 与健康画像' },
      { title: '营养测算', desc: '计算热量与宏量营养素' },
      { title: '风险拦截', desc: '如：苯丙酮尿症患者需避开阿斯巴甜' },
    ],
  },
  dish: {
    label: '识饭菜',
    title: '开启 AI 膳食分析',
    hint: '请上传清晰的菜品俯拍照片',
    thinking: '识别菜品与重量，查库拆解三大营养素，再结合健康目标预警。',
    tips: [
      { icon: '📐', title: '俯拍全貌', desc: '菜品完整入镜' },
      { icon: '💡', title: '光线充足', desc: '避免阴影遮挡' },
      { icon: '🍚', title: '主食配菜同框', desc: '方便估算总量' },
    ],
    steps: [
      { title: '视觉提取', tag: '识别菜品与重量', desc: '识别菜名并估算可食用克数' },
      { title: '营养拆解', tag: '查库算三大营养素', desc: '检索菜品库，换算碳水、蛋白质、脂肪' },
      { title: '画像匹配', tag: '结合健康目标', desc: '结合减脂、控糖、增肌等目标' },
      { title: '营养素预警', tag: '脂肪占比过高', desc: '如脂肪供能占比过高，提示下一餐平衡' },
    ],
  },
}

export function useAnalyzeTab() {
  // 当前项目请求后端时仍用 package / dish；模板层统一用 packaging / dish。
  const activeTab = ref<AnalyzeTab>('packaging')
  const mode = computed(() => ANALYZE_MODES[activeTab.value])

  function resetForTabChange() {
    // 切换 Tab 时清空已选图片，避免包装图跑菜品分析
  }

  return { activeTab, mode, resetForTabChange }
}
```

React 对应写法：

```tsx
const [activeTab, setActiveTab] = useState<AnalyzeTab>('packaging')
const mode = ANALYZE_MODES[activeTab]
```

## 2. 组件结构

```text
AnalyzePage
├── AppShell
│   ├── DesktopSidebar        hidden md:flex
│   ├── MobileHeader          md:hidden
│   ├── AnalyzeTabs           识包装 / 识饭菜
│   ├── UploadHero
│   │   ├── ModeIcon           📦 或餐盘 Icon
│   │   ├── ModeTitle          开启 AI 食品透视 / 开启 AI 膳食分析
│   │   ├── UploadActions      拍照、相册、扫码
│   │   └── ShootingTips       三项拍摄技巧
│   ├── ThinkingPanel         右侧四步流程
│   └── MobileBottomNav       fixed bottom-0 grid-cols-4 md:hidden
└── UploadPreview / Result
```

## 3. App Shell 与移动端 Bottom Navigation

```vue
<div class="min-h-screen bg-[#F4F8F5]">
  <!-- 桌面侧栏：<768px 隐藏 -->
  <aside
    class="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r
           border-emerald-100/80 bg-white px-4 py-5 md:flex"
  >
    <!-- brand / nav -->
  </aside>

  <!-- 移动端顶部栏 -->
  <header
    class="sticky top-0 z-30 flex h-14 items-center justify-between
           border-b border-emerald-100/80 bg-white/95 px-4 backdrop-blur md:hidden"
  >
    <button class="grid h-10 w-10 place-items-center rounded-xl text-slate-600">
      ☰
    </button>
    <strong class="text-[15px] font-semibold text-slate-800">AI 营养解析与评估</strong>
  </header>

  <!-- 主内容：手机上给底部导航留出空间 -->
  <main class="pb-[calc(72px+env(safe-area-inset-bottom))] md:pb-0 md:pl-64">
    <slot />
  </main>

  <!-- 手机底部导航：<768px 显示 -->
  <nav
    class="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t
           border-emerald-100 bg-white/95 px-2 pb-[env(safe-area-inset-bottom)]
           pt-1.5 backdrop-blur md:hidden"
  >
    <button
      v-for="item in mobileNav"
      :key="item.name"
      class="flex min-h-[48px] flex-col items-center justify-center gap-0.5
             rounded-xl text-[11px] text-slate-400 active:bg-emerald-50"
      :class="item.name === $route.name
        ? 'font-semibold text-emerald-600'
        : 'text-slate-400'"
    >
      <span class="text-xl">{{ item.icon }}</span>
      <span>{{ item.label }}</span>
    </button>
  </nav>
</div>
```

移动端导航四项：

```ts
const mobileNav = [
  { name: 'home', label: '首页', icon: '🏠' },
  { name: 'analyze', label: '检测', icon: '📷' },
  { name: 'knowledge', label: '知识库', icon: '📚' },
  { name: 'settings', label: '我的', icon: '👤' },
]
```

## 4. Tab 切换

```vue
<div class="mx-auto flex w-fit items-center gap-1 rounded-2xl bg-emerald-50 p-1">
  <button
    v-for="tab in tabs"
    :key="tab.value"
    class="rounded-xl px-5 py-2 text-sm font-medium transition"
    :class="activeTab === tab.value
      ? 'bg-white text-emerald-700 shadow-sm ring-1 ring-emerald-100'
      : 'text-slate-500 hover:text-emerald-700'"
    @click="activeTab = tab.value"
  >
    {{ tab.label }}
  </button>
</div>
```

## 5. 中间上传 Hero 面板

```vue
<section
  class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]"
>
  <div
    class="flex flex-col items-center justify-center rounded-[32px] border
           border-emerald-100 bg-white px-6 py-10 text-center
           shadow-[0_18px_50px_-24px_rgba(15,123,108,0.35)]"
  >
    <!-- 模式图标 -->
    <div
      class="grid h-24 w-24 place-items-center rounded-[30px]
             bg-gradient-to-br from-emerald-900 via-emerald-700 to-emerald-500
             shadow-[0_18px_36px_-12px_rgba(11,61,46,0.45)]"
    >
      <!-- import PlateIcon from '@/components/PlateIcon.vue' -->
      <PlateIcon v-if="activeTab === 'dish'" class="h-[76px] w-[76px]" />
      <span v-else class="text-5xl">📦</span>
    </div>

    <span class="mt-5 text-[10px] font-bold tracking-[0.18em] text-emerald-900/35">
      AI FOOD VISION
    </span>
    <h1 class="mt-1 text-3xl font-extrabold tracking-tight text-slate-900">
      {{ mode.title }}
    </h1>
    <p class="mt-2 text-sm font-medium text-emerald-900/55">
      {{ mode.hint }}
    </p>

    <div class="mt-6 flex flex-wrap items-center justify-center gap-3">
      <button class="rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-600/20">
        📷 拍照/上传图片
      </button>
      <button class="rounded-xl border border-emerald-200 bg-white px-5 py-2.5 text-sm font-semibold text-emerald-700">
        📁 从相册选择
      </button>
    </div>
  </div>

  <!-- 右侧 AI 思考过程 -->
  <aside class="rounded-[28px] border border-emerald-100 bg-white p-6 shadow-sm">
    <p class="text-[10px] font-bold tracking-[0.14em] text-emerald-900/35">AI THINKING</p>
    <h2 class="mt-1 text-lg font-bold text-slate-900">AI 的思考过程</h2>
    <p class="mt-1 text-xs leading-6 text-slate-400">{{ mode.thinking }}</p>

    <ol class="mt-5 space-y-5">
      <li v-for="(step, index) in mode.steps" :key="step.title" class="flex gap-3">
        <span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-500 ring-4 ring-emerald-50" />
        <div>
          <p class="text-sm font-semibold text-slate-700">
            {{ index + 1 }}. {{ step.title }}
            <span v-if="step.tag" class="ml-1 text-[11px] font-normal text-slate-400">
              ({{ step.tag }})
            </span>
          </p>
          <p class="mt-0.5 text-xs leading-5 text-slate-400">{{ step.desc }}</p>
        </div>
      </li>
    </ol>
  </aside>

  <!-- 底部拍摄技巧 -->
  <div class="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:col-span-2">
    <div
      v-for="tip in mode.tips"
      :key="tip.title"
      class="rounded-2xl border border-emerald-100/80 bg-emerald-50/60 p-4"
    >
      <span class="text-xl">{{ tip.icon }}</span>
      <p class="mt-2 text-sm font-semibold text-slate-700">{{ tip.title }}</p>
      <p class="mt-1 text-xs leading-5 text-slate-400">{{ tip.desc }}</p>
    </div>
  </div>
</section>
```

## 6. 关键 Tailwind 类名速查

| 区域 | 类名 |
| --- | --- |
| 手机隐藏侧栏 | `hidden md:flex` |
| 手机显示底栏 | `fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 md:hidden` |
| 主内容避让底栏 | `pb-[calc(72px+env(safe-area-inset-bottom))] md:pb-0 md:pl-64` |
| Tab 容器 | `mx-auto flex w-fit items-center gap-1 rounded-2xl bg-emerald-50 p-1` |
| Tab 激活态 | `bg-white text-emerald-700 shadow-sm ring-1 ring-emerald-100` |
| 中间大标题 | `mt-1 text-3xl font-extrabold tracking-tight text-slate-900` |
| 右侧卡片 | `rounded-[28px] border border-emerald-100 bg-white p-6 shadow-sm` |
| 步骤序号 | `text-sm font-semibold text-slate-700` |
| 拍摄技巧网格 | `grid grid-cols-1 gap-3 sm:grid-cols-3` |
| 技巧卡片 | `rounded-2xl border border-emerald-100/80 bg-emerald-50/60 p-4` |

> `md:` 在 Tailwind 中正好是 `min-width: 768px`，所以 `md:hidden` / `md:flex`
> 与“手机 <768px 隐藏侧栏、显示底部导航”的要求一致。