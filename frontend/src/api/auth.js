/**
 * ============================================================
 * 登录认证接口封装 auth.js
 * ------------------------------------------------------------
 * 被 stores/user.js 调用：login() 拿 token，getMe() 拿当前用户信息。
 * ============================================================
 */
import request from './request'

/**
 * 登录
 * @param {string} username 用户名
 * @param {string} password 密码
 * @returns {Promise<{access_token: string, token_type: string}>}
 */
export function login(username, password) {
  // 后端登录接口遵循 OAuth2 密码模式，要求 form 表单而不是 JSON，
  // 所以这里用 FormData 拼 multipart/form-data 请求体
  const formData = new FormData()
  formData.append('username', username)
  formData.append('password', password)
  return request({
    url: '/auth/login',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/**
 * 获取当前登录用户信息
 */
export function getMe() {
  return request({
    url: '/auth/me',
    method: 'get'
  })
}
