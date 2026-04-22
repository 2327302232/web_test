<template>
  <div class="panel-view" style="padding:16px;">
    
    <p>占位：这是 /me 路由的占位页面。后续可放用户信息或个人设置。</p>
    
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
onMounted(() => { document.title = '骑行头盔用户站-Me' })
</script>

<style scoped>
.panel-view {
  max-width: 900px;
  margin: 0 auto;
  color: #222;
}
</style>
