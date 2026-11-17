<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { familyApi, favoriteApi, pantryApi } from '@/api'
import { buildFreshProduct, buildStapleProduct, formatPrice, specLabel, type ProductSpec } from '@/data/shoppingCatalog'
import { ApiError } from '@/api/client'
import type { FamilyInfo, HealthProfile, PantryItem, PantryReminder, PantryShelfEstimate, RecipeHistoryItem, RecipeMeal, RecipePlan } from '@/api/types'
import PantrySmartImport from '@/components/PantrySmartImport.vue'
import FavoritesView from '@/views/FavoritesView.vue'
import WeatherWidget from '@/components/WeatherWidget.vue'
import OfflineShoppingMemo from '@/components/OfflineShoppingMemo.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useDietLog } from '@/composables/useDietLog'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

const { isMobile } = useBreakpoint()
const { addMeal } = useDietLog()
const route = useRoute()
const router = useRouter()

const activeTab = ref<'inventory' | 'plan' | 'favorites'>('inventory')
const isHealthProfilePage = computed(() => route.name === 'health-profile')
const loading = ref(false)
const errorMessage = ref('')
const items = ref<PantryItem[]>([])
const categories = ref<Array<{ value: string; label: string }>>([])
const reminder = ref<PantryReminder | null>(null)
const filters = reactive({ status: '', query: '' })
const family = ref<FamilyInfo | null>(null)
const familyLoading = ref(false)
const inviteCode = ref('')
const joiningFamily = ref(false)

function currentFamilyInviteCode() {
  return family.value?.family.invite_code || ''
}

const INVITE_CODE_TTL_SECONDS = 15 * 60

const generatedInviteCode = ref('')
const inviteCodeRevealed = ref(false)
const creatingFamily = ref(false)
const leavingFamily = ref(false)
const inviteRemaining = ref(0)
const inviteDeadline = ref(0)
let inviteCountdownTimer: number | undefined

const inviteCodeExpired = computed(
  () => inviteCodeRevealed.value && inviteRemaining.value <= 0,
)
const inviteCodeValid = computed(
  () => inviteCodeRevealed.value && inviteRemaining.value > 0,
)
const inviteCountdownText = computed(() => {
  const minutes = Math.floor(inviteRemaining.value / 60)
  const seconds = inviteRemaining.value % 60
  return `有效期 ${minutes}:${String(seconds).padStart(2, '0')}`
})
const inviteCodeDisplay = computed(() => {
  if (!inviteCodeRevealed.value) return '未获取'
  if (inviteCodeExpired.value) return '已过期'
  return generatedInviteCode.value
})

function stopInviteCountdown() {
  if (inviteCountdownTimer) {
    window.clearInterval(inviteCountdownTimer)
    inviteCountdownTimer = undefined
  }
}

function updateInviteCountdown() {
  inviteRemaining.value = Math.max(
    0,
    Math.ceil((inviteDeadline.value - Date.now()) / 1000),
  )
  if (inviteRemaining.value <= 0) stopInviteCountdown()
}

function startInviteCountdown() {
  stopInviteCountdown()
  inviteDeadline.value = Date.now() + INVITE_CODE_TTL_SECONDS * 1000
  updateInviteCountdown()
  inviteCountdownTimer = window.setInterval(updateInviteCountdown, 1000)
}

function obtainInviteCode() {
  const code = currentFamilyInviteCode()
  if (!code) {
    ElMessage.warning('家庭邀请码加载中，请稍后重试')
    return
  }
  generatedInviteCode.value = code
  inviteCodeRevealed.value = true
  startInviteCountdown()
}

function refreshInviteCode() {
  const code = currentFamilyInviteCode()
  if (!code) {
    ElMessage.warning('家庭邀请码加载中，请稍后重试')
    return
  }
  generatedInviteCode.value = code
  inviteCodeRevealed.value = true
  startInviteCountdown()
  ElMessage.success('邀请码已刷新')
}
const familyDialogOpen = ref(false)
const editingFamilyName = ref(false)
const familyNameDraft = ref('')
const savingFamilyName = ref(false)
const editingMemberId = ref<number | null>(null)
const memberNameDraft = ref('')
const savingMemberId = ref<number | null>(null)
let familyPollTimer: number | undefined

const FAMILY_MEMBER_ALIAS_KEY = 'fsai_family_member_aliases_v1'

function readFamilyMemberAliases(): Record<string, string> {
  try {
    const raw = localStorage.getItem(FAMILY_MEMBER_ALIAS_KEY)
    return raw ? (JSON.parse(raw) as Record<string, string>) : {}
  } catch {
    return {}
  }
}

const familyMemberAliases = ref<Record<string, string>>(
  readFamilyMemberAliases(),
)

function currentSelfId() {
  return family.value?.members.find((member) => member.is_self)?.id ?? 0
}

function familyMemberAliasKey(member: FamilyInfo['members'][number]) {
  return `${currentSelfId()}:${member.id}`
}

function familyMemberDisplayName(member: FamilyInfo['members'][number]) {
  return familyMemberAliases.value[familyMemberAliasKey(member)] || member.display_name
}

function persistFamilyMemberAliases() {
  try {
    localStorage.setItem(
      FAMILY_MEMBER_ALIAS_KEY,
      JSON.stringify(familyMemberAliases.value),
    )
  } catch {
    /* localStorage 不可用时仅保留本次会话内存状态 */
  }
}
const hasHealthProfile = computed(() =>
  Boolean(
    profileForm.conditions.length ||
    profileForm.goals.length ||
    profileForm.allergies.length ||
    profileForm.notes.trim(),
  ),
)

function goHealthProfile() {
  router.push({ name: 'health-profile' })
}
const removingMember = ref<number | null>(null)

const dialogOpen = ref(false)
const editing = ref<PantryItem | null>(null)
const saving = ref(false)
const formError = ref('')
const shelfEstimate = ref<PantryShelfEstimate | null>(null)
const estimating = ref(false)
const form = reactive({
  name: '',
  category: 'vegetable',
  quantity: 1,
  unit: '份',
  purchased_at: '',
  expires_at: '',
  note: '',
})

const profile = ref<HealthProfile | null>(null)
const profileSaving = ref(false)
const healthTip = ref('')
const healthTipSource = ref('')
const healthTipLoading = ref(false)
const healthTipBody = computed(() => healthTip.value.replace(/^AI 助理已同步您的健康画像[：:]?/, '').trim())
let healthTipTimer: number | undefined
const profileForm = reactive<{ conditions: string[]; goals: string[]; allergies: string[]; notes: string }>({
  conditions: [],
  goals: [],
  allergies: [],
  notes: '',
})
const profileUploadInput = ref<HTMLInputElement | null>(null)
const allergyDraft = ref('')
const allergyFocused = ref(false)
const allergyField = ref<HTMLInputElement | null>(null)
const savedProfileSignature = ref('')
const savedProfileSnapshot = ref<{
  conditions: string[]
  goals: string[]
  allergies: string[]
  notes: string
} | null>(null)

const ALLERGY_PRESETS = [
  '花生',
  '海鲜',
  '虾',
  '蟹',
  '牛奶',
  '鸡蛋',
  '麸质',
  '大豆',
]

const VALID_ENGLISH_ALLERGENS = new Set([
  'peanut', 'peanuts', 'milk', 'dairy', 'egg', 'eggs', 'gluten', 'wheat',
  'soy', 'soya', 'soybean', 'seafood', 'fish', 'shrimp', 'crab', 'shellfish',
  'nut', 'nuts', 'almond', 'almonds', 'cashew', 'cashews', 'walnut', 'walnuts',
  'sesame', 'mustard', 'celery', 'lupin', 'sulphite', 'sulfite', 'corn',
  'mushroom', 'beef', 'pork', 'chicken', 'lamb', 'oyster', 'squid', 'octopus',
  'tree nut', 'tree nuts', 'pine nut', 'pine nuts', 'sunflower seed',
  'sunflower seeds', 'poppy seed', 'poppy seeds', 'apple', 'banana', 'orange',
  'strawberry', 'peach', 'kiwi', 'grape', 'watermelon', 'tomato', 'potato',
  'carrot', 'onion', 'garlic', 'broccoli', 'spinach', 'rice', 'noodle',
  'bread', 'cheese', 'yogurt', 'butter', 'honey', 'chocolate', 'coffee', 'tea',
])

const COMMON_CHINESE_FOODS = new Set([
  '大米', '花生', '花生米', '花生酱', '海鲜', '海鱼', '虾', '虾仁', '蟹', '螃蟹',
  '贝类', '蛤蜊', '牡蛎', '鱼', '鱼肉', '三文鱼', '鳕鱼', '金枪鱼', '鱿鱼',
  '章鱼', '海带', '紫菜', '牛奶', '羊奶', '乳制品', '乳糖', '奶酪', '酸奶',
  '鸡蛋', '蛋清', '蛋黄', '蛋类', '麸质', '面筋', '小麦', '大麦', '燕麦',
  '黑麦', '米粉', '面粉', '玉米', '大豆', '黄豆', '黑豆', '红豆', '绿豆',
  '豆浆', '豆腐', '豆制品', '芒果', '菠萝', '草莓', '桃子', '猕猴桃', '香蕉',
  '苹果', '梨', '橙子', '橘子', '柠檬', '柚子', '葡萄', '西瓜', '哈密瓜',
  '坚果', '核桃', '杏仁', '腰果', '开心果', '榛子', '松子', '葵花籽',
  '南瓜子', '芝麻', '芝麻酱', '芹菜', '芥末', '香菜', '韭菜', '葱', '姜',
  '蒜', '辣椒', '花椒', '八角', '桂皮', '蘑菇', '香菇', '金针菇', '木耳',
  '竹笋', '南瓜', '红薯', '土豆', '山药', '莲藕', '萝卜', '白菜', '油菜',
  '生菜', '黄瓜', '苦瓜', '冬瓜', '丝瓜', '西兰花', '花菜', '洋葱', '豌豆',
  '扁豆', '四季豆', '牛肉', '猪肉', '羊肉', '鸡肉', '鸭肉', '鹅肉', '火腿',
  '香肠', '蜂蜜', '蜂王浆', '巧克力', '咖啡', '茶', '酒', '酒精', '味精',
  '鸡精', '阿斯巴甜', '山梨酸钾', '苯甲酸钠', '柠檬酸', '明胶', '酵母',
  '亚硫酸盐', '色素', '防腐剂', '粗粮', '杂粮', '红肉', '面包',
  '全麦面包', '荞麦面包', '黑麦面包', '吐司',
])

const FORBIDDEN_FOOD_WORDS = [
  '吃', '喝', '做', '食用', '进食', '烹调', '烹饪',
  '回复', '结果', '测试', '返回', '处理', '添加', '删除', '保存', '修改',
  '确认', '取消', '输入', '输出', '回答', '问题', '数据', '信息', '系统',
  '页面', '按钮', '选择', '查看', '提交', '操作', '步骤', '提示', '建议',
  '帮助', '用户', '管理员', '医生', '患者', '疾病', '症状', '药物', '药品',
  '医院', '治疗', '诊断', '错误', '乱码', '测试数据', '效果', '成果', '后果',
]

const GENERIC_FOOD_TERMS = new Set([
  '米饭', '白米饭', '水', '饮用水', '食物', '食材', '食品', '蔬菜', '水果',
  '主食', '肉类', '菜品', '饭', '面食', '零食', '饮料', '饮品', '调味品',
  '食品添加剂', '防腐剂', '色素', '添加剂', '过敏原', '忌口',
])

const FOOD_SUFFIX = /(肉|鱼|虾|蟹|贝|奶|蛋|豆|菜|瓜|果|菇|菌|笋|薯|米|面|粉|油|盐|酱|醋|糖|茶|酒|蜜|仁|籽|莓|桃|梨|橙|橘|柚|枣|梅|麦|麸|乳|酪|筋|藻|螺|参|翅|肚|肝|肠|舌|蹄|骨|排|腩|柳|胸|腿|皮|冻|露|糕|饼|饯|汁|汤|粥|饭|条|丝|片|丁|块|子|椒|葱|姜|蒜|茄)$/

// 单个汉字也可能是具体过敏原，例如：虾、蟹、鱼、蛋、奶、豆
const SINGLE_CHAR_FOODS = new Set([
  '虾', '蟹', '鱼', '蛋', '奶', '豆', '麦', '麸', '乳',
  '葱', '姜', '蒜', '椒', '茶', '酒', '蜜', '盐', '糖',
  '醋', '油', '米', '面', '参', '藻',
])

function profileSignature() {
  return JSON.stringify({
    conditions: [...profileForm.conditions],
    goals: [...profileForm.goals],
    allergies: [...profileForm.allergies],
    notes: profileForm.notes.trim(),
  })
}

function createProfileSnapshot() {
  return {
    conditions: [...profileForm.conditions],
    goals: [...profileForm.goals],
    allergies: [...profileForm.allergies],
    notes: profileForm.notes,
  }
}

function markProfileSaved() {
  savedProfileSnapshot.value = createProfileSnapshot()
  savedProfileSignature.value = profileSignature()

  // 同步给 AI 食安智询官：下一次提问可直接使用最新画像
  try {
    if (profile.value) {
      localStorage.setItem(
        'fsai_assistant_health_profile_v1',
        JSON.stringify(profile.value),
      )
    }
  } catch {
    /* localStorage 不可用时忽略，后端仍会回退数据库画像 */
  }
}

function restoreProfileSnapshot() {
  const snapshot = savedProfileSnapshot.value
  if (!snapshot) return
  profileForm.conditions = [...snapshot.conditions]
  profileForm.goals = [...snapshot.goals]
  profileForm.allergies = [...snapshot.allergies]
  profileForm.notes = snapshot.notes
  allergyDraft.value = ''
  allergyFocused.value = false
  savedProfileSignature.value = profileSignature()
}

const isProfileDirty = computed(
  () => savedProfileSignature.value !== '' && profileSignature() !== savedProfileSignature.value,
)

function profileOptionLabel(kind: 'conditions' | 'goals', key: string) {
  const options = profile.value?.options?.[kind] || []
  return options.find((item) => item.value === key)?.label || conditionLabel(key)
}

function joinWithAnd(items: string[]) {
  if (items.length <= 1) return items[0] || ''
  if (items.length === 2) return `${items[0]}和${items[1]}`
  return `${items.slice(0, -1).join('、')}和${items[items.length - 1]}`
}

function profileMealStyle(notes: string) {
  if (/减脂|低脂|控脂|体重|瘦身/.test(notes)) {
    return '温和低脂的餐食'
  }
  if (/肠胃|胃|消化|清淡/.test(notes)) {
    return '温和易消化的餐食'
  }
  if (/控糖|血糖|糖/.test(notes)) {
    return '控糖友好的餐食'
  }
  if (/高蛋白|增肌|蛋白/.test(notes)) {
    return '高蛋白餐食'
  }
  return '更贴合的餐食'
}

function buildProfileAssistantText() {
  const conditions = [
    ...new Set(
      profileForm.conditions.map((key) =>
        profileOptionLabel('conditions', key),
      ),
    ),
  ]
  const goals = [
    ...new Set(
      profileForm.goals.map((key) =>
        profileOptionLabel('goals', key),
      ),
    ),
  ]
  const allergies = [
    ...new Set(
      profileForm.allergies
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ]
  const notes = profileForm.notes.trim()

  const hasFocus = conditions.length > 0 || goals.length > 0
  const prefix = hasFocus
    ? 'AI 已为您生成专属健康策略：'
    : 'AI 已为您生成专属策略：'

  if (!hasFocus && !allergies.length && !notes) {
    return `${prefix}未来食谱规划会根据您的健康信息动态调整。`
  }

  if (!hasFocus && !allergies.length && notes) {
    return `${prefix}未来食谱规划会根据您的特殊说明（${notes}）为您安排${profileMealStyle(notes)}。`
  }

  const parts: string[] = []

  if (conditions.length) {
    parts.push(`重点针对您的${conditions.join('、')}`)
  }
  if (goals.length) {
    parts.push(`结合您的${goals.join('、')}目标`)
  }
  if (allergies.length) {
    parts.push(`严格避开${joinWithAnd(allergies)}`)
  }

  let text = `${prefix}未来食谱规划将${parts.join('，')}。`

  if (notes) {
    text += `同时，AI 会根据您的特殊说明（${notes}）为您安排${profileMealStyle(notes)}。`
  }

  return text
}

const profileAssistantState = computed(() => {
  const text = buildProfileAssistantText()

  if (isProfileDirty.value) {
    return {
      pending: true,
      title: '健康信息待保存',
      text,
    }
  }

  return {
    pending: false,
    title: 'AI 专属健康助理实时监控中',
    text,
  }
})

function isValidAllergyName(raw: string) {
  const value = raw.trim().replace(/[。；;、,，\s]+$/, '')
  if (!value) return false

  // 第一层：动作词、抽象词、无意义词黑名单
  if (FORBIDDEN_FOOD_WORDS.some((word) => value.includes(word))) {
    return false
  }

  // 第二层：禁止泛指主食/大类
  if (GENERIC_FOOD_TERMS.has(value)) {
    return false
  }

  // 第三层：中文允许 1-8 个字；单字只接受明确的常见过敏原
  if (/^[\u4e00-\u9fa5]{1,8}$/.test(value)) {
    if (value.length === 1) {
      return SINGLE_CHAR_FOODS.has(value)
    }
    return COMMON_CHINESE_FOODS.has(value) || FOOD_SUFFIX.test(value)
  }

  // 英文只允许单个常见食物单词
  const normalized = value.toLowerCase()
  return /^[a-z]{2,20}$/.test(normalized) && VALID_ENGLISH_ALLERGENS.has(normalized)
}

function addAllergy(showError = true) {
  const raw = allergyDraft.value.trim()
  if (!raw) return true

  const values = raw
    .split(/[、,，;；]/)
    .map((item) => item.trim())
    .filter(Boolean)

  if (!values.length) {
    allergyDraft.value = ''
    return true
  }

  const invalid = values.find((value) => !isValidAllergyName(value))
  if (invalid) {
    if (showError) {
      ElMessageBox.alert(
        `「${invalid}」无法识别为具体食材。请输入单个食材名称，如：虾、蟹、花生、牛奶。`,
        '无法添加',
        {
          type: 'warning',
          confirmButtonText: '知道了',
        },
      ).catch(() => undefined)
    }
    return false
  }

  values.forEach((value) => {
    if (!profileForm.allergies.includes(value)) profileForm.allergies.push(value)
  })
  allergyDraft.value = ''
  return true
}

function addPresetAllergy(value: string) {
  if (!profileForm.allergies.includes(value)) profileForm.allergies.push(value)
  allergyDraft.value = ''
  allergyField.value?.focus()
}

function removeAllergy(value: string) {
  profileForm.allergies = profileForm.allergies.filter((item) => item !== value)
  allergyField.value?.focus()
}

function onAllergyBlur() {
  allergyFocused.value = false
  addAllergy(false)
}

function handleAllergyKeydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'Enter' || event.key === ',' || event.key === '，') {
    event.preventDefault()
    addAllergy()
  } else if (event.key === 'Backspace' && !allergyDraft.value && profileForm.allergies.length) {
    profileForm.allergies.pop()
  }
}

function focusAllergyInput() {
  allergyField.value?.focus()
}

