<script setup lang="ts">

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import { ElMessage, ElMessageBox } from 'element-plus'

import { useAppStore } from '@/stores/app'

import { useAuthStore } from '@/stores/auth'

import { useUiStore } from '@/stores/ui'

import { feedbackApi, recordApi, type MyFeedbackItem } from '@/api'

import type { RecordSummary } from '@/api/types'

import { ApiError } from '@/api/client'

import { formatBytes } from '@/utils/format'

import AboutPanel from '@/components/AboutPanel.vue'



const app = useAppStore()

const auth = useAuthStore()

const ui = useUiStore()

const router = useRouter()

const route = useRoute()



const refreshing = ref(false)

const settings = computed(() => app.settings)

const ocrProviders = computed(() => settings.value?.ocr.providers || [])



const aiModeLabel = computed(() => {

  if (!settings.value) return '读取中…'

  return settings.value.ai.mode === 'ai' ? '大模型模式' : '基础规则模式'

})



const ocrModeLabel = computed(() => settings.value?.ocr.active_label || '读取中…')



const appearanceLabel = computed(() => ({ light: '浅色', dark: '深色', system: '跟随系统' }[ui.appearance] || '浅色'))



const generalSummary = computed(() => `${appearanceLabel.value} · ${ui.fontSize}px`)



const appearanceOptions: Array<{ value: 'light' | 'dark' | 'system'; label: string; icon: string }> = [

  { value: 'light', label: '浅色', icon: 'Sunny' },

  { value: 'dark', label: '深色', icon: 'Moon' },

  { value: 'system', label: '跟随系统', icon: 'Monitor' },

]



const assistantLabel = computed(() => {

  const assistant = settings.value?.assistant

  if (!assistant) return '未配置'

  return assistant.dedicated_llm ? `${assistant.llm_model || '独立模型'}` : `${assistant.llm_model || '通用配置'}`

})



/* ---------------- 弹层 ---------------- */

const accountOpen = ref(false)

const serviceOpen = ref(false)

const faqOpen = ref(false)

const boundaryOpen = ref(false)

const privacyOpen = ref(false)

const generalOpen = ref(false)

const aboutOpen = ref(false)

const feedbackOpen = ref(false)

const feedbackLoading = ref(false)

const feedbackTypes = [
  { value: 'bug', label: '🐞 功能异常' },
  { value: 'recognition', label: '⚠️ 识别错误' },
  { value: 'suggestion', label: '💡 产品建议' },
  { value: 'recipe', label: '🍽️ 菜谱补充' },
] as const

const feedbackForm = reactive({
  category: 'bug' as (typeof feedbackTypes)[number]['value'],
  content: '',
  contact: '',
  recordId: '',
})

const recentRecords = ref<RecordSummary[]>([])
const recentRecordsLoading = ref(false)

async function openFeedback() {
  feedbackOpen.value = true
  recentRecordsLoading.value = true

  try {
    const data = await recordApi.list({
      page: 1,
      per_page: 3,
    })
    recentRecords.value = data.items || []
  } catch {
    recentRecords.value = []
  } finally {
    recentRecordsLoading.value = false
  }
}

function formatRecordOption(record: RecordSummary) {
  const value = new Date(record.created_at)
  if (Number.isNaN(value.getTime())) return record.food_name

  const now = new Date()
  const sameDay =
    value.getFullYear() === now.getFullYear() &&
    value.getMonth() === now.getMonth() &&
    value.getDate() === now.getDate()

  const hh = String(value.getHours()).padStart(2, '0')
  const mm = String(value.getMinutes()).padStart(2, '0')

  return sameDay
    ? `${record.food_name}（今天 ${hh}:${mm}）`
    : `${record.food_name}（${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')} ${hh}:${mm}）`
}

const myFeedbackOpen = ref(false)
const myFeedbackLoading = ref(false)
const myFeedbacks = ref<MyFeedbackItem[]>([])

// 弹窗打开时通知全局 AI 悬浮球隐藏，避免穿透遮罩
watch(
  [feedbackOpen, myFeedbackOpen],
  ([feedbackVisible, mineVisible]) => {
    window.dispatchEvent(
      new CustomEvent('fsai:modal', {
        detail: { open: feedbackVisible || mineVisible },
      }),
    )
  },
)

onBeforeUnmount(() => {
  window.dispatchEvent(
    new CustomEvent('fsai:modal', { detail: { open: false } }),
  )
})


function readFeedbackReadIds(): Set<number> {
  try {
    const raw = JSON.parse(
      localStorage.getItem('fsai_feedback_read_ids') || '[]',
    ) as number[]
    return new Set(Array.isArray(raw) ? raw : [])
  } catch {
    return new Set()
  }
}

const feedbackReadIds = ref<Set<number>>(readFeedbackReadIds())

const feedbackUnread = computed(
  () =>
    myFeedbacks.value.filter(
      (item) =>
        item.status === 'resolved' &&
        Boolean((item.reply || '').trim()) &&
        !feedbackReadIds.value.has(item.id),
    ).length,
)

function feedbackCode(item: MyFeedbackItem, index: number) {
  const date = String(item.created_at || '')
    .slice(0, 10)
    .replace(/-/g, '')
  return `FB-${date || '00000000'}-${String(index + 1).padStart(3, '0')}`
}

