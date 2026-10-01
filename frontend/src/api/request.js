/**
 * ============================================================
 * axios 实例封装（所有后端 HTTP 请求的"总闸门"）
 * ------------------------------------------------------------
 * api/ 目录下除 chat.js 的流式接口外，所有请求都通过本文件
 * 导出的 request 发出，统一做三件事：
 *   1. baseURL = '/api'：代码里写 '/customers' 实际请求 '/api/customers'
 *      （开发环境由 vite.config.js 的 proxy 转发到后端 8000）；
 *   2. 请求拦截器：自动从 localStorage 读 token 塞进请求头，
 *      页面代码不用每次都手写 Authorization；
 *   3. 响应拦截器：统一拆后端响应壳（见 response.js）、统一弹错误
 *      提示、401 时自动清 token 并跳回登录页。
 *
 * 【小白须知 · 什么是拦截器】
 * 拦截器就像快递中转站：每个请求"出发前"和每个响应"到达后"都会
 * 先经过这里统一加工，业务代码只关心最终数据。
 * ============================================================
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { unwrapApiResponse } from './response'

// 创建 axios 实例
// baseURL 为 /api，开发环境通过 vite proxy 转发到后端
const request = axios.create({
  baseURL: '/api',
  timeout: 30000 // 30 秒无响应自动取消（SSE 流式接口不走这里，不受影响）
})

// 请求拦截器：自动携带 Authorization 头
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：先把后端的统一响应壳 { code, message, data } 拆开，
// 页面组件拿到的直接就是 data 里的业务数据（见 response.js）。
request.interceptors.response.use(
  (response) => {
    try {
      return unwrapApiResponse(response.data)
    } catch (error) {
      // 后端返回 code != 0 的业务错误：弹提示并当失败处理
      ElMessage.error(error.message)
      return Promise.reject(error)
    }
  },
  (error) => {
    // HTTP 层错误（4xx/5xx/网络失败）。?. 是可选链：前面为 null/undefined
    // 就短路返回 undefined 而不是报错，相当于一串安全的 .data?.message 取值。
    const message = error.response?.data?.message || error.response?.data?.detail || error.message || '请求失败'

    // 401 说明 token 失效（过期/被踢）：清掉本地 token，强制回登录页
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      ElMessage.error('登录已过期，请重新登录')
      window.location.href = '/login'
    } else {
      ElMessage.error(typeof message === 'string' ? message : '请求失败')
    }
    return Promise.reject(error)
  }
)

export default request