function toggleProfileValue(list: string[], value: string) {
  const index = list.indexOf(value)
  if (index >= 0) list.splice(index, 1)
  else list.push(value)
}

function openProfileUpload() {
  profileUploadInput.value?.click()
}

function handleProfileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    ElMessage.success(`已上传「${file.name}」，AI 正在解析体检单并生成健康档案…`)
  }
  input.value = ''
}

const planOptions = reactive({ meals: 3, max_minutes: 30, servings: 2, budget: 30, preference: '' })
const planBudgetText = computed(() => (planOptions.budget ? `单餐预算 ¥${planOptions.budget} 内` : '不限预算'))

const weather = reactive({
  city: '北京',
  adcode: '110000',
  emoji: '🌧️',
  temperature: 12,
  description: '小雨',
  condition: 'rain',
  severe: true,
})

const weatherLoading = ref(false)

function applyWeather(data: {
  city: string
  adcode: string
  emoji: string
  temperature: number
  description: string
  condition: string
  severe: boolean
}) {
  Object.assign(weather, data)
}

const isFatLossMode = computed(
  () =>
    profileForm.goals.includes('weight_loss') ||
    profileForm.goals.includes('fat_loss') ||
    /减脂|减重|控卡/.test(profileForm.notes),
)
const planning = ref(false)
const plan = ref<RecipePlan | null>(null)
const planError = ref('')
const history = ref<RecipeHistoryItem[]>([])
const smartImport = ref<InstanceType<typeof PantrySmartImport> | null>(null)
const rescuePlan = ref<RecipePlan | null>(null)
const rescueOpen = ref(false)
const rescuingId = ref(0)
const notifySending = ref(false)
const completedMeals = ref<Set<string>>(new Set())
const completingMeal = ref('')
const shoppingOpen = ref(false)
const shoppingSource = ref<{ id: number; name: string } | null>(null)
const shoppingPurchasing = ref(false)
const shoppingFreshRows = ref<Array<{ label: string; name: string; recipeAmount: string; sku: string; checked: boolean; specs: ProductSpec[]; specId: string }>>([])
const shoppingStaples = ref<Array<{ name: string; sku: string; checked: boolean; specs: ProductSpec[]; specId: string }>>([])
const staplesInCart = ref(false)
const shoppingCollapse = ref<string[]>([])
const favoriteIds = ref<Map<string, number>>(new Map())
const favoritingName = ref('')
const expandedMealKeys = ref<Set<string>>(new Set())
const offlineMemoOpen = ref(false)
const offlineMemoItems = ref<Array<{ id: string; name: string; detail: string }>>([])
const selectedIds = ref<number[]>([])
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const batchDeleting = ref(false)
const cookingOpen = ref(false)
const cookingContext = ref<{ plan: RecipePlan; meal: RecipeMeal; index: number } | null>(null)

const stats = computed(() => ({
  total: items.value.length,
  expiring: reminder.value?.counts.expiring || 0,
  expired: reminder.value?.counts.expired || 0,
}))

const statusType = (status: string) => {
  if (status === 'expired') return 'danger'
  if (status === 'expiring') return 'warning'
  if (status === 'fresh') return 'success'
  return 'info'
}

const profileSummary = computed(() => {
  const labels = [...(profile.value?.condition_labels || []), ...(profile.value?.allergies || [])]
  return labels.length ? labels.join(' · ') : '未设置'
})

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await pantryApi.list({ status: filters.status, query: filters.query.trim() })
    items.value = data.items
    categories.value = data.categories
    reminder.value = data.reminder
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '加载库存失败'
  } finally {
    loading.value = false
  }
}

async function loadFamily() {
  try {
    family.value = await familyApi.info()
    generatedInviteCode.value = family.value?.family.invite_code || ''
  } catch {
    family.value = null
    generatedInviteCode.value = ''
  }
}

async function createFamily() {
  if (family.value?.family?.id) return

  creatingFamily.value = true
  try {
    family.value = await familyApi.create()
    generatedInviteCode.value = family.value?.family.invite_code || ''
    inviteCode.value = ''
    await load()
    ElMessage.success('家庭创建成功')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '创建家庭失败')
  } finally {
    creatingFamily.value = false
  }
}

async function leaveCurrentFamily() {
  if (!family.value?.family?.id) return

  const isOwner = family.value.is_owner
  const familyName = family.value.family.name
  const message = isOwner
    ? `解散后数据将清空，所有成员都将退出「${familyName}」。确定解散吗？`
    : `退出后您将不再共享「${familyName}」的库存，确定退出吗？`

  try {
    await ElMessageBox.confirm(message, isOwner ? '解散家庭' : '退出家庭', {
      type: 'warning',
      confirmButtonText: isOwner ? '确认解散' : '确认退出',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  leavingFamily.value = true
  try {
    const result = await familyApi.leave()
    family.value = null
    generatedInviteCode.value = ''
    inviteCodeRevealed.value = false
    inviteCode.value = ''
    stopInviteCountdown()
    familyDialogOpen.value = false
    await load()
    ElMessage.success(
      result.action === 'dissolved' ? '家庭已解散' : '已退出当前家庭',
    )
  } catch (error) {
    ElMessage.error((error as ApiError).message || '操作失败')
  } finally {
    leavingFamily.value = false
  }
}

async function joinFamily() {
  const code = inviteCode.value.trim().toUpperCase()
  if (!code) {
    ElMessage.warning('请输入家人的邀请码')
    return
  }

  // 已经是户主/成员时，前端直接阻断，不发起加入请求
  if (family.value?.family?.id) {
    inviteCode.value = ''

    const goLeave = await ElMessageBox.confirm(
      '您已加入其他家庭。如需加入新家庭，请先退出当前家庭。',
      '加入家庭',
      {
        type: 'warning',
        confirmButtonText: '去退出',
        cancelButtonText: '取消',
      },
    )
      .then(() => true)
      .catch(() => false)

    if (goLeave) await leaveCurrentFamily()
    return
  }

  joiningFamily.value = true
  try {
    const joined = await familyApi.join(code)
    family.value = joined
    await load()
    inviteCode.value = ''

    await ElMessageBox.alert('加入成功', '加入家庭', {
      type: 'success',
      confirmButtonText: '知道了',
    }).catch(() => undefined)
  } catch (error) {
    inviteCode.value = ''

    await ElMessageBox.alert(
      (error as ApiError).message || '邀请码错误或已过期',
      '加入家庭',
      {
        type: 'error',
        confirmButtonText: '知道了',
      },
    ).catch(() => undefined)
  } finally {
    joiningFamily.value = false
  }
}

async function copyInviteCode() {
  if (!inviteCodeValid.value) {
    ElMessage.warning('邀请码已过期，请刷新后重试')
    return
  }
  const code = generatedInviteCode.value
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success('邀请码已复制')
  } catch {
    ElMessage.info(`邀请码：${code}`)
  }
}

async function copyInviteLink() {
  if (!inviteCodeValid.value) {
    ElMessage.warning('邀请码已过期，请刷新后重试')
    return
  }
  const code = generatedInviteCode.value
  if (!code) return
  const link = `${window.location.origin}/pantry?invite=${encodeURIComponent(code)}`
  try {
    await navigator.clipboard.writeText(link)
    ElMessage.success('邀请链接已复制，发给家人即可加入')
  } catch {
    ElMessage.info(link)
  }
}

function startEditFamilyName() {
  if (!family.value?.is_owner) return
  familyNameDraft.value = family.value.family.name
  editingFamilyName.value = true
}

function cancelEditFamilyName() {
  editingFamilyName.value = false
  familyNameDraft.value = ''
}

async function saveFamilyName() {
  const name = familyNameDraft.value.trim()
  if (!name) {
    ElMessage.warning('请输入家庭名称')
    return
  }

  savingFamilyName.value = true
  try {
    const data = await familyApi.rename(name)
    family.value = data
    editingFamilyName.value = false
    ElMessage.success('修改已实时同步至家庭成员')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '修改家庭名称失败')
  } finally {
    savingFamilyName.value = false
  }
}

function startEditMember(member: FamilyInfo['members'][number]) {
  editingMemberId.value = member.id
  memberNameDraft.value = familyMemberDisplayName(member)
}

function cancelEditMember() {
  editingMemberId.value = null
  memberNameDraft.value = ''
}

function saveMemberName(member: FamilyInfo['members'][number]) {
  const name = memberNameDraft.value.trim()
  if (!name) {
    ElMessage.warning('请输入成员备注')
    return
  }

  const key = familyMemberAliasKey(member)
  const next = { ...familyMemberAliases.value }

  // 备注只保存在当前浏览器/当前用户视角，绝不影响其他成员看到的名称
  if (name === member.display_name) {
    delete next[key]
  } else {
    next[key] = name
  }

  familyMemberAliases.value = next
  persistFamilyMemberAliases()
  editingMemberId.value = null
  memberNameDraft.value = ''
  ElMessage.success('备注已保存，仅自己可见')
}

function stopFamilyPolling() {
  if (familyPollTimer) {
    window.clearInterval(familyPollTimer)
    familyPollTimer = undefined
  }
}

function startFamilyPolling() {
  stopFamilyPolling()
  familyPollTimer = window.setInterval(() => {
    if (familyDialogOpen.value) void loadFamily()
  }, 5000)
}

watch(familyDialogOpen, (open) => {
  if (open) {
    void loadFamily()
    startFamilyPolling()
    return
  }
  stopFamilyPolling()
  editingFamilyName.value = false
  editingMemberId.value = null
  familyNameDraft.value = ''
  memberNameDraft.value = ''
})

async function removeMember(memberId: number, name: string) {
  try {
    await ElMessageBox.confirm(`确认将「${name}」移出当前家庭？移除后对方将无法查看共享库存。`, '移除家庭成员', {
      type: 'warning',
      confirmButtonText: '移除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  removingMember.value = memberId
  try {
    const result = await familyApi.removeMember(memberId)
    family.value = result.family
    await load()
    ElMessage.success('已移除家庭成员')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '移除失败')
  } finally {
    removingMember.value = null
  }
}

async function loadProfile() {
  try {
    const data = await pantryApi.profile()
    profile.value = data
    profileForm.conditions = data.conditions
    profileForm.goals = data.goals
    profileForm.allergies = data.allergies
    profileForm.notes = data.notes
    markProfileSaved()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '加载健康画像失败')
  }
}

function openCreate() {
  editing.value = null
  formError.value = ''
  shelfEstimate.value = null
  const today = new Date()
  Object.assign(form, {
    name: '',
    category: 'vegetable',
    quantity: 1,
    unit: '份',
    purchased_at: today.toISOString().slice(0, 10),
    // 不默认填 +7 天：由 AI 估算或用户自己选择，避免把猜测当成结论
    expires_at: '',
    note: '',
  })
  dialogOpen.value = true
}

function openEdit(item: PantryItem) {
  editing.value = item
  formError.value = ''
  shelfEstimate.value = null
  Object.assign(form, {
    name: item.name,
    category: item.category,
    quantity: item.quantity,
    unit: item.unit,
    purchased_at: item.purchased_at || '',
    expires_at: item.expires_at || '',
    note: item.note || '',
  })
  dialogOpen.value = true
}

function addDaysFrom(value: string | null | undefined, days: number): string {
  const base = value ? new Date(`${value}T00:00:00`) : new Date()
  const date = new Date(base.getTime())
  date.setDate(date.getDate() + days)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

async function estimateFormShelfLife() {
  const name = form.name.trim()
  if (!name || name.length < 1) return
  estimating.value = true
  try {
    const data = await pantryApi.estimateShelfLife(name)
    shelfEstimate.value = data
    if (data.days) {
      form.expires_at = addDaysFrom(form.purchased_at, data.days)
    } else {
      // 未估算时不保留默认 +7 天，避免把猜测当成结论
      form.expires_at = ''
      ElMessage.info(data.warning || '没有找到常规保质期，请手动选择到期日')
    }
  } catch (error) {
    ElMessage.error((error as ApiError).message || '保质期估算失败')
  } finally {
    estimating.value = false
  }
}

function applyEstimateDays(days: number) {
  form.expires_at = addDaysFrom(form.purchased_at, days)
}

function estimateConfidenceClass(percent: number): string {
  if (!percent) return 'unknown'
  if (percent >= 80) return 'high'
  if (percent >= 60) return 'medium'
  return 'low'
}

async function saveItem() {
  formError.value = ''
  if (!form.name.trim()) {
    formError.value = '请填写食材名称'
    return
  }
  if (!form.quantity || form.quantity <= 0) {
    formError.value = '数量需要大于 0'
    return
  }
  saving.value = true
  try {
    const payload = { ...form, name: form.name.trim() }
    if (editing.value) {
      await pantryApi.update(editing.value.id, payload)
      ElMessage.success('食材已更新')
    } else {
      await pantryApi.create(payload)
      ElMessage.success('食材已加入库存')
    }
    dialogOpen.value = false
    await load()
  } catch (error) {
    formError.value = (error as ApiError).message || '保存失败'
  } finally {
    saving.value = false
  }
}

function onTableSelection(rows: PantryItem[]) {
  selectedIds.value = rows.map((row) => row.id)
}

async function removeSelectedItems() {
  if (!selectedIds.value.length) return
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${selectedIds.value.length} 项食材吗？删除后不可恢复。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  batchDeleting.value = true
  try {
    const result = await pantryApi.removeMany(selectedIds.value)
    ElMessage.success(`已删除 ${result.deleted} 项食材`)
    selectedIds.value = []
    tableRef.value?.clearSelection()
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '批量删除失败')
  } finally {
    batchDeleting.value = false
  }
}

async function removeItem(item: PantryItem) {
  try {
    await ElMessageBox.confirm(`确定要删除该食材「${item.name}」吗？`, '删除食材', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  try {
    await pantryApi.remove(item.id)

    // 成功删除后立即更新本地列表，统计数字同步减少
    items.value = items.value.filter((entry) => entry.id !== item.id)
    selectedIds.value = selectedIds.value.filter((id) => id !== item.id)
    if (editing.value?.id === item.id) {
      dialogOpen.value = false
      editing.value = null
    }

    ElMessage.success('已删除')
    await load()
  } catch (error) {
    const apiError = error as ApiError
    const message = apiError.message || ''
    const isMissing =
      apiError.status === 404 ||
      /食材不存在|不存在/.test(message)

    if (isMissing) {
      // 本地列表里残留了已被其他页面/请求删除的脏数据
      items.value = items.value.filter((entry) => entry.id !== item.id)
      selectedIds.value = selectedIds.value.filter((id) => id !== item.id)
      if (editing.value?.id === item.id) {
        dialogOpen.value = false
        editing.value = null
      }
      ElMessage.warning('该食材已不存在，已为您自动刷新库存。')
      await load()
      return
    }

    ElMessage.error(message || '删除失败')
  }
}

function scheduleHealthTip() {
  window.clearTimeout(healthTipTimer)
  const hasProfile =
    profileForm.conditions.length || profileForm.goals.length || profileForm.allergies.length || profileForm.notes.trim()
  if (!hasProfile) {
    healthTip.value = ''
    healthTipSource.value = ''
    return
  }
  healthTipTimer = window.setTimeout(refreshHealthTip, 450)
}

async function refreshHealthTip() {
  healthTipLoading.value = true
  try {
    const result = await pantryApi.healthTip({
      conditions: profileForm.conditions,
      goals: profileForm.goals,
      allergies: profileForm.allergies,
      notes: profileForm.notes,
    } as { conditions: string[]; goals: string[]; allergies: string[]; notes: string })
    healthTip.value = result.tip
    healthTipSource.value = result.source
  } catch {
    healthTip.value = ''
  } finally {
    healthTipLoading.value = false
  }
}

async function saveProfile() {
  if (!addAllergy()) return
  profileSaving.value = true
  try {
    const data = await pantryApi.saveProfile({
      conditions: profileForm.conditions,
      goals: profileForm.goals,
      allergies: profileForm.allergies,
      notes: profileForm.notes,
    })
    profile.value = { ...data.profile, options: profile.value?.options }
    markProfileSaved()
    await refreshHealthTip()
    ElMessage.success('保存成功')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '保存失败')
  } finally {
    profileSaving.value = false
  }
}

function isUsablePlan(candidate: RecipePlan | null | undefined): boolean {
  return Boolean(
    candidate?.meals?.some(
      (meal) =>
        meal.name &&
        !meal.name.includes('库存不足') &&
        ((meal.ingredients || []).length > 0 ||
          (meal.main_ingredients || []).length > 0),
    ),
  )
}

function latestUsablePlan(): RecipePlan | null {
  return history.value.find((item) => isUsablePlan(item.result))?.result || null
}

function applyBestPlan(candidate: RecipePlan) {
  // 后端在库存为空时可能返回“库存不足”占位方案；
  // 若历史里有模型生成的有效食谱，优先展示有效方案。
  plan.value = isUsablePlan(candidate)
    ? candidate
    : latestUsablePlan() || candidate
}

async function generatePlan() {
  if (weatherLoading.value) {
    ElMessage.info('天气信息更新中，请稍候再生成')
    return
  }
  if (!hasHealthProfile.value) {
    try {
      await ElMessageBox.confirm(
        '还没有完善健康画像。补充后，食谱会更贴合你的健康状况与忌口。',
        '先完善健康画像？',
        { type: 'info', confirmButtonText: '去完善', cancelButtonText: '仍然生成' },
      )
      goHealthProfile()
      return
    } catch {
      // 用户选择仍然生成
    }
  }
  completedMeals.value = new Set()
  expandedMealKeys.value = new Set()
  planning.value = true
  planError.value = ''
  try {
    const generated = await pantryApi.plan({
      meals: planOptions.meals,
      max_minutes: planOptions.max_minutes,
      servings: planOptions.servings,
      budget: planOptions.budget,
      weather: {
        city: weather.city,
        condition: weather.condition,
        temperature: weather.temperature,
        description: weather.description,
      },
      preference: planOptions.preference.trim(),
    })

    activeTab.value = 'plan'
    await loadHistory()
    applyBestPlan(generated)
  } catch (error) {
    planError.value = (error as ApiError).message || '生成失败，请稍后重试'
  } finally {
    planning.value = false
  }
}

async function loadHistory() {
  try {
    history.value = (await pantryApi.history(5)).items
  } catch {
    history.value = []
  }
}

function openHistory(item: RecipeHistoryItem) {
  completedMeals.value = new Set()
  plan.value = item.result
  activeTab.value = 'plan'
}

function conditionLabel(key: string) {
  const map: Record<string, string> = {
    hypertension: '高血压',
    diabetes: '糖尿病',
    hyperlipidemia: '高血脂',
    gout: '痛风',
    allergy: '过敏',
    allergies: '过敏',
    kidney: '肾功能不全',
    weight_loss: '减脂',
    low_sodium: '控盐',
    low_sugar: '控糖',
    high_protein: '高蛋白',
    balanced: '均衡',
  }
  return map[key] || key
}

function shortNote(note: string | null | undefined): string {
  return (note || '').trim() || '—'
}

function formatDate(value: string | null) {
  return value || '未设置'
}

async function rescueItem(item: PantryItem) {
  rescuingId.value = item.id
  try {
    rescuePlan.value = await pantryApi.rescue(item.id, 2)
    rescueOpen.value = true
  } catch (error) {
    ElMessage.error((error as ApiError).message || '生成拯救食谱失败')
  } finally {
    rescuingId.value = 0
  }
}

function useRescuePlan() {
  if (rescuePlan.value) {
    completedMeals.value = new Set()
    plan.value = rescuePlan.value
    rescueOpen.value = false
    activeTab.value = 'plan'
  }
}

const selectedFresh = computed(() => shoppingFreshRows.value.filter((item) => item.checked))
const selectedStaples = computed(() => shoppingStaples.value.filter((item) => item.checked))
const cartStaples = computed(() => (staplesInCart.value ? selectedStaples.value : []))
const selectedShoppingCount = computed(() => selectedFresh.value.length)
const selectedStaplesCount = computed(() => selectedStaples.value.length)

function currentSpec(row: { specs: ProductSpec[]; specId: string }): ProductSpec {
  return row.specs.find((spec) => spec.id === row.specId) || row.specs[0]
}

function rowPrice(row: { specs: ProductSpec[]; specId: string }): number {
  return currentSpec(row).price
}

const freshTotal = computed(() => selectedFresh.value.reduce((sum, item) => sum + rowPrice(item), 0))
const stapleTotal = computed(() => cartStaples.value.reduce((sum, item) => sum + rowPrice(item), 0))
const checkoutTotal = computed(() => freshTotal.value + stapleTotal.value)
const canCheckout = computed(() => selectedFresh.value.length > 0 || cartStaples.value.length > 0)
const ctaLabel = computed(() => {
  const hasFresh = selectedFresh.value.length > 0
  const hasStaples = cartStaples.value.length > 0
  if (hasFresh && hasStaples) return `去结算（生鲜极速达 / 调料常规达）${formatPrice(checkoutTotal.value)}`
  if (hasFresh) return `🚀 极速送生鲜（30分钟）${formatPrice(checkoutTotal.value)}`
  if (hasStaples) return `📦 常规发货调料 ${formatPrice(checkoutTotal.value)}`
  if (selectedStaplesCount.value) return '请将调料加入购物车'
  return '请选择商品'
})

const allShoppingSelected = computed({
  get: () => shoppingFreshRows.value.length > 0 && shoppingFreshRows.value.every((item) => item.checked),
  set: (value: boolean) => {
    shoppingFreshRows.value = shoppingFreshRows.value.map((item) => ({ ...item, checked: value }))
  },
})

const STAPLE_WORDS = ['油', '盐', '酱油', '生抽', '老抽', '蚝油', '醋', '料酒', '淀粉', '糖', '胡椒', '花椒', '八角', '桂皮', '香叶', '味精', '鸡精', '豆瓣酱', '番茄酱', '辣椒酱', '芝麻', '孜然', '咖喱', '五香粉', '十三香', '香油', '腐乳', '豆豉']
const FRESH_WORDS = ['菜', '鱼', '肉', '蛋', '果', '葱', '姜', '蒜', '青椒', '瓜', '豆', '菌', '菇']
const STAPLE_EXCEPTIONS = ['生抽', '老抽', '酱油', '蚝油', '料酒', '醋', '淀粉', '胡椒', '花椒', '豆瓣酱', '番茄酱', '辣椒酱', '香油', '芝麻', '孜然', '咖喱', '蒸鱼豉油', '豉油', '鱼露', '豆豉']

function isStapleName(name: string): boolean {
  const text = name || ''
  if (STAPLE_EXCEPTIONS.some((word) => text.includes(word))) return true
  if (FRESH_WORDS.some((word) => text.includes(word))) return false
  return STAPLE_WORDS.some((word) => text.includes(word))
}

function isWaterName(name: string): boolean {
  return ['清水', '水', '冰块', '冰'].includes(name)
}

function baseShoppingName(raw: string): string {
  return (raw || '')
    .replace(/（.*?）/g, '')
    .replace(/\s*(?:半|一|两|三|四|五|六|七|八|九|十|\d+(?:\.\d+)?)?\s*(?:小碗|小勺|汤勺|瓶|袋|盒|个|根|把|块|片|条|只|颗|片|杯|g|ml|kg|份).*$/i, '')
    .replace(/\s*(适量|少量|少许).*$/, '')
    .trim()
}

function parseShoppingRow(label: string) {
  const cleaned = label.replace(/（.*?）/g, '').trim()
  let name = cleaned
  let amount = '1份'
  const match = cleaned.match(/^(.+?)\s+((?:半|一|两|三|四|五|六|七|八|九|十|\d+(?:\.\d+)?).*)$/)
  if (match) {
    name = match[1]
    amount = match[2]
  } else {
    const parts = cleaned.split(/\s+/)
    if (parts.length > 1) {
      name = parts[0]
      amount = parts.slice(1).join(' ')
    }
  }
  name = baseShoppingName(name) || name
  if (/^(适量|少量|少许)$/.test(amount)) amount = '适量'
  return { label, name, amount: amount.trim(), checked: true }
}

async function loadFavorites() {
  try {
    const result = await favoriteApi.list()
    favoriteIds.value = new Map(result.items.map((item) => [item.recipe_name, item.id]))
  } catch {
    // 收藏状态失败不影响食材管理
  }
}

async function toggleFavorite(meal: RecipeMeal) {
  const name = meal.name
  if (!name || favoritingName.value) return
  favoritingName.value = name
  try {
    const existing = favoriteIds.value.get(name)
    if (existing) {
      await favoriteApi.remove(existing)
      const next = new Map(favoriteIds.value)
      next.delete(name)
      favoriteIds.value = next
      ElMessage.success('已取消收藏')
    } else {
      const result = await favoriteApi.add(name, meal as unknown as Record<string, unknown>)
      const next = new Map(favoriteIds.value)
      next.set(name, result.favorite.id)
      favoriteIds.value = next
      ElMessage.success('已加入我的收藏')
    }
  } catch (error) {
    ElMessage.error((error as ApiError).message || '收藏操作失败')
  } finally {
    favoritingName.value = ''
  }
}

function askAssistant(meal: RecipeMeal) {
  const context = { ...meal, title: meal.name }
  router.push({ name: 'assistant', query: { context: JSON.stringify(context) } })
}

function fillShoppingRows(labels: string[], source: { id: number; name: string } | null = null) {
  const seen = new Set<string>()
  shoppingFreshRows.value = []
  shoppingStaples.value = []
  staplesInCart.value = false
  shoppingSource.value = source
  for (const label of labels) {
    const row = parseShoppingRow(label)
    if (seen.has(row.name) || isWaterName(row.name)) continue
    seen.add(row.name)
    if (isStapleName(row.name)) {
      const product = buildStapleProduct(row.name)
      shoppingStaples.value.push({
        name: row.name,
        sku: product.sku,
        checked: false,
        specs: product.specs,
        specId: product.specs[0].id,
      })
    } else {
      const product = buildFreshProduct(row.name, row.amount)
      shoppingFreshRows.value.push({
        label,
        name: row.name,
        recipeAmount: row.amount,
        sku: product.sku,
        checked: true,
        specs: product.specs,
        specId: product.specs[0].id,
      })
    }
  }
  shoppingOpen.value = true
}

function openShoppingList() {
  if (!plan.value) return
  const labels = [...plan.value.shopping_list]
  for (const meal of plan.value.meals) {
    for (const item of meal.missing || []) {
      labels.push(`${item.name} ${item.amount}（${meal.name}）`)
    }
  }
  fillShoppingRows(labels)
}

async function openFavoriteShopping(favoriteId: number, fallbackName = '') {
  try {
    const favorite = await favoriteApi.missing(favoriteId)
    const labels = (favorite.missing || []).map((item) => `${item.name} ${item.amount}`.trim())
    fillShoppingRows(labels, { id: favoriteId, name: favorite.recipe_name || fallbackName || '收藏菜谱' })
    if (!labels.length) ElMessage.success('这道菜的主料在家庭库存中已经齐全')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '读取收藏缺料失败')
  }
}

function addStaplesToCart() {
  const count = selectedStaplesCount.value
  if (!count) return
  staplesInCart.value = true
  ElMessage.success(`已将 ${count} 件调料加入购物车，常规发货（次日达）`)
}

function resetStaplesCart() {
  staplesInCart.value = false
}

async function writeClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
}

function shoppingShareText(): string {
  const fresh = selectedFresh.value.map((item) => `${item.sku}（菜谱用量：${item.recipeAmount}）`)
  const staples = selectedStaples.value.map((item) => `${item.name} ${currentSpec(item).label}`)
  return `【生鲜】${fresh.join('、') || '暂无'}\n【调料】${staples.join('、') || '暂无'}`
}

function saveShoppingList() {
  const payload = {
    saved_at: new Date().toISOString(),
    fresh: shoppingFreshRows.value.map((item) => ({ ...item })),
    staples: shoppingStaples.value.map((item) => ({ ...item })),
  }
  localStorage.setItem('fsai_shopping_list', JSON.stringify(payload))
  ElMessage.success('购物清单已保存到本机')
}

async function shareShoppingList() {
  const text = shoppingShareText()
  if (navigator.share) {
    try {
      await navigator.share({ title: '我的购物清单', text })
      return
    } catch {
      // 用户取消系统分享时回退到复制
    }
  }
  await writeClipboard(text)
  ElMessage.success('清单已复制，可发给家人')
}

function openOfflineMemo() {
  const items = [
    ...shoppingFreshRows.value.map((item) => ({
      id: `fresh-${item.name}`,
      name: item.name,
      detail: `${item.sku} · 菜谱用量 ${item.recipeAmount}`,
    })),
    ...shoppingStaples.value.map((item) => ({
      id: `staple-${item.name}`,
      name: item.name,
      detail: currentSpec(item).label,
    })),
  ]
  if (!items.length) {
    ElMessage.info('当前没有需要线下采购的食材')
    return
  }
  offlineMemoItems.value = items
  offlineMemoOpen.value = true
}

async function checkoutShopping() {
  const fresh = selectedFresh.value
  const staples = cartStaples.value
  if (!fresh.length && !staples.length) {
    ElMessage.info('请先选择需要配送的商品')
    return
  }
  shoppingPurchasing.value = true
  try {
    const labels = [
      ...fresh.map((item) => {
        const spec = currentSpec(item)
        return `${item.name} ${spec.quantity}${spec.unit}`
      }),
      ...staples.map((item) => {
        const spec = currentSpec(item)
        return `${item.name} ${spec.quantity}${spec.unit}`
      }),
    ]
    const result = await pantryApi.checkoutShopping(labels, staples.length > 0)
    const purchasedNames = new Set(result.purchased.map((item) => item.name))
    if (plan.value) {
      plan.value.shopping_list = plan.value.shopping_list.filter(
        (label) => ![...purchasedNames].some((name) => label.includes(name)),
      )
      plan.value.meals.forEach((meal) => {
        if (meal.missing) meal.missing = meal.missing.filter((item) => !purchasedNames.has(item.name))
      })
    }
    shoppingFreshRows.value = shoppingFreshRows.value.filter((item) => !purchasedNames.has(item.name))
    shoppingStaples.value = shoppingStaples.value.filter((item) => !purchasedNames.has(item.name))
    staplesInCart.value = false
    shoppingOpen.value = false
    ElMessage.success(result.message)
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '结算失败')
  } finally {
    shoppingPurchasing.value = false
  }
}

