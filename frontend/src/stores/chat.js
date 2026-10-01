/**
 * ============================================================
 * 聊天状态管理 stores/chat.js（Pinia store）
 * ------------------------------------------------------------
 * 【小白须知 · Pinia 是什么】
 * Pinia 是 Vue3 官方的全局状态管理库。可以把它理解为一个
 * "全局共享的数据仓库"：任何组件都能读写同一份数据，一处改了，
 * 所有用到的地方自动更新。比如这里的 messages 消息列表，
 * Chat.vue 往里追加内容，聊天气泡就立刻刷新。
 *
 * 本 store 管四样东西：当前客户、当前会话、消息列表、是否正在流式输出。
 * 主要使用者：views/Chat.vue。
 *
 * 写法说明：这是 setup 风格的 store——用 ref() 定义的就是"状态"，
 * 定义的 function 就是"动作（action）"，最后 return 出去才能被外部用。
 * ============================================================
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

// 聊天状态管理：当前会话、消息列表、发送状态
export const useChatStore = defineStore('chat', () => {
  // ref() 把普通值包成"响应式数据"，值变了页面自动跟着变；
  // JS 里读写要加 .value，模板里直接用
  const currentCustomerId = ref(null)
  // 当前会话 ID
  const currentConversationId = ref(null)
  // 消息列表：[{ role: 'user'|'assistant', content: '...' }]
  const messages = ref([])
  // 是否正在发送/接收流式响应
  const isStreaming = ref(false)

  /**
   * 设置当前客户
   */
  function setCurrentCustomer(customerId) {
    currentCustomerId.value = customerId
    // 切换客户时清空消息和会话
    currentConversationId.value = null
    messages.value = []
  }

  /**
   * 设置当前会话
   */
  function setCurrentConversation(conversationId) {
    currentConversationId.value = conversationId
  }

  /**
   * 追加用户消息
   */
  function addUserMessage(content) {
    messages.value.push({ role: 'user', content })
  }

  /**
   * 添加一条空的助手消息（流式输出时逐步填充）
   * @returns {number} 新消息的索引
   */
  function addAssistantMessage() {
    messages.value.push({ role: 'assistant', content: '' })
    return messages.value.length - 1
  }

  /**
   * 更新指定索引的助手消息内容（流式追加）
   * SSE 每来一小段就 += 一次，页面气泡实时变长 → 打字机效果
   */
  function updateAssistantMessage(index, chunk) {
    if (messages.value[index]) {
      messages.value[index].content += chunk
    }
  }

  /**
   * 重置聊天状态
   */
  function reset() {
    currentCustomerId.value = null
    currentConversationId.value = null
    messages.value = []
    isStreaming.value = false
  }

  return {
    currentCustomerId,
    currentConversationId,
    messages,
    isStreaming,
    setCurrentCustomer,
    setCurrentConversation,
    addUserMessage,
    addAssistantMessage,
    updateAssistantMessage,
    reset
  }
})
