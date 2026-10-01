<!--
  ============================================================
  Chat.vue —— 智能对话主页面（本项目核心页面）
  ------------------------------------------------------------
  布局：左侧边栏（客户下拉 + 会话列表）｜ 右侧（消息区 + 输入框）。

  【打字机效果是怎么来的？——三步】
    1. 点发送：先往消息列表 push 一条"空内容"的助手消息占位
       （chatStore.addAssistantMessage()），此时气泡显示"正在输入"动画；
    2. 调 api/chat.js 的 streamChat()，后端大模型每生成一小段文字，
       就通过 SSE 推一帧过来，触发 onChunk 回调；
    3. onChunk 里 chatStore.updateAssistantMessage() 把这小段文字
       += 到那条占位消息的 content 上。因为 messages 是响应式的，
       ChatMessage 组件立刻重新渲染，用户就看到文字一段段"长"出来。
    4. 收到 [DONE] → isStreaming 置 false，输入框恢复可用。

  联动：stores/chat.js（消息状态）、api/chat.js（SSE 流式接口）、
        components/ChatMessage.vue（单条消息气泡）、api/customer.js（客户下拉）。
  ============================================================
-->
<template>
  <!-- 聊天主页面：左侧客户/会话列表 + 中间消息区 + 底部输入框 -->
  <div class="chat-page">
    <!-- 左侧边栏：客户选择 + 会话列表 -->
    <div class="chat-sidebar">
      <!-- 客户选择下拉 -->
      <div class="sidebar-section">
        <div class="section-title">选择客户</div>
        <el-select
          v-model="selectedCustomerId"
          placeholder="请选择客户"
          filterable
          style="width: 100%"
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

      <!-- 会话列表 -->
      <div class="sidebar-section">
        <div class="section-header">
          <span class="section-title">会话列表</span>
          <el-button
            type="primary"
            size="small"
            :icon="Plus"
            :disabled="!selectedCustomerId || chatStore.isStreaming"
            @click="handleNewConversation"
          >新建</el-button>
        </div>

        <div v-loading="convLoading" class="conv-list">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="conv-item"
            :class="{ active: conv.id === chatStore.currentConversationId }"
            @click="handleSelectConversation(conv.id)"
          >
            <div class="conv-title">{{ conv.title || `会话 ${conv.id}` }}</div>
            <el-icon class="conv-delete" @click.stop="handleDeleteConversation(conv.id)">
              <Delete />
            </el-icon>
          </div>
          <!-- 空状态 -->
          <div v-if="!convLoading && conversations.length === 0" class="empty-tip">
            暂无会话，请新建
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧聊天主区域 -->
    <div class="chat-main">
      <!-- 消息展示区 -->
      <div ref="messageAreaRef" class="message-area">
        <!-- 未选择客户提示 -->
        <div v-if="!selectedCustomerId" class="chat-empty">
          <el-empty description="请先选择一个客户开始对话" />
        </div>

        <!-- 消息列表 -->
        <template v-else>
          <!-- 每条消息渲染一个 ChatMessage 气泡；
               streaming=true 的只有"流式输出中的最后一条助手消息"，
               它内容为空时会显示三个点的"正在输入"动画 -->
          <ChatMessage
            v-for="(msg, idx) in chatStore.messages"
            :key="idx"
            :message="msg"
            :streaming="chatStore.isStreaming && idx === chatStore.messages.length - 1 && msg.role === 'assistant'"
          />
        </template>
      </div>

      <!-- 底部输入区 -->
      <div class="chat-input-area">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="输入您的问题，按 Enter 发送，Shift+Enter 换行"
          :disabled="chatStore.isStreaming || !selectedCustomerId"
          @keydown.enter.exact.prevent="handleSend"
          resize="none"
        />
        <el-button
          type="primary"
          class="send-btn"
          :loading="chatStore.isStreaming"
          :disabled="!inputText.trim() || !selectedCustomerId"
          @click="handleSend"
        >
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { getCustomers } from '@/api/customer'
import { asList } from '@/api/response'
import {
  getConversations,
  createConversation,
  getMessages,
  deleteConversation,
  streamChat
} from '@/api/chat'
import ChatMessage from '@/components/ChatMessage.vue'

const chatStore = useChatStore()

// 客户列表
const customers = ref([])
const selectedCustomerId = ref(null)

// 会话列表
const conversations = ref([])
const convLoading = ref(false)

// 输入框文本
const inputText = ref('')

// 消息区域 DOM 引用（用于自动滚动）。
// ref(null) 配合模板里的 ref="messageAreaRef"，挂载后这里就拿到真实 DOM
const messageAreaRef = ref(null)

/**
 * 页面加载时获取客户列表
 * onMounted：组件挂载完成后执行一次的生命周期钩子
 */
onMounted(async () => {
  await loadCustomers()
})

/**
 * 加载客户列表
 */
async function loadCustomers() {
  try {
    const res = await getCustomers({ skip: 0, limit: 100 })
    customers.value = asList(res)
  } catch (e) {
    console.error('加载客户列表失败', e)
  }
}

/**
 * 客户切换：加载该客户的会话列表
 */
async function handleCustomerChange(customerId) {
  chatStore.setCurrentCustomer(customerId)
  await loadConversations()
}

/**
 * 加载会话列表
 */