async function removeMeal(planData: RecipePlan, index: number) {
  const meal = planData.meals[index]
  try {
    await ElMessageBox.confirm(
      `从当前方案中移除「${meal?.name || '这道菜'}」吗？`,
      '移除菜谱',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const result = await pantryApi.removeMeal(planData.plan_id, index)
    completedMeals.value = new Set()
    if (result.deleted_plan) {
      plan.value = null
      activeTab.value = 'inventory'
      ElMessage.success('方案已清空')
    } else if (result.result) {
      plan.value = result.result
      ElMessage.success('已从方案中移除')
    }
    await loadHistory()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '移除失败')
  }
}

function startCooking(planData: RecipePlan, meal: RecipeMeal, index: number) {
  cookingContext.value = { plan: planData, meal, index }
  cookingOpen.value = true
}

async function completeCooking() {
  if (!cookingContext.value) return
  await completeMeal(cookingContext.value.plan, cookingContext.value.index)
}

function mealDoneKey(plan: RecipePlan, index: number): string {
  return `${plan.plan_id || 'plan'}-${index}`
}

function isMealDone(plan: RecipePlan, index: number): boolean {
  return completedMeals.value.has(mealDoneKey(plan, index))
}

function mealDetailKey(planData: RecipePlan | null, index: number): string {
  return `${planData?.plan_id || 'draft'}-${index}`
}

function isMealExpanded(planData: RecipePlan | null, index: number): boolean {
  return expandedMealKeys.value.has(mealDetailKey(planData, index))
}

function toggleMealDetails(planData: RecipePlan | null, index: number) {
  const key = mealDetailKey(planData, index)
  const next = new Set(expandedMealKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedMealKeys.value = next
}

function isAuxiliaryName(name: string): boolean {
  return /(盐|生抽|老抽|酱油|蚝油|醋|料酒|食用油|白糖|冰糖|淀粉|胡椒粉|花椒|葱|姜|蒜|豆瓣酱|鸡精|味精|水)/.test(name)
}

function mainIngredients(meal: RecipeMeal) {
  if (meal.main_ingredients?.length) return meal.main_ingredients
  return (meal.ingredients || []).filter((item) =>
    item.role ? item.role !== 'auxiliary' : !isAuxiliaryName(item.name),
  )
}

function auxiliaryIngredients(meal: RecipeMeal) {
  if (meal.auxiliary_ingredients?.length) return meal.auxiliary_ingredients
  return (meal.ingredients || []).filter((item) =>
    item.role ? item.role === 'auxiliary' : isAuxiliaryName(item.name),
  )
}

function mealMissing(meal: RecipeMeal) {
  const items = meal.missing || (meal.ingredients || []).filter((item) => item.from_pantry === false)
  return items.filter((item) => !isStapleName(item.name) && !isWaterName(item.name))
}

function mealEmoji(name: string) {
  const text = name || ''
  if (/红烧肉|排骨|肘子|牛腩|肉/.test(text)) return '🍖'
  if (/粥|羹|糊/.test(text)) return '🥣'
  if (/鱼|虾|蟹|海鲜/.test(text)) return '🐟'
  if (/鸡|鸭|鹅/.test(text)) return '🍗'
  if (/面|粉|米线/.test(text)) return '🍜'
  if (/饭|炒饭|盖饭/.test(text)) return '🍚'
  if (/汤|煲|炖/.test(text)) return '🍲'
  if (/菜|蔬|瓜|豆腐|菌|菇/.test(text)) return '🥬'
  if (/蛋/.test(text)) return '🍳'
  return '🍽️'
}

function traceTone(line: string) {
  const text = line || ''
  if (/预算|成本|价格|省钱/.test(text)) return 'budget'
  if (/健康|过敏|高血压|糖尿病|忌口|营养/.test(text)) return 'health'
  if (/库存|临期|食材|补购/.test(text)) return 'pantry'
  if (/口味|偏好|想吃/.test(text)) return 'taste'
  return 'default'
}

function mealExerciseTip(meal: RecipeMeal) {
  if (!isFatLossMode.value) return ''

  const calories = Number(meal.nutrition?.energy_kcal || 0)
  if (!calories) return ''

  const minutes = Math.max(1, Math.round(calories / 10))
  const description = String(weather.description || '')
  const isRain = weather.condition === 'rain' || /雨|雷/.test(description)
  const isSnow = weather.condition === 'snow' || /雪|冰|冻/.test(description)
  const isBadAir =
    weather.condition === 'haze' ||
    /霾|雾|污染|沙尘/.test(description)

  if (isRain) {
    return `🏃 当前户外降雨，建议替换为室内运动 ${minutes} 分钟`
  }

  if (isSnow) {
    return `🏃 当前户外降雪，建议替换为室内运动 ${minutes} 分钟`
  }

  if (isBadAir) {
    return `🏃 当前空气质量不佳，建议进行室内低强度运动 ${minutes} 分钟`
  }

  return `🏃 天气适宜，建议去户外慢跑 ${minutes} 分钟`
}

function normalizeStapleName(name: string): string {
  if (name.includes('水淀粉') || name.includes('干淀粉')) return '干淀粉'
  if (name.includes('盐')) return '食盐'
  return name
}

function stapleShoppingText(name: string): string {
  const normalized = normalizeStapleName(name)
  if (normalized === '食盐') return '食盐 1袋（约200g）'
  if (normalized.includes('生抽')) return '生抽 1瓶（约500ml）'
  if (['酱油', '老抽', '蚝油', '醋', '料酒', '油'].some((word) => normalized.includes(word))) {
    return `${normalized} 1瓶（约500ml）`
  }
  if (['淀粉', '糖', '胡椒', '花椒', '鸡精', '味精', '咖喱'].some((word) => normalized.includes(word))) {
    return `${normalized} 1袋（约200g）`
  }
  if (normalized.includes('酱')) return `${normalized} 1瓶（约500g）`
  return `${normalized} 1份`
}


const planFocusName = computed(() => plan.value?.focus_item?.name || '')
const planFocusInFinal = computed(() => {
  if (!plan.value) return false
  if (typeof plan.value.focus_in_final === 'boolean') return plan.value.focus_in_final
  const name = planFocusName.value
  if (!name) return false
  return plan.value.meals.some((meal) =>
    (meal.ingredients || []).some((item) => item.name.includes(name) || name.includes(item.name)),
  )
})
const planMealShortfall = computed(() => {
  if (!plan.value) return null
  const requested = Number(plan.value.requested_meals || 0)
  const actual = Number(plan.value.actual_meals || plan.value.meals.length || 0)
  return requested > actual ? { requested, actual } : null
})
const planSummaryText = computed(() => {
  if (!plan.value) return ''
  const count = plan.value.meals.length || 0
  const raw = String(plan.value.summary || '').trim()
  // 兼容历史方案中偏说明书的旧文案
  if (!raw || raw.startsWith('当前方案共')) {
    return `🍄 为您生成了 ${count} 道菜的方案，记得按时吃饭哦~`
  }
  return raw
})
function prioritizeWeatherStep(lines: string[]) {
  const index = lines.findIndex((line) => String(line).startsWith('天气与环境感知'))
  if (index <= 0) return lines
  return [lines[index], ...lines.slice(0, index), ...lines.slice(index + 1)]
}

const planAgentTrace = computed(() => {
  const lines = (plan.value?.agent_trace || []).filter((line) => {
    const text = String(line)
    return !text.includes('追加助手菜谱')
      && !text.includes('已从收藏加入今日排期')
      && !text.includes('移除菜谱')
      && !/AI 智能修正|规则引擎/.test(text)
  })
  if (plan.value?.pantry_count === 0) {
    const emptyLine = '检测到当前库存为空，正根据用户口味偏好生成标准食谱。已为您自动生成全套采购清单。'
    const cleaned = lines.filter(
      (line) => line !== emptyLine && !/(消耗库存|使用 0 项库存|读取库存 0 项|库存充足)/.test(String(line)),
    )
    return prioritizeWeatherStep([emptyLine, ...cleaned])
  }
  return prioritizeWeatherStep(lines)
})

const traceExpanded = ref(false)
const visibleAgentTrace = computed(() =>
  traceExpanded.value ? planAgentTrace.value : planAgentTrace.value.slice(0, 2),
)

watch(
  () => plan.value?.plan_id,
  () => {
    traceExpanded.value = false
  },
)

function highlightNutrition(text: string): string {
  const escaped = String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

  return escaped.replace(
    /(低盐|控糖|高纤维|低糖|高蛋白|低脂|高钠|少油|低嘌呤)/g,
    '<span style="color: #10B981; font-weight: bold;">$1</span>',
  )
}

const weatherGuardianTip = computed(() => {
  const city = weather.city || '当前位置'
  const temp = weather.temperature
  const isCold = temp <= 15 || weather.severe || /雨|雪|降温/.test(weather.description)
  const isHot = temp >= 28 || /热|高温|闷热/.test(weather.description)

  if (isCold) {
    return `🌡️ 环境感知：今日${city} ${temp}℃ 降温，AI 已优先为您安排暖胃热汤/炖菜，请注意保暖。`
  }

  if (isHot) {
    return `🌡️ 环境感知：今日${city} ${temp}℃ 天气炎热，AI 已为您多搭配清爽解腻的菜品，请注意补水。`
  }

  return `🌡️ 环境感知：今日${city} ${temp}℃，AI 已结合天气调整菜品搭配，请注意适时增减衣物。`
})

const planWarnings = computed(() =>
  (plan.value?.warnings || [])
    .filter((warning) => {
      const text = String(warning)
      return (
        !text.includes('一票否决') &&
        !/AI 智能修正|规则引擎|AI 方案需修正/.test(text)
      )
    })
    .map((warning) => String(warning)),
)

const planOptimizationTip = computed(() => {
  const raw = [
    plan.value?.ai_error || '',
    ...(plan.value?.warnings || []),
    ...(plan.value?.agent_trace || []),
  ].join(' ')

  if (!/AI 智能修正|规则引擎|AI 方案需修正/.test(raw)) return ''

  if (/五花肉|高脂|胃炎|减脂/.test(raw)) {
    return '💡 AI 已自动优化：为配合您的胃炎和减脂目标，已将高脂的五花肉替换为优质蛋白。'
  }

  return '💡 AI 已结合您的健康画像自动优化了菜品搭配。'
})
const planFocusMissing = computed(() => Boolean(planFocusName.value && plan.value && !planFocusInFinal.value))
const planFocusAdjusted = computed(() => Boolean(planFocusName.value && planFocusInFinal.value))

const planShoppingGroups = computed(() => {
  const fresh: Array<{ name: string; amount: string }> = []
  const staples: string[] = []
  const seenFresh = new Set<string>()
  const seenStaples = new Set<string>()
  for (const label of plan.value?.shopping_list || []) {
    const row = parseShoppingRow(label)
    if (isWaterName(row.name)) continue
    if (isStapleName(row.name)) {
      const stapleText = stapleShoppingText(row.name)
      if (!seenStaples.has(stapleText)) {
        seenStaples.add(stapleText)
        staples.push(stapleText)
      }
    } else if (!seenFresh.has(row.name)) {
      seenFresh.add(row.name)
      fresh.push({ name: row.name, amount: row.amount })
    }
  }
  return { fresh, staples }
})

async function completeMeal(planData: RecipePlan, index: number) {
  const key = mealDoneKey(planData, index)
  completingMeal.value = key
  try {
    const result = await pantryApi.completeRecipe(planData.plan_id, index)
    completedMeals.value = new Set(completedMeals.value).add(key)

    if (result.already_done) {
      ElMessage.info('这道菜已经完成过，库存不会重复扣减')
    } else {
      const meal = planData.meals[index]
      const nutrition = meal?.nutrition || {}
      const calories = Math.round(Number(nutrition.energy_kcal || 0))

      // 同步到仪表盘的「今日热量」KPI
      addMeal({
        name: meal?.name || '今日餐食',
        category: '家常菜',
        calories: Number(nutrition.energy_kcal || 0),
        protein_g: Number(nutrition.protein_g || 0),
        fat_g: Number(nutrition.fat_g || 0),
        carbs_g: Number(nutrition.carbs_g || 0),
      })

      ElMessage.success(
        `✅ 已记录 ${calories} kcal 摄入，食材已从库存扣除`,
      )
    }

    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '完成失败')
  } finally {
    completingMeal.value = ''
  }
}

