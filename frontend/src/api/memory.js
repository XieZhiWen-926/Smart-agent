/**
 * ============================================================
 * 长期记忆接口封装 memory.js
 * ------------------------------------------------------------
 * 系统会从对话中自动抽取客户偏好/事实（如"对噪音敏感"）存为
 * 长期记忆，下次对话自动召回。这里提供查看/删除/手动触发抽取。
 * 被 views/Memory.vue 调用。
 * ============================================================
 */
import request from './request'

/**
 * 获取客户的记忆列表
 * @param {number} customerId 客户 ID
 */
export function getMemoryList(customerId) {
  return request({
    url: '/memory',
    method: 'get',
    params: { customer_id: customerId }
  })
}

/**
 * 删除记忆
 * @param {number} id 记忆 ID
 */
export function deleteMemory(id) {
  return request({
    url: `/memory/${id}`,
    method: 'delete'
  })
}

/**
 * 手动触发记忆抽取
 * @param {number} customerId 客户 ID
 */
export function extractMemory(customerId) {
  return request({
    url: '/memory/extract',
    method: 'post',
    data: { customer_id: customerId }
  })
}
