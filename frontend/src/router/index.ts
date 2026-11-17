import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAdminStore } from '@/stores/admin'

import { getAdminToken } from '@/api/admin'



const router = createRouter({

  history: createWebHistory(import.meta.env.BASE_URL),

  scrollBehavior(to, _from, savedPosition) {

    if (savedPosition) return savedPosition

    if (to.hash) return { el: to.hash, top: 80, behavior: 'smooth' }

    return { top: 0, behavior: 'smooth' }

  },

  routes: [

    {

      path: '/',

      name: 'home',

      component: () => import('@/views/DashboardView.vue'),

      meta: { title: '仪表盘', requiresAuth: true },

    },

    {

      path: '/login',

      name: 'login',

      component: () => import('@/views/LoginView.vue'),

      meta: { title: '登录 / 注册', layout: 'blank', public: true },

    },

    {

      path: '/analyze',

      name: 'analyze',

      component: () => import('@/views/AnalyzeView.vue'),

      meta: { title: 'AI 营养解析与评估', requiresAuth: true, back: 'home' },

    },

    {

      path: '/result/:id',

      name: 'result',

      component: () => import('@/views/ResultView.vue'),

      meta: { title: '分析结果', requiresAuth: true, back: 'history' },

    },

    {

      path: '/history',

      name: 'history',

      component: () => import('@/views/HistoryView.vue'),

      meta: { title: '历史记录', requiresAuth: true, back: 'home' },

    },

    {

      path: '/report/:id',

      name: 'report',

      component: () => import('@/views/ReportView.vue'),

      meta: { title: '分析报告', requiresAuth: true, back: 'result' },

    },

    {

      path: '/knowledge',

      name: 'knowledge',

      component: () => import('@/views/KnowledgeView.vue'),

      meta: { title: '智膳智库', public: true, back: 'home' },

    },

    {

      path: '/pantry',

      alias: '/inventory',

      name: 'pantry',

      component: () => import('@/views/PantryView.vue'),

      meta: { title: '家庭食材管家', requiresAuth: true, back: 'home' },

    },

    {

      path: '/favorites',

      name: 'favorites',

      redirect: { name: 'pantry', query: { tab: 'favorites' } },

      meta: { title: '我的收藏', requiresAuth: true, back: 'home' },

    },

    {

      path: '/assistant',

      name: 'assistant',

      component: () => import('@/views/AssistantView.vue'),

      meta: { title: 'AI 食安智询官', requiresAuth: true, back: 'home' },

    },

    {

      path: '/health-profile',

      name: 'health-profile',

      component: () => import('@/views/PantryView.vue'),

      meta: { title: '健康画像', requiresAuth: true, back: 'home' },

    },

    {

      path: '/settings',

      name: 'settings',

      component: () => import('@/views/SettingsView.vue'),

      meta: { title: '设置', requiresAuth: true, back: 'home' },

    },

    {

      path: '/about',

      redirect: { name: 'settings', query: { about: '1' } },

    },

    {

      path: '/admin/login',

      name: 'admin-login',

      component: () => import('@/views/admin/AdminLoginView.vue'),

      meta: { title: '管理员登录', layout: 'blank', public: true },

    },

    {

      path: '/admin',

      component: () => import('@/layouts/AdminLayout.vue'),

      meta: { admin: true, back: 'admin-dashboard' },

      children: [

        { path: '', redirect: { name: 'admin-dashboard' } },

        {

          path: 'dashboard',

          name: 'admin-dashboard',

          component: () => import('@/views/admin/AdminDashboardView.vue'),

          meta: { title: '后台概览', admin: true },

        },

        {

          path: 'users',

          name: 'admin-users',

          component: () => import('@/views/admin/AdminUsersView.vue'),

          meta: { title: '用户管理', admin: true },

        },

        {

          path: 'records',

          name: 'admin-records',

          component: () => import('@/views/admin/AdminRecordsView.vue'),

          meta: { title: '分析记录', admin: true },

        },

        {

          path: 'feedback',

          name: 'admin-feedback',

          component: () => import('@/views/admin/AdminFeedbackView.vue'),

          meta: { title: '用户反馈', admin: true },

        },

        {

          path: 'knowledge',

          name: 'admin-knowledge',

          component: () => import('@/views/admin/AdminKnowledgeView.vue'),

          meta: { title: '知识库管理', admin: true },

        },

        {

          path: 'rules',

          name: 'admin-rules',

          component: () => import('@/views/admin/AdminRulesView.vue'),

          meta: { title: '核查规则', admin: true },

        },

        {

          path: 'prompts',

          name: 'admin-prompts',

          component: () => import('@/views/admin/AdminPromptsView.vue'),

          meta: { title: 'Prompt 管理', admin: true },

        },

        {

          path: 'monitor',

          name: 'admin-monitor',

          component: () => import('@/views/admin/AdminMonitorView.vue'),

          meta: { title: '系统监控', admin: true },

        },

        {

          path: 'audit-logs',

          name: 'admin-audit-logs',

          component: () => import('@/views/admin/AdminAuditLogsView.vue'),

          meta: { title: '操作审计', admin: true },

        },

      ],

    },

    {

      path: '/:pathMatch(.*)*',

      name: 'not-found',

      component: () => import('@/views/NotFoundView.vue'),

      meta: { title: '页面不存在', public: true },

    },

  ],

})



router.beforeEach(async (to) => {

  const auth = useAuthStore()

  const admin = useAdminStore()



  if (to.meta.admin) {

    // 1) 已登录且角色是管理员：直接放行（复用普通登录会话，不再要求二次登录）

    if (auth.isAuthenticated && auth.user?.role === 'admin') {

      admin.syncToken()

      return true

    }

    // 2) 只有管理员令牌（例如从 /admin/login 登录过）：校验后放行

    if (getAdminToken()) {

      const ok = await admin.ensureUser().catch(() => false)

      if (ok) return true

    }

    // 3) 已登录但不是管理员：刷新一次角色（可能刚被提升为管理员）

    if (auth.isAuthenticated) {

      await auth.fetchMe().catch(() => undefined)

      if (auth.user?.role === 'admin') {

        admin.syncToken()

        return true

      }

      // 普通用户看不到后台：直接回首页，不展示管理员登录页

      return { name: 'home' }

    }

    // 4) 完全未登录：去普通登录页，登录后回到原目标

    return { name: 'login', query: { redirect: to.fullPath } }

  }



  if (to.name === 'admin-login') {

    if (auth.user?.role === 'admin' || (getAdminToken() && admin.isAdmin)) {

      return { name: 'admin-dashboard' }

    }

    // 已登录的普通用户不应看到管理员登录页

    if (auth.isAuthenticated) {

      return { name: 'home' }

    }

  }



  if (to.meta.requiresAuth && !auth.isAuthenticated) {

    return { name: 'login', query: { redirect: to.fullPath } }

  }

  if (to.name === 'login' && auth.isAuthenticated) {

    return { name: 'home' }

  }

  return true

})



router.afterEach((to) => {

  const title = (to.meta.title as string) || '智膳 AI'

  document.title = `${title} · 智膳 AI`

})



export default router