async function sendDigest() {
  notifySending.value = true
  try {
    const data = await pantryApi.notifyTest()
    const simulated = data.channels.find((item) => item.channel === 'email')?.status === 'simulated'
    ElMessage.success(simulated ? '摘要已生成；未配置 SMTP，已写入模拟邮件日志' : '今日摘要已发送')
  } catch (error) {
    ElMessage.error((error as ApiError).message || '发送失败')
  } finally {
    notifySending.value = false
  }
}

function onPantryReminder(event: Event) {
  const detail = (event as CustomEvent).detail as PantryReminder | null
  if (!detail) return
  const before = `${reminder.value?.counts.expiring}-${reminder.value?.counts.expired}-${reminder.value?.urgent_count}`
  const after = `${detail.counts.expiring}-${detail.counts.expired}-${detail.urgent_count}`
  reminder.value = detail
  if (before !== after) load()
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!isHealthProfilePage.value || !isProfileDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(async () => {
  if (!isHealthProfilePage.value || !isProfileDirty.value) return true

  try {
    await ElMessageBox.confirm(
      '您有未保存的修改，确定要离开吗？',
      '未保存的修改',
      {
        type: 'warning',
        confirmButtonText: '确认离开',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return false
  }

  restoreProfileSnapshot()
  return true
})

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  if (String(route.query.tab || '') === 'profile') {
    router.replace({ name: 'health-profile' })
    return
  }
  await Promise.all([load(), loadProfile(), loadFavorites(), loadFamily()])
  inviteCode.value = ''
  await loadHistory()
  const requestedTab = String(route.query.tab || localStorage.getItem('fsai_pantry_tab') || '')
  if (requestedTab === 'plan' && history.value.length) {
    plan.value = latestUsablePlan() || history.value[0].result
    activeTab.value = 'plan'
  } else if (['inventory', 'plan', 'favorites'].includes(requestedTab)) {
    activeTab.value = requestedTab as 'inventory' | 'plan' | 'favorites'
  }
  const purchaseName = String(route.query.purchase || '').trim()
  const favoriteId = Number(route.query.favorite_id || route.query.recipe_id || 0)
  if (favoriteId) {
    await openFavoriteShopping(favoriteId, purchaseName)
  } else if (purchaseName && plan.value) {
    openShoppingList()
  }
  window.addEventListener('pantry:reminder', onPantryReminder)
})

watch(
  () => [route.query.favorite_id, route.query.recipe_id, route.query.purchase],
  async () => {
    const favoriteId = Number(route.query.favorite_id || route.query.recipe_id || 0)
    if (!favoriteId) return
    const name = String(route.query.purchase || '').trim()
    await openFavoriteShopping(favoriteId, name)
  },
)

watch(activeTab, (tab) => {
  localStorage.setItem('fsai_pantry_tab', tab)
  if (tab === 'plan' && !plan.value && history.value.length) {
    plan.value = latestUsablePlan() || history.value[0].result
  }
})

watch(
  () => route.query.tab,
  (tab) => {
    const next = String(tab || '')
    if (['inventory', 'plan', 'favorites'].includes(next)) {
      activeTab.value = next as 'inventory' | 'plan' | 'favorites'
    }
  },
)

onUnmounted(() => {
  window.clearTimeout(healthTipTimer)
  stopFamilyPolling()
  stopInviteCountdown()
  window.removeEventListener('pantry:reminder', onPantryReminder)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<template>
  <div class="page pantry-page" :class="{ 'health-profile-page': isHealthProfilePage }">
    <header class="page-head">
      <div>
        <h1 class="page-title">{{ isHealthProfilePage ? '我的专属 AI 健康档案' : '家庭食材管家' }}</h1>
        <p class="page-sub">
          {{
            isHealthProfilePage
              ? '健康画像会实时同步到扫码检测预警与一日三餐规划。'
              : '录入库存与保质期，临期提醒，AI Agent 结合健康画像规划食谱。'
          }}
        </p>
      </div>
      <div v-if="!isHealthProfilePage" class="head-actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button @click="smartImport?.open('receipt')">拍照 / 小票</el-button>
        <el-button @click="smartImport?.open('voice')">语音</el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          添加食材
        </el-button>
      </div>

    </header>

    <section v-if="family && !isHealthProfilePage" class="family-bar card">
      <button type="button" class="family-members family-members-button" @click="familyDialogOpen = true">
        <div class="family-avatar-stack">
          <span v-for="member in family.members" :key="member.id" class="family-avatar" :title="member.display_name">
            {{ member.initial }}
          </span>
        </div>
        <div class="family-members-copy">
          <div class="family-name">{{ family.family.name }}</div>
          <div class="family-sub">{{ family.member_count }} 位家人 · 点击查看成员</div>
        </div>
      </button>
      <div class="family-invite">
        <span class="family-invite-label">邀请码</span>

        <div class="family-code-wrap">
          <div class="family-code-row">
            <button
              v-if="!inviteCodeRevealed"
              type="button"
              class="family-code family-code-get"
              @click="obtainInviteCode"
            >
              点击获取邀请码
            </button>

            <template v-else>
              <span
                v-if="inviteCodeExpired"
                class="family-code family-code-expired"
              >
                邀请码已过期
              </span>
              <button
                v-else
                type="button"
                class="family-code"
                @click="copyInviteCode"
              >
                {{ generatedInviteCode }}
              </button>

              <button
                type="button"
                class="family-code-refresh"
                aria-label="刷新邀请码"
                title="刷新邀请码"
                @click="refreshInviteCode"
              >
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M20 11a8 8 0 0 0-14.9-3M4 5v4h4M4 13a8 8 0 0 0 14.9 3M20 19v-4h-4"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
            </template>
          </div>
          <span v-if="inviteCodeRevealed" class="family-code-expiry">
            {{ inviteCountdownText }}
          </span>
        </div>

        <el-input
          v-model="inviteCode"
          class="family-join-input"
          maxlength="6"
          placeholder="输入对方邀请码"
          @keyup.enter="joinFamily"
        />
        <el-button :loading="joiningFamily" plain @click="joinFamily">加入家庭</el-button>
      </div>
    </section>

    <section v-if="!family && !isHealthProfilePage" class="family-bar card family-empty">
      <div class="family-empty-copy">
        <div class="family-name">还没有加入家庭</div>
        <div class="family-sub">创建家庭共享库存，或输入邀请码加入家人。</div>
      </div>

      <div class="family-empty-actions">
        <el-button type="primary" :loading="creatingFamily" @click="createFamily">
          创建家庭
        </el-button>

        <el-input
          v-model="inviteCode"
          class="family-join-input"
          maxlength="6"
          placeholder="输入家庭邀请码"
          @keyup.enter="joinFamily"
        />

        <el-button :loading="joiningFamily" plain @click="joinFamily">
          加入家庭
        </el-button>
      </div>
    </section>

    <div v-if="!isHealthProfilePage" class="stat-grid">
      <div class="stat-card">
        <div class="stat-icon">🧺</div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.total }}</span>
          <span class="stat-label">家庭共享食材</span>
        </div>
      </div>
      <div class="stat-card warn">
        <div class="stat-icon">⏰</div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.expiring }}</span>
          <span class="stat-label">临期（3 天内）</span>
        </div>
      </div>
      <div class="stat-card danger">
        <div class="stat-icon">⚠️</div>
        <div class="stat-info">
          <span class="stat-value">{{ stats.expired }}</span>
          <span class="stat-label">已过期</span>
        </div>
      </div>
      <button type="button" class="stat-card profile stat-card-button" @click="goHealthProfile">
        <div class="stat-icon">💚</div>
        <div class="stat-info">
          <span class="stat-value small">{{ profileSummary }}</span>
          <span class="stat-label">健康画像 · 去修改 →</span>
        </div>
      </button>
    </div>

    <el-alert
      v-if="reminder && (reminder.counts.expiring || reminder.counts.expired)"
      type="warning"
      show-icon
      :closable="false"
      class="reminder-alert"
    >
      <template #title>{{ reminder.message }}</template>
      <div class="reminder-list">
        <span v-for="item in [...reminder.expired, ...reminder.expiring].slice(0, 6)" :key="item.id" class="reminder-chip">
          {{ item.name }} · {{ item.status_text }}
        </span>
      </div>
      <div class="reminder-actions">
        <el-button size="small" :loading="notifySending" @click="sendDigest">发送今日摘要（模拟邮件）</el-button>
        <span class="reminder-hint">每日 8:00 可由定时脚本推送到邮箱 / 企业微信 / 钉钉</span>
      </div>
    </el-alert>

    <div v-if="reminder?.urgent?.length" class="rescue-strip">
      <div>
        <strong>临期拯救</strong>
        <p>
          以下食材只剩 1 天或今天到期，已自动生成快速消耗建议：<strong class="rescue-preview">{{
            reminder.urgent.map((item) => item.rescue?.recipe_name).filter(Boolean).join('、')
          }}</strong>
        </p>
      </div>
      <div class="rescue-actions">
        <el-button
          v-for="item in reminder.urgent"
          :key="item.id"
          size="small"
          type="warning"
          plain
          :loading="rescuingId === item.id"
          @click="rescueItem(item)"
        >
          {{ item.name }} · {{ item.rescue?.recipe_name || '拯救食谱' }}
        </el-button>
      </div>
    </div>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="mb" />

    <el-tabs v-if="!isHealthProfilePage" v-model="activeTab" class="pantry-tabs">
      <el-tab-pane label="库存" name="inventory">
        <div class="toolbar">
          <el-input
            v-model="filters.query"
            placeholder="搜索食材名称或备注"
            clearable
            @keyup.enter="load"
          />
          <el-select v-model="filters.status" placeholder="全部状态" clearable @change="load">
            <el-option label="全部状态" value="" />
            <el-option label="已过期" value="expired" />
            <el-option label="临期" value="expiring" />
            <el-option label="正常" value="fresh" />
            <el-option label="未设保质期" value="no_expiry" />
          </el-select>
          <el-button @click="load">查询</el-button>
          <el-button
            type="danger"
            plain
            :loading="batchDeleting"
            :disabled="!selectedIds.length"
            @click="removeSelectedItems"
          >
            批量删除{{ selectedIds.length ? `（${selectedIds.length}）` : '' }}
          </el-button>
        </div>

        <div v-if="!isMobile()" v-loading="loading" class="card table-card">
          <el-table
            ref="tableRef"
            :data="items"
            size="small"
            stripe
            row-key="id"
            @selection-change="onTableSelection"
          >
            <el-table-column type="selection" width="48" />
            <el-table-column prop="name" label="食材" min-width="140" />
            <el-table-column prop="category_label" label="分类" width="100" />
            <el-table-column label="数量" width="100">
              <template #default="{ row }">{{ row.quantity }} {{ row.unit }}</template>
            </el-table-column>
            <el-table-column label="购买日期" width="120">
              <template #default="{ row }">{{ formatDate(row.purchased_at) }}</template>
            </el-table-column>
            <el-table-column label="保质期" width="120">
              <template #default="{ row }">{{ formatDate(row.expires_at) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="150">
              <template #default="{ row }">
                <el-tag size="small" :type="statusType(row.status)">{{ row.status_text }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="备注" width="180">
              <template #default="{ row }">
                <el-tooltip :content="row.note || '—'" placement="top" :show-after="200">
                  <span class="note-ellipsis">{{ shortNote(row.note) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" text type="danger" @click="removeItem(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-else v-loading="loading" class="item-cards">
          <div v-for="item in items" :key="item.id" class="card item-card">
            <div class="item-head">
              <strong>{{ item.name }}</strong>
              <el-tag size="small" :type="statusType(item.status)">{{ item.status_text }}</el-tag>
            </div>
            <div class="item-meta">
              <span>{{ item.category_label }} · {{ item.quantity }} {{ item.unit }}</span>
              <span>保质期：{{ formatDate(item.expires_at) }}</span>
              <el-tooltip v-if="item.note" :content="item.note" placement="top">
                <span class="note-ellipsis">备注：{{ shortNote(item.note) }}</span>
              </el-tooltip>
            </div>
            <div class="item-actions">
              <el-button size="small" plain @click="openEdit(item)">编辑</el-button>
              <el-button size="small" plain type="danger" @click="removeItem(item)">删除</el-button>
            </div>
          </div>
          <div v-if="!items.length && !loading" class="empty-text">
            还没有食材，点击右上角「添加食材」开始管理。
          </div>
        </div>
      </el-tab-pane>



      <el-tab-pane label="食谱规划" name="plan">
        <div class="card plan-controls">
          <div class="plan-form">
            <div class="plan-field">
              <span>规划餐数</span>
              <el-select v-model="planOptions.meals" style="width: 110px">
                <el-option
                  v-for="count in [2, 3, 4, 5, 6]"
                  :key="count"
                  :value="count"
                  :label="`${count} 餐`"
                />
              </el-select>
            </div>
            <div class="plan-field">
              <span>份量</span>
              <el-select v-model="planOptions.servings" style="width: 110px">
                <el-option :value="1" label="1 人份" />
                <el-option :value="2" label="2 人份" />
                <el-option :value="3" label="3 人份" />
                <el-option :value="4" label="4 人份" />
                <el-option :value="5" label="5 人份" />
                <el-option :value="6" label="6 人份" />
              </el-select>
            </div>
            <div class="plan-field">
              <span>单餐时间</span>
              <el-select v-model="planOptions.max_minutes" style="width: 120px">
                <el-option :value="15" label="15 分钟" />
                <el-option :value="30" label="30 分钟" />
                <el-option :value="45" label="45 分钟" />
              </el-select>
            </div>
            <div class="plan-field">
              <span>单餐预算</span>
              <el-select v-model="planOptions.budget" style="width: 120px">
                <el-option :value="20" label="20 元内" />
                <el-option :value="30" label="30 元内" />
                <el-option :value="50" label="50 元内" />
                <el-option :value="0" label="不限预算" />
              </el-select>
            </div>
            <WeatherWidget
              @change="applyWeather"
              @loading="weatherLoading = $event"
            />
            <div class="plan-field plan-preference">
              <span>想吃什么 / 要求</span>
              <el-input
                v-model="planOptions.preference"
                maxlength="200"
                clearable
                placeholder="例如：今晚想吃红烧肉，少辣，30分钟内搞定"
              />
            </div>
            <el-button
              type="primary"
              class="plan-generate-btn"
              :loading="planning"
              :disabled="planning || weatherLoading"
              @click="generatePlan"
            >
              <el-icon><MagicStick /></el-icon>
              生成食谱方案
            </el-button>
          </div>
          <p class="plan-hint">
            {{ planOptions.servings }} 人份 · {{ planOptions.meals }} 餐 · 每餐约 {{ planOptions.max_minutes }} 分钟 · {{ planBudgetText }} · 按你的口味生成，优先消耗临期食材，缺料自动加入补购。
          </p>
          <div v-if="!hasHealthProfile" class="plan-profile-hint">
            <span>💡 还没有完善健康画像，生成本方案前建议先补充。</span>
            <button type="button" @click="goHealthProfile">去完善健康画像 →</button>
          </div>
          <el-alert v-if="planError" :title="planError" type="error" show-icon :closable="false" />
        </div>

        <template v-if="plan">
          <div class="card plan-summary">
            <div class="plan-summary-head">
              <div>
                <h3>{{ planSummaryText }}</h3>
                <el-alert
                  v-if="planMealShortfall"
                  type="warning"
                  :closable="false"
                  show-icon
                  class="plan-shortfall"
                  :title="`💡 提示：当前库存仅够生成 ${planMealShortfall.actual} 餐，建议您去采购后再规划。`"
                />
                <p class="plan-meta">
                  <el-tag size="small" :type="plan.mode === 'ai' ? 'success' : 'info'" effect="plain">{{ plan.mode_label }}</el-tag>
                  <span v-if="plan.model">模型：{{ plan.model }}</span>
                  <span>{{ plan.servings || 2 }} 人份</span>
                  <span v-if="plan.budget">单餐预算 ¥{{ plan.budget }} 内</span>
                  <span>库存 {{ plan.pantry_count }} 项</span>
                  <span>方案 #{{ plan.plan_id }}</span>
                </p>
              </div>
              <el-button text @click="plan = null">清除</el-button>
            </div>
            <div class="nutrition-totals">
              <span>总能量 {{ plan.nutrition_totals.energy_kcal }} kcal</span>
              <span>蛋白质 {{ plan.nutrition_totals.protein_g }} g</span>
              <span>钠 {{ plan.nutrition_totals.sodium_mg }} mg</span>
              <span>糖 {{ plan.nutrition_totals.sugar_g }} g</span>
            </div>
            <section v-if="planWarnings.length || weatherGuardianTip" class="ai-guardian-card">
              <div class="ai-guardian-head">
                <span class="ai-guardian-icon" aria-hidden="true">🛡️</span>
                <div class="ai-guardian-title">
                  <strong>AI 专属健康护航</strong>
                  <span>AI 营养师对您说：</span>
                </div>
              </div>

              <div class="ai-guardian-keywords">
                <span
                  v-for="keyword in ['低盐', '控糖', '高纤维']"
                  :key="keyword"
                  class="ai-guardian-keyword"
                  style="color: #10B981; font-weight: bold;"
                >
                  {{ keyword }}
                </span>
              </div>

              <ul class="ai-guardian-list">
                <li v-if="weatherGuardianTip" class="ai-guardian-weather">
                  <span class="ai-guardian-dot" aria-hidden="true"></span>
                  <p v-html="highlightNutrition(weatherGuardianTip)"></p>
                </li>
                <li v-if="planOptimizationTip" class="ai-guardian-weather">
                  <span class="ai-guardian-dot" aria-hidden="true"></span>
                  <p v-html="highlightNutrition(planOptimizationTip)"></p>
                </li>
                <li v-for="(warning, index) in planWarnings" :key="index">
                  <span class="ai-guardian-dot" aria-hidden="true"></span>
                  <p v-html="highlightNutrition(warning)"></p>
                </li>
              </ul>
            </section>

            <div class="agent-trace">
              <div class="trace-head">
                <div class="trace-title">🤖 AI 营养师的思考过程</div>
                <button
                  v-if="planAgentTrace.length > 2"
                  type="button"
                  class="trace-toggle"
                  :aria-expanded="traceExpanded"
                  @click="traceExpanded = !traceExpanded"
                >
                  {{ traceExpanded ? '收起推演过程' : '展开查看完整推演过程' }}
                  <span class="trace-toggle-arrow" :class="{ 'is-expanded': traceExpanded }">⌄</span>
                </button>
              </div>
              <ol class="agent-timeline" :class="{ 'is-collapsed': !traceExpanded }">
                <li
                  v-for="(line, index) in visibleAgentTrace"
                  :key="index"
                  class="agent-step"
                  :class="`tone-${traceTone(line)}`"
                >
                  <span class="agent-step-dot">{{ index + 1 }}</span>
                  <div class="agent-step-content">
                    <span class="agent-step-label">STEP {{ index + 1 }}</span>
                    <p>{{ line }}</p>
                  </div>
                </li>
              </ol>
              <p
                v-if="!traceExpanded && planAgentTrace.length > 2"
                class="trace-more-hint"
              >
                还有 {{ planAgentTrace.length - visibleAgentTrace.length }} 个推演步骤，展开后可查看完整过程
              </p>
            </div>
            <el-alert
              v-if="planFocusMissing"
              type="warning"
              show-icon
              :closable="false"
              class="plan-warning"
              :title="`💡 AI 已优先考虑临期食材，但最终方案未安排「${planFocusName}」，请手动调整。`"
            >
              <ul v-if="plan.rule_vetoes?.length" class="veto-list">
                <li v-for="(item, index) in plan.rule_vetoes" :key="index">{{ item }}</li>
              </ul>
            </el-alert>
            <el-alert
              v-else-if="planFocusAdjusted"
              type="success"
              show-icon
              :closable="false"
              class="plan-warning"
              :title="`💡 AI 已优先为您安排消耗临期食材「${planFocusName}」。`"
            />
          </div>

          <div class="meal-grid">
            <article
              v-for="(meal, mealIndex) in plan.meals"
              v-show="!isMealDone(plan, mealIndex)"
              :key="meal.meal_type + meal.name"
              class="card meal-card flex flex-col h-full"
              :class="{ expanded: isMealExpanded(plan, mealIndex) }"
              @click="toggleMealDetails(plan, mealIndex)"
            >
              <div class="meal-cover" :class="`tone-${mealIndex % 4}`">
                <span class="meal-cover-thumb" aria-hidden="true">{{ mealEmoji(meal.name) }}</span>
                <span class="meal-cover-type">{{ meal.meal_type }}</span>
                <span class="meal-cover-calorie">🔥 {{ meal.nutrition.energy_kcal || 0 }} kcal</span>
              </div>

              <div class="meal-content flex flex-col h-full">
              <div class="meal-main flex-grow">
              <div class="meal-head">
                <strong>{{ meal.name }}</strong>
                <span v-if="meal.version && isMealExpanded(plan, mealIndex)" class="meal-version">{{ meal.version === 'chef' ? '大厨版' : '新手版' }}</span>
                <button
                  v-if="isMealExpanded(plan, mealIndex)"
                  type="button"
                  class="meal-favorite"
                  :class="{ active: favoriteIds.has(meal.name) }"
                  :disabled="favoritingName === meal.name"
                  @click.stop="toggleFavorite(meal)"
                >
                  {{ favoriteIds.has(meal.name) ? '⭐ 已收藏' : '☆ 收藏' }}
                </button>
                <button
                  type="button"
                  class="meal-remove"
                  title="从方案中移除这道菜"
                  @click.stop="removeMeal(plan, mealIndex)"
                >
                  删除
                </button>
                <span class="meal-expand-hint">
                  {{ isMealExpanded(plan, mealIndex) ? '收起详情' : '点击查看详情' }}
                </span>
              </div>
              <div
                v-show="isMealExpanded(plan, mealIndex)"
                class="meal-ingredient-groups"
              >
                <div class="ingredient-group">
                  <span class="ingredient-group-label">主食材</span>
                  <div class="meal-ingredients">
                    <span v-for="ingredient in mainIngredients(meal)" :key="ingredient.name" class="ingredient-chip">
                      {{ ingredient.name }} {{ ingredient.amount }}
                      <em v-if="ingredient.expiring">临期</em>
                    </span>
                    <span v-if="!mainIngredients(meal).length" class="muted">暂无主料</span>
                  </div>
                </div>
                <template v-if="isMealExpanded(plan, mealIndex)">
                  <div v-if="auxiliaryIngredients(meal).length" class="ingredient-group">
                    <span class="ingredient-group-label">辅料</span>
                    <div class="meal-ingredients">
                      <span v-for="ingredient in auxiliaryIngredients(meal)" :key="ingredient.name" class="ingredient-chip auxiliary">
                        {{ ingredient.name }} {{ ingredient.amount }}
                      </span>
                    </div>
                  </div>
                </template>
              </div>

              <button
                v-if="mealMissing(meal).length"
                type="button"
                class="meal-shopping-tag"
                @click.stop="openShoppingList"
              >
                ⚠️ {{ mealMissing(meal).length }} 种食材，去采购
              </button>

              <template v-if="isMealExpanded(plan, mealIndex)">
              <div class="meal-nutrition">
                <span>能量 {{ meal.nutrition.energy_kcal || 0 }} kcal</span>
                <span>蛋白质 {{ meal.nutrition.protein_g || 0 }} g</span>
                <span>钠 {{ meal.nutrition.sodium_mg || 0 }} mg</span>
                <span>糖 {{ meal.nutrition.sugar_g || 0 }} g</span>
              </div>
              <div v-if="mealMissing(meal).length" class="meal-missing-block">
                <div class="meal-missing-title">这道菜需要补购（{{ mealMissing(meal).length }}）</div>
                <div class="meal-missing-chips">
                  <span v-for="item in mealMissing(meal)" :key="item.name" class="meal-missing-chip">
                    {{ item.name }} {{ item.amount }}
                  </span>
                </div>
              </div>
              <p v-else class="meal-ready">这道菜食材已齐，可以直接做</p>
              </template>
              </div>

              <div class="meal-card-bottom mt-auto">
                <div class="meal-card-foot">
                  <el-button class="ask-assistant" plain round @click.stop="askAssistant(meal)">
                    ❓ 问助手
                  </el-button>
                  <el-button class="start-cooking" type="primary" round @click.stop="startCooking(plan, meal, mealIndex)">
                    👨‍🍳 开始烹饪
                  </el-button>
                </div>

                <div v-if="mealExerciseTip(meal)" class="meal-exercise-tip">
                  {{ mealExerciseTip(meal) }}
                </div>
              </div>
              </div>
            </article>
          </div>

          <div class="card plan-extra">
            <div v-if="plan.shopping_list.length || plan.meals.some((meal) => (meal.missing || []).length)" class="shopping">
              <div class="shopping-head">
                <div class="shopping-heading">
                  <div class="trace-title">全部需要补购（合计）</div>
                  <p class="shopping-sub">按类别汇总，一眼看清还差什么。</p>
                </div>
                <el-button type="success" size="small" @click="openShoppingList">🛒 一键生成购物清单</el-button>
              </div>
              <el-collapse v-model="shoppingCollapse" class="shopping-collapse">
                <el-collapse-item name="fresh">
                  <template #title>
                    <span class="shopping-section-title">🛒 生鲜食材（需购买）</span>
                    <span class="shopping-count">{{ planShoppingGroups.fresh.length }} 项</span>
                  </template>
                  <div v-if="planShoppingGroups.fresh.length" class="shopping-rows">
                    <div v-for="item in planShoppingGroups.fresh" :key="item.name" class="shopping-row">
                      <strong>{{ item.name }}</strong>
                      <span>{{ item.amount }}</span>
                    </div>
                  </div>
                  <p v-else class="hint">暂无生鲜缺口</p>
                </el-collapse-item>
                <el-collapse-item name="staples">
                  <template #title>
                    <span class="shopping-section-title">🧂 常备调料（家里有的可跳过）</span>
                    <span class="shopping-count">{{ planShoppingGroups.staples.length }} 项</span>
                  </template>
                  <div v-if="planShoppingGroups.staples.length" class="shopping-rows">
                    <div v-for="item in planShoppingGroups.staples" :key="item" class="shopping-row">
                      <strong>{{ item }}</strong>
                      <span class="muted">常备物资</span>
                    </div>
                  </div>
                  <p v-else class="hint">暂无调料缺口</p>
                </el-collapse-item>
              </el-collapse>
            </div>
            <p class="plan-disclaimer">{{ plan.disclaimer }}</p>
          </div>
        </template>

        <div v-else class="card empty-plan">
          <el-icon><Dish /></el-icon>
          <p>点击「生成食谱方案」，告诉 Agent 想吃什么；没有库存的食材会自动加入补购清单。</p>
        </div>

        <div v-if="history.length" class="card history-card">
          <div class="trace-title">最近方案</div>
          <div class="history-list">
            <button v-for="item in history" :key="item.id" type="button" class="history-item" @click="openHistory(item)">
              <span>#{{ item.id }} · {{ item.mode === 'ai' ? 'AI 规划' : '智能规划' }}</span>
              <span>{{ item.created_at?.replace('T', ' ').slice(0, 16) }}</span>
            </button>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="⭐ 我的收藏" name="favorites">
        <FavoritesView />
      </el-tab-pane>
    </el-tabs>

    <div v-if="isHealthProfilePage" class="profile-standalone">
      <section class="profile-ai-banner">
        <div class="profile-ai-banner-copy">
          <span class="profile-ai-banner-icon">📑</span>
          <div>
            <strong>懒得手动填？上传体检单，让 AI 自动为您建档</strong>
            <p>支持体检报告、化验单图片或 PDF，AI 自动识别关键指标。</p>
          </div>
        </div>
        <el-button class="profile-upload-btn" @click="openProfileUpload">
          <span class="profile-upload-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 16V4" />
              <path d="m7 9 5-5 5 5" />
              <path d="M5 20h14" />
            </svg>
          </span>
          上传体检单
        </el-button>
        <input
          ref="profileUploadInput"
          class="profile-upload-input"
          type="file"
          accept="image/*,.pdf"
          @change="handleProfileUpload"
        />
      </section>

      <div class="profile-grid">
        <section class="profile-panel">
          <header class="profile-panel-head">
            <div class="profile-panel-icon">🩺</div>
            <div>
              <h2>基础健康状况</h2>
              <p>可多选，AI 会据此调整风险提醒与食谱建议。</p>
            </div>
          </header>
          <div class="profile-chip-group">
            <button
              v-for="item in profile?.options?.conditions || []"
              :key="item.value"
              type="button"
              class="profile-chip"
              :class="{ 'is-selected': profileForm.conditions.includes(item.value) }"
              :aria-pressed="profileForm.conditions.includes(item.value)"
              @click="toggleProfileValue(profileForm.conditions, item.value)"
            >
              <span v-if="profileForm.conditions.includes(item.value)" class="profile-chip-mark">✓</span>
              {{ item.label }}
            </button>
          </div>
        </section>

        <section class="profile-panel">
          <header class="profile-panel-head">
            <div class="profile-panel-icon">🎯</div>
            <div>
              <h2>我的饮食目标</h2>
              <p>告诉我们你当前最想达成的方向。</p>
            </div>
          </header>
          <div class="profile-chip-group">
            <button
              v-for="item in profile?.options?.goals || []"
              :key="item.value"
              type="button"
              class="profile-chip"
              :class="{ 'is-selected': profileForm.goals.includes(item.value) }"
              :aria-pressed="profileForm.goals.includes(item.value)"
              @click="toggleProfileValue(profileForm.goals, item.value)"
            >
              <span v-if="profileForm.goals.includes(item.value)" class="profile-chip-mark">✓</span>
              {{ item.label }}
            </button>
          </div>
        </section>

        <section class="profile-panel profile-panel--wide">
          <header class="profile-panel-head">
            <div class="profile-panel-icon">🥜</div>
            <div>
              <h2>过敏与忌口</h2>
              <p>输入后按回车添加，越完整，AI 的避雷提醒越准确。</p>
            </div>
          </header>

          <div class="profile-field">
            <label class="profile-field-label">过敏原 / 忌口</label>
            <div class="allergy-quick-group">
              <button
                v-for="item in ALLERGY_PRESETS"
                :key="item"
                type="button"
                class="allergy-quick-chip"
                :class="{ 'is-added': profileForm.allergies.includes(item) }"
                :disabled="profileForm.allergies.includes(item)"
                @click="addPresetAllergy(item)"
              >
                + {{ item }}
              </button>
            </div>
            <div
              class="allergy-tag-input"
              :class="{ 'is-focused': allergyFocused }"
              @click="focusAllergyInput"
            >
              <span
                v-for="item in profileForm.allergies"
                :key="item"
                class="allergy-tag"
              >
                {{ item }}
                <button
                  type="button"
                  class="allergy-tag-remove"
                  :aria-label="`删除忌口 ${item}`"
                  @click.stop="removeAllergy(item)"
                >
                  ×
                </button>
              </span>
              <input
                ref="allergyField"
                v-model="allergyDraft"
                class="allergy-tag-field"
                type="text"
                placeholder="+ 添加忌口"
                aria-label="添加忌口"
                @keydown="handleAllergyKeydown"
                @focus="allergyFocused = true"
                @blur="onAllergyBlur"
              />
              <button
                type="button"
                class="allergy-add-btn"
                @click.stop="addAllergy()"
              >
                添加
              </button>
            </div>
          </div>

          <div class="profile-field">
            <label class="profile-field-label">补充说明</label>
            <el-input
              v-model="profileForm.notes"
              class="profile-notes-input"
              type="textarea"
              :rows="3"
              maxlength="300"
              show-word-limit
              placeholder="例如：医生建议每天盐不超过 5g"
            />
          </div>

          <div class="profile-save-row">
            <span v-if="isProfileDirty" class="profile-unsaved">
              <i aria-hidden="true"></i>
              未保存
            </span>
            <el-button
              type="primary"
              class="profile-top-save profile-bottom-save"
              :loading="profileSaving"
              @click="saveProfile"
            >
              <span class="profile-save-icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" />
                  <path d="M17 21v-8H7v8" />
                  <path d="M7 3v5h8" />
                </svg>
              </span>
              保存并同步至全系统
            </el-button>
          </div>
        </section>
      </div>

      <section class="profile-ai-summary" :class="{ 'is-loading': healthTipLoading }">
        <div class="profile-ai-summary-avatar">🤖</div>
        <div class="profile-ai-summary-body">
          <div class="profile-ai-summary-title">
            <strong>AI 专属健康档案助理</strong>
            <span
              class="profile-ai-live"
              :class="{ 'is-pending': profileAssistantState.pending }"
            >
              <i></i>
              {{ profileAssistantState.title }}
            </span>
          </div>
          <p class="profile-ai-summary-text">
            {{ profileAssistantState.text }}
          </p>
        </div>
      </section>

      <p class="profile-privacy-note">
        健康画像只保存在你的账号下，仅用于生成食谱建议，不会展示给其他用户。
      </p>
    </div>

    <el-dialog v-model="familyDialogOpen" title="家庭成员" width="min(92vw, 480px)" class="family-dialog">
      <div v-if="family" class="family-dialog-body">
        <div class="family-dialog-head">
          <div class="family-dialog-title">
            <div v-if="!editingFamilyName" class="family-name-display">
              <strong>{{ family.family.name }}</strong>
              <button
                v-if="family.is_owner"
                type="button"
                class="family-edit-icon"
                aria-label="修改家庭名称"
                title="修改家庭名称"
                @click="startEditFamilyName"
              >
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z"
                    stroke="currentColor"
                    stroke-width="1.7"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <path d="m13.5 7.5 3 3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
                </svg>
              </button>
            </div>

            <div v-else class="family-name-edit-row">
              <el-input
                v-model="familyNameDraft"
                size="small"
                maxlength="30"
                placeholder="输入家庭名称"
                @keyup.enter="saveFamilyName"
              />
              <el-button size="small" type="primary" :loading="savingFamilyName" @click="saveFamilyName">
                保存
              </el-button>
              <el-button size="small" text @click="cancelEditFamilyName">取消</el-button>
            </div>

            <p>{{ family.member_count }} 位家人 · 邀请码 {{ inviteCodeDisplay }}</p>
          </div>
          <div class="family-dialog-actions">
            <el-button size="small" plain :disabled="!inviteCodeValid" @click="copyInviteCode">复制邀请码</el-button>
            <el-button size="small" type="primary" plain :disabled="!inviteCodeValid" @click="copyInviteLink">生成邀请链接</el-button>
          </div>
        </div>

        <div class="family-member-list">
          <div v-for="member in family.members" :key="member.id" class="family-member-row">
            <span class="family-avatar family-avatar-large">{{ member.initial }}</span>
            <div class="family-member-info">
              <div v-if="editingMemberId === member.id" class="family-member-edit-row">
                <el-input
                  v-model="memberNameDraft"
                  size="small"
                  maxlength="20"
                  placeholder="输入成员备注"
                  @keyup.enter="saveMemberName(member)"
                />
                <el-button
                  size="small"
                  type="primary"
                  :loading="savingMemberId === member.id"
                  @click="saveMemberName(member)"
                >
                  保存
                </el-button>
                <el-button size="small" text @click="cancelEditMember">取消</el-button>
              </div>
              <template v-else>
                <strong
                  class="family-member-name-editable"
                  @click="startEditMember(member)"
                >
                  {{ familyMemberDisplayName(member) }}<span v-if="member.is_self" class="family-self">我</span>
                  <button
                    type="button"
                    class="family-edit-icon family-member-edit-icon"
                    aria-label="修改成员备注"
                    title="修改成员备注"
                    @click.stop="startEditMember(member)"
                  >
                    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z"
                        stroke="currentColor"
                        stroke-width="1.7"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                      <path d="m13.5 7.5 3 3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
                    </svg>
                  </button>
                </strong>
                <small>{{ member.role }}</small>
              </template>
            </div>
            <el-button
              v-if="family.is_owner && !member.is_self"
              size="small"
              text
              type="danger"
              :loading="removingMember === member.id"
              @click="removeMember(member.id, member.display_name)"
            >
              移除
            </el-button>
          </div>
        </div>

        <p class="family-dialog-hint">只有户主可以移除成员；移除后对方将不再看到家庭共享库存。</p>

        <div class="family-dialog-footer">
          <el-button
            type="danger"
            plain
            :loading="leavingFamily"
            @click="leaveCurrentFamily"
          >
            {{ family.is_owner ? '解散家庭' : '退出当前家庭' }}
          </el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 添加/编辑食材 -->
    <el-dialog v-model="dialogOpen" :title="editing ? '编辑食材' : '添加食材'" width="min(94vw, 520px)">
      <el-alert v-if="formError" :title="formError" type="error" show-icon :closable="false" class="mb" />
      <el-form label-position="top">
        <el-form-item label="食材名称" required>
          <el-input v-model="form.name" maxlength="40" placeholder="例如：鸡胸肉、菠菜、牛奶" @blur="estimateFormShelfLife" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="分类">
            <el-select v-model="form.category">
              <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="数量">
            <el-input v-model.number="form.quantity" type="number" min="0.1" step="0.1" />
          </el-form-item>
          <el-form-item label="单位">
            <el-input v-model="form.unit" maxlength="10" />
          </el-form-item>
        </div>
        <div class="form-row">
          <el-form-item label="购买日期">
            <el-date-picker v-model="form.purchased_at" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" />
          </el-form-item>
          <el-form-item label="保质期至">
            <el-date-picker v-model="form.expires_at" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" />
            <div v-if="shelfEstimate" class="form-estimate">
              <span class="form-estimate-badge" :class="estimateConfidenceClass(shelfEstimate.confidence_percent)" :title="shelfEstimate.basis">
                {{
                  shelfEstimate.days
                    ? `AI智能估算：${shelfEstimate.days}天（置信度 ${shelfEstimate.confidence_percent}%）`
                    : 'AI未估算：请手动选择到期日'
                }}
              </span>
              <button
                v-for="day in shelfEstimate.alternatives"
                :key="day"
                type="button"
                class="form-estimate-chip"
                @click="applyEstimateDays(day)"
              >
                {{ day }}天
              </button>
              <span class="form-estimate-custom">也可直接改日期</span>
            </div>
            <el-button text size="small" :loading="estimating" class="form-estimate-btn" @click="estimateFormShelfLife">
              AI 估算保质期
            </el-button>
          </el-form-item>
        </div>
        <el-form-item label="备注">
          <el-input v-model="form.note" maxlength="200" placeholder="例如：开封后冷藏、已分装" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveItem">保存</el-button>
      </template>
    </el-dialog>

    <PantrySmartImport ref="smartImport" @imported="load" />

    <el-dialog v-model="shoppingOpen" width="min(96vw, 920px)">
      <template #header>
        <div class="shopping-dialog-title">
          购物清单
          <el-tag v-if="shoppingSource" size="small" type="info">
            来自：{{ shoppingSource.name }}
          </el-tag>
        </div>
      </template>
      <div class="shopping-toolbar">
        <p class="hint">生鲜按电商实际售卖单位展示，括号内保留菜谱用量；调料请按家里实际情况勾选补货。</p>
        <div class="shopping-toolbar-actions">
          <el-button text size="small" @click="saveShoppingList">💾 保存清单</el-button>
          <el-button text size="small" @click="shareShoppingList">分享给家人</el-button>
        </div>
      </div>

      <div class="shopping-columns">
        <section class="shopping-column">
          <div class="shopping-column-head">
            <div>
              <strong>生鲜缺料</strong>
              <span>即时配送</span>
            </div>
            <el-checkbox v-model="allShoppingSelected" size="small">全选生鲜</el-checkbox>
          </div>
          <div v-if="shoppingFreshRows.length" class="shopping-fresh-list">
            <div v-for="row in shoppingFreshRows" :key="row.label" class="shopping-fresh-row product-row">
              <el-checkbox v-model="row.checked" />
              <div class="shopping-fresh-main">
                <strong>{{ row.sku }}</strong>
                <span class="usage-tip">对应菜谱用量：{{ row.recipeAmount }}</span>
              </div>
              <el-select v-model="row.specId" size="small" class="spec-select">
                <el-option v-for="spec in row.specs" :key="spec.id" :label="specLabel(spec)" :value="spec.id" />
              </el-select>
              <span class="product-price">{{ formatPrice(rowPrice(row)) }}</span>
            </div>
          </div>
          <p v-else class="hint">本次没有需要即时配送的生鲜。</p>
          <p class="hint">已选 {{ selectedShoppingCount }} / {{ shoppingFreshRows.length }} 项生鲜。</p>
        </section>

        <section class="shopping-column shopping-staples">
          <div class="shopping-column-head">
            <div>
              <strong>常备调料</strong>
              <span>缺料自查</span>
            </div>
          </div>
          <p class="staple-tip">请检查以下调料，勾选您需要补货的项</p>
          <div v-if="shoppingStaples.length" class="staple-list">
            <div v-for="item in shoppingStaples" :key="item.name" class="staple-row">
              <el-checkbox v-model="item.checked" @change="resetStaplesCart" />
              <div class="staple-main">
                <strong>{{ item.name }}</strong>
                <span>{{ item.sku }}</span>
              </div>
              <el-select v-model="item.specId" size="small" class="spec-select" @change="resetStaplesCart">
                <el-option v-for="spec in item.specs" :key="spec.id" :label="specLabel(spec)" :value="spec.id" />
              </el-select>
              <span class="product-price">{{ formatPrice(rowPrice(item)) }}</span>
            </div>
          </div>
          <p v-else class="hint">本次没有需要补的调料。</p>
          <el-button
            v-if="selectedStaplesCount"
            class="add-staples-cart"
            type="success"
            plain
            :disabled="staplesInCart"
            @click="addStaplesToCart"
          >
            {{ staplesInCart ? '✓ 调料已加入购物车' : `🛒 将${selectedStaplesCount}件调料加入购物车` }}
          </el-button>
          <p class="hint">调料走常规发货（预计次日达），不参与生鲜 30 分钟配送；不勾选视为家里已有。</p>
        </section>
      </div>

      <template #footer>
        <el-button text type="primary" class="offline-buy-button" @click="openOfflineMemo">
          🏪 去附近超市买
        </el-button>
        <el-button type="primary" size="large" :loading="shoppingPurchasing" :disabled="!canCheckout" @click="checkoutShopping">
          {{ ctaLabel }}
        </el-button>
      </template>
    </el-dialog>

    <OfflineShoppingMemo v-model="offlineMemoOpen" :items="offlineMemoItems" />

    <el-dialog v-model="rescueOpen" title="临期拯救食谱" width="min(94vw, 620px)">
      <template v-if="rescuePlan">
        <p class="rescue-lead">
          优先消耗：<strong>{{ rescuePlan.focus_item?.name || '临期食材' }}</strong>
          <el-tag size="small" type="success" effect="plain">{{ rescuePlan.mode_label }}</el-tag>
        </p>
        <div v-for="meal in rescuePlan.meals" :key="meal.meal_type + meal.name" class="rescue-meal">
          <strong>{{ meal.meal_type }} · {{ meal.name }}</strong>
          <p>{{ meal.ingredients.map((item) => `${item.name} ${item.amount}`).join('、') }}</p>
          <ol>
            <li v-for="(step, index) in meal.steps" :key="index">{{ step }}</li>
          </ol>
        </div>
        <p class="rescue-note">{{ rescuePlan.disclaimer }}</p>
      </template>
      <template #footer>
        <el-button @click="rescueOpen = false">关闭</el-button>
        <el-button type="primary" @click="useRescuePlan">查看完整方案</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="cookingOpen" :with-header="false" direction="rtl" size="min(94vw, 680px)" class="cooking-drawer">
      <div v-if="cookingContext" class="cook-panel">
        <div class="cook-top">
          <button type="button" class="cook-close" aria-label="关闭烹饪步骤" @click="cookingOpen = false">×</button>
          <div class="cook-art">🍳</div>
          <div class="cook-heading">
            <span class="cook-kicker">
              {{ cookingContext.meal.meal_type }} · {{ cookingContext.plan.servings || 2 }} 人份
              <template v-if="cookingContext.meal.version"> · {{ cookingContext.meal.version === 'chef' ? '大厨版' : '新手版' }}</template>
            </span>
            <h2>{{ cookingContext.meal.name }}</h2>
            <p>边看边做，随时可以关掉；做完再回来扣库存。</p>
          </div>
        </div>

        <div class="cook-body">
          <section class="cook-section">
            <h3>食材清单</h3>
            <div class="cook-ingredients">
              <span v-for="item in cookingContext.meal.ingredients" :key="item.name" class="cook-chip">
                {{ item.name }} {{ item.amount }}
                <em v-if="item.expiring">临期</em>
              </span>
            </div>
            <div v-if="mealMissing(cookingContext.meal).length" class="cook-missing">
              <strong>这道菜还需要补购：</strong>
              {{ mealMissing(cookingContext.meal).map((item) => `${item.name} ${item.amount}`).join('、') }}
            </div>
            <p v-else class="cook-ready">食材齐备，可以开始。</p>
          </section>

          <section class="cook-section">
            <h3>一步一步做</h3>
            <div v-if="cookingContext.meal.steps.length" class="cook-steps">
              <div v-for="(step, index) in cookingContext.meal.steps" :key="index" class="cook-step">
                <span class="cook-step-num">{{ index + 1 }}</span>
                <p>{{ step }}</p>
              </div>
            </div>
            <p v-else class="muted">这道菜还没有分步步骤。</p>
          </section>


        </div>

        <footer class="cook-footer">
          <div class="cook-energy-hero">
            <strong>🔥 {{ Math.round(Number(cookingContext.meal.nutrition.energy_kcal || 0)) }} kcal</strong>
            <span>蛋白质 {{ cookingContext.meal.nutrition.protein_g || 0 }}g</span>
            <span>碳水 {{ cookingContext.meal.nutrition.carbs_g || 0 }}g</span>
            <span>脂肪 {{ cookingContext.meal.nutrition.fat_g || 0 }}g</span>
            <span>钠 {{ cookingContext.meal.nutrition.sodium_mg || 0 }}mg</span>
          </div>
          <el-tag v-if="isMealDone(cookingContext.plan, cookingContext.index)" type="success" effect="plain">
            已完成，库存已扣减
          </el-tag>
          <el-button @click="cookingOpen = false">继续看别的</el-button>
          <el-button
            type="primary"
            :loading="completingMeal === mealDoneKey(cookingContext.plan, cookingContext.index)"
            :disabled="isMealDone(cookingContext.plan, cookingContext.index)"
            @click="completeCooking"
          >
            {{ isMealDone(cookingContext.plan, cookingContext.index) ? '已完成' : '已完成，扣减库存' }}
          </el-button>
        </footer>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.family-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 14px;
  padding: 13px 16px;
}

.family-empty-copy {
  min-width: 0;
}

.family-empty-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.family-empty-actions .family-join-input {
  width: 150px;
}

.family-dialog-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #edf2ef;
}

@media (max-width: 767px) {
  .family-empty {
    align-items: stretch;
    flex-direction: column;
  }

  .family-empty-actions {
    flex-wrap: wrap;
    width: 100%;
  }

  .family-empty-actions .family-join-input {
    flex: 1 1 140px;
    width: auto;
  }

  .family-dialog-footer .el-button {
    width: 100%;
  }
}

.family-members-button {
  border: 0;
  background: transparent;
  padding: 0;
  text-align: left;
  cursor: pointer;
}

.family-members-button:hover .family-name {
  color: #0f7b6c;
}

.family-members-copy {
  min-width: 0;
}

.family-dialog-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #edf2ef;
}

.family-dialog-head strong {
  color: #173e32;
  font-size: 14px;
}

.family-dialog-head p {
  margin: 4px 0 0;
  color: #8a9e93;
  font-size: 11px;
}

.family-dialog-title {
  flex: 1;
  min-width: 0;
}

.family-name-display {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.family-edit-icon {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  padding: 0;
  border: 1px solid #dce9e2;
  border-radius: 6px;
  background: #ffffff;
  color: #6b8e7e;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, color 0.16s ease;
}

.family-edit-icon:hover {
  border-color: #b9d4c7;
  background: #eef8f3;
  color: #1f7a5f;
}

.family-edit-icon svg {
  width: 13px;
  height: 13px;
}

.family-name-edit-row,
.family-member-edit-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  flex-wrap: wrap;
}

.family-name-edit-row :deep(.el-input),
.family-member-edit-row :deep(.el-input) {
  flex: 1;
  min-width: 110px;
}

.family-member-name-editable {
  cursor: pointer;
}

.family-member-name-editable:hover {
  color: #1f7a5f;
}

.family-member-edit-icon {
  width: 19px;
  height: 19px;
  flex-basis: 19px;
  margin-left: 5px;
  vertical-align: -4px;
}

.family-member-edit-icon svg {
  width: 11px;
  height: 11px;
}

.family-dialog-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.family-member-list {
  margin-top: 8px;
}

.family-member-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 2px;
  border-bottom: 1px solid #f1f5f2;
}

