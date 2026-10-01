<!--
  ============================================================
  Datasets.vue —— 数据集管理页
  ------------------------------------------------------------
  左侧：上传 CSV + 数据集列表；右侧：RAG 检索效果测试。
  上传后后端用 Celery 异步解析入库，列表的"状态"列会变：
  处理中 → 已就绪/失败（如需看进度可轮询 api/dataset.js 的 getTaskStatus）。
  联动：api/dataset.js。
  ============================================================
-->
<template>
  <!-- 数据集管理页面：上传 + 列表 + 查询测试 -->
  <div class="page-container">
    <el-row :gutter="20">
      <!-- 左侧：上传区域 + 数据集列表 -->
      <el-col :span="14">
        <!-- 上传区域 -->
        <el-card shadow="never" class="upload-card">
          <template #header>上传数据集</template>
          <!-- el-upload 组件内部自己发请求（不走 axios 实例），
               所以请求地址 uploadUrl 要带完整 /api 前缀、请求头要手动
               塞 token；:data 是随文件一起提交的额外表单字段 -->
          <el-upload
            drag
            :action="uploadUrl"
            :headers="uploadHeaders"
            :data="uploadExtra"
            :show-file-list="false"
            :on-success="handleUploadSuccess"
            :on-error="handleUploadError"
            :before-upload="beforeUpload"
            name="file"
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">
              拖拽文件到此处，或<em>点击上传</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                仅支持 CSV 格式文件
              </div>
            </template>
          </el-upload>
        </el-card>

        <!-- 数据集列表 -->
        <el-card shadow="never" class="list-card">
          <template #header>
            <div class="card-header">
              <span>数据集列表</span>
              <el-button size="small" @click="loadDatasets">刷新</el-button>
            </div>
          </template>
          <el-table v-loading="loading" :data="tableData" stripe>
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="name" label="名称" min-width="120" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">
                  {{ statusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="row_count" label="行数" width="80" />
            <el-table-column prop="col_count" label="列数" width="80" />
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 右侧：查询测试 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>问题查询（RAG 检索测试）</template>
          <el-input
            v-model="queryText"
            type="textarea"
            :rows="3"
            placeholder="输入问题测试知识库检索效果"
          />
          <el-button
            type="primary"
            style="margin-top: 12px"
            :loading="querying"
            @click="handleQuery"
          >
            查询
          </el-button>

          <!-- 查询结果 -->
          <div v-if="queryResult" class="query-result">
            <div class="result-title">检索结果：</div>
            <div v-if="queryResult.length === 0" class="empty-result">未检索到相关内容</div>
            <div v-for="(item, idx) in queryResult" :key="idx" class="result-item">
              <div class="result-score">相似度: {{ (item.score * 100).toFixed(1) }}%</div>
              <div class="result-content">{{ item.content }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getDatasets, deleteDataset, queryDataset } from '@/api/dataset'

// 数据集列表
const tableData = ref([])
const loading = ref(false)

// 查询相关
const queryText = ref('')
const querying = ref(false)
const queryResult = ref(null)

// 上传地址和请求头
const uploadUrl = '/api/datasets/upload'
const uploadHeaders = ref({})
// 随文件一起提交的额外表单字段。
// 【bug修复】后端 /api/datasets/upload 要求 Form 里必须带 name（数据集名称），
// 原来只传了 file，后端会返回 422 导致上传永远失败；
// 这里在 before-upload 里用文件名（去扩展名）自动填上。
const uploadExtra = ref({ name: '' })

onMounted(() => {
  // 设置上传请求头中的 Authorization
  const token = localStorage.getItem('token')
  if (token) {
    uploadHeaders.value = { Authorization: `Bearer ${token}` }
  }
  loadDatasets()
})

/**
 * 加载数据集列表
 */
async function loadDatasets() {
  loading.value = true
  try {
    const res = await getDatasets()
    tableData.value = res.items || res || []
  } catch (e) {
    console.error('加载数据集列表失败', e)
  } finally {
    loading.value = false
  }
}

/**
 * 上传前校验（返回 false 会阻止上传）
 */
function beforeUpload(file) {
  // 【bug修复】后端目前只认 .csv，原来前端却放行 xlsx/txt/json，
  // 用户传了这些文件会被后端 400 拒绝，前后端口径不一致；统一为仅 CSV。
  const allowedTypes = ['.csv']
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
  if (!allowedTypes.includes(ext)) {
    ElMessage.error('仅支持 CSV 文件')
    return false
  }
  // 用文件名（去掉扩展名）作为数据集名称，随文件一起提交
  uploadExtra.value = { name: file.name.replace(/\.[^.]+$/, '') }
  return true
}

/**
 * 上传成功回调
 */
function handleUploadSuccess(res) {
  ElMessage.success('上传成功，正在处理数据')
  loadDatasets()
}

/**
 * 上传失败回调
 */
function handleUploadError(err) {
  ElMessage.error('上传失败：' + (err.message || '未知错误'))
}

/**
 * 删除数据集
 */
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除数据集「${row.name}」吗？`, '提示', { type: 'warning' })
    await deleteDataset(row.id)
    ElMessage.success('删除成功')
    loadDatasets()
  } catch (e) {
    // 用户取消或删除失败
  }
}

/**
 * 执行查询
 */
async function handleQuery() {
  const q = queryText.value.trim()
  if (!q) {
    ElMessage.warning('请输入查询内容')
    return
  }
  querying.value = true
  queryResult.value = null
  try {
    const res = await queryDataset({ query: q, top_k: 5 })
    queryResult.value = res.results || res || []
  } catch (e) {
    queryResult.value = []
  } finally {
    querying.value = false
  }
}

/**
 * 状态标签类型
 * 【bug修复】后端实际状态是 pending/processing/completed/failed（见 sql/init.sql），
 * 原来按 ready 映射导致 completed 显示成英文原文；这里按后端口径补齐。
 */
function statusTagType(status) {
  const map = { completed: 'success', ready: 'success', processing: 'warning', pending: 'info', failed: 'danger' }
  return map[status] || 'info'
}

/**
 * 状态中文文本
 */
function statusText(status) {
  const map = { completed: '已就绪', ready: '已就绪', processing: '处理中', pending: '排队中', failed: '失败' }
  return map[status] || status
}
</script>

<style scoped>
.page-container {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.upload-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.query-result {
  margin-top: 16px;
}

.result-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
  color: #303133;
}

.empty-result {
  color: #909399;
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

.result-item {
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 8px;
}

.result-score {
  font-size: 12px;
  color: #409eff;
  margin-bottom: 4px;
}

.result-content {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
</style>
