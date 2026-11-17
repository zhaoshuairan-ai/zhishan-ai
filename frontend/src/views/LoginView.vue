<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import BrandMark from '@/components/BrandMark.vue'
import CaptchaField from '@/components/CaptchaField.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const tab = ref<'login' | 'register'>('login')
const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()
const submitting = ref(false)
const errorMessage = ref('')

const loginForm = reactive({ username: '', password: '', captcha_code: '', captcha_id: '' })
const captchaRef = ref<InstanceType<typeof CaptchaField> | null>(null)
const registerForm = reactive({ username: '', password: '', confirm: '', display_name: '', email: '' })

const DEMO_ACCOUNT = { username: 'demo', password: 'demo123456' }

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha_code: [{ required: true, message: '请输入验证码计算结果', trigger: 'blur' }],
}

const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度 3-20 位', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_\u4e00-\u9fa5]+$/, message: '仅支持中文、字母、数字、下划线', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
    {
      pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/,
      message: '密码需同时包含字母和数字',
      trigger: 'blur',
    },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
}

const redirectTarget = computed(() => {
  const target = route.query.redirect
  return typeof target === 'string' && target.startsWith('/') ? target : '/'
})

function fillDemo() {
  tab.value = 'login'
  loginForm.username = DEMO_ACCOUNT.username
  loginForm.password = DEMO_ACCOUNT.password
  errorMessage.value = ''
  ElMessage.info('已填入默认演示账号，如管理员修改过密码请以实际配置为准')
}

async function handleLogin() {
  errorMessage.value = ''
  const valid = await loginFormRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (!loginForm.captcha_code.trim()) {
      errorMessage.value = '请输入验证码计算结果'
      return
    }
    await auth.login(loginForm.username.trim(), loginForm.password, {
      captcha_id: loginForm.captcha_id,
      captcha_code: loginForm.captcha_code.trim(),
    })
    ElMessage.success('登录成功')
    router.replace(redirectTarget.value)
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '登录失败'
    captchaRef.value?.refresh()
  } finally {
    submitting.value = false
  }
}