function persistFeedbackReadIds(ids: number[]) {
  try {
    localStorage.setItem('fsai_feedback_read_ids', JSON.stringify(ids))
    feedbackReadIds.value = new Set(ids)
    const remaining = myFeedbacks.value.filter(
      (item) =>
        item.status === 'resolved' &&
        Boolean((item.reply || '').trim()) &&
        !ids.includes(item.id),
    ).length
    window.dispatchEvent(
      new CustomEvent('feedback:read', { detail: { unread: remaining } }),
    )
  } catch {
    /* localStorage 不可用时忽略 */
  }
}

function markOneFeedbackRead(item: MyFeedbackItem) {
  if (
    item.status !== 'resolved' ||
    !(item.reply || '').trim() ||
    feedbackReadIds.value.has(item.id)
  ) {
    return
  }
  persistFeedbackReadIds([
    ...feedbackReadIds.value,
    item.id,
  ])
}

function markFeedbackRead() {
  const ids = myFeedbacks.value
    .filter(
      (item) =>
        item.status === 'resolved' &&
        Boolean((item.reply || '').trim()),
    )
    .map((item) => item.id)
  persistFeedbackReadIds(ids)
}

async function loadMyFeedback() {
  myFeedbackLoading.value = true
  try {
    // 显式带上当前登录用户，服务端仍会校验登录态
    const data = await feedbackApi.mine()
    myFeedbacks.value = (data.items || []).map((item) => ({
      ...item,
      // 后端新标准字段为 reply_content，旧字段 reply 无缝兼容
      reply: item.reply || item.reply_content || '',
    }))
  } catch {
    myFeedbacks.value = []
  } finally {
    myFeedbackLoading.value = false
  }
}

async function openMyFeedback() {
  myFeedbackOpen.value = true
  await loadMyFeedback()
}



/* ---------------- 修改密码 ---------------- */

const pwdLoading = ref(false)

const pwdVisible = reactive({
  old: false,
  new: false,
  confirm: false,
})

const editingName = ref(false)
const displayNameDraft = ref('')
const savingName = ref(false)

const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })



function startEditName() {
  displayNameDraft.value = auth.user?.display_name || auth.user?.username || ''
  editingName.value = true
}

function cancelEditName() {
  editingName.value = false
  displayNameDraft.value = ''
}

async function saveDisplayName() {
  const value = displayNameDraft.value.trim()

  if (!value) {
    ElMessage.warning('昵称不能为空')
    return
  }

  if (value === (auth.user?.display_name || '')) {
    editingName.value = false
    return
  }

  savingName.value = true
  try {
    await auth.updateProfile(value)
    editingName.value = false
    ElMessage.success('昵称修改成功')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '昵称修改失败')
  } finally {
    savingName.value = false
  }
}

function resetAccountDialog() {
  editingName.value = false
  displayNameDraft.value = ''
  pwdVisible.old = false
  pwdVisible.new = false
  pwdVisible.confirm = false
}

async function submitPassword() {

  const { old_password, new_password, confirm } = pwdForm

  if (!old_password) {

    ElMessage.warning('请输入原密码')

    return

  }

  if (new_password !== confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }

  if (new_password === old_password) {
    ElMessage.warning('新密码不能与原密码相同')
    return
  }

  if (new_password.length < 8 || !/[A-Za-z]/.test(new_password) || !/\d/.test(new_password)) {
    ElMessage.warning('密码需至少 8 位，且包含字母和数字')
    return
  }

  pwdLoading.value = true

  try {

    await auth.changePassword(old_password, new_password)

    ElMessage.success('密码已修改，其他设备上的登录已失效')

    pwdForm.old_password = ''

    pwdForm.new_password = ''

    pwdForm.confirm = ''
    pwdVisible.old = false
    pwdVisible.new = false
    pwdVisible.confirm = false

    accountOpen.value = false

  } catch (error) {

    ElMessage.error((error as Error).message || '修改失败，请稍后重试')

  } finally {

    pwdLoading.value = false

  }

}



/* ---------------- 常见问题 ---------------- */

const faqs = [

  {

    title: '第一次运行需要做什么？',

    body:

      '安装 Python 与 Node.js → 创建 Python 虚拟环境 → 安装前后端依赖 → 复制 .env.example 为 .env（可选填 API Key）→ 运行后端 init_db.py 初始化数据库 → 启动后端与前端。完整命令见 README.md 与 docs/WINDOWS_SETUP.md。',

  },

  {

    title: '为什么识别出来的文字有错？',

    body:

      'OCR 对反光、曲面、倾斜、小字号文字容易出错。建议让文字占满画面、光线均匀、避免包装膜反光，并在「核对校正」页逐字修改；低置信度字段会以黄色标签标出。你也可以直接手动输入配料表。',

  },

  {

    title: '没有配置任何 API Key 能用吗？',

    body:

      '可以。系统自带本地离线 OCR 引擎（RapidOCR），无需联网即可识别中文标签；配料解读会使用本地知识库的规则模式，并在页面与报告中明确标注「基础规则模式，未调用大模型」。配置 AI_API_KEY 后重新分析即可获得大模型解读。',

  },

  {

    title: '手机怎么访问电脑上的网站？',

    body:

      '让手机和电脑连同一个 Wi-Fi，在电脑上执行 ipconfig 查看 IPv4 地址（例如 192.168.1.5），手机浏览器访问 http://192.168.1.5:5173 即可（前端开发服务器已监听 0.0.0.0 并代理 /api）。如果打不开，请在 Windows 防火墙允许 5173 与 5000 端口的入站连接。注意：localhost 只能在电脑本机使用。',

  },

  {

    title: '手机和电脑看到的是同一份记录吗？',

    body:

      '是。分析记录、图片与报告全部保存在后端 SQLite 数据库和 uploads 目录中，前端只通过 API 访问。用同一个账号在手机和电脑登录，看到的就是同一份数据；换浏览器或刷新页面都不会丢失。',

  },

  {

    title: '记录保存在哪里？删除后会怎样？',

    body:

      '数据库文件默认在 data/food_safety.db，图片默认在 uploads/ 目录（均可通过 .env 修改）。删除记录会同时删除数据库中的关联数据和磁盘上的图片文件，且不可恢复；删除操作仅限记录的所有者。',

  },

  {

    title: '演示数据和真实数据怎么区分？',

    body:

      '演示账号（默认 demo）的记录带有 is_demo 标记，页面与报告中会显示「演示」标签，首页也会把演示记录与真实记录的数量分开说明。任何使用示例 OCR 数据的记录同样会被标记，不会被当作真实识别结果。',

  },

  {

    title: 'AI 分析结果可靠吗？',

    body:

      'AI 结果可能存在幻觉或偏差，系统会对模型输出做结构校验、过滤虚构引用，并标注每条解释的可信度与来源。所有结论仅用于辅助理解标签，不构成食品安全性或合规性判定，也不能替代实验室检测。',

  },

]



