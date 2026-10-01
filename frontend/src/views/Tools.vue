<!--
  ============================================================
  Tools.vue —— 工具管理页
  ------------------------------------------------------------
  管理 ReAct 智能体可调用的工具（地图、HTTP API 等），比 Customers
  页多了"在线测试"对话框；JSON 字段用 JsonEditor 组件编辑。
  联动：api/tool.js、components/JsonEditor.vue。
  ============================================================
-->
<template>
  <!-- 工具管理页面：表格 + 新增/编辑对话框 + 测试功能 -->
  <div class="page-container">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <span class="toolbar-title">工具列表</span>
      <el-button type="primary" :icon="Plus" @click="handleAdd">新增工具</el-button>
    </div>

    <!-- 工具表格 -->
    <el-table v-loading="loading" :data="tableData" stripe style="width: 100%">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="工具名称" min-width="140" />
      <el-table-column prop="tool_type" label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small">{{ row.tool_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="handleTest(row)">测试</el-button>
          <el-button size="small" @click="handleEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑工具' : '新增工具'"
      width="600px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="工具名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入工具名称" />
        </el-form-item>
        <el-form-item label="工具类型" prop="tool_type">
          <el-select v-model="form.tool_type" placeholder="请选择类型" style="width: 100%">
            <el-option label="HTTP API" value="http_api" />
            <el-option label="数据库查询" value="database" />
            <el-option label="代码执行" value="code_execution" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="工具功能描述" />
        </el-form-item>
        <el-form-item label="参数 Schema">
          <JsonEditor v-model="form.parameters_schema" placeholder='{"type":"object","properties":{}}' :rows="5" />
        </el-form-item>
        <el-form-item label="配置">
          <JsonEditor v-model="form.config" placeholder='{"url":"...","method":"GET"}' :rows="5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 测试工具对话框 -->
    <el-dialog v-model="testDialogVisible" title="测试工具" width="500px">
      <div class="test-tool-name">工具：{{ currentTestTool?.name }}</div>
      <el-form label-width="80px">
        <el-form-item label="测试参数">
          <JsonEditor v-model="testParams" placeholder='{"key": "value"}' :rows="6" />
        </el-form-item>
      </el-form>
      <!-- 测试结果 -->
      <div v-if="testResult" class="test-result">
        <div class="result-title">测试结果：</div>
        <pre>{{ testResult }}</pre>
      </div>
      <template #footer>
        <el-button @click="testDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="testing" @click="handleRunTest">执行测试</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTools, createTool, updateTool, deleteTool, testTool } from '@/api/tool'
import JsonEditor from '@/components/JsonEditor.vue'

// 表格数据
const tableData = ref([])
const loading = ref(false)

// 对话框
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref(null)

// 表单数据
const form = reactive({
  id: null,
  name: '',
  tool_type: '',
  description: '',
  parameters_schema: {},
  config: {}
})

// 表单校验
const rules = {
  name: [{ required: true, message: '请输入工具名称', trigger: 'blur' }],
  tool_type: [{ required: true, message: '请选择工具类型', trigger: 'change' }]
}

// 测试对话框
const testDialogVisible = ref(false)
const currentTestTool = ref(null)
const testParams = ref({})
const testResult = ref('')
const testing = ref(false)

onMounted(() => {
  loadTools()
})

/**
 * 加载工具列表
 */
async function loadTools() {
  loading.value = true
  try {
    const res = await getTools()
    tableData.value = res.items || res || []
  } catch (e) {
    console.error('加载工具列表失败', e)
  } finally {
    loading.value = false
  }
}

/**
 * 打开新增对话框
 */
function handleAdd() {
  isEdit.value = false
  Object.assign(form, {
    id: null,
    name: '',
    tool_type: '',
    description: '',
    parameters_schema: {},
    config: {}
  })
  dialogVisible.value = true
}

/**
 * 打开编辑对话框
 */
function handleEdit(row) {
  isEdit.value = true
  Object.assign(form, row)
  dialogVisible.value = true
}

/**
 * 提交表单
 */
async function handleSubmit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    if (isEdit.value) {
      await updateTool(form.id, { ...form })
      ElMessage.success('更新成功')
    } else {
      await createTool({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadTools()
  } catch (e) {
    // 错误已拦截器提示
  } finally {
    submitting.value = false
  }
}

/**
 * 删除工具
 */
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除工具「${row.name}」吗？`, '提示', { type: 'warning' })
    await deleteTool(row.id)
    ElMessage.success('删除成功')
    loadTools()
  } catch (e) {
    // 用户取消或删除失败
  }
}

/**
 * 打开测试对话框
 */
function handleTest(row) {
  currentTestTool.value = row
  testParams.value = {}
  testResult.value = ''
  testDialogVisible.value = true
}

/**
 * 执行测试
 */
async function handleRunTest() {
  testing.value = true
  testResult.value = ''
  try {
    const res = await testTool(currentTestTool.value.id, testParams.value)
    testResult.value = JSON.stringify(res, null, 2)
    ElMessage.success('测试完成')
  } catch (e) {
    testResult.value = `测试失败: ${e.message || '未知错误'}`
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.page-container {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-title {
  font-size: 16px;
  font-weight: 600;
}

.test-tool-name {
  margin-bottom: 16px;
  font-size: 14px;
  color: #606266;
}

.test-result {
  margin-top: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.result-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.test-result pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  max-height: 300px;
  overflow-y: auto;
}
</style>
