<!--
  ============================================================
  Login.vue —— 登录页
  ------------------------------------------------------------
  唯一不需要登录就能访问的页面（路由 meta.requiresAuth=false）。
  登录成功：token 存入 localStorage（由 userStore 完成）→ 跳 /chat。
  联动：stores/user.js（login 动作）、router/index.js（守卫）。
  ============================================================
-->
<template>
  <!-- 登录页：居中卡片布局 -->
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1 class="title">智扫通智能客服 v2</h1>
        <p class="subtitle">请登录您的账号</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="rules"
        @keyup.enter="handleLogin"
        class="login-form"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            :prefix-icon="Lock"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

// <script setup> 是 Vue3 Composition API 的语法糖：
// 这里声明的变量/函数可以直接在模板里用，无需 return。
const loginFormRef = ref(null) // ref 绑定到 <el-form>，用来调它的 validate() 方法
const loading = ref(false)

// reactive() 把对象变成响应式（适合表单这类"一坨"数据；
// 单个值用 ref()，对象用 reactive()，是本项目的约定）
const loginForm = reactive({
  username: '',
  password: ''
})

// 表单校验规则
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

/**
 * 提交登录
 */
async function handleLogin() {
  // 先校验表单。validate() 校验不通过会抛异常（Promise 拒绝），
  // 【bug修复】必须 try/catch 接住并直接 return，否则用户没填用户名时
  // 点击登录，控制台会出现未捕获的 Promise 拒绝，且函数继续往下发请求。
  try {
    await loginFormRef.value.validate()
  } catch {
    return // 校验失败：el-form 已自动红字提示，直接结束
  }

  loading.value = true
  try {
    await userStore.login(loginForm.username, loginForm.password)
    ElMessage.success('登录成功')
    router.push('/chat')
  } catch (e) {
    // 错误已在拦截器中提示
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.title {
  font-size: 24px;
  color: #303133;
  margin-bottom: 8px;
}

.subtitle {
  font-size: 14px;
  color: #909399;
}

.login-form {
  margin-top: 20px;
}

.login-btn {
  width: 100%;
}
</style>
