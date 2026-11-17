import type {
  RouteLocationNormalizedLoaded,
  RouteLocationRaw,
} from 'vue-router'

/**
 * 模块级返回规则：
 * - 详情页回自己的列表/模块页
 * - 模块根页面回仪表盘
 * - 后台子页面回后台概览
 *
 * 不使用 router.back()，避免跨菜单操作后一路退回别的模块。
 */
const MODULE_DETAIL_ROOTS: Array<{
  prefix: string
  name: string
}> = [
  { prefix: '/knowledge', name: 'knowledge' },
  { prefix: '/pantry', name: 'pantry' },
  { prefix: '/inventory', name: 'pantry' },
  { prefix: '/favorites', name: 'favorites' },
  { prefix: '/assistant', name: 'assistant' },
  { prefix: '/health-profile', name: 'health-profile' },
  { prefix: '/settings', name: 'settings' },
  { prefix: '/analyze', name: 'analyze' },
]

export function resolveBackRoute(
  route: RouteLocationNormalizedLoaded,
): RouteLocationRaw {
  const path = (route.path || '/').replace(/\/+$/, '') || '/'
  const metaBack = route.meta.back as string | undefined

  if (metaBack === 'result') {
    const id = route.params.id
    return id
      ? { name: 'result', params: { id } }
      : { name: 'history' }
  }
  if (metaBack) {
    return { name: metaBack }
  }

  // 后台：任何后台子页面都回后台概览
  if (path.startsWith('/admin/')) {
    return { name: 'admin-dashboard' }
  }

  // 分析结果：详情回历史列表
  if (path.startsWith('/result/')) {
    return { name: 'history' }
  }

  // 报告详情：优先回对应分析结果，没有 id 时回历史列表
  if (path.startsWith('/report/')) {
    const id = route.params.id
    return id
      ? { name: 'result', params: { id } }
      : { name: 'history' }
  }

  // 兼容未来可能出现的模块详情页，如 /knowledge/detail/1
  for (const item of MODULE_DETAIL_ROOTS) {
    if (path.startsWith(`${item.prefix}/`)) {
      return { name: item.name }
    }
  }

  // 所有模块根页面、首页、未知路径都回仪表盘
  return { name: 'home' }
}
