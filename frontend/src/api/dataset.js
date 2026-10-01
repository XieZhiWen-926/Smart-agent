/**
 * ============================================================
 * 数据集接口封装 dataset.js
 * ------------------------------------------------------------
 * 数据集是用户上传的 CSV 文件，导入后可被 RAG/Text2SQL 检索。
 * 上传属于"重活"，后端丢给 Celery 异步执行，所以提供了
 * getTaskStatus() 供前端轮询任务进度。
 * 被 views/Datasets.vue 调用。
 * ============================================================
 */
import request from './request'

/**
 * 获取数据集列表
 */
export function getDatasets() {
  return request({
    url: '/datasets',
    method: 'get'
  })
}

/**
 * 上传数据集文件
 * @param {File} file - 上传的文件
 * @param {string} name - 数据集名称
 */
export function uploadDataset(file, name) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('name', name)
  return request({
    url: '/datasets/upload',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/**
 * 删除数据集
 * @param {number} id 数据集 ID
 */
export function deleteDataset(id) {
  return request({
    url: `/datasets/${id}`,
    method: 'delete'
  })
}

/**
 * 查询数据集（RAG 检索）
 * @param {object} data - { query, top_k }
 */
export function queryDataset(data) {
  return request({
    url: '/datasets/query',
    method: 'post',
    data
  })
}

/**
 * 获取任务状态
 * @param {string} taskId 任务 ID
 */
export function getTaskStatus(taskId) {
  return request({
    url: `/tasks/${taskId}`,
    method: 'get'
  })
}
