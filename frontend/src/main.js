/**
 * ============================================================
 * 前端入口文件 main.js
 * ------------------------------------------------------------
 * 作用：浏览器打开 index.html 后第一个执行的 JS 文件。
 *   1. 创建 Vue 应用实例（根组件是 App.vue）；
 *   2. 挂载三大插件：Pinia（全局状态管理）、Vue Router（路由）、
 *      Element Plus（UI 组件库，配中文语言包）；
 *   3. 把 Element Plus 的全部图标注册成全局组件，页面里可直接
 *      写 <Plus /> <Delete /> 而无需逐个 import；
 *   4. 最后把应用挂载到 index.html 里的 <div id="app"> 上。
 * 联动：App.vue（根组件）、router/index.js（路由表）、stores/（Pinia）。
 * ============================================================
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'

// 创建 Vue 应用实例，App 是整个组件树的根
const app = createApp(App)

// 注册所有 Element Plus 图标为全局组件
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册 Pinia 状态管理
app.use(createPinia())
// 注册路由
app.use(router)
// 注册 Element Plus 组件库，使用中文语言包
app.use(ElementPlus, { locale: zhCn })

// 把应用渲染到 index.html 的 <div id="app"> 里，页面才真正显示
app.mount('#app')
