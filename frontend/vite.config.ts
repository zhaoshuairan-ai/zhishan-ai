import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：开发时默认 127.0.0.1:8000；手机访问 5173 时由 Vite 代理转发到本机后端
const proxyTarget = process.env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 0.0.0.0 让同一 Wi-Fi 下的手机可以访问电脑的前端开发服务器
    host: '0.0.0.0', // 允许同一 Wi-Fi 下的手机访问
    port: 5173,
    strictPort: true,
    watch: {
      // 忽略编辑器/工具产生的临时目录，避免 Windows 上文件监听报 EBUSY
      ignored: ['**/*.tmpdir/**', '**/.*.tmpdir/**', '**/__pycache__/**'],
    },
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1400,
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          element: ['element-plus', '@element-plus/icons-vue'],
          echarts: ['echarts'],
        },
      },
    },
  },
})