.family-avatar-large {
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  margin: 0;
  font-size: 14px;
}

.family-member-info {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.family-member-info strong {
  color: #294d3e;
  font-size: 13px;
}

.family-member-info small {
  color: #8a9e93;
  font-size: 11px;
}

.family-self {
  margin-left: 6px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #eaf6ef;
  color: #2f7d5e;
  font-size: 10px;
  font-weight: 400;
}

.family-dialog-hint {
  margin: 12px 0 0;
  color: #8a9e93;
  font-size: 11px;
  line-height: 1.6;
}

.family-members {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.family-avatar-stack {
  display: flex;
  padding-left: 6px;
}

.family-avatar {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  margin-left: -6px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #dceee4;
  color: #245f49;
  font-size: 12px;
  font-weight: 700;
}

.family-avatar:nth-child(2n) {
  background: #f7e7ce;
  color: #8a6425;
}

.family-name {
  color: #173e32;
  font-size: 13px;
  font-weight: 700;
}

.family-sub {
  margin-top: 2px;
  color: #869990;
  font-size: 10.5px;
}

.family-invite {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.family-invite-label {
  color: #7d938a;
  font-size: 11px;
}

.family-code-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.family-code-row {
  display: flex;
  align-items: center;
  gap: 5px;
}

.family-code-expiry {
  padding-left: 3px;
  color: #a1b0a8;
  font-size: 9.5px;
  line-height: 1.4;
}

.family-code-refresh {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid #dce9e2;
  border-radius: 6px;
  background: #ffffff;
  color: #6b8e7e;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, color 0.16s ease;
}

.family-code-refresh:hover {
  border-color: #b9d4c7;
  background: #eef8f3;
  color: #1f7a5f;
}

.family-code-refresh svg {
  width: 13px;
  height: 13px;
}

.family-code-get {
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}

.family-code-expired {
  border-style: solid;
  border-color: #e5ebe7;
  background: #f4f6f5;
  color: #9aa8a1;
  font-family: inherit;
  font-weight: 600;
  cursor: default;
}

.family-code {
  border: 1px dashed #b8d2c1;
  border-radius: 7px;
  background: #f1f9f4;
  padding: 5px 9px;
  color: #1c6b51;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
  cursor: pointer;
}

.family-join-input {
  width: 130px;
}

@media (max-width: 760px) {
  .family-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .family-invite {
    width: 100%;
  }

  .family-join-input {
    flex: 1;
    min-width: 110px;
  }
}

.page-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.page-sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--muted);
}

.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.profile-head-actions {
  align-items: center;
  justify-content: flex-end;
}

.profile-unsaved {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #c14936;
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
}

.profile-unsaved i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #e05a4f;
  box-shadow: 0 0 0 3px rgba(224, 90, 79, 0.12);
}

