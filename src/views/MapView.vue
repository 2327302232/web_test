<template>
  <div id="map" class="map"></div>

  <div class="panel">
    <div class="row"><strong>骑行头盔用户站</strong></div>
    <div class="row">状态：<span>{{ status }}</span></div>
    <div class="row">坐标：<code>{{ posText }}</code></div>
    <div class="row">精度：<code>{{ accText }}</code></div>
    <div class="row">
      <button @click="locate">定位到我</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { loadAmapSdk, initMap, createMarker, initGeolocation } from '../utils/amap.js'

const status = ref('加载中…')
const posText = ref('-')
const accText = ref('-')

let map
let marker
let geolocation

async function locate() {
  if (!geolocation) {
    status.value = '定位组件未就绪'
    return
  }

  // Parameters (可微调)
  const attempts = 3
  const desiredAccuracy = 10 // meters (目标精度)
  const initialTimeout = 100 // ms, 首次等待时间，尽量快速展示结果

  status.value = '高德定位中…'
  accText.value = '-'

  // Helper: wrap AMap geolocation callback into a promise
  const getAmapPositionOnce = () => new Promise((resolve) => {
    try {
      geolocation.getCurrentPosition((st, result) => resolve({ st, result }))
    } catch (e) {
      resolve({ st: 'error', result: e })
    }
  })

  // Helper: promise with timeout that resolves to null on timeout
  const withTimeout = (p, ms) => new Promise((resolve) => {
    let done = false
    p.then((v) => { if (!done) { done = true; resolve(v) } }).catch((e) => { if (!done) { done = true; resolve({ st: 'error', result: e }) } })
    setTimeout(() => { if (!done) { done = true; resolve(null) } }, ms)
  })

  // 1) 尝试快速获取首个结果（短超时），尽快显示给用户
  const initial = await withTimeout(getAmapPositionOnce(), initialTimeout)
  let best = null

  if (initial && initial.st === 'complete' && initial.result && initial.result.position) {
    const acc = initial.result.accuracy != null ? initial.result.accuracy : Infinity
    best = { result: initial.result, acc }
    const lng = initial.result.position.lng
    const lat = initial.result.position.lat
    posText.value = `${lng.toFixed(6)}, ${lat.toFixed(6)}`
    accText.value = acc !== Infinity ? `${Math.round(acc)} m` : '未知'
    marker.setPosition([lng, lat])
    map.setCenter([lng, lat])
    map.setZoom(17)

    if (acc <= desiredAccuracy) {
      status.value = '定位成功'
      return
    }

    // 后台继续优化，但不阻塞用户体验
    status.value = '初始定位完成，后台优化精度中…'

    // 2) 额外尝试，但以后台方式进行，用户先看到初始位置
    for (let i = 0; i < attempts - 1; i++) {
      // small delay between attempts to allow chipset/GNSS to refine
      await new Promise((r) => setTimeout(r, 700))
      const next = await withTimeout(getAmapPositionOnce(), 3000)
      if (next && next.st === 'complete' && next.result && next.result.position) {
        const acc = next.result.accuracy != null ? next.result.accuracy : Infinity
        if (!best || acc < best.acc) {
          best = { result: next.result, acc }
          const lng2 = next.result.position.lng
          const lat2 = next.result.position.lat
          posText.value = `${lng2.toFixed(6)}, ${lat2.toFixed(6)}`
          accText.value = acc !== Infinity ? `${Math.round(acc)} m` : '未知'
          marker.setPosition([lng2, lat2])
          map.setCenter([lng2, lat2])
          map.setZoom(17)
          if (acc <= desiredAccuracy) {
            status.value = '定位成功'
            return
          }
        }
      }
    }

    status.value = '定位完成（精度可能有限）'
    return
  }

  // 3) 如果短超时内未得到初始结果，做一次较长的 AMap 定位尝试
  status.value = '等待高德定位结果…'
  const final = await withTimeout(getAmapPositionOnce(), 8000)
  if (final && final.st === 'complete' && final.result && final.result.position) {
    const acc = final.result.accuracy != null ? final.result.accuracy : Infinity
    const lng = final.result.position.lng
    const lat = final.result.position.lat
    posText.value = `${lng.toFixed(6)}, ${lat.toFixed(6)}`
    accText.value = acc !== Infinity ? `${Math.round(acc)} m` : '未知'
    marker.setPosition([lng, lat])
    map.setCenter([lng, lat])
    map.setZoom(17)
    status.value = acc <= desiredAccuracy ? '定位成功' : '定位完成（精度可能有限）'
    return
  }

  // 4) 最后退回到浏览器原生定位
  status.value = '定位失败（高德），尝试浏览器定位…'
  try {
    const pos = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 })
    })
    const lng = pos.coords.longitude
    const lat = pos.coords.latitude
    const acc = pos.coords.accuracy
    posText.value = `${lng.toFixed(6)}, ${lat.toFixed(6)}`
    accText.value = acc != null ? `${Math.round(acc)} m` : '未知'
    marker.setPosition([lng, lat])
    map.setCenter([lng, lat])
    map.setZoom(17)
    status.value = '浏览器定位成功（回退）'
    return
  } catch (e) {
    status.value = '定位失败：' + (e?.message || String(e))
    accText.value = '-'
    console.warn('定位回退失败', e)
    return
  }
}

onMounted(async () => {
  try {
    status.value = '加载高德 SDK…'
    await loadAmapSdk()

    status.value = '初始化地图…'
    map = initMap('map', { zoom: 14, center: [116.397428, 39.90923] })

    marker = createMarker(map, map.getCenter())

    geolocation = await initGeolocation()
    status.value = '地图已加载'
  } catch (err) {
    status.value = '错误：' + (err?.message || String(err))
    console.error(err)
  }
})
</script>

<style scoped>
.map { height: 100vh; width: 100vw; }
.panel {
  position: fixed; left: 12px; top: 12px;
  background: rgba(255,255,255,0.96);
  padding: 10px 12px; border-radius: 10px;
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  font-size: 14px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.15);
  max-width: 92vw;
}
.row { margin: 6px 0; }
button { padding: 8px 10px; }
code { user-select: all; }
</style>
