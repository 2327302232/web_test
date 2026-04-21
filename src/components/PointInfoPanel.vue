<template>
  <div v-show="visible" class="pip-container" role="region" aria-label="点信息面板">
    <div class="pip-header">
      <div class="pip-left" aria-hidden="true"></div>
        <div class="pip-center">
        <button class="pip-btn pip-prev" @click="onPrev" :disabled="!options.onPrev" title="上一个">
          <img v-if="icons && icons.prev" :src="icons.prev" alt="prev" />
          <span v-else class="pip-ic">◀</span>
        </button>
        <button class="pip-btn pip-play" @click="onTogglePlay" :title="isPlaying ? '停止' : '开始'">
          <img v-if="(isPlaying ? icons.stop : icons.play)" :src="isPlaying ? icons.stop : icons.play" :alt="isPlaying ? 'stop' : 'play'" />
          <span v-else class="pip-ic">{{ isPlaying ? '■' : '▶' }}</span>
        </button>
        <button class="pip-btn pip-next" @click="onNext" :disabled="!options.onNext" title="下一个">
          <img v-if="icons && icons.next" :src="icons.next" alt="next" />
          <span v-else class="pip-ic">▶</span>
        </button>
      </div>
      <button class="pip-close" @click="onClose" aria-label="关闭">×</button>
    </div>
    <div class="pip-body">
      <slot>
        <div v-if="options.data">
          <div class="pip-row"><strong>经纬度：</strong><span>{{ displayFields.latlng }}</span></div>
          <div class="pip-row"><strong>时间：</strong><span>{{ displayFields.time }}</span></div>
          <div class="pip-row"><strong>电量：</strong><span>{{ displayFields.battery }}</span></div>
        </div>
        <div v-else class="pip-placeholder">点信息将在此显示。</div>
      </slot>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, defineExpose, computed } from 'vue'
import panelIcons from '../lib/panelIcons.js'

const visible = ref(false)
const options = reactive({ title: '', data: null, onPrev: null, onNext: null, onTogglePlay: null })
const icons = reactive({ prev: panelIcons.prev, play: panelIcons.play, stop: panelIcons.stop, next: panelIcons.next })
const isPlaying = ref(false)

let _resolver = null

function open(opts = {}) {
  options.title = opts.title || '点信息'
  options.data = opts.data || null
  options.onPrev = typeof opts.onPrev === 'function' ? opts.onPrev : null
  options.onNext = typeof opts.onNext === 'function' ? opts.onNext : null
  options.onTogglePlay = typeof opts.onTogglePlay === 'function' ? opts.onTogglePlay : null

  // allow providing icon URLs via opts.icons
  icons.prev = opts.icons && opts.icons.prev ? opts.icons.prev : icons.prev
  icons.play = opts.icons && opts.icons.play ? opts.icons.play : icons.play
  icons.stop = opts.icons && opts.icons.stop ? opts.icons.stop : icons.stop
  icons.next = opts.icons && opts.icons.next ? opts.icons.next : icons.next

  visible.value = true
  isPlaying.value = !!opts.isPlaying
  return new Promise((resolve) => { _resolver = resolve })
}

function close(result = { action: 'close' }) {
  visible.value = false
  if (_resolver) {
    _resolver(result)
    _resolver = null
  }
  try {
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(new CustomEvent('pointPanel:close', { detail: result }))
    }
  } catch (e) { /* ignore */ }
}

function onClose() { close({ action: 'close' }) }

function onPrev() {
  if (typeof options.onPrev === 'function') {
    try { options.onPrev() } catch (e) { console.warn('onPrev callback failed', e) }
  }
}

function onNext() {
  if (typeof options.onNext === 'function') {
    try { options.onNext() } catch (e) { console.warn('onNext callback failed', e) }
  }
}

function onTogglePlay() {
  isPlaying.value = !isPlaying.value
  if (typeof options.onTogglePlay === 'function') {
    try { options.onTogglePlay(isPlaying.value) } catch (e) { console.warn('onTogglePlay callback failed', e) }
  }
}

function setIcons(ic = {}) {
  icons.prev = ic.prev || icons.prev
  icons.play = ic.play || icons.play
  icons.stop = ic.stop || icons.stop
  icons.next = ic.next || icons.next
}

defineExpose({ open, close, prev: onPrev, next: onNext, togglePlay: onTogglePlay, setIcons })

function _normalizeTs(raw) {
  const n = Number(raw)
  if (!Number.isFinite(n)) return NaN
  return n < 1e12 ? Math.round(n * 1000) : Math.round(n)
}

const displayFields = computed(() => {
  const d = options.data
  if (!d) return { latlng: '—', time: '—', battery: '—' }
  const ts = _normalizeTs(d.ts)
  const time = Number.isFinite(ts) ? new Date(ts).toLocaleString() : '—'
  const lng = Number(d.lng); const lat = Number(d.lat)
  const latlng = (Number.isFinite(lng) && Number.isFinite(lat)) ? `${lng.toFixed(6)}, ${lat.toFixed(6)}` : '—'
  const battery = (d.battery == null || d.battery === '') ? '—' : (Number.isFinite(Number(d.battery)) ? `${Number(d.battery)}%` : String(d.battery))
  return { latlng, time, battery }
})
</script>

<style scoped>
.pip-container {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: 33vh;
  min-height: 140px;
  max-height: 45vh;
  background: rgba(255,255,255,0.98);
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
  box-shadow: 0 -8px 30px rgba(0,0,0,0.12);
  z-index: 9998;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  -webkit-user-select: none;
  user-select: none;
}
.pip-header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #eee;
  background: rgba(255,255,255,0.95);
}
.pip-left { width:36px }
.pip-center { display:flex; gap:12px; align-items:center; justify-content:center; flex:1 }
.pip-close { background:transparent; border:none; font-size:22px; padding:6px 8px; cursor:pointer; color:#666; }
.pip-btn { width:44px; height:44px; border-radius:50%; background:#fff; border:1px solid #eee; display:flex; align-items:center; justify-content:center; cursor:pointer; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
.pip-btn img { width:60%; height:60%; object-fit:contain }
.pip-ic { font-size:18px; color:#333 }
.pip-close { background:transparent; border:none; font-size:22px; padding:6px 8px; cursor:pointer; color:#666; }
.pip-body { padding:10px 12px; overflow:auto; flex:1; }
.pip-pre { margin:0; font-size:13px; color:#333; white-space:pre-wrap; word-break:break-word; }
.pip-placeholder { color:#888; }
.pip-row { display:flex; gap:8px; padding:6px 0; align-items:center; }
.pip-row strong { width:88px; color:#444; font-weight:600; }
.pip-btn[disabled] { opacity: 0.45; cursor: not-allowed; pointer-events: none; }
@media (max-width:480px) {
  .pip-container { height: 40vh; }
  .pip-btn { width:48px; height:48px }
}
</style>
