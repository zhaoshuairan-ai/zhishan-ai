<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAdminStore } from '@/stores/admin'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
import BrandMark from '@/components/BrandMark.vue'
import CaptchaField from '@/components/CaptchaField.vue'

const route = useRoute()
const router = useRouter()
const admin = useAdminStore()
const auth = useAuthStore()

const form = ref({ username: '', password: '', captcha_code: '', captcha_id: '' })
const captchaRef = ref<InstanceType<typeof CaptchaField> | null>(null)
const errorMessage = ref('')
const loading = ref(false)
const showPassword = ref(false)

async function submit() {
  if (!form.value.username.trim() || !form.value.password) {
    errorMessage.value = '请输入管理员账号与密码'
    return
  }
  if (!form.value.captcha_code.trim()) {
    errorMessage.value = '请输入验证码计算结果'
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await admin.login(form.value.username.trim(), form.value.password, {
      captcha_id: form.value.captcha_id,
      captcha_code: form.value.captcha_code.trim(),
    })
    // 同一令牌同时作为前台会话，进入后台后切回前台不需要再登录
    auth.applyAuth({ token: result.token, expires_at: result.expires_at, user: result.user })
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/admin/dashboard'
    router.replace(redirect.startsWith('/admin') ? redirect : '/admin/dashboard')
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '登录失败，请稍后重试'
    captchaRef.value?.refresh()
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="admin-login">
    <div class="login-card card">
      <div class="login-brand">
        <BrandMark compact />
        <div>
          <strong>智膳 AI</strong>
          <small>管理后台</small>
        </div>
      </div>
      <h1>管理员登录</h1>
      <p class="login-sub">仅限已由运维初始化的管理员账号使用。普通用户请前往前台登录。</p>

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="false"
        class="login-alert"
      />

      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="管理员账号">
          <el-input v-model="form.username" size="large" placeholder="请输入管理员用户名" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            :type="showPassword ? 'text' : 'password'"
            size="large"
            placeholder="请输入密码"
            autocomplete="current-password"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item label="验证码">
          <CaptchaField
            ref="captchaRef"
            v-model="form.captcha_code"
            v-model:captcha-id="form.captcha_id"
            :disabled="loading"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="submit">
          登录管理后台
        </el-button>
      </el-form>

      <div class="login-tips">
        <p><strong>首次使用：</strong>管理员账号必须通过服务器命令行初始化（<code>python scripts/create_admin.py</code>），公开注册页不能选择管理员角色。</p>
        <p>连续登录失败会触发限流；所有登录成功与失败都会写入审计日志。</p>
      </div>

      <div class="login-links">
        <router-link :to="{ name: 'home' }">返回前台</router-link>
        <router-link :to="{ name: 'login' }">普通用户登录</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-login {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: radial-gradient(circle at 20% 10%, #e8f4f0 0, #f5f8f7 45%, #eef3f1 100%);
}

.login-card {
  width: min(440px, 100%);
  padding: 28px 28px 22px;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}

.login-brand div {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.login-brand strong {
  font-size: 14px;
}

.login-brand small {
  font-size: 11.5px;
  color: var(--muted);
}

h1 {
  margin: 0 0 6px;
  font-size: 22px;
}

.login-sub {
  margin: 0 0 16px;
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.7;
}

.login-alert {
  margin-bottom: 12px;
}

.login-btn {
  width: 100%;
  margin-top: 4px;
}

.login-tips {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px dashed var(--border);
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}

.login-tips p {
  margin: 0 0 6px;
}

.login-tips code {
  background: #f2f5f4;
  padding: 1px 4px;
  border-radius: 4px;
}

.login-links {
  display: flex;
  justify-content: space-between;
  margin-top: 14px;
  font-size: 12.5px;
}

.login-links a {
  color: var(--brand-700);
}
</style>
