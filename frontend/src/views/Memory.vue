<!--
  ============================================================
  Memory.vue —— 长期记忆管理页
  ------------------------------------------------------------
  查看某客户被系统记住的偏好/事实（如"养宠物"），支持删除和
  手动触发一次记忆抽取（后端从历史对话里重新提炼，异步执行，
  所以点击后延迟 2 秒再刷新列表）。
  联动：api/memory.js、api/customer.js（客户下拉）。
  ============================================================
-->
<template>
  <!-- 记忆管理页面：选择客户 → 展示长期记忆列表 -->
  <div class="page-container">
    <!-- 顶部：客户选择 + 操作按钮 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <span class="label">选择客户：</span>
        <el-select
          v-model="selectedCustomerId"
          placeholder="请选择客户"
          filterable
          style="width: 250px"
          @change="handleCustomerChange"
        >
          <el-option
            v-for="c in customers"
            :key="c.id"
            :label="c.name"
            :value="c.id"
          />
        </el-select>
      </div>
      <el-button
        type="primary"
        :disabled="!selectedCustomerId || extracting"
        :loading="extracting"
        @click="handleExtract"
      >
        手动抽取记忆
      </el-button>
    </div>

    <!-- 记忆列表 -->
    <div v-loading="loading" class="memory-list">
      <el-empty v-if="!selectedCustomerId" description="请先选择客户查看记忆" />

      <template v-else-if="memoryList.length > 0">
        <el-card
          v-for="item in memoryList"
          :key="item.id"
          shadow="hover"
          class="memory-card"
        >
          <div class="memory-header">
            <el-tag :type="memoryTypeTag(item.memory_type)" size="small">
              {{ memoryTypeText(item.memory_type) }}
            </el-tag>
            <span class="memory-importance">
              <!-- 【bug修复】后端 importance 取值是 1~10，原来直接
                   '☆'.repeat(5 - importance)，当 importance > 5 时
                   repeat(负数) 会抛 RangeError 导致整页白屏；
                   starsText() 里先把分数收敛到 1~5 再生成星级。 -->
              重要性: {{ starsText(item.importance) }}
            </span>
            <el-button
              type="danger"
              size="small"
              text
              @click="handleDelete(item)"
            >
              删除
            </el-button>
          </div>
          <div class="memory-content">{{ item.content }}</div>
          <div class="memory-meta">
            <!-- 【bug修复】后端返回的字段名是 use_count（见数据库表
                 long_term_memories 与后端 schema），原来写的 usage_count
                 永远取不到值；用 ?? 做兼容兜底，两个名字都能显示。 -->
            使用次数: {{ item.use_count ?? item.usage_count ?? 0 }} 次
            <span v-if="item.created_at"> · {{ item.created_at }}</span>
          </div>
        </el-card>
      </template>

      <el-empty v-else description="该客户暂无记忆数据" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCustomers } from '@/api/customer'
import { getMemoryList, deleteMemory, extractMemory } from '@/api/memory'

// 客户列表
const customers = ref([])
const selectedCustomerId = ref(null)

// 记忆列表
const memoryList = ref([])
const loading = ref(false)
const extracting = ref(false)

onMounted(() => {
  loadCustomers()
})

/**
 * 加载客户列表
 */
async function loadCustomers() {
  try {
    const res = await getCustomers({ skip: 0, limit: 100 })
    customers.value = res.items || res || []
  } catch (e) {
    console.error('加载客户列表失败', e)
  }
}

/**
 * 客户切换：加载记忆列表
 */
async function handleCustomerChange(customerId) {
  await loadMemoryList()
}

/**
 * 加载记忆列表
 */
async function loadMemoryList() {
  if (!selectedCustomerId.value) return
  loading.value = true
  try {
    const res = await getMemoryList(selectedCustomerId.value)
    memoryList.value = res.items || res || []
  } catch (e) {
    console.error('加载记忆列表失败', e)
    memoryList.value = []
  } finally {
    loading.value = false
  }
}

/**
 * 删除记忆
 */
async function handleDelete(item) {
  try {
    await ElMessageBox.confirm('确定删除这条记忆吗？', '提示', { type: 'warning' })
    await deleteMemory(item.id)
    ElMessage.success('删除成功')
    loadMemoryList()
  } catch (e) {
    // 用户取消或删除失败
  }
}

/**
 * 手动触发记忆抽取
 */
async function handleExtract() {
  extracting.value = true
  try {
    await extractMemory(selectedCustomerId.value)
    ElMessage.success('记忆抽取任务已触发')
    // 延迟刷新列表
    setTimeout(() => loadMemoryList(), 2000)
  } catch (e) {
    // 错误已拦截器提示
  } finally {
    extracting.value = false
  }
}

/**
 * 生成星级文本：把后端的 1~10 重要性收敛到 1~5 颗星
 * （Math.ceil(10/2)=5 星，并保证星+空星总数恒为 5，不会出现负数）
 */
function starsText(importance) {
  const stars = Math.min(5, Math.max(1, Math.ceil((importance || 1) / 2)))
  return '★'.repeat(stars) + '☆'.repeat(5 - stars)
}

/**
 * 记忆类型标签颜色
 */
function memoryTypeTag(type) {
  const map = {
    preference: 'primary',
    fact: 'success',
    history: 'warning',
    profile: 'danger'
  }
  return map[type] || 'info'
}

/**
 * 记忆类型中文文本
 */
function memoryTypeText(type) {
  const map = {
    preference: '偏好',
    fact: '事实',
    history: '历史',
    profile: '画像'
  }
  return map[type] || type
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
  margin-bottom: 20px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.label {
  font-size: 14px;
  color: #606266;
}

.memory-list {
  min-height: 300px;
}

.memory-card {
  margin-bottom: 12px;
}

.memory-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.memory-importance {
  font-size: 13px;
  color: #e6a23c;
}

.memory-content {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 8px;
}

.memory-meta {
  font-size: 12px;
  color: #909399;
}
</style>