.profile-top-save {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 42px;
  padding: 0 17px;
  border: 0 !important;
  border-radius: 12px !important;
  background: #0f6b52 !important;
  color: #ffffff !important;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 7px 18px rgba(15, 107, 82, 0.22);
}

.profile-top-save:hover {
  background: #0b5a45 !important;
  box-shadow: 0 10px 22px rgba(15, 107, 82, 0.28);
}

.profile-save-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
}

@media (max-width: 767px) {
  .profile-save-row {
    flex-wrap: wrap;
    gap: 8px;
  }

  .profile-bottom-save {
    width: 100%;
    justify-content: center;
  }
}

.profile-top-save .profile-save-icon {
  width: 16px;
  height: 16px;
}

.pantry-page {
  background: #f3f8f5;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 86px;
  padding: 16px 18px;
  border: 0;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 6px 18px rgba(31, 61, 50, 0.05);
}

.stat-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  border-radius: 12px;
  background: #eaf6f0;
  font-size: 20px;
}

.stat-card.warn .stat-icon {
  background: #fff5e6;
}

.stat-card.danger .stat-icon {
  background: #fff0ec;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.stat-value {
  color: #1d3a2e;
  font-size: 30px;
  font-weight: 800;
  line-height: 1;
}

.stat-value.small {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

.stat-label {
  color: #84988e;
  font-size: 11.5px;
}

.stat-card.warn .stat-value {
  color: #b7791f;
}

.stat-card.danger .stat-value {
  color: #c14936;
}

.reminder-alert {
  margin-bottom: 12px;
}

.reminder-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.reminder-chip {
  font-size: 11.5px;
  background: rgba(255, 255, 255, 0.55);
  border-radius: 999px;
  padding: 2px 8px;
}

.reminder-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.reminder-hint {
  font-size: 10.5px;
  opacity: 0.8;
}

.rescue-strip {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  border: 1px solid #f0d4a8;
  background: #fff8ec;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
}

.rescue-strip strong {
  color: #9a5a0a;
  font-size: 13px;
}

.rescue-preview {
  color: #9a5a0a;
}

.rescue-strip p {
  margin: 3px 0 0;
  font-size: 11.5px;
  color: #8a6a3a;
}

.rescue-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.rescue-lead {
  margin: 0 0 10px;
  font-size: 13px;
}

.rescue-meal {
  border-top: 1px dashed var(--border);
  padding: 8px 0;
  font-size: 12px;
}

.rescue-meal p {
  margin: 4px 0;
  color: var(--muted);
}

.rescue-meal ol {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
  color: var(--text-2);
}

.rescue-note {
  margin: 8px 0 0;
  font-size: 10.5px;
  color: var(--muted);
}

.veto-list {
  margin: 4px 0 0;
  padding-left: 16px;
  font-size: 11.5px;
  line-height: 1.7;
}

.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.toolbar .el-input {
  flex: 1 1 220px;
}

.toolbar .el-select {
  width: 150px;
}

.table-card {
  padding: 8px 10px;
}

.item-cards {
  display: grid;
  gap: 10px;
}

.item-card {
  padding: 12px 14px;
}

.item-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.item-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 6px 0 10px;
  font-size: 12px;
  color: var(--muted);
}

