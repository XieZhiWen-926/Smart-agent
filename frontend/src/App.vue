<!--
  ============================================================
  App.vue —— 整个前端的根组件
  ------------------------------------------------------------
  它本身几乎什么都不画，只放一个 <router-view />（路由出口）。
  用户在浏览器地址栏输入不同路径时，Vue Router 会把对应的
  页面组件（Login / Layout+Chat 等）"塞"进这个出口里显示。
  路由跳转规则见 router/index.js。
  ============================================================
-->
<template>
  <!-- 路由出口：当前匹配到的页面组件会渲染在这里 -->
  <router-view />
</template>

<script setup>
// 根组件，路由守卫在 router/index.js 中处理跳转逻辑
</script>

<style>
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  width: 100%;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
}
</style>