const boundaries = [

  '本平台仅识别包装上的可见文字，不做任何实验室检测，无法判断微生物、农药残留、重金属、真菌毒素或非法添加物。',

  'OCR 与 AI 结果都可能出错；「未识别」不代表包装上缺少该信息，「需要进一步核实」也不代表食品不安全。',

  '核查依据只引用标准名称，系统未收录标准原文，不构成合规认定；请以官方发布的现行文本为准。',

  '知识库中的「待核验」条目仅作参考；正式使用前请查阅权威资料。',

  '演示数据与规则模式结果都会在界面与报告中明确标注，不会被伪装成真实 AI 分析。',

]



async function submitFeedback() {

  const content = feedbackForm.content.trim()

  if (content.length < 10) {

    ElMessage.warning('请至少输入 10 个字，以便我们定位问题')

    return

  }

  const recordIdText = feedbackForm.recordId.trim()

  const typeLabel =
    feedbackTypes.find((item) => item.value === feedbackForm.category)?.label ||
    '反馈'

  // 现有接口没有独立分类字段，用前缀把类型写入反馈正文，后台可直接看到
  const contentWithType = `【${typeLabel}】${content}`.slice(0, 500)

  feedbackLoading.value = true

  try {

    await feedbackApi.submit({

      content: contentWithType,

      contact: feedbackForm.contact.trim() || undefined,

      record_id: recordIdText ? Number(recordIdText) : null,

    })

    ElMessage.success('提交成功')

    feedbackForm.content = ''

    feedbackForm.contact = ''

    feedbackForm.recordId = ''

    feedbackOpen.value = false

    await loadMyFeedback()

  } catch (error) {

    ElMessage.error((error as ApiError).message || '提交失败，请稍后重试')

  } finally {

    feedbackLoading.value = false

  }

}



async function refresh() {

  refreshing.value = true

  await app.loadSettings(true)

  refreshing.value = false

}



async function handleLogout() {

  try {

    await ElMessageBox.confirm('退出后需要重新登录才能查看分析记录。', '退出登录', {

      confirmButtonText: '退出登录',

      cancelButtonText: '取消',

      type: 'warning',

    })

  } catch {

    return

  }

  await auth.logout()

  ElMessage.success('已退出登录')

  router.replace({ name: 'login' })

}



onMounted(async () => {

  app.loadSettings()

  // 以服务端当前令牌为准修复本地缓存的用户信息，避免反馈查询带上过期的 user_id
  await auth.fetchMe().catch(() => undefined)

  await loadMyFeedback()

  if (route.query.feedback === 'mine') {
    openMyFeedback()
  }

  if (route.query.about === '1') {

    aboutOpen.value = true

    router.replace({ name: 'settings' })

  }

})

</script>