.item-actions {
  display: flex;
  gap: 8px;
}

.empty-text {
  text-align: center;
  color: var(--muted);
  padding: 20px;
  font-size: 13px;
}

.health-profile-page {
  padding-bottom: 132px;
}

.profile-standalone {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 980px;
}

.profile-ai-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 24px;
  border: 1px solid #dcece6;
  border-radius: 20px;
  background: linear-gradient(120deg, #f0faf6 0%, #eef7fc 100%);
  box-shadow: 0 8px 24px rgba(24, 87, 67, 0.05);
}

.profile-ai-banner-copy {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}

.profile-ai-banner-icon {
  font-size: 26px;
  line-height: 1.2;
}

.profile-ai-banner-copy strong {
  display: block;
  color: #193c32;
  font-size: 16px;
  line-height: 1.5;
}

.profile-ai-banner-copy p {
  margin: 3px 0 0;
  color: #6f847d;
  font-size: 12px;
  line-height: 1.6;
}

.profile-upload-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  gap: 8px;
  height: 40px;
  padding: 0 20px;
  border: 0 !important;
  border-radius: 999px !important;
  background: #0f6b52 !important;
  color: #ffffff !important;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(15, 107, 82, 0.16);
  transition: background-color 0.2s ease, box-shadow 0.2s ease;
}

.profile-upload-btn:hover {
  border-color: transparent !important;
  background: #0b5a45 !important;
  color: #ffffff !important;
  box-shadow: 0 6px 16px rgba(15, 107, 82, 0.22);
}

.profile-upload-icon {
  display: inline-flex;
  width: 16px;
  height: 16px;
}

.profile-upload-icon svg {
  width: 16px;
  height: 16px;
}

.profile-upload-input {
  display: none;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: stretch;
}

.profile-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
  border: 1px solid #f0f3f2;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
}

.profile-panel--wide {
  grid-column: 1 / -1;
}

.profile-panel-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 16px;
}

.profile-panel-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  border-radius: 10px;
  background: #f1f8f5;
  font-size: 18px;
}

.profile-panel-head h2 {
  margin: 0;
  color: #1f342d;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.5;
}

.profile-panel-head p {
  margin: 2px 0 0;
  color: #8a9a94;
  font-size: 11.5px;
  line-height: 1.6;
}

.profile-chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.profile-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 40px;
  padding: 8px 16px;
  border: 1px solid transparent;
  border-radius: 20px;
  background: #f4f6f8;
  color: #4b5563;
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.profile-chip:hover {
  background: #eef2f0;
  transform: translateY(-1px);
}

.profile-chip.is-selected {
  border-color: #a5d6a7;
  background: #e8f5e9;
  color: #1b5e20;
  font-weight: 600;
}

.profile-chip-mark {
  font-size: 12px;
  font-weight: 800;
}

.profile-field + .profile-field {
  margin-top: 16px;
}

.profile-field-label {
  display: block;
  margin-bottom: 7px;
  color: #4b5f58;
  font-size: 12px;
  font-weight: 600;
}

.allergy-quick-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.allergy-quick-chip {
  padding: 5px 10px;
  border: 1px solid #dce9e2;
  border-radius: 999px;
  background: #f7fbf9;
  color: #4b7a66;
  font-family: inherit;
  font-size: 11px;
  line-height: 1.4;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, color 0.16s ease;
}

.allergy-quick-chip:hover:not(:disabled) {
  border-color: #b9d4c7;
  background: #eef8f3;
  color: #1f7a5f;
}

.allergy-quick-chip.is-added,
.allergy-quick-chip:disabled {
  border-color: #dce9e2;
  background: #f1f5f3;
  color: #9aaba2;
  cursor: default;
}

.allergy-add-btn {
  flex: 0 0 auto;
  padding: 4px 9px;
  border: 1px solid #dce9e2;
  border-radius: 8px;
  background: #ffffff;
  color: #3f7d68;
  font-family: inherit;
  font-size: 11.5px;
  cursor: pointer;
}

.allergy-add-btn:hover {
  border-color: #b9d4c7;
  background: #f2f8f5;
}

.allergy-tag-input {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 42px;
  padding: 6px 10px;
  border: 1px dashed #d5dbdf;
  border-radius: 10px;
  background: #ffffff;
  cursor: text;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.allergy-tag-input:hover {
  border-color: #b7c9c1;
}

.allergy-tag-input.is-focused {
  border-color: #9dbbaf;
  box-shadow: 0 0 0 2px rgba(15, 107, 82, 0.05);
}

.allergy-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 999px;
  background: #f1f3f5;
  color: #4b5563;
  font-size: 12px;
  line-height: 1.4;
}

.allergy-tag-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #8a949b;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}

.allergy-tag-remove:hover {
  background: #e3e7ea;
  color: #d9534f;
}

.allergy-tag-field {
  flex: 1 1 120px;
  min-width: 100px;
  padding: 4px 2px;
  border: 0;
  outline: none;
  background: transparent;
  color: #374151;
  font: inherit;
  font-size: 13px;
  line-height: 1.5;
}

.allergy-tag-field::placeholder {
  color: #9ca3af;
}

.profile-notes-input :deep(.el-textarea__inner) {
  padding: 10px 12px;
  line-height: 1.7;
  border-radius: 10px;
}

.profile-ai-summary {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  overflow: hidden;
  padding: 18px 20px;
  border: 1px solid #d5e8e2;
  border-radius: 16px;
  background: linear-gradient(120deg, #eaf5ff 0%, #e9f8f0 100%);
  box-shadow: 0 8px 24px rgba(54, 120, 150, 0.07);
}

.profile-ai-summary::before {
  position: absolute;
  bottom: -56px;
  left: -32px;
  width: 170px;
  height: 170px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(124, 92, 255, 0.16), rgba(124, 92, 255, 0) 70%);
  content: '';
  pointer-events: none;
}

.profile-ai-summary.is-loading {
  opacity: 0.78;
}

.profile-ai-summary-avatar {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  border-radius: 12px;
  background: radial-gradient(circle at 50% 42%, #f3efff, #ffffff 72%);
  font-size: 22px;
  box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.08), 0 6px 14px rgba(124, 92, 255, 0.16);
  filter: drop-shadow(0 0 6px rgba(139, 92, 246, 0.5));
}

.profile-ai-summary-body {
  position: relative;
  z-index: 1;
}

.profile-ai-summary-body {
  min-width: 0;
}

.profile-ai-summary-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}

.profile-ai-summary-title strong {
  color: #174438;
  font-size: 14px;
  font-weight: 700;
}

.profile-ai-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: #2f7d62;
  font-size: 10.5px;
  font-weight: 600;
}

.profile-ai-live i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2fae7d;
  box-shadow: 0 0 0 0 rgba(47, 174, 125, 0.45);
  animation: profile-pulse 1.8s infinite;
}

.profile-ai-live.is-pending {
  background: rgba(255, 248, 232, 0.92);
  color: #9a6b18;
}

.profile-ai-live.is-pending i {
  background: #d99a2b;
  box-shadow: 0 0 0 0 rgba(217, 154, 43, 0.42);
  animation: profile-pulse-warm 1.8s infinite;
}

@keyframes profile-pulse-warm {
  0% {
    box-shadow: 0 0 0 0 rgba(217, 154, 43, 0.42);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(217, 154, 43, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(217, 154, 43, 0);
  }
}

@keyframes profile-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(47, 174, 125, 0.45);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(47, 174, 125, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(47, 174, 125, 0);
  }
}

.profile-ai-summary-body p {
  margin: 0;
  color: #42645a;
  font-size: 12.5px;
  line-height: 1.75;
}

.profile-privacy-note {
  margin: 0;
  color: #8b9b95;
  font-size: 11px;
  line-height: 1.7;
  text-align: center;
}

.profile-save-bar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 40;
  padding: 12px 24px calc(12px + env(safe-area-inset-bottom));
  border-top: 1px solid rgba(31, 122, 95, 0.1);
  background: rgba(244, 247, 249, 0.92);
  backdrop-filter: blur(16px);
}

.profile-save-inner {
  display: flex;
  justify-content: center;
  max-width: 980px;
  margin: 0 auto;
}

.profile-save-btn {
  width: 240px;
  max-width: 100%;
  height: 48px;
  padding: 0 24px;
  border: 0 !important;
  border-radius: 12px !important;
  background: #0f6b52 !important;
  color: #ffffff !important;
  font-size: 15px;
  font-weight: 700;
  box-shadow: 0 6px 16px rgba(15, 107, 82, 0.2);
  transition: transform 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.profile-save-btn:hover {
  transform: translateY(-2px);
  background: #0b5a45 !important;
  box-shadow: 0 9px 20px rgba(15, 107, 82, 0.24);
}

.profile-save-float {
  position: fixed !important;
  right: 32px !important;
  bottom: 32px !important;
  z-index: 50 !important;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: auto !important;
  max-width: calc(100vw - 32px);
  height: 48px;
  padding: 0 22px;
  border: 0 !important;
  border-radius: 12px !important;
  background: #0f6b52 !important;
  color: #ffffff !important;
  font-size: 15px;
  font-weight: 700;
  box-shadow: 0 16px 32px rgba(15, 107, 82, 0.28), 0 4px 12px rgba(0, 0, 0, 0.08);
  transition: transform 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.profile-save-float:hover {
  transform: translateY(-2px);
  background: #0b5a45 !important;
  box-shadow: 0 20px 38px rgba(15, 107, 82, 0.32), 0 6px 14px rgba(0, 0, 0, 0.1);
}

.profile-save-icon {
  display: inline-flex;
  width: 16px;
  height: 16px;
}

.profile-save-icon svg {
  width: 16px;
  height: 16px;
}

.stat-card-button {
  border: 0;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.stat-card-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(31, 122, 95, 0.11);
}

.plan-profile-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  padding: 9px 12px;
  border: 1px solid #f0dfba;
  border-radius: 9px;
  background: #fffbf1;
  color: #85652b;
  font-size: 12px;
}

.plan-profile-hint button {
  flex: 0 0 auto;
  border: 0;
  background: none;
  color: #1f7a5f;
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.profile-save-fab {
  position: fixed;
  right: 28px;
  bottom: 26px;
  z-index: 30;
  height: 46px;
  padding: 0 22px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 10px 26px rgba(31, 122, 95, 0.28);
}

.section-note {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.8;
}

.profile-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}



.plan-controls {
  margin-bottom: 16px;
  padding: 20px;
  border-radius: 18px;
}

.plan-preference {
  flex: 1 1 320px;
  min-width: 240px;
}

.plan-preference :deep(.el-input) {
  width: 100%;
}

.plan-preference :deep(.el-input__wrapper) {
  min-height: 46px;
  padding: 0 18px;
  border: 1px solid #dce8e2;
  border-radius: 999px;
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(31, 61, 50, 0.04);
}

.plan-preference :deep(.el-input__wrapper.is-focus) {
  border-color: #91c6b1;
  box-shadow: 0 0 0 3px rgba(31, 122, 95, 0.08);
}

.plan-form {
  display: flex;
  align-items: center;
  gap: 12px 14px;
  flex-wrap: wrap;
}

.plan-field {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-2);
  font-size: 12.5px;
}

.plan-generate-btn {
  height: 46px;
  padding: 0 22px;
  border: 0 !important;
  border-radius: 999px !important;
  background: #0f6b52 !important;
  color: #ffffff !important;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 6px 16px rgba(15, 107, 82, 0.2);
}

.plan-generate-btn:hover {
  background: #0b5a45 !important;
  box-shadow: 0 8px 20px rgba(15, 107, 82, 0.26);
}

.plan-hint {
  margin: 8px 0 0;
  font-size: 11.5px;
  color: var(--muted);
}

.plan-summary {
  margin-bottom: 12px;
}

.plan-summary-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.plan-summary-head h3 {
  margin: 0 0 5px;
  font-size: 15px;
}

.plan-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin: 0;
  font-size: 11.5px;
  color: var(--muted);
}

.nutrition-totals {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}

.nutrition-totals span {
  font-size: 11.5px;
  background: var(--surface-2);
  border-radius: 999px;
  padding: 3px 9px;
  color: var(--text-2);
}

.trace-title {
  font-size: 12.5px;
  font-weight: 600;
  margin-bottom: 6px;
}

.agent-trace {
  margin-top: 14px;
  padding: 14px 16px;
  border: 1px solid #e6f0ea;
  border-radius: 14px;
  background: #f8fcf9;
}

.trace-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.trace-head .trace-title {
  margin-bottom: 0;
}

.trace-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid #dce9e2;
  border-radius: 999px;
  background: #ffffff;
  color: #4b7a66;
  font-family: inherit;
  font-size: 10.5px;
  white-space: nowrap;
  cursor: pointer;
}

.trace-toggle:hover {
  border-color: #b9d4c7;
  background: #f1f9f5;
  color: #1f7a5f;
}

.trace-toggle-arrow {
  display: inline-block;
  font-size: 12px;
  line-height: 1;
  transition: transform 0.18s ease;
}

.trace-toggle-arrow.is-expanded {
  transform: rotate(180deg);
}

.trace-more-hint {
  margin: 9px 0 0;
  padding-top: 9px;
  border-top: 1px dashed #e1eee7;
  color: #8aa196;
  font-size: 10.5px;
  line-height: 1.5;
}

.agent-timeline {
  margin: 0;
  padding: 0;
  list-style: none;
}

.agent-step {
  position: relative;
  display: flex;
  gap: 10px;
  padding-bottom: 12px;
}

.agent-step:last-child {
  padding-bottom: 0;
}

.agent-step::before {
  position: absolute;
  top: 24px;
  bottom: 0;
  left: 11px;
  width: 2px;
  background: #e1eee7;
  content: '';
}

.agent-step:last-child::before {
  display: none;
}

.agent-step-dot {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  border: 2px solid #ffffff;
  border-radius: 50%;
  background: #eaf5ef;
  color: #1f7a5f;
  font-size: 10px;
  font-weight: 700;
  box-shadow: 0 0 0 1px #dcebe3;
}

.agent-step-content {
  min-width: 0;
  padding-top: 1px;
}

.agent-step-label {
  display: block;
  margin-bottom: 2px;
  color: #9aaca2;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.agent-step-content p {
  margin: 0;
  color: #4b6359;
  font-size: 12px;
  line-height: 1.7;
}

.agent-step.tone-health .agent-step-dot {
  background: #e8f5e9;
  color: #2e7d32;
  box-shadow: 0 0 0 1px #cfe6d1;
}

.agent-step.tone-pantry .agent-step-dot {
  background: #eaf5ff;
  color: #2f6f9e;
  box-shadow: 0 0 0 1px #d5e7f3;
}

.agent-step.tone-budget .agent-step-dot {
  background: #fff6e5;
  color: #b7791f;
  box-shadow: 0 0 0 1px #f1dfbd;
}

.agent-step.tone-taste .agent-step-dot {
  background: #f3efff;
  color: #7c5cff;
  box-shadow: 0 0 0 1px #e2d9ff;
}

.plan-shortfall {
  margin: 7px 0 9px;
  padding: 7px 10px;
}

.plan-warning {
  margin-top: 8px;
}

.ai-guardian-card {
  margin-top: 12px;
  padding: 16px 18px;
  border: 1px solid #dcebe3;
  border-radius: 16px;
  background: linear-gradient(135deg, #f5fbf8 0%, #fff9f1 100%);
  box-shadow: 0 6px 18px rgba(31, 122, 95, 0.05);
}

.ai-guardian-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.ai-guardian-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  border-radius: 12px;
  background: #e6f4ec;
  font-size: 18px;
}

.ai-guardian-title {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.ai-guardian-title strong {
  color: #2b5c49;
  font-size: 13.5px;
  font-weight: 700;
  line-height: 1.5;
}

.ai-guardian-title span {
  color: #81988d;
  font-size: 10.5px;
  line-height: 1.5;
}

.ai-guardian-list {
  display: grid;
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ai-guardian-list li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.ai-guardian-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  margin-top: 7px;
  border-radius: 50%;
  background: #6eb894;
}

.ai-guardian-list p {
  margin: 0;
  color: #5a7569;
  font-size: 12px;
  line-height: 1.75;
}

.meal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  grid-auto-rows: 1fr;
  align-items: stretch;
  gap: 16px;
  margin-bottom: 12px;
}

.meal-grid .meal-card,
.meal-grid .meal-card + .meal-card {
  margin-top: 0;
}

.meal-card {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 0;
  border: 1px solid #e6efea;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 8px 22px rgba(31, 61, 50, 0.06);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.meal-card:hover {
  transform: translateY(-2px);
  border-color: #d4e5dc;
  box-shadow: 0 14px 30px rgba(31, 61, 50, 0.1);
}