async function handleRegister() {
  errorMessage.value = ''
  const valid = await registerFormRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await auth.register({
      username: registerForm.username.trim(),
      password: registerForm.password,
      display_name: registerForm.display_name.trim() || undefined,
      email: registerForm.email.trim() || undefined,
    })
    ElMessage.success('注册成功，已自动登录')
    router.replace(redirectTarget.value)
  } catch (error) {
    errorMessage.value = (error as ApiError).message || '注册失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="intro">
      <div class="intro-inner">
        <BrandMark />
        <h1 class="intro-title">智膳 AI</h1>
        <p class="intro-tagline"><span>全场景膳食管家</span></p>
        <p class="intro-sub">
          吃得明白，活得轻盈。从今天的第一餐开始，让 AI 守护全家健康。
        </p>
        <div class="feature-grid" aria-label="产品核心能力">
          <span class="feature-pill">
            <span class="feature-icon" aria-hidden="true">📷</span>
            多模态识食
          </span>
          <span class="feature-pill">
            <span class="feature-icon" aria-hidden="true">📑</span>
            国标溯源
          </span>
          <span class="feature-pill">
            <span class="feature-icon" aria-hidden="true">🧑‍⚕️</span>
            健康建档
          </span>
          <span class="feature-pill">
            <span class="feature-icon" aria-hidden="true">🥗</span>
            智能配餐
          </span>
        </div>
        <p class="intro-note">
          本平台只读取包装上的可见文字，不做实验室检测，不能判断食品是否安全或是否合规。
        </p>
      </div>

      <div class="intro-art intro-art--top" aria-hidden="true">
        <span class="art-item">🥦</span>
        <span class="art-item">🍅</span>
      </div>

      <div class="intro-art intro-art--bottom" aria-hidden="true">
        <span class="art-item">🥕</span>
        <span class="art-item">🥑</span>
        <span class="art-item">🍃</span>
      </div>

      <div class="intro-art intro-art--right" aria-hidden="true">
        <span class="art-item">🍅</span>
        <span class="art-item">🥦</span>
        <span class="art-item art-item--heart">💚</span>
      </div>
    </section>

    <section class="form-side">
      <div class="form-card">
        <div class="form-head">
          <h2>{{ tab === 'login' ? '登录你的账号' : '创建新账号' }}</h2>
          <p class="form-sub">
            {{ tab === 'login' ? '登录后，随时随地同步您的家庭健康档案与 AI 配餐方案。' : '账号用于隔离分析记录，密码使用 scrypt 哈希存储' }}
          </p>
        </div>

        <div class="tab-switch">
          <button type="button" :class="{ active: tab === 'login' }" @click="tab = 'login'; errorMessage = ''">登录</button>
          <button type="button" :class="{ active: tab === 'register' }" @click="tab = 'register'; errorMessage = ''">
            注册
          </button>
        </div>

        <div v-if="errorMessage" class="notice notice-danger form-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ errorMessage }}</span>
        </div>

        <el-form
          v-if="tab === 'login'"
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          label-position="top"
          size="large"
          @submit.prevent="handleLogin"
        >
          <el-form-item label="用户名" prop="username">
            <el-input v-model="loginForm.username" placeholder="请输入用户名" autocomplete="username" clearable />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="loginForm.password"
              type="password"
              show-password
              placeholder="请输入密码"
              autocomplete="current-password"
              @keyup.enter="handleLogin"
            />
          </el-form-item>
          <el-form-item label="验证码" prop="captcha_code">
            <CaptchaField
              ref="captchaRef"
              v-model="loginForm.captcha_code"
              v-model:captcha-id="loginForm.captcha_id"
              :disabled="submitting"
            />
          </el-form-item>
          <el-button type="primary" size="large" class="submit-btn" :loading="submitting" @click="handleLogin">
            登录
          </el-button>
        </el-form>

        <el-form
          v-else
          ref="registerFormRef"
          :model="registerForm"
          :rules="registerRules"
          label-position="top"
          size="large"
          @submit.prevent="handleRegister"
        >
          <el-form-item label="用户名" prop="username">
            <el-input v-model="registerForm.username" placeholder="3-20 位中文、字母、数字或下划线" autocomplete="username" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="registerForm.password"
              type="password"
              show-password
              placeholder="至少 8 位，需含字母和数字"
              autocomplete="new-password"
            />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm">
            <el-input v-model="registerForm.confirm" type="password" show-password placeholder="再次输入密码" />
          </el-form-item>
          <div class="form-grid">
            <el-form-item label="昵称（可选）" prop="display_name">
              <el-input v-model="registerForm.display_name" placeholder="显示名称" maxlength="20" />
            </el-form-item>
            <el-form-item label="邮箱（可选）" prop="email">
              <el-input v-model="registerForm.email" placeholder="用于联系，可不填" />
            </el-form-item>
          </div>
          <el-button type="primary" size="large" class="submit-btn" :loading="submitting" @click="handleRegister">
            注册并登录
          </el-button>
        </el-form>

        <div class="demo-box">
          <div class="demo-text">
            <strong>想先看看效果？</strong>
            <span>使用演示账号可直接体验完整流程（含明确标记的演示数据）。</span>
          </div>
          <el-button class="demo-fill-btn" @click="fillDemo">
            <span>填入演示账号</span>
            <span class="demo-arrow" aria-hidden="true">→</span>
          </el-button>
        </div>

        <p class="privacy-note">
          我们采用脱敏技术安全保存您的分析记录与健康画像，密码已加密存储，绝不泄露隐私。
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  background: var(--bg);
}