<template>

  <div class="page settings-page">

    <div class="settings-wrap">

      <header class="settings-head">

        <div>

          <h1 class="page-title">设置</h1>

          <p class="page-sub">账号、服务与帮助</p>

        </div>

        <el-button text circle :loading="refreshing" aria-label="刷新状态" @click="refresh">

          <el-icon><Refresh /></el-icon>

        </el-button>

      </header>



      <div v-if="app.settingsError" class="notice notice-danger mb">

        <el-icon><WarningFilled /></el-icon>

        <div>状态读取失败：{{ app.settingsError }}（请确认后端服务已启动）</div>

      </div>



      <!-- 账号 -->

      <section class="settings-group">

        <button type="button" class="settings-row" @click="accountOpen = true">

          <span class="row-icon"><el-icon><User /></el-icon></span>

          <span class="row-label">账号与安全</span>

          <span class="row-value">{{ auth.user?.username || '未登录' }}</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

      </section>



      <!-- 通用 -->

      <section class="settings-group">

        <button type="button" class="settings-row" @click="generalOpen = true">

          <span class="row-icon"><el-icon><Setting /></el-icon></span>

          <span class="row-label">通用设置</span>

          <span class="row-value">{{ generalSummary }}</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

        <button type="button" class="settings-row" @click="serviceOpen = true">

          <span class="row-icon"><el-icon><Cpu /></el-icon></span>

          <span class="row-label">服务状态</span>

          <span class="row-value">{{ ocrModeLabel }}</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

        <button type="button" class="settings-row" @click="router.push({ name: 'knowledge' })">

          <span class="row-icon"><el-icon><Reading /></el-icon></span>

          <span class="row-label">知识库与规则</span>

          <span class="row-value">规则集 {{ settings?.ruleset.version || '—' }}</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

        <button type="button" class="settings-row" @click="privacyOpen = true">

          <span class="row-icon"><el-icon><Lock /></el-icon></span>

          <span class="row-label">数据与隐私</span>

          <span class="row-value">仅本人可见</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

      </section>



      <!-- 支持 -->

      <section class="settings-group">

        <button type="button" class="settings-row" @click="faqOpen = true">

          <span class="row-icon"><el-icon><QuestionFilled /></el-icon></span>

          <span class="row-label">常见问题</span>

          <span class="row-value">{{ faqs.length }} 条</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

        <button type="button" class="settings-row" @click="boundaryOpen = true">

          <span class="row-icon"><el-icon><Warning /></el-icon></span>

          <span class="row-label">功能边界与免责声明</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

        <button type="button" class="settings-row" @click="aboutOpen = true">

          <span class="row-icon"><el-icon><InfoFilled /></el-icon></span>

          <span class="row-label">关于项目</span>

          <span class="row-value">v{{ settings?.app.version || '1.0.0' }}</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

        <button type="button" class="settings-row" @click="openMyFeedback">

          <span class="row-icon"><el-icon><Bell /></el-icon></span>

          <span class="row-label">我的反馈</span>

          <span class="row-value" :class="{ 'feedback-unread-text': feedbackUnread }">

            {{ myFeedbacks.length }} 条{{ feedbackUnread ? ` · ${feedbackUnread} 新回复` : '' }}

          </span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

        <button type="button" class="settings-row" @click="openFeedback">

          <span class="row-icon"><el-icon><ChatDotRound /></el-icon></span>

          <span class="row-label">提交反馈</span>

          <span class="row-value">去提交</span>

          <el-icon class="row-arrow"><ArrowRight /></el-icon>

        </button>

      </section>



      <button type="button" class="logout-row" @click="handleLogout">退出登录</button>



      <p class="settings-footer">

        智膳 AI v{{ settings?.app.version || '1.0.0' }}<br />

        本项目为比赛作品，不构成医疗诊断或官方检测结论

      </p>

    </div>



    <!-- 账号与安全 -->

    <el-dialog v-model="accountOpen" title="账号与安全" width="min(94vw, 460px)" @closed="resetAccountDialog">

      <div class="info-list">

        <div class="info-row"><span>用户名</span><strong>{{ auth.user?.username || '—' }}</strong></div>

        <div class="info-row info-row--name">
          <span>昵称</span>

          <div v-if="!editingName" class="nickname-display">
            <strong>{{ auth.user?.display_name || '—' }}</strong>
            <button
              type="button"
              class="name-edit-btn"
              title="修改昵称"
              aria-label="修改昵称"
              @click="startEditName"
            >
              <el-icon><EditPen /></el-icon>
            </button>
          </div>

          <div v-else class="nickname-editor">
            <el-input
              v-model="displayNameDraft"
              maxlength="20"
              show-word-limit
              size="small"
              placeholder="请输入昵称"
              @keyup.enter="saveDisplayName"
              @keyup.esc="cancelEditName"
            />
            <el-button
              size="small"
              type="primary"
              :loading="savingName"
              @click="saveDisplayName"
            >
              保存
            </el-button>
            <el-button size="small" @click="cancelEditName">取消</el-button>
          </div>
        </div>

        <div class="info-row"><span>角色</span><strong>{{ auth.user?.role === 'admin' ? '管理员' : '普通用户' }}</strong></div>

        <div class="info-row"><span>密码存储</span><strong>scrypt 哈希（不可逆）</strong></div>

      </div>

      <div class="dialog-subtitle">修改密码</div>

      <div class="pwd-form">

        <el-input
          v-model="pwdForm.old_password"
          :type="pwdVisible.old ? 'text' : 'password'"
          autocomplete="current-password"
          placeholder="原密码"
        >
          <template #suffix>
            <el-icon
              class="pwd-eye"
              :title="pwdVisible.old ? '隐藏密码' : '显示密码'"
              @click="pwdVisible.old = !pwdVisible.old"
            >
              <View v-if="!pwdVisible.old" />
              <Hide v-else />
            </el-icon>
          </template>
        </el-input>

        <el-input
          v-model="pwdForm.new_password"
          :type="pwdVisible.new ? 'text' : 'password'"
          autocomplete="new-password"
          placeholder="新密码（至少 8 位，含字母和数字）"
        >
          <template #suffix>
            <el-icon
              class="pwd-eye"
              :title="pwdVisible.new ? '隐藏密码' : '显示密码'"
              @click="pwdVisible.new = !pwdVisible.new"
            >
              <View v-if="!pwdVisible.new" />
              <Hide v-else />
            </el-icon>
          </template>
        </el-input>

        <el-input
          v-model="pwdForm.confirm"
          :type="pwdVisible.confirm ? 'text' : 'password'"
          autocomplete="new-password"
          placeholder="再次输入新密码"
        >
          <template #suffix>
            <el-icon
              class="pwd-eye"
              :title="pwdVisible.confirm ? '隐藏密码' : '显示密码'"
              @click="pwdVisible.confirm = !pwdVisible.confirm"
            >
              <View v-if="!pwdVisible.confirm" />
              <Hide v-else />
            </el-icon>
          </template>
        </el-input>

      </div>

      <p class="dialog-hint">修改成功后，其他设备上的登录会立即失效。</p>

      <template #footer>

        <el-button @click="accountOpen = false">取消</el-button>

        <el-button type="primary" :loading="pwdLoading" @click="submitPassword">修改密码</el-button>

      </template>

    </el-dialog>



    <!-- 通用设置 -->

    <el-dialog v-model="generalOpen" title="通用设置" width="min(94vw, 560px)">

      <div class="general-block">

        <div class="general-head">

          <strong>语言</strong>

          <span>界面语言</span>

        </div>

        <el-select :model-value="ui.language" class="general-select" @change="ui.setLanguage">

          <el-option label="简体中文" value="zh-CN" />

          <el-option label="English（即将支持）" value="en-US" disabled />

        </el-select>

        <p class="general-note">当前版本仅提供简体中文界面，英文翻译正在完善。</p>

      </div>



      <div class="general-block">

        <div class="general-head">

          <strong>外观</strong>

          <span>选择界面的明暗风格</span>

        </div>

        <div class="appearance-grid">

          <button

            v-for="item in appearanceOptions"

            :key="item.value"

            type="button"

            class="appearance-card"

            :class="{ active: ui.appearance === item.value }"

            @click="ui.setAppearance(item.value)"

          >

            <el-icon><component :is="item.icon" /></el-icon>

            <span>{{ item.label }}</span>

          </button>

        </div>

      </div>



      <div class="general-block">

        <div class="general-head">

          <strong>字号大小</strong>

          <span>仅影响科普助手会话内容的字号</span>

        </div>

        <div class="font-size-row">

          <el-slider

            :model-value="ui.fontSize"

            :min="12"

            :max="20"

            :step="1"

            :show-tooltip="false"

            @input="ui.setFontSize"

          />

          <span class="font-size-value">{{ ui.fontSize }}px</span>

        </div>

        <div class="font-preview">

          <span class="font-preview-label">预览</span>

          <p :style="{ fontSize: `${ui.fontSize}px` }">隔夜菜能不能吃，关键看储存和加热条件，而不是「隔夜」本身。</p>

        </div>

      </div>



      <template #footer>

        <el-button type="primary" @click="generalOpen = false">完成</el-button>

      </template>

    </el-dialog>



    <!-- 服务状态 -->

    <el-dialog v-model="serviceOpen" title="服务状态" width="min(94vw, 640px)" top="6vh">

      <div class="status-block" v-loading="refreshing">

        <div class="status-block-head">

          <strong>OCR 识别</strong>

          <el-tag size="small" effect="plain">{{ settings?.ocr.active_provider || '—' }}</el-tag>

        </div>

        <p class="status-line">当前使用：{{ ocrModeLabel }}</p>

        <div class="provider-chips">

          <span v-for="provider in ocrProviders" :key="provider.key" class="provider-chip" :class="{ on: provider.available }">

            {{ provider.name }} · {{ provider.available ? '可用' : '未配置' }}

          </span>

        </div>

        <p v-if="settings?.ocr.vision_model" class="status-line">视觉模型：{{ settings.ocr.vision_model }}</p>

      </div>



      <div class="status-block">

        <div class="status-block-head"><strong>AI 配料分析</strong><el-tag size="small" effect="plain">{{ aiModeLabel }}</el-tag></div>

        <p class="status-line">模型：{{ settings?.ai.model || '未配置' }}</p>

        <p class="status-line">API Key：{{ settings?.ai.api_key || '未配置（使用规则模式）' }}</p>

      </div>



      <div class="status-block">

        <div class="status-block-head"><strong>科普助手</strong><el-tag size="small" effect="plain">{{ assistantLabel }}</el-tag></div>

        <p class="status-line">通用回答：{{ settings?.assistant?.general_answer_enabled === '1' ? '允许（标注 AI 补充）' : '关闭' }}</p>

      </div>



      <div class="status-block">

        <div class="status-block-head"><strong>存储与数据</strong></div>

        <p class="status-line">数据库：{{ settings?.storage.database || '—' }}</p>

        <p class="status-line">图片：{{ settings?.storage.file_count ?? 0 }} 个 · {{ formatBytes(settings?.storage.total_bytes ?? 0) }}</p>

        <p class="status-line">单张上限：{{ settings?.storage.max_upload_mb ?? '—' }}MB · {{ (settings?.storage.allowed_formats || []).join(' / ') }}</p>

      </div>



      <div class="status-block">

        <div class="status-block-head"><strong>安全与规则</strong></div>

        <p class="status-line">密码哈希：{{ settings?.security.password_hashing || 'scrypt' }} · 会话 {{ settings?.security.session_days ?? '—' }} 天</p>

        <p class="status-line">规则集：{{ settings?.ruleset.version || '—' }}（更新于 {{ settings?.ruleset.updated_at || '—' }}，共 {{ settings?.ruleset.rule_count ?? '—' }} 条）</p>

      </div>

      <template #footer>

        <el-button :loading="refreshing" @click="refresh">刷新</el-button>

        <el-button type="primary" @click="serviceOpen = false">知道了</el-button>

      </template>

    </el-dialog>



    <!-- 常见问题 -->

    <el-dialog v-model="faqOpen" title="常见问题" width="min(94vw, 560px)" top="6vh">

      <el-collapse accordion>

        <el-collapse-item v-for="(faq, index) in faqs" :key="index" :title="faq.title" :name="index">

          <p class="faq-body">{{ faq.body }}</p>

        </el-collapse-item>

      </el-collapse>

      <template #footer>

        <el-button type="primary" @click="faqOpen = false">知道了</el-button>

      </template>

    </el-dialog>



    <!-- 功能边界 -->

    <el-dialog v-model="boundaryOpen" title="功能边界与免责声明" width="min(94vw, 560px)">

      <ul class="boundary-list">

        <li v-for="item in boundaries" :key="item">{{ item }}</li>

      </ul>

      <p class="dialog-hint">

        运行环境：Python {{ settings?.runtime.python || '—' }} · Flask {{ settings?.runtime.flask || '—' }} ·

        应用版本 v{{ settings?.app.version || '—' }}（{{ settings?.app.env || '—' }}）

      </p>

      <template #footer>

        <el-button type="primary" @click="boundaryOpen = false">知道了</el-button>

      </template>

    </el-dialog>



    <!-- 关于项目 -->

    <el-dialog v-model="aboutOpen" title="关于项目" width="min(94vw, 680px)" top="4vh">

      <AboutPanel />

      <template #footer>

        <el-button type="primary" @click="aboutOpen = false">知道了</el-button>

      </template>

    </el-dialog>



    <!-- 意见反馈 -->
    <el-dialog
      v-model="feedbackOpen"
      title="意见反馈"
      width="min(90vw, 28rem)"
      class="feedback-dialog"
      append-to-body
    >
      <div class="feedback-form">
        <div class="feedback-field">
          <label class="feedback-label">反馈类型</label>

          <div class="feedback-type-pills">
            <button
              v-for="type in feedbackTypes"
              :key="type.value"
              type="button"
              class="feedback-type-pill"
              :class="{ active: feedbackForm.category === type.value }"
              @click="feedbackForm.category = type.value"
            >
              {{ type.label }}
            </button>
          </div>
        </div>

        <div class="feedback-field">
          <label class="feedback-label">
            反馈内容 <span>*</span>
          </label>

          <el-input
            v-model="feedbackForm.content"
            type="textarea"
            :rows="4"
            maxlength="480"
            show-word-limit
            placeholder="请描述具体问题或建议，至少 10 个字"
          />
        </div>

        <div class="feedback-field">
          <label class="feedback-label">
            关联记录
            <small>选填</small>
          </label>

          <el-select
            v-model="feedbackForm.recordId"
            clearable
            filterable
            :loading="recentRecordsLoading"
            placeholder="可选：关联最近一次分析记录"
            class="feedback-select"
          >
            <el-option
              v-for="record in recentRecords"
              :key="record.id"
              :label="formatRecordOption(record)"
              :value="String(record.id)"
            />
          </el-select>

          <p class="feedback-field-hint">
            默认展示最近 3 条分析记录，点选即可关联。
          </p>
        </div>

        <div class="feedback-field">
          <label class="feedback-label">
            联系方式
            <small>选填</small>
          </label>

          <el-input
            v-model="feedbackForm.contact"
            maxlength="80"
            placeholder="请输入手机号或邮箱（选填，以便我们回复您）"
          />
        </div>
      </div>

      <p class="dialog-hint">
        管理员会在后台「用户反馈」中处理，回复会同步到「我的反馈」。
      </p>

      <template #footer>
        <div class="feedback-footer">
          <el-button @click="feedbackOpen = false">取消</el-button>
          <el-button
            type="primary"
            :loading="feedbackLoading"
            @click="submitFeedback"
          >
            提交反馈
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 我的反馈 -->
    <el-dialog v-model="myFeedbackOpen" title="我的反馈" width="min(94vw, 560px)">
      <div v-loading="myFeedbackLoading" class="my-feedback-list">
        <!-- 已处理且未读的回复提示 -->
        <div v-if="feedbackUnread" class="my-feedback-unread-banner">
          <span class="my-feedback-unread-dot" />
          <span>您有新的反馈回复</span>
          <strong>{{ feedbackUnread }} 条</strong>
          <button type="button" @click="markFeedbackRead">
            全部已读
          </button>
        </div>

        <p v-if="!myFeedbacks.length && !myFeedbackLoading" class="my-feedback-empty">
          还没有提交过反馈。
        </p>

        <article
          v-for="(item, index) in myFeedbacks"
          :key="item.id"
          class="my-feedback-card"
          :class="{
            'is-unread':
              item.status === 'resolved' &&
              Boolean(item.reply) &&
              !feedbackReadIds.has(item.id),
          }"
          @click="markOneFeedbackRead(item)"
        >
          <div class="my-feedback-head">
            <strong>{{ feedbackCode(item, index) }}</strong>
            <el-tag
              size="small"
              :type="item.status === 'resolved' ? 'success' : 'warning'"
            >
              {{ item.status_label }}
            </el-tag>
          </div>

          <p class="my-feedback-content">{{ item.content }}</p>

          <div v-if="item.reply" class="my-feedback-reply">
            <span class="my-feedback-reply-label">官方回复</span>
            <p>{{ item.reply }}</p>
          </div>

          <p v-else class="my-feedback-pending">
            处理中，管理员回复后会显示在这里。
          </p>

          <time class="my-feedback-time">
            {{ item.created_at?.replace('T', ' ').slice(0, 16) }}
          </time>
        </article>
      </div>
    </el-dialog>

    <!-- 数据与隐私 -->

    <el-dialog v-model="privacyOpen" title="数据与隐私" width="min(94vw, 520px)">

      <ul class="boundary-list">

        <li>分析记录、图片与报告保存在你所在部署的服务器数据库中，前端只通过 API 访问。</li>

        <li>同一账号在手机与电脑登录可看到同一份记录；不同账号之间的数据互相隔离。</li>

        <li>演示账号的记录带有「演示」标记，不会被当作真实识别或真实统计。</li>

        <li>管理员后台可以查看记录用于复核，但不会展示用户密码；密码只支持重置为临时密码。</li>

        <li>删除记录或账号后，关联数据与图片会从数据库和上传目录清理，且不可恢复。</li>

      </ul>

      <template #footer>

        <el-button type="primary" @click="privacyOpen = false">知道了</el-button>

      </template>

    </el-dialog>

  </div>

