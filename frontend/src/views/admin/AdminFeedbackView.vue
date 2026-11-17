<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type FeedbackItem } from '@/api/admin'
import { ApiError } from '@/api/client'

const loading = ref(false)
const errorMessage = ref('')
const items = ref<FeedbackItem[]>([])
const stats = ref({ open: 0, resolved: 0 })
const filter = reactive({ status: '' })

const dialogOpen = ref(false)
const active = ref<FeedbackItem | null>(null)
const reply = ref('')
const saving = ref(false)

const filteredItems = computed(() =>
  items.value.map((item, index) => ({
    ...item,
    displayIndex: index + 1,
    feedbackCode: feedbackCode(item, index),
  })),
)
const openCount = computed(() => stats.value.open || 0)
const resolvedCount = computed(() => stats.value.resolved || 0)
const totalCount = computed(() => openCount.value + resolvedCount.value)
const replyError = ref('')

// 顶部状态按钮：全部 -> 已处理 -> 待处理
const statusTabs = computed(() => [
  { value: '', label: '全部', count: totalCount.value },
  { value: 'resolved', label: '已处理', count: resolvedCount.value },
  { value: 'open', label: '待处理', count: openCount.value },
])

function selectStatus(value: string) {
  if (filter.status === value) return
  filter.status = value
  void load()
}

function feedbackCode(item: FeedbackItem, index: number) {
  const date = String(item.created_at || '')
    .slice(0, 10)
    .replace(/-/g, '')
  return `FB-${date || '00000000'}-${String(index + 1).padStart(3, '0')}`
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await adminApi.feedback({
      status: filter.status,
      page: 1,
      per_page: 100,
    })
    items.value = data.items
    stats.value = data.stats
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '反馈加载失败'
  } finally {
    loading.value = false
  }
}

function openResolve(item: FeedbackItem) {
  active.value = item
  reply.value = item.reply || ''
  replyError.value = ''
  dialogOpen.value = true
}

async function saveResolve(status: 'resolved' | 'open') {
  if (!active.value) return
  if (status === 'resolved' && !reply.value.trim()) {
    replyError.value = '请填写回复内容后再标记已处理'
    return
  }
  replyError.value = ''
  saving.value = true
  try {
    if (status === 'resolved') {
      await adminApi.replyFeedback(
        active.value.id,
        reply.value.trim(),
      )
    } else {
      await adminApi.resolveFeedback(
        active.value.id,
        status,
        reply.value.trim(),
      )
    }
    ElMessage.success(status === 'resolved' ? '反馈已处理' : '已重新打开')
    dialogOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as ApiError).message || '处理失败')
  } finally {
    saving.value = false
  }
}

function formatTime(value: string) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 19)
}

onMounted(load)
</script>

