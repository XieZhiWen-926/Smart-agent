<!--
  ============================================================
  Customers.vue —— 客户管理页
  ------------------------------------------------------------
  典型的后台 CRUD 页面：搜索 + 表格 + 分页 + 新增/编辑对话框，
  是其余"管理类"页面（Tools/Datasets）的模板，看懂它再看别的会很快。
  联动：api/customer.js。
  ============================================================
-->
<template>
  <!-- 客户管理页面：表格 + 搜索 + 新增/编辑对话框 -->
  <div class="page-container">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索客户名称/电话"
        style="width: 250px"
        clearable
        @change="loadCustomers"
      />
      <el-button type="primary" :icon="Plus" @click="handleAdd">新增客户</el-button>
    </div>

    <!-- 客户表格 -->
    <el-table v-loading="loading" :data="tableData" stripe style="width: 100%">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="客户名称" min-width="120" />
      <el-table-column prop="phone" label="联系电话" width="140" />
      <el-table-column prop="email" label="邮箱" min-width="160" />
      <el-table-column prop="company" label="公司" min-width="140" />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="150" fixed="right">
        <!-- #default="{ row }" 是 Element Plus 表格的"作用域插槽"：
             表格把当前行数据 row 传给这个插槽，我们才能按行渲染按钮 -->
        <template #default="{ row }">
          <el-button size="small" @click="handleEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 16px; justify-content: flex-end; display: flex"
      @current-change="loadCustomers"
    />

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑客户' : '新增客户'"
      width="500px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入客户名称" />
        </el-form-item>
        <el-form-item label="电话" prop="phone">
          <el-input v-model="form.phone" placeholder="请输入联系电话" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="公司">
          <el-input v-model="form.company" placeholder="请输入公司名称" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCustomers, createCustomer, updateCustomer, deleteCustomer } from '@/api/customer'

// 表格数据
const tableData = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')

// 对话框
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref(null)

// 表单数据
const form = reactive({
  id: null,
  name: '',
  phone: '',
  email: '',
  company: '',
  remark: ''
})

// 表单校验规则
const rules = {
  name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }]
}

onMounted(() => {
  loadCustomers()
})

/**
 * 加载客户列表
 */
async function loadCustomers() {
  loading.value = true
  try {
    const res = await getCustomers({
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      // || undefined：搜索框为空时不传这个参数，避免后端收到空字符串
      keyword: searchKeyword.value || undefined
    })
    // 兼容后端两种返回：分页对象 { items, total } 或直接数组
    tableData.value = res.items || res || []
    total.value = res.total || tableData.value.length
  } catch (e) {
    console.error('加载客户列表失败', e)
  } finally {
    loading.value = false
  }
}

/**
 * 打开新增对话框
 */
function handleAdd() {
  isEdit.value = false
  Object.assign(form, { id: null, name: '', phone: '', email: '', company: '', remark: '' })
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
      await updateCustomer(form.id, { ...form })
      ElMessage.success('更新成功')
    } else {
      await createCustomer({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadCustomers()
  } catch (e) {
    // 错误已拦截器提示
  } finally {
    submitting.value = false
  }
}

/**
 * 删除客户
 */
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除客户「${row.name}」吗？`, '提示', { type: 'warning' })
    await deleteCustomer(row.id)
    ElMessage.success('删除成功')
    loadCustomers()
  } catch (e) {
    // 用户取消或删除失败
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
  margin-bottom: 16px;
}
</style>