</template>



<style scoped>

.general-block {

  padding: 4px 0 16px;

  border-bottom: 1px dashed var(--border);

  margin-bottom: 14px;

}



.general-block:last-of-type {

  border-bottom: none;

  margin-bottom: 0;

  padding-bottom: 0;

}



.general-head {

  display: flex;

  align-items: baseline;

  justify-content: space-between;

  gap: 10px;

  margin-bottom: 10px;

}



.general-head strong {

  font-size: 13.5px;

}



.general-head span {

  font-size: 11.5px;

  color: var(--muted);

}



.general-select {

  width: 200px;

}



.general-note {

  margin: 8px 0 0;

  font-size: 11.5px;

  color: var(--muted);

}



.appearance-grid {

  display: grid;

  grid-template-columns: repeat(3, minmax(0, 1fr));

  gap: 8px;

}



.appearance-card {

  display: flex;

  flex-direction: column;

  align-items: center;

  gap: 6px;

  padding: 14px 6px;

  border: 1px solid var(--border);

  border-radius: 10px;

  background: var(--card);

  color: var(--text-2);

  font-size: 12.5px;

  cursor: pointer;

}



.appearance-card .el-icon {

  font-size: 20px;

}



.appearance-card.active {

  border-color: var(--brand);

  background: var(--brand-50);

  color: var(--brand-700);

  box-shadow: 0 0 0 1px var(--brand) inset;

}



