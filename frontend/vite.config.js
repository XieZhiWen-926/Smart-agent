/**
 * ============================================================
 * Vite 构建/开发服务器配置
 * ------------------------------------------------------------
 * Vite 是本项目的"开发服务器 + 打包工具"：
 *   - npm run dev    启动开发服务器（本文件 server 部分生效）；
 *   - npm run build  打包出 dist/ 静态文件，交给 Nginx 托管（见 Dockerfile）。
 *
 * 关键点：开发时前端跑在 5173 端口，后端在 8000 端口，直接请求会
 * 跨域。proxy 的作用是让浏览器"以为"自己在请求 5173，实际上 Vite
 * 在后台把 /api 开头的请求转发给 8000 的 FastAPI，从而绕开跨域。
 * 生产环境不存在这个问题——前后端都由 Nginx 网关统一从 80 端口出。
 * ============================================================
 */
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()], // 让 Vite 能解析 .vue 单文件组件
  resolve: {
    alias: {
      // 路径别名：代码里写 '@/api/chat' 等价于 'src/api/chat'
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    proxy: {
      // 将 /api 开头的请求代理到后端服务（仅开发环境生效）
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true // 把 Host 头改成目标地址，避免后端校验失败
      }
    }
  }
})
