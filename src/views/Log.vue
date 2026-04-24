

<template>
  <div class="log-panel-view">
    <div class="log-header">
            <label class="log-label">设备 ID：
              <select v-model="deviceId" class="log-select">
                <option value="all">全部</option>
                <option value="dev-001">dev-001</option>
                <option value="dev-002">dev-002</option>
                <option value="dev-003">dev-003</option>
              </select>
            </label>
      
    </div>

    <div v-if="segments.length === 0" class="log-empty">无骑行分段或尚未加载。</div>
    <ul v-else class="log-segment-list">
      <li v-for="(seg, idx) in segments" :key="segmentId(seg, idx)" class="log-segment-item">
        <div class="log-seg-title">
          <strong>{{ formatDate(seg.points[0]?.ts) }}</strong>
          <span class="log-seg-device">设备: {{ seg.deviceId || deviceId }}</span>
          <span class="log-seg-count">点数: {{ seg.points.length }}</span>
        </div>
        <div class="log-seg-checkbox">
          <input type="checkbox"
            :value="segmentId(seg, idx)"
            :checked="selectionStore.isSelected(segmentId(seg, idx))"
            @change="() => selectionStore.toggle(segmentId(seg, idx))"
          />
        </div>
        <div class="log-seg-content">
          <div class="log-seg-row">
            <span class="log-label-bold">起点时间: </span><span>{{ formatTime(seg.points[0]?.ts) }}</span>
            ；
            <span class="log-label-bold">终点时间: </span><span>{{ formatTime(seg.points[seg.points.length-1]?.ts) }}</span>
          </div>
          <div class="log-seg-row"><span class="log-label-bold">起点: </span><span>{{ formatLatLng(seg.points[0]) }}</span></div>
          <div class="log-seg-row"><span class="log-label-bold">终点: </span><span>{{ formatLatLng(seg.points[seg.points.length-1]) }}</span></div>
        </div>
      </li>
    </ul>
    <!-- 底部工具栏：左侧复选（全选/部分/未选），中间统计，右侧确定按钮 -->
    <div class="log-footer">
      <div class="log-footer-left">
        <input ref="bulkCheckbox" type="checkbox" class="log-footer-checkbox" :checked="allSelected" @change="toggleAll" />
      </div>
      <div class="log-footer-center">
        <span class="total-count">{{ totalCount }} 条记录</span>
        <span v-if="selectedCount > 0" class="selected-count">；已选 {{ selectedCount }} 条</span>
      </div>
      <div class="log-footer-right">
        <button class="log-btn" @click="confirmSelection">确定</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { segmentTrack } from '../utils/segment.js'
import { useTrackSelection } from '../stores/trackSelection.js'
onMounted(() => { document.title = '骑行头盔用户站-Log' })

const deviceId = ref('dev-001')
const segments = ref([])
const selectionStore = useTrackSelection()
const router = useRouter()
const bulkCheckbox = ref(null)

const totalCount = computed(() => segments.value.length)
const selectedCount = computed(() => selectionStore.count)
const allSelected = computed(() => selectedCount.value > 0 && selectedCount.value === totalCount.value)
const partialSelected = computed(() => selectedCount.value > 0 && selectedCount.value < totalCount.value)

function segmentId(seg, idx) {
  // `${deviceId}:${startTs}:${endTs}` using segment's deviceId if present
  const dev = (seg && seg.deviceId) ? seg.deviceId : deviceId.value
  const start = seg.points[0]?.ts
  const end = seg.points[seg.points.length - 1]?.ts
  return `${dev}:${start}:${end}`
}