.font-size-row {

  display: flex;

  align-items: center;

  gap: 12px;

}



.font-size-row .el-slider {

  flex: 1;

}



.font-size-value {

  min-width: 42px;

  text-align: right;

  font-size: 12.5px;

  color: var(--text-2);

}



.font-preview {

  margin-top: 10px;

  padding: 10px 12px;

  border-radius: 10px;

  background: var(--brand-50);

}



.font-preview-label {

  font-size: 10.5px;

  color: var(--muted);

}



.font-preview p {

  margin: 4px 0 0;

  line-height: 1.8;

  color: var(--text-2);

}



.feedback-form {

  display: flex;

  flex-direction: column;

  gap: 10px;

}



.settings-page {

  padding-bottom: 32px;

}



.settings-wrap {

  max-width: 560px;

  margin: 0 auto;

}



.settings-head {

  display: flex;

  align-items: flex-start;

  justify-content: space-between;

  gap: 10px;

  margin-bottom: 14px;

}



.settings-head .page-sub {

  margin: 4px 0 0;

  font-size: 12.5px;

  color: var(--muted);

}



.settings-group {

  background: var(--card);

  border: 1px solid var(--border);

  border-radius: 12px;

  overflow: hidden;

  margin-bottom: 10px;

}



.settings-row {

  width: 100%;

  display: flex;

  align-items: center;

  gap: 10px;

  padding: 13px 14px;

  border: none;

  border-bottom: 1px solid #f1f4f3;

  background: var(--card);

  color: var(--text-1);

  font-size: 14.5px;

  text-align: left;

  cursor: pointer;

}