/* 左侧介绍区 */
.intro {
  position: relative;
  padding: 56px 52px;
  color: #eaf6f2;
  background:
    radial-gradient(circle at 18% 12%, rgba(58, 190, 165, 0.5), transparent 45%),
    radial-gradient(circle at 85% 78%, rgba(240, 162, 50, 0.28), transparent 50%),
    linear-gradient(150deg, #0a4a41 0%, #0b5d52 45%, #0e7364 100%);
  display: flex;
  align-items: center;
  overflow: hidden;
}

.intro::after {
  content: '';
  position: absolute;
  inset: auto -80px -120px auto;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.14);
}

.intro-inner {
  position: relative;
  z-index: 1;
  max-width: 500px;
  margin-left: auto;
  margin-right: auto;
  width: 100%;
}

:deep(.brand-name),
:deep(.brand-sub) {
  color: #ffffff;
}

:deep(.brand-sub) {
  color: rgba(255, 255, 255, 0.72);
}

.intro-title {
  margin-top: 34px;
  font-size: 38px;
  line-height: 1.25;
  font-weight: 780;
  color: #fff;
  letter-spacing: -0.5px;
}

.intro-sub {
  margin-top: 16px;
  font-size: 15px;
  line-height: 1.85;
  color: rgba(255, 255, 255, 0.82);
}

.feature-list {
  margin-top: 28px;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feature-list li {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.9);
}

.feature-list .el-icon {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.13);
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  font-size: 15px;
}

.intro-note {
  margin-top: 32px;
  font-size: 12px;
  line-height: 1.75;
  color: rgba(255, 255, 255, 0.6);
  border-top: 1px solid rgba(255, 255, 255, 0.14);
  padding-top: 16px;
}

/* 右侧表单 */
.form-side {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 28px;
}

.form-card {
  width: 100%;
  max-width: 430px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 20px;
  box-shadow: 0 20px 50px rgba(15, 60, 52, 0.08);
  padding: 30px 28px;
}

.form-head h2 {
  font-size: 22px;
  letter-spacing: -0.2px;
}

.form-sub {
  margin-top: 6px;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.6;
}

.tab-switch {
  display: flex;
  gap: 4px;
  background: var(--surface-2);
  border-radius: 11px;
  padding: 4px;
  margin: 20px 0 18px;
}

.tab-switch button {
  flex: 1;
  border: none;
  background: transparent;
  padding: 9px 0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  min-height: 38px;
}

.tab-switch button.active {
  background: var(--card);
  color: var(--brand-700);
  box-shadow: 0 2px 8px rgba(15, 60, 52, 0.08);
}

.form-error {
  margin-bottom: 14px;
  font-size: 13px;
}

.submit-btn {
  width: 100%;
  margin-top: 4px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}

.demo-box {
  margin-top: 20px;
  padding: 13px 14px;
  border: 1px dashed var(--border-strong);
  border-radius: 12px;
  background: var(--surface-2);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.demo-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12.5px;
  color: var(--muted);
  min-width: 0;
}

.demo-text strong {
  color: var(--text);
  font-size: 13.5px;
}

.privacy-note {
  margin-top: 16px;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
  text-align: center;
}

@media (max-width: 1023px) {
  .login-page {
    grid-template-columns: minmax(0, 1fr);
  }
  .intro {
    padding: 30px 22px 34px;
    align-items: flex-start;
  }
  .intro-title {
    margin-top: 20px;
    font-size: 26px;
  }
  .intro-sub {
    font-size: 13.5px;
  }
  .feature-list {
    margin-top: 18px;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 9px;
  }
  .feature-list li {
    font-size: 12.5px;
    align-items: flex-start;
  }
  .feature-list .el-icon {
    width: 24px;
    height: 24px;
    font-size: 13px;
    border-radius: 7px;
  }
  .intro-note {
    margin-top: 18px;
    padding-top: 12px;
  }
  .form-side {
    padding: 18px 14px 34px;
    margin-top: -18px;
  }
  .form-card {
    padding: 22px 18px;
    border-radius: 18px;
  }
}

