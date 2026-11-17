<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="page not-found">
    <div class="card">
      <div class="code">404</div>
      <h1>页面不存在</h1>
      <p>你访问的地址可能已被移除，或链接输入有误。</p>
      <div class="actions">
        <el-button type="primary" @click="router.push({ name: 'home' })">返回仪表盘</el-button>
        <el-button @click="router.push({ name: 'analyze' })">开始检测</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  justify-content: center;
  padding-top: 60px;
}

.card {
  max-width: 460px;
  text-align: center;
  padding: 40px 26px;
}

.code {
  font-size: 62px;
  font-weight: 800;
  color: var(--brand-100);
  line-height: 1;
  letter-spacing: -2px;
}

h1 {
  margin-top: 8px;
  font-size: 20px;
}

p {
  margin-top: 8px;
  color: var(--muted);
  font-size: 13.5px;
}

.actions {
  margin-top: 20px;
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
