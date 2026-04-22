<template>
  <div class="panel-view" style="padding:16px;">
    
    <p>占位：这是 /config 路由的占位页面。后续可放配置与参数管理。</p>
    
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
onMounted(() => { document.title = '骑行头盔用户站-Config' })
</script>

<style scoped>
.panel-view {
  max-width: 900px;
  margin: 0 auto;
  color: #222;
}
</style>