async function load() {
  try {
    const backendBase = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8787'

    // clear previous meta and selection
    selectionStore.meta = {}
    selectionStore.clear()
    segments.value = []

    if (deviceId.value === 'all') {
      // fetch devices list, then fetch tracks per device and combine segments
      const devsUrl = `${backendBase.replace(/\/$/, '')}/api/devices`
      const devsResp = await fetch(devsUrl)
      if (!devsResp.ok) throw new Error(`Failed to list devices HTTP ${devsResp.status}`)
      const devsData = await devsResp.json()
      const devices = Array.isArray(devsData.devices) ? devsData.devices : []
      const combined = []
      for (const d of devices) {
        try {
          const dId = d.deviceId || d.device_id
          if (!dId) continue
          const params = new URLSearchParams()
          params.set('deviceId', dId)
          const url = `${backendBase.replace(/\/$/, '')}/api/track?${params.toString()}`
          const resp = await fetch(url)
          if (!resp.ok) { console.warn('fetch track failed for', dId, resp.status); continue }
          const data = await resp.json()
          const pts = Array.isArray(data.points) ? data.points : []
          const res = segmentTrack(pts)
          const segs = res.segments || []
          for (const seg of segs) {
            // annotate segment with deviceId for later rendering/lookup
            seg.deviceId = dId
            combined.push(seg)
          }
        } catch (e) {
          console.warn('failed processing device', d, e)
        }
      }
      // sort by start timestamp
      combined.sort((a, b) => (a.points[0]?.ts || 0) - (b.points[0]?.ts || 0))
      segments.value = combined
      // register meta per-segment with per-segment deviceId
      segments.value.forEach((seg, idx) => {
        const id = segmentId(seg, idx)
        const meta = {
          deviceId: seg.deviceId,
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
    } else {
      const params = new URLSearchParams()
      params.set('deviceId', deviceId.value)
      const url = `${backendBase.replace(/\/$/, '')}/api/track?${params.toString()}`
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      const pts = Array.isArray(data.points) ? data.points : []
      const res = segmentTrack(pts)
      const segs = res.segments || []
      // annotate and register
      segs.forEach((seg, idx) => { seg.deviceId = deviceId.value })
      segments.value = segs
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
    }
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

function toggleAll() {
  if (allSelected.value) {
    selectionStore.clear()
  } else {
    const allIds = segments.value.map((seg, idx) => segmentId(seg, idx))
    selectionStore.bulkSelect(allIds)
  }
}

function confirmSelection() {
  // Navigate to map page where MapView will render selectionStore.selected
  router.push({ name: 'map' })
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
// auto-load when deviceId changes
watch(deviceId, () => { load() })

// initial load
load()

// watch selection/segments to update bulk checkbox indeterminate state
watch([() => selectionStore.selected.slice(), () => segments.value.length], async () => {
  await nextTick()
  try {
    if (bulkCheckbox.value) bulkCheckbox.value.indeterminate = partialSelected.value
  } catch (e) { /* ignore */ }
}, { immediate: true })
</script>

<style scoped>
.log-panel-view {
  --left-col: 34px;
  --checkbox-accent: #2196f3;
  max-width: 900px;
  margin: 0 auto;
  color: #111;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 4px 18px rgba(33,150,243,0.07), 0 1.5px 6px rgba(0,0,0,0.04);
  padding: 24px 18px 110px 18px;
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
  position: relative;
  margin-bottom: 18px;
  padding: 12px 14px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1.5px 6px rgba(33,150,243,0.04);
  color: #111;
  border: 1px solid #e3eaf2;
}
.log-seg-checkbox {
  position: absolute;
  left: 30px; /* align with item padding-left */
  top: 50%;
  transform: translateY(-50%);
  width: 0px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.log-seg-checkbox input { transform: scale(1.12); accent-color: var(--checkbox-accent); }
.log-seg-content { margin-left: calc(var(--left-col) + 0px); }
.log-segment-item:last-child {
  margin-bottom: 0;
}
.log-seg-title {
  font-size: 16px;
  font-weight: 600;
  color: #222;
  margin-bottom: 6px;
  display: flex;
  gap: 12px;
  margin-left: 5px;
  justify-content: flex-start;
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
/* footer styles */
.log-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  border-top: 1px solid #eef3f9;
  background: #fff;
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: 0;
  width: min(900px, calc(100% - 36px));
  box-shadow: 0 -6px 18px rgba(33,150,243,0.03);
  z-index: 999;
}
.log-footer-left { display:flex; align-items:center; margin-left: 7px; width: var(--left-col); justify-content:center }
.log-footer-checkbox { margin-right: 10px; transform: scale(1.18); vertical-align: middle; accent-color: var(--checkbox-accent); }
.log-footer-center { color: #666; font-size: 14px; }
.log-footer-right { }
.log-footer .log-btn { padding: 8px 16px; }
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
