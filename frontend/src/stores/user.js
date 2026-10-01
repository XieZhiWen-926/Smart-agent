/**
 * ============================================================
 * 用户状态管理 stores/user.js（Pinia store）
 * ------------------------------------------------------------
 * 管登录态：token + 当前用户信息。token 同时写进 localStorage，
 * 这样刷新页面后还能保持登录；request.js 的拦截器和路由守卫
 * 也都是从 localStorage 读 token 的，三处保持一致。
 * 主要使用者：views/Login.vue、components/Layout.vue。
 * ============================================================
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login as apiLogin, getMe } from '@/api/auth'

// 用户状态管理：登录、登出、获取用户信息
export const useUserStore = defineStore('user', () => {
  // token 存储在 localStorage 中，刷新页面不丢失
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(null)

  /**
   * 登录
   * @param {string} username 用户名
   * @param {string} password 密码
   */
  async function login(username, password) {
    const res = await apiLogin(username, password)
    token.value = res.access_token
    localStorage.setItem('token', res.access_token)
    // 登录成功后获取用户信息
    await fetchUserInfo()
  }

  /**
   * 获取当前登录用户信息
   */
  async function fetchUserInfo() {
    if (!token.value) return
    try {
      const info = await getMe()
      userInfo.value = info
    } catch (e) {
      // 获取用户信息失败，可能 token 已过期
      logout()
    }
  }

  /**
   * 退出登录：清除 token 和用户信息
   */
  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    // 跳转到登录页
    window.location.href = '/login'
  }

  return { token, userInfo, login, logout, fetchUserInfo }
})
