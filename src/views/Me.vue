<template>
  <div class="panel-view" style="padding:16px;">
    <h1>Me 页面</h1>
    <p>占位：这是 /me 路由的占位页面。后续可放用户信息或个人设置。</p>
    <router-link to="/">返回地图</router-link>
  </div>
</template>

<script setup>
// Me 页面目前只做占位，暂无脚本逻辑
</script>

<style scoped>
.panel-view {
  max-width: 900px;
  margin: 0 auto;
  color: #222;
}
</style>
