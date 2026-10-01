/**
 * ============================================================
 * 客户管理接口封装 customer.js
 * ------------------------------------------------------------
 * 客户信息的增删改查（CRUD），被 views/Customers.vue（客户管理页）
 * 和 views/Chat.vue、views/Memory.vue（客户下拉选择）调用。
 * ============================================================
 */
import request from './request'

/**
 * 获取客户列表
 * @param {object} params - { skip, limit, keyword } 分页偏移/条数/搜索词
 */
export function getCustomers(params) {
  return request({
    url: '/customers',
    method: 'get',
    params
  })
}

/**
 * 创建客户
 * @param {object} data - 客户信息
 */
export function createCustomer(data) {
  return request({
    url: '/customers',
    method: 'post',
    data
  })
}

/**
 * 获取单个客户详情
 * @param {number} id 客户 ID
 */
export function getCustomer(id) {
  return request({
    url: `/customers/${id}`,
    method: 'get'
  })
}

/**
 * 更新客户信息
 * @param {number} id 客户 ID
 * @param {object} data 更新数据
 */
export function updateCustomer(id, data) {
  return request({
    url: `/customers/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除客户
 * @param {number} id 客户 ID
 */
export function deleteCustomer(id) {
  return request({
    url: `/customers/${id}`,
    method: 'delete'
  })
}
