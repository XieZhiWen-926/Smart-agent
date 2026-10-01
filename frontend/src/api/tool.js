/**
 * ============================================================
 * 工具管理接口封装 tool.js
 * ------------------------------------------------------------
 * "工具"是 ReAct 智能体可以调用的能力（查地图、查天气、HTTP API 等）。
 * 这里提供工具的增删改查和在线测试。
 * 被 views/Tools.vue 调用。
 * ============================================================
 */
import request from './request'

/**
 * 获取工具列表
 */
export function getTools() {
  return request({
    url: '/tools',
    method: 'get'
  })
}

/**
 * 创建工具
 * @param {object} data - 工具信息
 */
export function createTool(data) {
  return request({
    url: '/tools',
    method: 'post',
    data
  })
}

/**
 * 更新工具
 * @param {number} id 工具 ID
 * @param {object} data 更新数据
 */
export function updateTool(id, data) {
  return request({
    url: `/tools/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除工具
 * @param {number} id 工具 ID
 */
export function deleteTool(id) {
  return request({
    url: `/tools/${id}`,
    method: 'delete'
  })
}

/**
 * 测试工具
 * @param {number} id 工具 ID
 * @param {object} params 测试参数
 */
export function testTool(id, params) {
  return request({
    url: `/tools/${id}/test`,
    method: 'post',
    data: params
  })
}
