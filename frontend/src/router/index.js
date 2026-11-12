import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getToken, parseToken } from '@/utils/session'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/orders',
    name: 'Orders',
    component: () => import('@/views/Orders.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/orders/:id',
    name: 'OrderDetail',
    component: () => import('@/views/OrderDetail.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/quotes',
    name: 'Quotes',
    component: () => import('@/views/Quotes.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/approvals',
    name: 'Approvals',
    component: () => import('@/views/Approvals.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/supplier-orders',
    name: 'SupplierOrders',
    component: () => import('@/views/SupplierOrders.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/receipts',
    name: 'Receipts',
    component: () => import('@/views/Receipts.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('@/views/Knowledge.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/memory',
    name: 'MaterialMemory',
    component: () => import('@/views/MaterialMemory.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：未登录跳 /login；有 token 但无 team_id 也跳 /login
router.beforeEach((to) => {
  if (to.meta.public) return true

  const token = getToken()
  if (!token) return { name: 'Login' }

  // 解析 JWT payload（不验证签名，仅读 claims）
  try {
    const payload = parseToken(token)
    if (!payload.team_id) return { name: 'Login' }
  } catch {
    return { name: 'Login' }
  }

  return true
})

export default router
