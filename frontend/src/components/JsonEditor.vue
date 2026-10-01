<!--
  ============================================================
  JsonEditor.vue —— 带格式校验的 JSON 输入框组件
  ------------------------------------------------------------
  把"多行文本框 + JSON.parse 校验 + 错误提示"封装成一个可复用组件，
  用于 Tools.vue 里编辑工具的参数 Schema、配置和测试参数。

  【小白须知 · 自定义组件的 v-model】
  本组件通过 props.modelValue 接收值、emit('update:modelValue', 新值)
  往外发——这两件套配齐后，父组件就能写 <JsonEditor v-model="xxx" />，
  像原生输入框一样双向绑定。
  ============================================================
-->
<template>
  <!-- JSON 编辑组件：el-input textarea + JSON 格式校验 -->
  <div class="json-editor">
    <el-input
      v-model="text"
      type="textarea"
      :rows="rows"
      :placeholder="placeholder"
      @input="handleInput"
    />
    <!-- 校验错误提示 -->
    <div v-if="error" class="json-error">
      <el-icon><WarningFilled /></el-icon>
      {{ error }}
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  // 绑定的 JSON 对象值
  modelValue: {
    type: [Object, String],
    default: () => ({})
  },
  // 占位提示
  placeholder: {
    type: String,
    default: '请输入 JSON 格式内容'
  },
  // 文本框行数
  rows: {
    type: Number,
    default: 6
  }
})

const emit = defineEmits(['update:modelValue'])

const text = ref('')
const error = ref('')

// 初始化：将对象格式化为 JSON 字符串
if (typeof props.modelValue === 'string') {
  text.value = props.modelValue
} else if (props.modelValue) {
  text.value = JSON.stringify(props.modelValue, null, 2)
}

/**
 * 输入处理：尝试解析 JSON，成功则 emit 对象给父组件，失败则提示错误
 * （解析失败时不 emit，父组件拿到的还是上一次合法的值）
 */
function handleInput(val) {
  error.value = ''
  try {
    if (val.trim()) {
      const parsed = JSON.parse(val)
      emit('update:modelValue', parsed)
    } else {
      emit('update:modelValue', {})
    }
  } catch (e) {
    error.value = `JSON 格式错误: ${e.message}`
  }
}

// 外部值变化时同步到文本框
watch(() => props.modelValue, (newVal) => {
  if (typeof newVal === 'string') {
    text.value = newVal
  } else if (newVal && typeof newVal === 'object') {
    // 避免循环更新
    try {
      const current = JSON.parse(text.value || '{}')
      if (JSON.stringify(current) !== JSON.stringify(newVal)) {
        text.value = JSON.stringify(newVal, null, 2)
      }
    } catch {
      text.value = JSON.stringify(newVal, null, 2)
    }
  }
})
</script>

<style scoped>
.json-error {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
