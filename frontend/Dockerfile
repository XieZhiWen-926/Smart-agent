# ==============================================
# 前端 Dockerfile - 多阶段构建
# ------------------------------------------------------------
# 为什么要"多阶段"：Vue 项目打包需要 Node 环境（几百 MB），
# 但打包完产物只是几个静态文件，用轻巧的 Nginx 托管就够了。
# 阶段1 用完即弃，最终镜像只含 Nginx + dist，体积小、更安全。
#
# 【基础镜像为什么用 ARG 传参？】
# 国内直连 Docker Hub 拉 node/nginx 镜像经常超时。做成构建参数后，
# 可在 .env 里配置 DOCKER_MIRROR 走国内加速源，无需改动本文件。
# 默认值仍是官方镜像名，不配置也能正常构建。
# ==============================================

# 【重要】用于 FROM 的 ARG 必须声明在"第一个 FROM 之前"（全局作用域）。
# 若写在两个 FROM 之间，它会变成上一个阶段的局部变量，后面的 FROM 取不到值，
# 构建会直接报 `base name (...) should not be blank`。
ARG NODE_IMAGE=node:20-alpine
ARG NGINX_IMAGE=nginx:alpine

# ---------- 阶段1: 构建（Node 编译 Vue 项目）----------
FROM ${NODE_IMAGE} AS builder

WORKDIR /app

# 先只复制依赖清单再 npm install：只要 package.json 没变，
# 这一层就能命中 Docker 缓存，改代码重建时不用重装依赖
COPY package.json package-lock.json* ./
# 国内网络访问 registry.npmjs.org 极慢，改用 npmmirror 淘宝镜像
RUN npm install --registry=https://registry.npmmirror.com

# 复制源码并构建，产出 dist/ 静态文件
COPY . .
RUN npm run build

# ---------- 阶段2: 生产运行（Nginx 托管静态文件）----------
# 注意：这里不再声明 ARG NGINX_IMAGE，它已提到文件顶部
FROM ${NGINX_IMAGE}

# 从阶段1 里只拿走构建产物，Node 环境不进入最终镜像
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制自定义 nginx 配置（前端容器内的，处理 SPA 路由刷新 404 问题）
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# "daemon off" 让 Nginx 在前台运行：容器以主进程存活为准，后台跑会立刻退出
CMD ["nginx", "-g", "daemon off;"]
