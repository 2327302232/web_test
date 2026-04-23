

<template>
  <div class="log-panel-view">
    <div class="log-header">
      <label class="log-label">设备 ID：
        <select v-model="deviceId" class="log-select">
          <option value="dev-001">dev-001</option>
          <option value="dev-002">dev-002</option>
          <option value="dev-003">dev-003</option>
        </select>
      </label>
      <button @click="load" class="log-btn">加载</button>
      <span v-if="segments.length" style="margin-left:16px;">
        <strong>已选: {{ selectionStore.count }}</strong>
        <button class="log-btn" style="margin-left:8px;" @click="selectAll">全选</button>
        <button class="log-btn" style="margin-left:4px;background:#eee;color:#333;" @click="clearSelection">清除</button>
      </span>
    </div>

    <div v-if="segments.length === 0" class="log-empty">无骑行分段或尚未加载。</div>
    <ul v-else class="log-segment-list">
      <li v-for="(seg, idx) in segments" :key="segmentId(seg, idx)" class="log-segment-item">
        <input type="checkbox"
          :value="segmentId(seg, idx)"
          :checked="selectionStore.isSelected(segmentId(seg, idx))"
          @change="() => selectionStore.toggle(segmentId(seg, idx))"
          style="margin-right:10px;transform:scale(1.2);vertical-align:middle;"
        />
        <div class="log-seg-title">
          <strong>{{ formatDate(seg.points[0]?.ts) }}</strong>
          <span class="log-seg-device">设备: {{ deviceId }}</span>
          <span class="log-seg-count">点数: {{ seg.points.length }}</span>
        </div>
        <div class="log-seg-row">
          <span class="log-label-bold">起点时间: </span><span>{{ formatTime(seg.points[0]?.ts) }}</span>
          ；
          <span class="log-label-bold">终点时间: </span><span>{{ formatTime(seg.points[seg.points.length-1]?.ts) }}</span>
        </div>
        <div class="log-seg-row"><span class="log-label-bold">起点: </span><span>{{ formatLatLng(seg.points[0]) }}</span></div>
        <div class="log-seg-row"><span class="log-label-bold">终点: </span><span>{{ formatLatLng(seg.points[seg.points.length-1]) }}</span></div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { segmentTrack } from '../utils/segment.js'
import { useTrackSelection } from '../stores/trackSelection.js'
onMounted(() => { document.title = '骑行头盔用户站-Log' })

const deviceId = ref('dev-001')
const segments = ref([])
const selectionStore = useTrackSelection()

function segmentId(seg, idx) {
  // `${deviceId}:${startTs}:${endTs}`
  const start = seg.points[0]?.ts
  const end = seg.points[seg.points.length - 1]?.ts
  return `${deviceId.value}:${start}:${end}`
}

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
    // 注册 meta
    segments.value.forEach((seg, idx) => {
      const id = segmentId(seg, idx)
      const meta = {
        deviceId: deviceId.value,
        startTs: seg.points[0]?.ts,
        endTs: seg.points[seg.points.length - 1]?.ts,
        pointCount: seg.points.length,
        startLng: seg.points[0]?.lng,
        startLat: seg.points[0]?.lat,
        endLng: seg.points[seg.points.length - 1]?.lng,
        endLat: seg.points[seg.points.length - 1]?.lat,
      }
      selectionStore.registerMeta(id, meta)
    })
  } catch (e) {
    console.error('load segments failed', e)
    segments.value = []
  }
}

function selectAll() {
  const allIds = segments.value.map((seg, idx) => segmentId(seg, idx))
  selectionStore.bulkSelect(allIds)
}
function clearSelection() {
  selectionStore.clear()
}

function formatTs(ts) {
  if (!ts) return '—'
  const n = Number(ts)
  if (!Number.isFinite(n)) return String(ts)
  const ms = n < 1e12 ? Math.round(n * 1000) : Math.round(n)
  return new Date(ms).toLocaleString()
}
function formatDate(ts) {
  if (!ts) return '—'
  const n = Number(ts)
  if (!Number.isFinite(n)) return String(ts)
  const ms = n < 1e12 ? Math.round(n * 1000) : Math.round(n)
  const d = new Date(ms)
  return d.getFullYear() + '年' + (d.getMonth() + 1) + '月' + d.getDate() + '日'
}
function formatTime(ts) {
  if (!ts) return '—'
  const n = Number(ts)
  if (!Number.isFinite(n)) return String(ts)
  const ms = n < 1e12 ? Math.round(n * 1000) : Math.round(n)
  const d = new Date(ms)
  return d.toTimeString().slice(0, 8)
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
.log-panel-view {
  max-width: 900px;
  margin: 0 auto;
  color: #111;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 4px 18px rgba(33,150,243,0.07), 0 1.5px 6px rgba(0,0,0,0.04);
  padding: 24px 18px 18px 18px;
  font-size: 15px;
}
.log-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}
.log-label {
  font-weight: 500;
  color: #1976d2;
}
.log-select {
  margin-left: 8px;
  padding: 7px 10px;
  border: 1px solid #bcdffb;
  border-radius: 7px;
  font-size: 15px;
  outline: none;
  transition: border 0.2s;
  background: #fff;
  color: #222;
}
.log-select:focus {
  border-color: #2196f3;
}
.log-btn {
  background: #2196f3;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(33,150,243,0.08);
  transition: background 0.2s;
}
.log-btn:hover {
  background: #1976d2;
}
.log-empty {
  color: #888;
  background: #f7fafd;
  border-radius: 8px;
  padding: 18px 0;
  text-align: center;
  font-size: 16px;
}
.log-segment-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.log-segment-item {
  margin-bottom: 18px;
  padding: 16px 14px 12px 14px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1.5px 6px rgba(33,150,243,0.04);
  color: #111;
  border: 1px solid #e3eaf2;
}
.log-segment-item:last-child {
  margin-bottom: 0;
}
.log-seg-title {
  font-size: 16px;
  font-weight: 600;
  color: #222;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.log-seg-count {
  font-size: 13px;
  color: #2196f3;
  background: #e3f2fd;
  border-radius: 6px;
  padding: 2px 8px;
  margin-left: 2px;
}
.log-seg-device {
  font-size: 13px;
  color: #ff9800;
  background: #fff3e0;
  border-radius: 6px;
  padding: 2px 8px;
  margin-left: 2px;
}
.log-seg-row {
  margin-bottom: 3px;
  color: #111;
}
.log-label-bold {
  font-weight: 600;
  color: #111;
}
@media (max-width: 600px) {
  .log-panel-view {
    padding: 12px 2vw 10px 2vw;
    font-size: 16px;
  }
  .log-header {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .log-segment-item {
    padding: 12px 8px 10px 10px;
    font-size: 15px;
  }
  .log-seg-title {
    font-size: 15px;
  }
}
</style>