@media (max-width: 480px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .intro-title {
    font-size: 23px;
  }
  .hide-mobile {
    display: none;
  }
}

/* ---------- 登录页左侧：浅色插画 + 轻量化排版 ---------- */
.login-page {
  background: #f7fbf7;
}

.intro {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px clamp(32px, 5vw, 76px);
  color: #111827;
  background:
    radial-gradient(circle at 12% 18%, rgba(190, 236, 207, 0.5), transparent 34%),
    radial-gradient(circle at 88% 18%, rgba(255, 232, 194, 0.5), transparent 30%),
    radial-gradient(circle at 72% 88%, rgba(205, 239, 220, 0.55), transparent 34%),
    linear-gradient(135deg, #f8fcf8 0%, #f2faf3 52%, #fffaf2 100%);
  overflow: hidden;
}

.intro::before {
  position: absolute;
  top: -110px;
  left: -90px;
  width: 310px;
  height: 310px;
  border-radius: 46% 54% 58% 42% / 52% 44% 56% 48%;
  background: rgba(184, 231, 200, 0.28);
  content: "";
  filter: blur(2px);
}

.intro::after {
  position: absolute;
  right: -90px;
  bottom: -120px;
  width: 360px;
  height: 360px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 226, 183, 0.28);
  content: "";
}

.intro-inner {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 580px;
  margin: 0 auto;
  padding: 30px 0;
}

.intro :deep(.brand-name) {
  color: #111827;
}

.intro :deep(.brand-name span) {
  color: #0f6b52;
  background: #e8f7ee;
}

.intro :deep(.brand-sub) {
  color: #7b8b80;
}

.intro-title {
  margin: 30px 0 0;
  color: #111827;
  font-size: clamp(36px, 3.4vw, 50px);
  font-weight: 820;
  line-height: 1.16;
  letter-spacing: -1.2px;
}

.intro-title span {
  display: block;
  margin-top: 8px;
  color: #111827;
  font-size: 0.78em;
  font-weight: 780;
  letter-spacing: -0.8px;
}

.intro-sub {
  max-width: 500px;
  margin: 20px 0 0;
  color: #6b7280;
  font-size: 16px;
  font-weight: 400;
  line-height: 1.9;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  max-width: 500px;
  margin-top: 26px;
}

.feature-pill {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  min-height: 44px;
  padding: 9px 13px;
  border: 1px solid rgba(194, 229, 205, 0.9);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.76);
  color: #374151;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.35;
  box-shadow: 0 4px 14px rgba(58, 104, 78, 0.04);
  backdrop-filter: blur(6px);
}

.feature-icon {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  border-radius: 9px;
  background: #ecfdf5;
  color: #10b981;
  font-size: 15px;
}

.intro-note {
  max-width: 500px;
  margin-top: 24px;
  padding-top: 14px;
  border-top: 1px solid rgba(177, 207, 188, 0.4);
  color: #9ca3af;
  font-size: 10.5px;
  line-height: 1.75;
}

/* 右侧轻插画，作为背景层不参与文字排版 */
.intro-art {
  position: absolute;
  right: -22px;
  bottom: -22px;
  z-index: 1;
  width: 290px;
  height: 270px;
  pointer-events: none;
  opacity: 0.42;
  filter: saturate(0.92);
}