<template>
  <div class="admin-page">
    <header class="page-head">
      <div>
        <h1 class="page-title">用户反馈</h1>
        <p class="page-sub">
          用户「意见反馈」提交后会实时进入这里；支持查看联系方式、关联记录与处理回复。
        </p>
      </div>
      <div class="head-actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>
    </header>

    <div class="feedback-status-tabs" role="tablist" aria-label="反馈状态筛选">
      <button
        v-for="tab in statusTabs"
        :key="tab.value || 'all'"
        type="button"
        role="tab"
        class="feedback-status-tab"
        :class="{ active: filter.status === tab.value }"
        :aria-selected="filter.status === tab.value"
        @click="selectStatus(tab.value)"
      >
        {{ tab.label }}
        <span>{{ tab.count }}</span>
      </button>
    </div>

    <div class="filter-bar card">
      <el-select v-model="filter.status" placeholder="全部状态" clearable @change="load">
        <el-option label="全部状态" value="" />
        <el-option label="待处理" value="open" />
        <el-option label="已处理" value="resolved" />
      </el-select>
    </div>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      class="mb"
    />

    <div v-loading="loading" class="card table-card">
      <div v-if="!filteredItems.length" class="empty-text">暂无用户反馈</div>

      <el-table v-else :data="filteredItems" row-key="id" size="small" stripe>
        <el-table-column label="序号" width="64" align="center">
          <template #default="{ row }">{{ row.displayIndex }}</template>
        </el-table-column>
        <el-table-column label="反馈编号" width="176">
          <template #default="{ row }">
            <span class="record-code">{{ row.feedbackCode }}</span>
          </template>
        </el-table-column>
        <el-table-column label="用户" min-width="120">
          <template #default="{ row }">
            <strong>{{ row.username || `用户 #${row.user_id}` }}</strong>
          </template>
        </el-table-column>
        <el-table-column prop="content" label="反馈内容" min-width="320">
          <template #default="{ row }">
            <span class="feedback-content">{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联记录" width="100">
          <template #default="{ row }">
            {{ row.record_id ? `#${row.record_id}` : '未关联' }}
          </template>
        </el-table-column>
        <el-table-column prop="contact" label="联系方式" width="150">
          <template #default="{ row }">{{ row.contact || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'resolved' ? 'success' : 'warning'">
              {{ row.status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openResolve(row)">
              {{ row.status === 'resolved' ? '查看 / 重新打开' : '处理' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogOpen" title="处理用户反馈" width="min(94vw, 560px)">
      <div v-if="active" class="feedback-detail">
        <p class="feedback-user">
          {{ active.username || `用户 #${active.user_id}` }} · {{ formatTime(active.created_at) }}
        </p>
        <p class="feedback-body">{{ active.content }}</p>
        <p v-if="active.contact" class="feedback-contact">联系方式：{{ active.contact }}</p>
        <p v-if="active.record_id" class="feedback-contact">关联记录：#{{ active.record_id }}</p>
        <div class="reply-field">
          <label class="reply-label">回复内容 <span>*</span></label>
          <el-input
            v-model="reply"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="必填：回复会同步到用户的「我的反馈」"
            @input="replyError = ''"
          />
          <p v-if="replyError" class="reply-error">{{ replyError }}</p>
        </div>
      </div>

      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button v-if="active?.status === 'resolved'" :loading="saving" @click="saveResolve('open')">
          重新打开
        </el-button>
        <el-button type="primary" :loading="saving" @click="saveResolve('resolved')">
          标记已处理
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.page-title {
  margin: 0;
  color: #173e32;
  font-size: 22px;
  font-weight: 800;
}

.page-sub {
  margin: 5px 0 0;
  color: #7b8f86;
  font-size: 12.5px;
  line-height: 1.6;
}

.feedback-status-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.feedback-status-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid #e1ece6;
  border-radius: 999px;
  background: #ffffff;
  color: #607b70;
  font-family: inherit;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.feedback-status-tab > span {
  display: inline-grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: #f0f6f3;
  color: #71877c;
  font-size: 10px;
}

.feedback-status-tab:hover {
  border-color: #9bcdb7;
  color: #246b53;
}

.feedback-status-tab.active {
  border-color: #14796b;
  background: #14796b;
  color: #ffffff;
}

.feedback-status-tab.active > span {
  background: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}

.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  padding: 12px;
}

.filter-bar .el-select {
  width: 160px;
}

.table-card {
  padding: 10px;
}

.feedback-content {
  display: block;
  max-width: 520px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-text {
  padding: 24px;
  color: #8a9e94;
  text-align: center;
  font-size: 13px;
}

.feedback-detail {
  display: grid;
  gap: 10px;
}

.feedback-user {
  margin: 0;
  color: #7b8f86;
  font-size: 11.5px;
}

.feedback-body {
  margin: 0;
  padding: 12px;
  border-radius: 9px;
  background: #f6faf8;
  color: #294d3e;
  font-size: 13px;
  line-height: 1.8;
}

.feedback-contact {
  margin: 0;
  color: #647a70;
  font-size: 12px;
}

.record-code {
  color: #527064;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  white-space: nowrap;
}

.reply-field {
  display: grid;
  gap: 6px;
}

.reply-label {
  color: #3a5b4e;
  font-size: 12.5px;
  font-weight: 700;
}

.reply-label span {
  color: #c0392b;
}

.reply-error {
  margin: 0;
  color: #c0392b;
  font-size: 11.5px;
}

</style>
