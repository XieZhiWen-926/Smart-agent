<!--
  ============================================================
  Layout.vue —— 登录后所有页面共用的"外壳"布局
  ------------------------------------------------------------
  结构：左侧深色导航菜单 ｜ 顶部（页面标题 + 用户下拉）｜ 主内容区。
  路由上它是 /chat、/customers 等页面的父路由（见 router/index.js），
  子页面渲染在下面 el-main 里的 <router-view /> 中——
  所以切换菜单时，导航和顶栏不会刷新，只有内容区在变。
  联动：stores/user.js（显示用户名、退出登录）。
  ============================================================
-->
<template>
  <!-- 主布局：左侧导航 + 顶部用户栏 + 主内容区 -->
  <el-container class="layout-container">
    <!-- 左侧侧边导航 -->
    <el-aside width="220px" class="aside">
      <div class="logo">
        <span class="logo-text">智扫通 v2</span>
      </div>
      <!-- el-menu 加 router 属性后，点菜单项会自动按 index 做路由跳转，
           不用再手写 @click="router.push(...)" -->
      <el-menu
        :default-active="activeMenu"
        class="menu"
        router
      >
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能对话</span>
        </el-menu-item>
        <el-menu-item index="/customers">
          <el-icon><User /></el-icon>
          <span>客户管理</span>
        </el-menu-item>
        <el-menu-item index="/tools">
          <el-icon><Tools /></el-icon>
          <span>工具管理</span>
        </el-menu-item>
        <el-menu-item index="/datasets">
          <el-icon><FolderOpened /></el-icon>
          <span>数据集管理</span>
        </el-menu-item>
        <el-menu-item index="/memory">
          <el-icon><Collection /></el-icon>
          <span>记忆管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶部栏 -->
      <el-header class="header">
        <div class="header-left">
          <span class="page-title">{{ currentTitle }}</span>
        </div>
        <div class="header-right">
          <el-dropdown trigger="click">
            <span class="user-info">
              <el-icon><UserFilled /></el-icon>
              {{ userStore.userInfo?.username || '用户' }}
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="handleLogout">
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 主内容区：子路由页面（Chat/Customers/…）渲染在这里 -->
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'

const route = useRoute()     // useRoute()：当前路由信息（路径、meta 等）
const router = useRouter()   // useRouter()：路由器实例，用来编程式跳转
const userStore = useUserStore()

// 当前激活的菜单项
const activeMenu = computed(() => route.path)

// 当前页面标题
const currentTitle = computed(() => route.meta.title || '')

/**
 * 退出登录
 */
function handleLogout() {
  userStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
}

.aside {
  background: #304156;
  overflow-x: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2b3a4d;
}

.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: bold;
}

.menu {
  border-right: none;
  background: #304156;
}

/* 菜单文字颜色适配深色侧边栏 */
:deep(.el-menu-item) {
  color: #bfcbd9;
}

:deep(.el-menu-item.is-active) {
  color: #409eff;
  background: #263445;
}

:deep(.el-menu-item:hover) {
  background: #263445;
}

.header {
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.user-info {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  color: #606266;
  font-size: 14px;
}

.main {
  background: #f0f2f5;
  padding: 0;
  overflow: hidden;
}
</style>