.art-plate {
  position: absolute;
  right: 8px;
  bottom: 18px;
  width: 190px;
  height: 190px;
  border: 12px solid rgba(255, 255, 255, 0.9);
  border-radius: 50%;
  background:
    radial-gradient(circle at 48% 52%, #fffefb 0 42%, #f4fbf5 43% 68%, #e8f5eb 69%);
  box-shadow:
    0 14px 38px rgba(83, 121, 95, 0.12),
    inset 0 0 0 1px rgba(188, 221, 197, 0.45);
}

.art-veg {
  position: absolute;
  font-size: 35px;
  filter: drop-shadow(0 4px 4px rgba(55, 91, 67, 0.12));
}

.art-broccoli {
  top: 38px;
  left: 36px;
  transform: rotate(-10deg);
}

.art-tomato {
  top: 58px;
  right: 26px;
  font-size: 33px;
  transform: rotate(9deg);
}

.art-carrot {
  bottom: 30px;
  left: 26px;
  font-size: 37px;
  transform: rotate(-25deg);
}

.art-avocado {
  right: 46px;
  bottom: 22px;
  font-size: 34px;
  transform: rotate(11deg);
}

.art-spark {
  position: absolute;
  font-size: 22px;
  filter: drop-shadow(0 4px 5px rgba(55, 91, 67, 0.08));
}

.art-heart {
  top: 24px;
  right: 8px;
  transform: rotate(12deg);
}

.art-leaf {
  top: 100px;
  left: -6px;
  font-size: 24px;
  transform: rotate(-22deg);
}

.art-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #b7dfc3;
}

.art-dot-one {
  top: 30px;
  left: 40px;
}

.art-dot-two {
  right: 4px;
  bottom: 60px;
  width: 5px;
  height: 5px;
  background: #f1c98f;
}

.form-side {
  background: #fdfbf7;
}

.form-card {
  border-color: #e7eee8;
  box-shadow: 0 18px 50px rgba(69, 95, 75, 0.08);
}

@media (max-width: 1023px) {
  .intro {
    min-height: 390px;
    padding: 30px 22px 34px;
  }

  .intro-inner {
    max-width: 620px;
    padding: 12px 0;
  }

  .intro-title {
    margin-top: 22px;
    font-size: 30px;
  }

  .intro-title span {
    font-size: 0.78em;
  }

  .intro-sub {
    margin-top: 14px;
    font-size: 14px;
    line-height: 1.8;
  }

  .feature-grid {
    margin-top: 18px;
  }

  .feature-pill {
    min-height: 40px;
    padding: 7px 10px;
    font-size: 12px;
  }

  .feature-icon {
    width: 24px;
    height: 24px;
    flex-basis: 24px;
    font-size: 13px;
  }

  .intro-note {
    margin-top: 18px;
    padding-top: 11px;
  }

  .intro-art {
    right: -72px;
    bottom: -42px;
    width: 220px;
    height: 210px;
    opacity: 0.32;
  }

  .art-plate {
    width: 160px;
    height: 160px;
    border-width: 9px;
  }

  .art-veg {
    font-size: 28px;
  }

  .art-tomato,
  .art-avocado {
    font-size: 26px;
  }
}

@media (max-width: 480px) {
  .intro-title {
    font-size: 26px;
  }

  .intro-sub {
    font-size: 13px;
  }

  .feature-grid {
    gap: 8px;
  }

  .feature-pill {
    min-height: 38px;
    padding: 7px 9px;
    font-size: 11.5px;
  }
}

/* ===== 登录页左侧最终精修：纯薄荷底 + 散落蔬果水印 ===== */
.login-page {
  background: #f4f9f7;
}

.intro {
  background: #f4f9f7;
  align-items: center;
  justify-content: center;
  padding: 52px clamp(32px, 5vw, 76px);
}

.intro::before,
.intro::after {
  display: none;
}

.intro-inner {
  max-width: 580px;
  padding: 38px 0;
  z-index: 2;
}

.intro-title {
  margin: 28px 0 0;
  color: #111827;
  font-size: clamp(48px, 4vw, 64px);
  font-weight: 850;
  line-height: 1.04;
  letter-spacing: -2px;
}

.intro-tagline {
  margin: 14px 0 0;
}

