/**
 * ============================================================
 * 后端响应"拆壳"工具 response.js
 * ------------------------------------------------------------
 * 后端接口有两种返回风格：
 *   1. 统一信封：{ code: 0, message: 'ok', data: ... }（约定 code=0 成功）
 *   2. 直接返回业务数据（数组/对象）
 * 本文件提供三个小工具，让上层代码不用关心后端用的是哪种风格。
 * 被 request.js 的响应拦截器和部分页面（如 Customers.vue）使用。
 * ============================================================
 */

// 判断一个返回值是不是后端的统一信封格式 { code, message, data }
export function isApiResponse(value) {
  return Boolean(
    value &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    Object.hasOwn(value, 'code') &&
    Object.hasOwn(value, 'message') &&
    Object.hasOwn(value, 'data')
  )
}

// 拆壳：是信封且 code=0 → 返回 data；code≠0 → 抛业务错误；不是信封 → 原样返回
export function unwrapApiResponse(value) {
  if (!isApiResponse(value)) return value

  if (value.code !== 0) {
    const error = new Error(value.message || '请求失败')
    error.code = value.code
    throw error
  }

  return value.data
}

// 列表接口兜底：后端可能直接返回数组，也可能返回 { items: [...], total }，
// 统一取出数组部分，取不到就给空数组，避免页面 .map 时报错
export function asList(value, key = 'items') {
  if (Array.isArray(value)) return value
  return Array.isArray(value?.[key]) ? value[key] : []
}
