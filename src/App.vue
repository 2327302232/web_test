<template>
  <div id="app-root">
    <FloatTaskbar />
    <router-view />
  </div>
</template>

<script>
import FloatTaskbar from './components/FloatTaskbar.vue'

export default {
  name: 'App',
  components: {
    FloatTaskbar
  }
}
</script>

<style>
html, body, #app { height: 100%; margin: 0; padding: 0; }
</style>