.intro-tagline span {
  display: inline-flex;
  align-items: center;
  padding: 5px 11px;
  border-radius: 999px;
  background: #e8f7ee;
  color: #0f6b52;
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.intro-sub {
  max-width: 480px;
  margin: 19px 0 0;
  color: #6b7280;
  font-size: 16px;
  line-height: 1.9;
}

.feature-pill {
  min-height: 42px;
  padding: 8px 12px;
  border: 0;
  border-radius: 10px;
  background: #ecfdf5;
  color: #047857;
  box-shadow: none;
  backdrop-filter: none;
  font-weight: 650;
}

.feature-icon {
  width: 27px;
  height: 27px;
  flex-basis: 27px;
  border-radius: 8px;
  background: #d1fae5;
  color: #059669;
}

.intro-note {
  margin-top: 26px;
  color: #9ca3af;
}

/* 蔬果水印：放大，散落三处，低透明度 */
.intro-art {
  position: absolute;
  z-index: 0;
  display: flex;
  gap: 2px;
  width: auto;
  height: auto;
  margin: 0;
  opacity: 0.1;
  pointer-events: none;
  user-select: none;
  filter: saturate(0.85);
}

.intro-art--top {
  top: -34px;
  left: -48px;
  transform: rotate(-9deg);
}

.intro-art--bottom {
  bottom: -38px;
  left: -42px;
  transform: rotate(7deg);
}

.intro-art--right {
  top: 27%;
  right: -34px;
  transform: rotate(-7deg);
}

.art-item {
  display: block;
  color: #111827;
  font-size: clamp(88px, 8vw, 122px);
  line-height: 0.92;
}

.art-item--heart {
  font-size: clamp(52px, 4.8vw, 70px);
  align-self: center;
}

@media (max-width: 1023px) {
  .intro {
    padding: 34px 22px 38px;
  }

  .intro-inner {
    padding: 18px 0;
  }

  .intro-title {
    margin-top: 22px;
    font-size: 42px;
    letter-spacing: -1.2px;
  }

  .intro-tagline {
    margin-top: 10px;
  }

  .intro-tagline span {
    padding: 4px 9px;
    font-size: 12px;
  }

  .intro-sub {
    margin-top: 14px;
    font-size: 14px;
    line-height: 1.8;
  }

  .feature-pill {
    min-height: 38px;
    padding: 7px 9px;
    font-size: 11.5px;
  }

  .feature-icon {
    width: 23px;
    height: 23px;
    flex-basis: 23px;
    font-size: 13px;
  }

  .intro-note {
    margin-top: 18px;
    padding-top: 11px;
  }

  .intro-art {
    opacity: 0.08;
  }

  .intro-art--top {
    top: -48px;
    left: -70px;
  }

  .intro-art--bottom {
    bottom: -62px;
    left: -82px;
  }

  .intro-art--right {
    top: 22%;
    right: -48px;
  }

  .art-item {
    font-size: 74px;
  }

  .art-item--heart {
    font-size: 46px;
  }
}

@media (max-width: 480px) {
  .intro-title {
    font-size: 36px;
  }

  .intro-sub {
    font-size: 13px;
  }

  .feature-pill {
    min-height: 36px;
    font-size: 11px;
  }
}

/* ===== 登录表单右侧细节 ===== */
.form-card :deep(.el-input__wrapper) {
  transition:
    box-shadow 0.18s ease,
    border-color 0.18s ease;
}

.form-card :deep(.el-input__wrapper.is-focus),
.form-card :deep(.el-input__wrapper:focus-within) {
  box-shadow:
    0 0 0 2px rgba(16, 185, 129, 0.5),
    inset 0 0 0 1px #10b981 !important;
}

.form-card :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(16, 185, 129, 0.22);
}

.demo-fill-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  padding: 0 14px;
  border: 0;
  border-radius: 9px;
  background: #d1fae5;
  color: #047857;
  font-size: 13px;
  font-weight: 700;
  box-shadow: none;
  transition:
    background 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;
}

.demo-fill-btn:hover,
.demo-fill-btn:focus {
  background: #a7f3d0;
  color: #065f46;
  transform: translateY(-1px);
}

.demo-fill-btn .demo-arrow {
  font-size: 17px;
  font-weight: 700;
  line-height: 1;
}
</style>