.settings-group .settings-row:last-child {

  border-bottom: none;

}



.settings-row:hover,

.settings-row:active {

  background: var(--surface-2);

}



.row-icon {

  width: 26px;

  height: 26px;

  border-radius: 7px;

  display: grid;

  place-items: center;

  background: var(--brand-50);

  color: var(--brand-700);

  font-size: 15px;

  flex-shrink: 0;

}



.row-label {

  flex: 1;

  min-width: 0;

}



.row-value {

  max-width: 50%;

  overflow: hidden;

  text-overflow: ellipsis;

  white-space: nowrap;

  font-size: 12.5px;

  color: var(--muted);

}



.row-arrow {

  color: #c2ccc9;

  font-size: 12px;

  flex-shrink: 0;

}



.logout-row {

  width: 100%;

  margin-top: 14px;

  padding: 14px;

  border: 1px solid var(--border);

  border-radius: 12px;

  background: var(--card);

  color: #c0392b;

  font-size: 14.5px;

  cursor: pointer;

}



.logout-row:hover {

  background: #fff7f6;

}



.settings-footer {

  margin: 18px 0 6px;

  text-align: center;

  font-size: 11px;

  line-height: 1.9;

  color: var(--muted);

}



.info-list {

  border: 1px solid var(--border);

  border-radius: 10px;

  overflow: hidden;

  margin-bottom: 16px;

}



.info-row {

  display: flex;

  justify-content: space-between;

  gap: 10px;

  padding: 10px 12px;

  font-size: 13px;

  border-bottom: 1px solid #f1f4f3;

}



.info-row:last-child {

  border-bottom: none;

}



.info-row span {

  color: var(--muted);

}



.dialog-subtitle {

  font-size: 13px;

  font-weight: 600;

  margin: 4px 0 10px;

}



.pwd-form {

  display: grid;

  gap: 10px;

}



.dialog-hint {

  margin: 10px 0 0;

  font-size: 11.5px;

  color: var(--muted);

  line-height: 1.7;

}



.status-block {

  padding: 10px 0;

  border-bottom: 1px dashed var(--border);

}



