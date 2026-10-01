<!--
  ============================================================
  ChatMessage.vue —— 单条聊天消息气泡组件
  ------------------------------------------------------------
  被 views/Chat.vue 循环渲染。两个 props：
    message  —— { role: 'user'|'assistant', content: string }
    streaming —— 是否正在流式输出中（true 且内容为空时显示"正在输入"动画）
  助手消息的内容按 Markdown 渲染（大模型回答常带列表/代码块），
  用户消息只是纯文本，也统一走同一渲染。
  ============================================================
-->
<template>
  <!-- 单条聊天消息组件：区分用户/助手，不同对齐和样式 -->
  <div class="chat-message" :class="message.role">
    <!-- 头像 -->
    <div class="avatar">
      <el-avatar :size="36" :class="message.role">
        {{ message.role === 'user' ? '我' : 'AI' }}
      </el-avatar>
    </div>

    <!-- 消息内容气泡 -->
    <div class="bubble" :class="message.role">
      <!-- 流式输出时显示打字指示器 -->
      <div v-if="streaming && message.content === ''" class="typing-indicator">
        <span></span><span></span><span></span>
      </div>
      <!-- 渲染消息内容（支持 Markdown）。
           v-html 直接把 HTML 字符串塞进 DOM：因为 marked 把 Markdown
           转成了 HTML 字符串，必须用 v-html 才能显示格式。
           （注意：v-html 有 XSS 风险，本项目内容来自自家大模型接口，
            不要把它用于渲染用户可提交的富文本） -->
      <div v-else class="message-content" v-html="renderedContent"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  // 消息对象：{ role: 'user'|'assistant', content: string }
  message: {
    type: Object,
    required: true
  },
  // 是否正在流式输出
  streaming: {
    type: Boolean,
    default: false
  }
})

// computed：计算属性，依赖的 message.content 一变就自动重算。
// 流式输出时 content 不断变长，这里会把整段 Markdown 反复重新解析，
// 所以气泡里的加粗/列表/代码块是"边打字边排版"的。
const renderedContent = computed(() => {
  if (!props.message.content) return ''
  return marked.parse(props.message.content)
})
</script>

<style scoped>
.chat-message {
  display: flex;
  margin-bottom: 16px;
  gap: 10px;
}

/* 用户消息右对齐 */
.chat-message.user {
  flex-direction: row-reverse;
}

.avatar {
  flex-shrink: 0;
}

.el-avatar.user {
  background: #409eff;
}

.el-avatar.assistant {
  background: #67c23a;
}

.bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 8px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
}

/* 用户消息气泡样式 */
.bubble.user {
  background: #409eff;
  color: #fff;
  border-top-right-radius: 2px;
}

/* 助手消息气泡样式 */
.bubble.assistant {
  background: #fff;
  color: #303133;
  border: 1px solid #e4e7ed;
  border-top-left-radius: 2px;
}

/* Markdown 内容样式微调 */
.message-content :deep(p) {
  margin: 0 0 8px 0;
}

.message-content :deep(p:last-child) {
  margin-bottom: 0;
}

.message-content :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 13px;
}

.message-content :deep(pre) {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.message-content :deep(pre code) {
  background: none;
  padding: 0;
}

/* 打字指示器动画 */
.typing-indicator {
  display: flex;
  gap: 4px;
  align-items: center;
  height: 20px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-6px);
  }
}
</style>
