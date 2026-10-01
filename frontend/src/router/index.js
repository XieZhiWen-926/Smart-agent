/**
 * ============================================================
 * 路由表 router/index.js
 * ------------------------------------------------------------
 * 作用：定义"浏览器地址 → 页面组件"的映射关系，并在这里做
 * 全局登录守卫（没登录的访问一律踢回 /login）。
 *
 * 结构说明：
 *   /login          —— 独立页面，不需要登录；
 *   /               —— 以 Layout.vue（侧边栏+顶栏框架）作为父路由，
 *                      里面的 children（chat/customers/tools/…）都会
 *                      渲染在 Layout 的 <router-view /> 里。
 *
 * 小白须知：
 *   - () => import('...') 是"路由懒加载"：只有真正访问该页面时才
 *     下载对应代码，加快首屏速度；
 *   - meta 是给路由附加的自定义数据，这里用来标记是否需要登录
 *     （requiresAuth）和页面标题（Layout 顶栏会读 title）。
 * ============================================================
 */
import { createRouter, createWebHistory } from 'vue-router'
import Layout from '@/components/Layout.vue'

// 路由配置：登录页独立，其余页面使用 Layout 作为父布局
const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false, title: '登录' }
  },
  {
    path: '/',
    component: Layout,
    redirect: '/chat',
    children: [
      {
        path: '/chat',
        name: 'Chat',
        component: () => import('@/views/Chat.vue'),
        meta: { requiresAuth: true, title: '智能对话' }
      },
      {
        path: '/customers',
        name: 'Customers',
        component: () => import('@/views/Customers.vue'),
        meta: { requiresAuth: true, title: '客户管理' }
      },
      {
        path: '/tools',
        name: 'Tools',
        component: () => import('@/views/Tools.vue'),
        meta: { requiresAuth: true, title: '工具管理' }
      },
      {
        path: '/datasets',
        name: 'Datasets',
        component: () => import('@/views/Datasets.vue'),
        meta: { requiresAuth: true, title: '数据集管理' }
      },
      {
        path: '/memory',
        name: 'Memory',
        component: () => import('@/views/Memory.vue'),
        meta: { requiresAuth: true, title: '记忆管理' }
      }
    ]
  }
]

const router = createRouter({
  // history 模式：地址栏是 /chat 这种"干净"路径（不带 #）。
  // 注意：该模式要求服务器把所有路径都回退到 index.html，
  // 前端容器 nginx.conf 里的 try_files 就是干这个的。
  history: createWebHistory(),
  routes
})

// 全局前置守卫：每次路由跳转前都会先执行这个函数。
//   to   —— 要去的目标路由；from —— 当前路由；
//   next —— 调用它才放行，next('/login') 表示改道去登录页。
// 规则：无 token 且访问需要认证的页面 → 跳登录页；
//       有 token 还访问登录页 → 直接跳聊天页。
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  // to.matched 是目标路由匹配到的整条路由链（含父路由），
  // 只要链上有任意一段没显式声明 requiresAuth: false，就视为需要登录
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth !== false)

  if (requiresAuth && !token) {
    // 未登录，跳转登录页
    next('/login')
  } else if (to.path === '/login' && token) {
    // 已登录还访问登录页，直接跳聊天页
    next('/chat')
  } else {
    next()
  }
})

export default router