.status-block:last-of-type {

  border-bottom: none;

}



.status-block-head {

  display: flex;

  justify-content: space-between;

  gap: 8px;

  align-items: center;

  margin-bottom: 6px;

}



.status-line {

  margin: 4px 0;

  font-size: 12.5px;

  color: var(--muted);

  line-height: 1.7;

  word-break: break-word;

}



.provider-chips {

  display: flex;

  flex-wrap: wrap;

  gap: 6px;

  margin: 6px 0;

}



.provider-chip {

  font-size: 11.5px;

  padding: 3px 8px;

  border-radius: 999px;

  background: #f4f6f5;

  color: var(--muted);

}



.provider-chip.on {

  background: #eaf6f2;

  color: var(--brand-700);

}



.faq-body {

  margin: 0;

  font-size: 12.5px;

  line-height: 1.8;

  color: var(--text-2);

}



.boundary-list {

  margin: 0;

  padding-left: 18px;

  font-size: 12.5px;

  line-height: 1.9;

  color: var(--text-2);

}



.boundary-list li {

  margin-bottom: 6px;

}



@media (max-width: 767px) {

  .settings-wrap {

    max-width: none;

  }



  .settings-row {

    padding: 13px 12px;

    font-size: 14px;

  }



  .row-value {

    max-width: 46%;

  }

}


/* 我的反馈 */
.feedback-unread-text {
  color: #c0392b;
  font-weight: 700;
}

.my-feedback-list {
  display: grid;
  gap: 10px;
}

.my-feedback-empty {
  margin: 0;
  padding: 24px 0;
  color: #8a9e94;
  text-align: center;
  font-size: 12.5px;
}

.my-feedback-card {
  padding: 13px;
  border: 1px solid #e5eee8;
  border-radius: 11px;
  background: #fafcfb;
}

.my-feedback-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.my-feedback-head strong {
  color: #315c4b;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11.5px;
}

.my-feedback-content {
  margin: 9px 0 0;
  color: #294d3e;
  font-size: 13px;
  line-height: 1.7;
}

.my-feedback-reply {
  margin-top: 10px;
  padding: 9px 11px;
  border-left: 3px solid #55ae86;
  border-radius: 0 8px 8px 0;
  background: #eef8f2;
}

.my-feedback-reply-label {
  color: #2c7c5b;
  font-size: 10.5px;
  font-weight: 700;
}

.my-feedback-reply p {
  margin: 4px 0 0;
  color: #315c4b;
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.my-feedback-pending {
  margin: 9px 0 0;
  color: #9a8a6b;
  font-size: 11.5px;
}

.my-feedback-time {
  display: block;
  margin-top: 8px;
  color: #96a69e;
  font-size: 10.5px;
}


.my-feedback-unread-banner {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 11px;
  border: 1px solid #f0cbc6;
  border-radius: 9px;
  background: #fff7f5;
  color: #a94138;
  font-size: 12px;
}

.my-feedback-unread-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #df4c43;
}

.my-feedback-unread-banner strong {
  font-size: 11px;
}

.my-feedback-unread-banner button {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: #b3544b;
  font-family: inherit;
  font-size: 11px;
  text-decoration: underline;
  cursor: pointer;
}

.my-feedback-card {
  cursor: pointer;
}

.my-feedback-card.is-unread {
  border-color: #cfe7da;
  box-shadow: 0 0 0 1px rgba(72, 155, 118, 0.08);
}


/* 意见反馈弹窗 */
.feedback-form {
  gap: 14px;
}

.feedback-field {
  display: grid;
  gap: 7px;
}

.feedback-label {
  color: #315c4b;
  font-size: 12.5px;
  font-weight: 700;
}

.feedback-label span {
  color: #c0392b;
}

.feedback-label small {
  margin-left: 4px;
  color: #94a69c;
  font-size: 10.5px;
  font-weight: 400;
}

.feedback-type-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.feedback-type-pill {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid #dfebe3;
  border-radius: 999px;
  background: #f8fbf9;
  color: #466558;
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.feedback-type-pill:hover {
  border-color: #a8d5be;
}

.feedback-type-pill.active {
  border-color: #4a9b78;
  background: #eaf7f0;
  color: #1e6b4e;
  font-weight: 700;
}

.feedback-select {
  width: 100%;
}

.feedback-select :deep(.el-select__wrapper) {
  min-height: 40px;
}

.feedback-field-hint {
  margin: 0;
  color: #94a69c;
  font-size: 10.5px;
  line-height: 1.5;
}

.feedback-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.feedback-footer :deep(.el-button) {
  min-height: 40px;
  padding: 0 18px;
}

@media (max-width: 767px) {
  .feedback-footer :deep(.el-button) {
    flex: 1;
    min-height: 44px;
  }
}


/* ---------- 账号与安全弹窗：昵称 / 密码可见性 ---------- */
.info-row--name {
  align-items: center;
}

.nickname-display {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.nickname-display strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.name-edit-btn {
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 7px;
  background: #ecfdf5;
  color: #0f6b52;
  cursor: pointer;
  transition: background 0.18s ease, transform 0.18s ease;
}

.name-edit-btn:hover {
  background: #d1fae5;
  transform: translateY(-1px);
}

.nickname-editor {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.nickname-editor .el-input {
  min-width: 0;
  max-width: 180px;
}

.pwd-eye {
  cursor: pointer;
  color: #7a8a84;
  transition: color 0.18s ease;
}

.pwd-eye:hover {
  color: #10b981;
}
</style>