async function loadConversations() {
  if (!selectedCustomerId.value) return
  convLoading.value = true
  try {
    const res = await getConversations(selectedCustomerId.value)
    conversations.value = asList(res)
  } catch (e) {
    console.error('加载会话列表失败', e)
  } finally {
    convLoading.value = false
  }
}

/**
 * 新建会话
 */
async function handleNewConversation() {
  try {
    const res = await createConversation(selectedCustomerId.value)
    conversations.value.unshift(res)
    chatStore.setCurrentConversation(res.id)
    chatStore.messages = []
    ElMessage.success('新会话已创建')
  } catch (e) {
    // 错误已拦截器提示
  }
}

/**
 * 选择会话：加载历史消息
 */
async function handleSelectConversation(convId) {
  if (chatStore.isStreaming) return
  chatStore.setCurrentConversation(convId)
  try {
    const res = await getMessages(convId)
    const msgs = res.items || res || []
    // 转换为统一格式
    chatStore.messages = msgs.map(m => ({
      role: m.role,
      content: m.content
    }))
    await scrollToBottom()
  } catch (e) {
    console.error('加载消息失败', e)
  }
}

/**
 * 删除会话
 */
async function handleDeleteConversation(convId) {
  try {
    await ElMessageBox.confirm('确定删除该会话吗？', '提示', { type: 'warning' })
    await deleteConversation(convId)
    conversations.value = conversations.value.filter(c => c.id !== convId)
    // 如果删除的是当前会话，清空消息
    if (chatStore.currentConversationId === convId) {
      chatStore.currentConversationId = null
      chatStore.messages = []
    }
    ElMessage.success('会话已删除')
  } catch (e) {
    // 用户取消或删除失败
  }
}

/**
 * 发送消息
 */
async function handleSend() {
  const text = inputText.value.trim()
  if (!text || chatStore.isStreaming) return

  // 如果还没有会话，先创建一个
  if (!chatStore.currentConversationId) {
    try {
      const conv = await createConversation(selectedCustomerId.value)
      chatStore.setCurrentConversation(conv.id)
      conversations.value.unshift(conv)
    } catch (e) {
      return
    }
  }

  // 添加用户消息到列表
  chatStore.addUserMessage(text)
  inputText.value = ''

  // 添加空的助手消息占位（流式输出时逐段填充这个气泡），
  // 并记住它的下标，后面每来一段 SSE 数据就往这条消息里追加
  const assistantIndex = chatStore.addAssistantMessage()
  chatStore.isStreaming = true

  await scrollToBottom()

  // 调用 SSE 流式接口（实现细节见 api/chat.js 的 streamChat 注释）
  await streamChat(
    {
      conversation_id: chatStore.currentConversationId,
      customer_id: selectedCustomerId.value,
      query: text
    },
    // onChunk: 每收到一段内容，追加到占位消息里 —— 打字机效果的来源
    (chunk) => {
      chatStore.updateAssistantMessage(assistantIndex, chunk)
      scrollToBottom()
    },
    // onDone: 流结束
    () => {
      chatStore.isStreaming = false
      scrollToBottom()
    },
    // onError: 出错
    (err) => {
      chatStore.isStreaming = false
      // 把后端给出的真实原因显示在气泡里（例如"账户欠费"），
      // 而不是只写"请求失败"——否则用户根本不知道该怎么解决
      const reason = (err && err.message) ? err.message : '未知错误'
      chatStore.updateAssistantMessage(assistantIndex, `⚠️ ${reason}`)
      ElMessage.error('聊天请求失败，详见回复内容')
      scrollToBottom()
    }
  )
}

/**
 * 自动滚动到底部
 * nextTick()：等 Vue 把最新数据真正渲染到 DOM 之后再操作 DOM，
 * 否则此刻 scrollHeight 还是更新前的旧值，滚动会"差一截"
 */
async function scrollToBottom() {
  await nextTick()
  if (messageAreaRef.value) {
    messageAreaRef.value.scrollTop = messageAreaRef.value.scrollHeight
  }
}

// watch：侦听消息条数变化（新增消息时）自动滚到底部。
// 注意只侦听 length 就够——流式追加由 onChunk 里直接调 scrollToBottom
watch(() => chatStore.messages.length, () => {
  scrollToBottom()
})
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 60px);
}

/* 左侧边栏 */
.chat-sidebar {
  width: 260px;
  background: #fff;
  border-right: 1px solid #e6e6e6;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-section {
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.section-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.section-header .section-title {
  margin-bottom: 0;
}

.conv-list {
  max-height: 300px;
  overflow-y: auto;
}

.conv-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 4px;
  font-size: 13px;
  color: #606266;
}

.conv-item:hover {
  background: #f5f7fa;
}

.conv-item.active {
  background: #ecf5ff;
  color: #409eff;
}

.conv-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.conv-delete {
  opacity: 0;
  transition: opacity 0.2s;
  color: #f56c6c;
}

.conv-item:hover .conv-delete {
  opacity: 1;
}

.empty-tip {
  text-align: center;
  color: #c0c4cc;
  font-size: 13px;
  padding: 20px 0;
}

/* 右侧主区域 */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.message-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f5f7fa;
}

.chat-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

/* 底部输入区 */
.chat-input-area {
  display: flex;
  gap: 10px;
  padding: 12px 20px;
  background: #fff;
  border-top: 1px solid #e6e6e6;
  align-items: flex-end;
}

.send-btn {
  flex-shrink: 0;
  height: 40px;
}
</style>
