<template>
  <div class="panel-view" style="padding:16px;">
    
    <p>占位：这是 /helmet 路由的占位页面。后续可放 Helmet 相关控制页。</p>
    
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
onMounted(() => { document.title = '骑行头盔用户站-Helmet' })
</script>

<style scoped>
.panel-view {
  max-width: 900px;
  margin: 0 auto;
  color: #222;
}
</style>