.meal-cover {
  position: relative;
  display: grid;
  place-items: center;
  height: 116px;
  overflow: hidden;
  background: linear-gradient(135deg, #fff3e6, #ffe4c7);
}

.meal-cover.tone-1 {
  background: linear-gradient(135deg, #edf9f2, #d9f0e3);
}

.meal-cover.tone-2 {
  background: linear-gradient(135deg, #eef6ff, #dcecff);
}

.meal-cover.tone-3 {
  background: linear-gradient(135deg, #f6f0ff, #e9ddff);
}

.meal-cover-thumb {
  font-size: 46px;
  line-height: 1;
  filter: drop-shadow(0 8px 12px rgba(91, 58, 28, 0.16));
}

.meal-cover-type {
  position: absolute;
  top: 10px;
  left: 12px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  color: #376653;
  font-size: 10px;
  font-weight: 600;
  backdrop-filter: blur(6px);
}

.meal-cover-calorie {
  position: absolute;
  top: 10px;
  right: 12px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: #b45309;
  font-size: 10.5px;
  font-weight: 700;
  backdrop-filter: blur(6px);
}

.meal-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 14px 16px 16px;
}

.meal-main {
  flex: 1 1 auto;
  min-height: 0;
}

.meal-card-bottom {
  display: flex;
  flex-direction: column;
  width: 100%;
  margin-top: auto;
}

.meal-card-bottom .meal-card-foot {
  margin-top: 0;
}

.meal-card-bottom .meal-exercise-tip {
  margin-top: 10px;
  align-self: flex-start;
}

.meal-exercise-tip {
  align-self: flex-start;
  margin-top: auto;
  padding: 6px 10px;
  border: 1px solid #f6dfbd;
  border-radius: 999px;
  background: #fff5e8;
  color: #a9650a;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
}

.ask-assistant {
  color: #1f7a5f;
}

.meal-card-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: auto;
  padding-top: 10px;
}

.meal-card-foot + .meal-exercise-tip {
  margin-top: 10px;
}

.start-cooking {
  font-weight: 700;
  box-shadow: 0 6px 16px rgba(31, 122, 95, 0.18);
}

.meal-card {
  cursor: pointer;
}

.meal-card.expanded {
  cursor: default;
  border-color: #cfe3d9;
}

.meal-expand-hint {
  margin-left: auto;
  color: #8aa196;
  font-size: 10.5px;
  white-space: nowrap;
}

.meal-card.expanded .meal-expand-hint {
  color: #2d7a5e;
}

.meal-head {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 6px 8px;
}

.meal-favorite {
  margin-left: 0;
  flex: 0 0 auto;
  border: 1px solid #f0dca8;
  background: #fffaf0;
  color: #a97812;
  border-radius: 999px;
  padding: 3px 7px;
  font-size: 10.5px;
  cursor: pointer;
  white-space: nowrap;
}

.meal-favorite.active {
  background: #fff4cf;
}

.meal-favorite:disabled {
  opacity: 0.6;
  cursor: wait;
}

.meal-remove {
  flex: 0 0 auto;
  margin-left: 0;
  border: 0;
  white-space: nowrap;
  background: transparent;
  color: #a4b2ac;
  font-size: 11px;
  cursor: pointer;
  padding: 2px 0 2px 6px;
}

.meal-remove:hover {
  color: #c14b3b;
}

.meal-version {
  font-size: 10px;
  color: #8a5a12;
  background: #fdf5e6;
  border: 1px solid #f0dfc4;
  border-radius: 999px;
  padding: 1px 7px;
}

.meal-type {
  font-size: 10.5px;
  color: var(--brand-700);
  background: var(--brand-50);
  border-radius: 999px;
  padding: 2px 8px;
}

.meal-head strong {
  flex: 1 1 160px;
  min-width: 0;
  color: #203a2e;
  font-size: 15px;
  line-height: 1.4;
}

.meal-ingredient-groups {
  display: grid;
  gap: 5px;
  margin: 8px 0;
}

.ingredient-group {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.ingredient-group-label {
  flex: none;
  font-size: 10.5px;
  color: #7b9188;
  background: #f2f7f4;
  border-radius: 5px;
  padding: 2px 5px;
  line-height: 1.7;
}

.ingredient-chip.auxiliary {
  color: #7c8d84;
  background: #fafcfb;
}

.meal-ingredients {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 8px 0;
}

.ingredient-chip {
  font-size: 11.5px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--text-2);
}

.ingredient-chip em {
  font-style: normal;
  color: var(--warn);
  margin-left: 3px;
}

.muted {
  color: var(--muted);
  font-size: 12px;
}

.meal-steps {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--text-2);
}

.meal-nutrition {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.meal-nutrition span {
  font-size: 10.5px;
  color: var(--muted);
  background: var(--surface-2);
  border-radius: 4px;
  padding: 1px 6px;
}

.suitability {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
}

.suitability p {
  margin: 2px 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--text-2);
}

.meal-missing-block {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fdf8ef;
  border: 1px solid #f0dfc4;
}

.meal-shopping-tag {
  align-self: flex-start;
  margin-top: 8px;
  padding: 5px 10px;
  border: 1px solid #efc0ba;
  border-radius: 999px;
  background: #fff1ef;
  color: #b23b32;
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 650;
  line-height: 1.5;
  cursor: pointer;
}

.meal-shopping-tag:hover {
  background: #ffe7e3;
  border-color: #e39a92;
}

.meal-missing-title {
  font-size: 11.5px;
  font-weight: 600;
  color: #9a5a0a;
  margin-bottom: 5px;
}

.meal-missing-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.meal-missing-chip {
  font-size: 11px;
  color: #8a5a12;
  background: #fff;
  border: 1px solid #efdcc0;
  border-radius: 999px;
  padding: 1px 7px;
}

.meal-ready {
  margin: 8px 0 0;
  font-size: 11px;
  color: #2f7a56;
}

.meal-missing {
  margin: 6px 0 0;
  font-size: 11.5px;
  color: #a05c0a;
  line-height: 1.7;
}

.meal-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.meal-tips {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--muted);
}

.plan-extra {
  margin-bottom: 12px;
}

.shopping {
  padding: 18px;
  border: 1px solid #dfede5;
  border-radius: 16px;
  background: #f6fbf8;
}

.shopping-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 14px;
  border-bottom: 1px solid #e4f0e9;
}

.shopping-heading {
  min-width: 0;
}

.shopping-head .trace-title {
  color: #234c3d;
  font-size: 15px;
  font-weight: 700;
}

.shopping-sub {
  margin: 4px 0 0;
  color: #8a9e94;
  font-size: 11.5px;
  line-height: 1.6;
}

.shopping-head .el-button {
  flex: none;
  border: 0 !important;
  border-radius: 999px !important;
  background: #0f6b52 !important;
  color: #ffffff !important;
}

.shopping-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.shopping-column {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  min-width: 0;
}

.shopping-column-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.shopping-column-head div {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.shopping-column-head strong {
  font-size: 14px;
}

.shopping-column-head span {
  font-size: 10.5px;
  color: var(--muted);
}

.shopping-fresh-list {
  display: grid;
  gap: 6px;
  max-height: 44vh;
  overflow: auto;
}

.shopping-fresh-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 7px;
  cursor: pointer;
}

.shopping-fresh-row:hover {
  background: var(--surface-2);
}

.shopping-fresh-main {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.shopping-fresh-main strong {
  font-size: 12.5px;
}

.shopping-fresh-main span {
  font-size: 11px;
  color: var(--muted);
}

.shopping-staples {
  background: #fbf8f1;
  border-color: #f0dfc4;
}

.staple-list {
  display: grid;
  gap: 6px;
  max-height: 44vh;
  overflow: auto;
}

.staple-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 7px;
  background: #fff;
  border: 1px solid #efdcc0;
}

.staple-row strong {
  font-size: 12.5px;
  color: #7a4a08;
}

.staple-row span {
  font-size: 10.5px;
  color: #9a6a20;
  white-space: nowrap;
}

.shopping-dialog-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #173e32;
  font-size: 16px;
  font-weight: 700;
}

.shopping-dialog-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.shopping-checklist {
  display: grid;
  gap: 6px;
  max-height: 50vh;
  overflow: auto;
}

.shopping-checklist-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
}

.shopping-checklist-row:hover {
  border-color: var(--brand);
  background: var(--surface-2);
}

.shopping-checklist-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.shopping-checklist-main strong {
  font-size: 13px;
}

.shopping-checklist-main span {
  font-size: 11.5px;
  color: var(--muted);
}

.note-ellipsis {
  display: block;
  max-width: 150px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: #728a7e;
}

.shopping-collapse {
  margin-top: 10px;
  border-top: 0;
  border-bottom: 0;
}

.shopping-collapse :deep(.el-collapse-item__header) {
  height: 46px;
  border-bottom: 1px dashed #e1ede6;
  background: transparent;
  font-size: 13px;
}

.shopping-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
}

.shopping-section-title {
  color: #294d3e;
  font-size: 13px;
  font-weight: 700;
}

.shopping-count {
  margin-left: 8px;
  padding: 2px 7px;
  border-radius: 999px;
  background: #eaf5ef;
  color: #5c8070;
  font-size: 10.5px;
}

.shopping-rows {
  display: grid;
  gap: 7px;
  padding: 8px 0 12px;
}

.shopping-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 12px;
  border: 1px solid #e8f1ec;
  border-radius: 10px;
  background: #ffffff;
  font-size: 12px;
}

.shopping-row strong {
  color: #315b49;
  font-size: 12.5px;
  font-weight: 650;
}

.shopping-row span {
  color: #8a9e94;
  text-align: right;
  white-space: nowrap;
}

.shopping-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.shopping-chip {
  font-size: 11.5px;
  background: var(--brand-50);
  color: var(--brand-700);
  border-radius: 999px;
  padding: 3px 9px;
}

.plan-disclaimer {
  margin: 10px 0 0;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.8;
}

.empty-plan {
  text-align: center;
  color: var(--muted);
  padding: 26px;
}

.empty-plan .el-icon {
  font-size: 30px;
  margin-bottom: 8px;
}

.history-card {
  margin-top: 12px;
}

.history-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.history-item {
  display: flex;
  gap: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 11.5px;
  color: var(--text-2);
  cursor: pointer;
}

.history-item:hover {
  border-color: var(--brand);
}

.form-estimate {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 4px;
  font-size: 11px;
}

.form-estimate-badge {
  white-space: nowrap;
  font-size: 10.5px;
  border-radius: 999px;
  padding: 1px 8px;
  background: var(--surface-2);
  color: var(--muted);
}

.form-estimate-badge.high {
  color: #1d7a4f;
  background: #e8f5ee;
}

.form-estimate-badge.medium {
  color: #8a5a0a;
  background: #fdf3e2;
}

.form-estimate-badge.low,
.form-estimate-badge.unknown {
  color: #a33b2b;
  background: #fcebe8;
}

.form-estimate-chip {
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text-2);
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 11px;
  cursor: pointer;
}

.form-estimate-chip:hover {
  border-color: var(--brand);
  color: var(--brand-700);
}

.form-estimate-custom {
  color: var(--muted);
}

.form-estimate-btn {
  margin-top: 2px;
  padding: 0;
  height: auto;
  font-size: 11px;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 10px;
}

.form-row .el-date-editor {
  width: 100%;
}

@media (max-width: 767px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .form-estimate {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 4px;
  font-size: 11px;
}

.form-estimate-badge {
  white-space: nowrap;
  font-size: 10.5px;
  border-radius: 999px;
  padding: 1px 8px;
  background: var(--surface-2);
  color: var(--muted);
}

.form-estimate-badge.high {
  color: #1d7a4f;
  background: #e8f5ee;
}

.form-estimate-badge.medium {
  color: #8a5a0a;
  background: #fdf3e2;
}

.form-estimate-badge.low,
.form-estimate-badge.unknown {
  color: #a33b2b;
  background: #fcebe8;
}

.form-estimate-chip {
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text-2);
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 11px;
  cursor: pointer;
}

.form-estimate-chip:hover {
  border-color: var(--brand);
  color: var(--brand-700);
}

.form-estimate-custom {
  color: var(--muted);
}

.form-estimate-btn {
  margin-top: 2px;
  padding: 0;
  height: auto;
  font-size: 11px;
}

.form-row {
    grid-template-columns: 1fr;
  }

  .plan-preference {
  flex: 1 1 260px;
  min-width: 220px;
}

.plan-preference :deep(.el-input) {
  width: 100%;
}

.plan-form {
    align-items: flex-start;
  }

  .meal-grid {
    grid-template-columns: 1fr;
  }
}

.cooking-drawer :deep(.el-drawer__body) {
  padding: 0;
  overflow: hidden;
}

.cook-panel {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.cook-top {
  position: relative;
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 26px 28px 22px;
  background:
    radial-gradient(circle at 90% 10%, rgba(255, 255, 255, 0.28), transparent 32%),
    linear-gradient(135deg, #1f7a5f, #2f9b78);
  color: #fff;
}

.cook-close {
  position: absolute;
  top: 12px;
  right: 14px;
  border: 0;
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
}

.cook-art {
  flex: none;
  width: 76px;
  height: 76px;
  display: grid;
  place-items: center;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.24);
  font-size: 42px;
}

.cook-kicker {
  font-size: 12px;
  opacity: 0.85;
}

.cook-heading h2 {
  margin: 4px 0 6px;
  font-size: 26px;
  line-height: 1.25;
}

.cook-heading p {
  margin: 0;
  font-size: 12.5px;
  opacity: 0.82;
}

.cook-body {
  flex: 1;
  overflow: auto;
  padding: 22px 28px 108px;
}

.cook-section {
  margin-bottom: 24px;
}

.cook-section h3 {
  margin: 0 0 10px;
  font-size: 17px;
  color: var(--text);
}

.cook-ingredients {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cook-chip {
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  font-size: 13px;
  color: var(--text-2);
}

.cook-chip em {
  font-style: normal;
  color: var(--warn);
  margin-left: 3px;
}

.cook-missing {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fdf8ef;
  border: 1px solid #f0dfc4;
  color: #8a5a12;
  font-size: 12.5px;
  line-height: 1.7;
}

.cook-ready {
  margin: 8px 0 0;
  color: #2f7a56;
  font-size: 12.5px;
}

.cook-step {
  display: flex;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
}

.cook-step:last-child {
  border-bottom: 0;
}

.cook-step-num {
  flex: none;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 17px;
  font-weight: 700;
}

.cook-step p {
  margin: 2px 0 0;
  font-size: 17px;
  line-height: 1.85;
  color: var(--text);
}

.cook-nutrition > div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.cook-nutrition span {
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--surface-2);
  font-size: 12px;
  color: var(--text-2);
}

.cook-footer {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 13px 24px;
  border-top: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(8px);
}

@media (max-width: 640px) {
  .cook-top {
    padding: 22px 18px 18px;
  }

  .cook-art {
    width: 58px;
    height: 58px;
    font-size: 32px;
  }

  .cook-heading h2 {
    font-size: 21px;
  }

  .cook-body {
    padding: 18px 18px 112px;
  }

  .cook-step p {
    font-size: 16px;
  }

  .cook-footer {
    padding: 12px 16px;
  }
}
@media (max-width: 640px) {
  .shopping-columns {
    grid-template-columns: 1fr;
  }
}

.offline-buy-button {
  margin-right: auto;
  color: #7b5a19;
}

.shopping-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}

.shopping-toolbar .hint {
  margin: 0;
  max-width: 620px;
}

.shopping-toolbar-actions {
  display: flex;
  gap: 2px;
  flex: none;
}

.product-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) 168px 58px;
  align-items: center;
  gap: 8px;
}

.shopping-fresh-row.product-row {
  padding: 9px 4px;
  border-bottom: 1px solid #edf3ef;
  border-radius: 0;
}

.shopping-fresh-row.product-row:last-child {
  border-bottom: 0;
}

.spec-select {
  width: 168px;
}

.product-price {
  font-size: 13px;
  font-weight: 700;
  color: #c17618;
  text-align: right;
  white-space: nowrap;
}

.usage-tip {
  font-size: 10.5px !important;
  color: #8a9b93 !important;
}

.staple-tip {
  margin: 0 0 8px;
  font-size: 11.5px;
  color: #7d5b22;
}

.staple-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) 148px 58px;
  align-items: center;
  gap: 7px;
  background: #fff;
  border: 1px solid #efdcc0;
  border-radius: 8px;
  padding: 7px 8px;
}

.staple-row .spec-select {
  width: 148px;
}

.staple-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.staple-main strong {
  font-size: 12.5px;
  color: #6e4a10;
}

.staple-main span {
  font-size: 10px;
  color: #9b7b48;
  white-space: normal;
}

.staple-row .product-price {
  color: #a26b14;
}

.add-staples-cart {
  width: 100%;
  margin-top: 10px;
  white-space: normal;
  height: auto;
  min-height: 32px;
}

@media (max-width: 760px) {
  .offline-buy-button {
  margin-right: auto;
  color: #7b5a19;
}

.shopping-toolbar {
    flex-direction: column;
  }

  .product-row {
    grid-template-columns: auto minmax(0, 1fr) 58px;
  }

  .product-row .spec-select {
    grid-column: 2 / 4;
    width: 100%;
  }

  .staple-row {
    grid-template-columns: auto minmax(0, 1fr) 58px;
  }

  .staple-row .spec-select {
    grid-column: 2 / 4;
    width: 100%;
  }

  .profile-save-fab {
    right: 14px;
    bottom: calc(var(--tabbar-h, 60px) + env(safe-area-inset-bottom) + 12px);
    height: 44px;
    padding: 0 18px;
    font-size: 13px;
  }

  .plan-profile-hint {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 760px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }

  .profile-panel--wide {
    grid-column: auto;
  }

  .profile-ai-banner {
    flex-direction: column;
    align-items: stretch;
    padding: 18px;
  }

  .profile-upload-btn {
    width: 100%;
  }

  .profile-save-float {
    right: 16px !important;
    bottom: calc(var(--tabbar-h, 60px) + env(safe-area-inset-bottom) + 16px) !important;
    max-width: calc(100vw - 32px);
  }

  .health-profile-page {
    padding-bottom: 190px;
  }
}

.health-tip-box {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin: 12px 0 16px;
  padding: 13px 15px;
  border: 1px solid #cfe3f7;
  border-radius: 11px;
  background: linear-gradient(135deg, #f2f8ff, #eef6ff);
  color: #1e5f92;
}

.health-tip-box.loading {
  opacity: 0.75;
}

.health-tip-icon {
  font-size: 22px;
  line-height: 1.2;
}

.health-tip-box strong {
  display: block;
  font-size: 13px;
  margin-bottom: 3px;
}

.health-tip-box p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: #2b6d9c;
}

.health-tip-box small {
  display: block;
  margin-top: 5px;
  color: #6e9bb9;
  font-size: 10.5px;
}

.favorites-tab-placeholder {
  padding: 32px;
  text-align: center;
  color: #7b9188;
  font-size: 13px;
}

.pantry-tabs :deep(.el-tabs__item) {
  white-space: nowrap;
}

/* 烹饪弹窗：底部营养重点 */
.cook-energy-hero {
  display: flex;
  align-items: baseline;
  flex: 1 0 100%;
  flex-wrap: wrap;
  gap: 7px 14px;
  padding: 10px 13px;
  border: 1px solid #dcece4;
  border-radius: 12px;
  background: #f2faf5;
}

.cook-energy-hero strong {
  color: #166548;
  font-size: 22px;
  font-weight: 850;
  letter-spacing: -0.03em;
}

.cook-energy-hero span {
  color: #527466;
  font-size: 12px;
  font-weight: 650;
}


/* ---------- 健康画像双卡强制等高 ---------- */
.profile-grid {
  display: flex !important;
  flex-wrap: wrap;
  align-items: stretch !important;
  gap: 16px;
}

.profile-panel {
  flex: 1 1 calc(50% - 8px);
  height: auto !important;
  min-height: 100%;
}

.profile-panel--wide {
  flex: 1 1 100%;
}

/* ---------- AI 规划建议：拉开行距、提升可读性 ---------- */
.ai-guardian-list p,
.ai-guardian-weather p {
  margin: 0 !important;
  color: #475569 !important;
  font-size: 15px !important;
  line-height: 2 !important;
}

.ai-guardian-list li {
  align-items: flex-start;
}

@media (max-width: 767px) {
  .profile-panel,
  .profile-panel--wide {
    flex-basis: 100%;
  }
}

.ai-guardian-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 12px 42px;
}

.ai-guardian-keyword {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border: 1px solid #bbf7d0;
  border-radius: 999px;
  background: #ecfdf5;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 767px) {
  .ai-guardian-keywords {
    margin-left: 0;
  }
}
</style>
