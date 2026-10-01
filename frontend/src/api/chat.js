/**
 * ============================================================
 * 聊天接口封装 chat.js（含本项目亮点：SSE 流式聊天）
 * ------------------------------------------------------------
 * 前半部分是普通的会话/消息 CRUD（走 axios request 实例）；
 * 最后的 streamChat() 是"打字机效果"的来源，被 views/Chat.vue 调用。
 *
 * 【SSE 流式渲染全景（配合 Chat.vue 一起读）】
 *   1. Chat.vue 调 streamChat() 并传三个回调：onChunk/onDone/onError；
 *   2. 本函数用 fetch 发起 POST，拿到 response.body 这个"可读流"，
 *      后端大模型每生成一小段文字就推一帧 SSE 数据过来；
 *   3. 每解析出一帧 { content: "..." } 就调一次 onChunk，
 *      Chat.vue 把这段文字追加到最后一条助手消息末尾；
 *   4. Vue 的响应式系统自动让页面上的气泡"长"出这段文字
 *      ——用户看到的就是一个字一个字蹦出来的打字机效果；
 *   5. 后端推 data: [DONE] 表示说完，调 onDone 收尾。
 * ============================================================
 */
import request from './request'

/**
 * 获取会话列表
 * @param {number} customerId 客户 ID
 */
export function getConversations(customerId) {
  return request({
    url: '/chat/conversations',
    method: 'get',
    params: { customer_id: customerId }
  })
}

/**
 * 创建新会话
 * @param {number} customerId 客户 ID
 */
export function createConversation(customerId) {
  return request({
    url: '/chat/conversations',
    method: 'post',
    data: { customer_id: customerId }
  })
}

/**
 * 获取会话历史消息
 * @param {number} conversationId 会话 ID
 */
export function getMessages(conversationId) {
  return request({
    url: `/chat/conversations/${conversationId}/messages`,
    method: 'get'
  })
}

/**
 * 删除会话
 * @param {number} conversationId 会话 ID
 */
export function deleteConversation(conversationId) {
  return request({
    url: `/chat/conversations/${conversationId}`,
    method: 'delete'
  })
}

/**
 * 流式聊天（SSE）
 *
 * 【重要说明】
 * 为什么不用 EventSource？
 * EventSource 是浏览器原生 SSE API，但它不支持自定义请求头，
 * 无法携带 Authorization: Bearer <token> 认证信息。
 * 因此使用原生 fetch + ReadableStream 手动解析 SSE 流。
 *
 * SSE 协议格式：
 *   data: {"content":"你好"}
 *   data: {"content":"，我是助手"}
 *   data: [DONE]
 *
 * @param {object} params - { conversation_id, customer_id, query }
 * @param {function} onChunk - 每收到一段内容的回调 (chunkText: string)
 * @param {function} onDone - 流结束回调
 * @param {function} onError - 错误回调
 */
export async function streamChat(params, onChunk, onDone, onError) {
  const token = localStorage.getItem('token')

  try {
    // 注意：这里故意不用上面的 axios 实例——axios 会等整个响应下载完
    // 才返回，拿不到"边下边读"的流。原生 fetch 的 response.body 是一个
    // ReadableStream（可读流），可以数据到多少读多少。
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(params)
    })

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    // 从响应体上取一个"读取器"，之后每 await 一次 read() 就能拿到
    // 网络新到的一小段二进制数据（Uint8Array）
    const reader = response.body.getReader()
    // 文本解码器：把二进制转成字符串。{ stream: true } 很关键——
    // 一个中文字符的字节可能被拆到两批数据里，流式解码能正确拼接
    const decoder = new TextDecoder('utf-8')
    let buffer = '' // 缓冲区：网络分包不保证按 SSE 事件边界切，先攒着

    // 循环读取，直到后端关闭连接（done=true）
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      // 将二进制数据解码为文本，追加到缓冲区
      buffer += decoder.decode(value, { stream: true })

      // SSE 协议规定：事件之间用空行（\n\n）分隔，所以按 \n\n 切开
      const events = buffer.split('\n\n')
      // 最后一段可能只是个"半拉子"事件（剩下的字节下一批才到），
      // 先弹出来留在缓冲区，等下一批数据补上再处理
      buffer = events.pop() || ''

      for (const event of events) {
        if (!event.trim()) continue

        // 一个事件可能有多行（data:/event:/id: 等），本项目只用 data: 行
        const lines = event.split('\n')
        for (const line of lines) {
          if (!line.startsWith('data:')) continue

          const data = line.slice(5).trim() // 去掉开头的 "data:" 前缀

          // 约定的结束标记：后端发 data: [DONE] 表示本次回答完毕
          if (data === '[DONE]') {
            onDone && onDone()
            return
          }

          try {
            // 每帧 data 是一个 JSON，正常帧是 {"content":"你好"}；
            // 后端出错时会推 {"error":"..."}（见 backend/app/api/chat.py）。
            // 【注意】这里必须显式处理 error，否则错误会被静默丢弃，
            // 页面表现就是"AI 气泡一直空白、毫无反应"，极难排查。
            const parsed = JSON.parse(data)
            if (parsed.error) {
              onError && onError(new Error(parsed.error))
              return
            }
            if (parsed.content) {
              onChunk && onChunk(parsed.content)
            }
          } catch (e) {
            console.warn('SSE 数据解析失败:', data, e)
          }
        }
      }
    }

    // 连接自然关闭（没收到 [DONE] 也兜底调一次 onDone）
    onDone && onDone()
  } catch (err) {
    console.error('SSE 流式请求错误:', err)
    onError && onError(err)
  }
}
