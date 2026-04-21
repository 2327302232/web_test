<template>
  <div class="panel-view" style="padding:16px;">
    <h1>Log 页面 — 骑行分段</h1>
    <div style="margin-bottom:12px">
      <label>设备 ID：<input v-model="deviceId" style="margin-left:8px" /></label>
      <button @click="load" style="margin-left:12px">加载</button>
      <router-link to="/" style="margin-left:12px">返回地图</router-link>
    </div>

    <div v-if="segments.length === 0">无骑行分段或尚未加载。</div>
    <ul v-else>
      <li v-for="(seg, idx) in segments" :key="idx" style="margin-bottom:12px; padding:8px; border:1px solid #eee; border-radius:6px">
        <div><strong>段 {{ idx + 1 }}</strong> — 点数: {{ seg.points.length }}</div>
        <div>起点时间: {{ formatTs(seg.points[0]?.ts) }} ； 终点时间: {{ formatTs(seg.points[seg.points.length-1]?.ts) }}</div>
        <div>起点: {{ formatLatLng(seg.points[0]) }} ； 终点: {{ formatLatLng(seg.points[seg.points.length-1]) }}</div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { segmentTrack } from '../utils/segment.js'

const deviceId = ref('dev-001')
const segments = ref([])

async function load() {
  try {
    const backendBase = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8787'
    const params = new URLSearchParams()
    params.set('deviceId', deviceId.value)
    const url = `${backendBase.replace(/\/$/, '')}/api/track?${params.toString()}`
    const resp = await fetch(url)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    const pts = Array.isArray(data.points) ? data.points : []
    const res = segmentTrack(pts)
    segments.value = res.segments || []
  } catch (e) {
    console.error('load segments failed', e)
    segments.value = []
  }
}

function formatTs(ts) {
  if (!ts) return '—'
  const n = Number(ts)
  if (!Number.isFinite(n)) return String(ts)
  const ms = n < 1e12 ? Math.round(n * 1000) : Math.round(n)
  return new Date(ms).toLocaleString()
}

function formatLatLng(p) {
  if (!p) return '—'
  const lng = Number(p.lng); const lat = Number(p.lat)
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return '—'
  return `${lng.toFixed(6)}, ${lat.toFixed(6)}`
}

// initial load
load()
</script>

<style scoped>
.panel-view {
  max-width: 900px;
  margin: 0 auto;
  color: #222;
}
</style>
