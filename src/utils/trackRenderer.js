// Track renderer helper for drawing GPS tracks on AMap map instances.
// Exports: initTrackRenderer(map) -> { renderTrack, clearTrack, appendPoints }
import { addPolyline, createMarker } from './amap.js'
import { showPointPanel } from '../composables/usePointPanel'
import { splitByGap } from './segment.js'

function _normalizeTs(raw) {
  const n = Number(raw)
  if (!Number.isFinite(n)) return NaN
  // If less than 1e12 treat as seconds -> convert to ms
  return n < 1e12 ? Math.round(n * 1000) : Math.round(n)
}

function _validatePoint(p) {
  if (!p) return null
  const ts = _normalizeTs(p.ts)
  const lng = Number(p.lng)
  const lat = Number(p.lat)
  if (!Number.isFinite(ts) || !Number.isFinite(lng) || !Number.isFinite(lat)) return null
  if (lng < -180 || lng > 180 || lat < -90 || lat > 90) return null
  return Object.assign({}, p, { ts, lng: Number(lng), lat: Number(lat) })
}

function _preprocess(points) {
  const out = []
  let discarded = 0
  if (!Array.isArray(points)) return { points: [], discarded: 0 }
  for (const pt of points) {
    const v = _validatePoint(pt)
    if (!v) {
      discarded++
      continue
    }
    out.push(v)
  }
  // sort by ts asc
  out.sort((a, b) => a.ts - b.ts)
  // minimal adjacent dedupe: same lng/lat and ts diff < 1 ms
  const dedup = []
  for (const p of out) {
    const prev = dedup[dedup.length - 1]
    if (prev && prev.lng === p.lng && prev.lat === p.lat && Math.abs(p.ts - prev.ts) < 1) {
      // skip duplicate
      continue
    }
    dedup.push(p)
  }
  return { points: dedup, discarded }
}

export function initTrackRenderer(map) {
  if (!map) throw new Error('map is required')

  let currentPolylines = []
  let startMarker = null
  let endMarker = null
  let singleMarker = null
  let pointMarkers = []
  let lastPoints = []
  let lastSegments = []
  let selectedMarker = null

  // panel close handler (will be registered on window)
  function _handlePanelCloseEvent(e) {
    try { _clearSelection() } catch (err) { /* ignore */ }
  }

  function _makeCircleHtml(style = {}) {
    const size = Number(style.size) || 12
    const color = style.color || '#ff8800'
    const border = style.border || '#ffffff'
    const borderWidth = Number(style.borderWidth) || 2
    const boxShadow = style.boxShadow || '0 0 4px rgba(0,0,0,0.12)'
    return `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:${borderWidth}px solid ${border};box-shadow:${boxShadow}"></div>`
  }

  function _applyStyleToMarker(marker, style = {}) {
    try {
      if (!marker) return
      const html = _makeCircleHtml(style)
      if (typeof marker.setContent === 'function') marker.setContent(html)
      if (typeof marker.setOffset === 'function' && typeof window !== 'undefined' && window.AMap && typeof window.AMap.Pixel === 'function') {
        const size = Number(style.size) || 12
        try { marker.setOffset(new window.AMap.Pixel(Math.round(-size / 2), Math.round(-size / 2))) } catch (e) { /* ignore offset failures */ }
      }
      marker.__trackStyle = style
    } catch (e) {
      console.warn('[trackRenderer] applyStyleToMarker failed', e)
    }
  }

  function _clearSelection() {
    try {
      if (selectedMarker) {
        const base = selectedMarker.__baseStyle || selectedMarker.__trackStyle || {}
        _applyStyleToMarker(selectedMarker, base)
        selectedMarker = null
      }
    } catch (e) { /* ignore */ }
  }

  function _getMarkerForIndex(i) {
    try {
      if (!Array.isArray(lastPoints) || lastPoints.length === 0) return null
      if (i <= 0) return startMarker
      if (i >= lastPoints.length - 1) return endMarker
      const idx = i - 1
      return Array.isArray(pointMarkers) && pointMarkers[idx] ? pointMarkers[idx] : null
    } catch (e) {
      return null
    }
  }

  function _selectMarker(marker) {
    try {
      if (!marker) return
      if (selectedMarker === marker) return
      if (selectedMarker) {
        const basePrev = selectedMarker.__baseStyle || selectedMarker.__trackStyle || {}
        _applyStyleToMarker(selectedMarker, basePrev)
      }
      selectedMarker = marker
      const base = marker.__baseStyle || marker.__trackStyle || {}
      const selStyle = Object.assign({}, base, { border: '#2c9cff', borderWidth: Math.max(2, Number(base.borderWidth || 2)), boxShadow: '0 0 8px rgba(44,156,255,0.7)' })
      _applyStyleToMarker(marker, selStyle)
    } catch (e) {
      console.warn('[trackRenderer] selectMarker failed', e)
    }
  }

  function clearTrack() {
    try {
      try { if (typeof window !== 'undefined' && typeof window.removeEventListener === 'function') window.removeEventListener('pointPanel:close', _handlePanelCloseEvent) } catch (ee) { /* ignore */ }
      if (Array.isArray(currentPolylines) && currentPolylines.length) {
        for (const pl of currentPolylines) {
          try { if (pl && typeof pl.setMap === 'function') pl.setMap(null) } catch (e) { /* ignore individual failures */ }
        }
      }
      if (startMarker && typeof startMarker.setMap === 'function') startMarker.setMap(null)
      if (endMarker && typeof endMarker.setMap === 'function') endMarker.setMap(null)
      if (singleMarker && typeof singleMarker.setMap === 'function') singleMarker.setMap(null)
      if (Array.isArray(pointMarkers) && pointMarkers.length) {
        for (const m of pointMarkers) {
          try { if (m && typeof m.setMap === 'function') m.setMap(null) } catch (e) { /* ignore individual failures */ }
        }
      }
    } catch (e) {
      console.warn('[trackRenderer] clear error', e)
    } finally {
      currentPolylines = []
      startMarker = null
      endMarker = null
      singleMarker = null
      pointMarkers = []
      lastPoints = []
      selectedMarker = null
    }
  }

  function _createMarkerAtPoint(p, opts = {}) {
    try {
      const marker = createMarker(map, [p.lng, p.lat], opts)
      try { _attachClickToMarker(marker, p) } catch (e) { /* ignore */ }
      return marker
    } catch (e) {
      console.warn('[trackRenderer] createMarker failed', e)
      return null
    }
  }

  function _createCircleMarkerAtPoint(p, style = {}) {
    try {
      const size = Number(style.size) || 12
      const html = _makeCircleHtml(style)
      const opts = { content: html }
      if (typeof window !== 'undefined' && window.AMap && typeof window.AMap.Pixel === 'function') {
        opts.offset = new window.AMap.Pixel(Math.round(-size / 2), Math.round(-size / 2))
      }
      const marker = createMarker(map, [p.lng, p.lat], opts)
      // store base style so we can revert when unselecting
      try { marker.__baseStyle = Object.assign({}, style); marker.__trackStyle = marker.__baseStyle } catch (e) { /* ignore */ }
      try { _attachClickToMarker(marker, p) } catch (e) { /* ignore */ }
      return marker
    } catch (e) {
      console.warn('[trackRenderer] createCircleMarker failed', e)
      return _createMarkerAtPoint(p, {})
    }
  }

  function _attachClickToMarker(marker, point) {
    if (!marker || !point) return
    try {
      const handler = async () => {
        try {
          const title = '轨迹点信息'

          // mark this marker as selected (visual)
          try { _selectMarker(marker) } catch (e) { /* ignore */ }

          const findIndex = () => {
            if (!Array.isArray(lastPoints)) return -1
            return lastPoints.findIndex(p => p && p.ts === point.ts && p.lng === point.lng && p.lat === point.lat)
          }

          const openForIndex = (i) => {
            if (!Array.isArray(lastPoints) || lastPoints.length === 0) {
              // still select the clicked marker
              try { _selectMarker(marker) } catch (e) { /* ignore */ }
              const p = showPointPanel({ title, data: point })
              if (p && typeof p.finally === 'function') p.finally(() => { try { _clearSelection() } catch (e) {} })
              return
            }
            const idx = Math.max(0, Math.min(i, lastPoints.length - 1))
            // select marker for this index (start / middle / end)
            try { const m = _getMarkerForIndex(idx); if (m) _selectMarker(m) } catch (e) { /* ignore */ }

            // determine segment boundaries (if available) and restrict prev/next to same segment
            let onPrevFn = null
            let onNextFn = null
            try {
              if (Array.isArray(lastSegments) && lastSegments.length) {
                const seg = lastSegments.find(s => idx >= s.startIndex && idx <= s.endIndex)
                if (seg) {
                  if (idx > seg.startIndex) onPrevFn = () => openForIndex(idx - 1)
                  if (idx < seg.endIndex) onNextFn = () => openForIndex(idx + 1)
                } else {
                  onPrevFn = () => openForIndex(idx - 1)
                  onNextFn = () => openForIndex(idx + 1)
                }
              } else {
                onPrevFn = () => openForIndex(idx - 1)
                onNextFn = () => openForIndex(idx + 1)
              }
            } catch (e) { onPrevFn = () => openForIndex(idx - 1); onNextFn = () => openForIndex(idx + 1) }

            const p = showPointPanel({
              title,
              data: lastPoints[idx],
              isPlaying: false,
              onPrev: onPrevFn,
              onNext: onNextFn,
              onTogglePlay: (playing) => { /* placeholder for playback control */ }
            })
            if (p && typeof p.finally === 'function') p.finally(() => { try { _clearSelection() } catch (e) {} })
          }

          const idx = findIndex()
          openForIndex(idx >= 0 ? idx : 0)
        } catch (e) {
          console.warn('[trackRenderer] showPointPanel failed', e)
        }
      }
      if (typeof marker.on === 'function') {
        marker.on('click', handler)
      } else if (typeof marker.addEventListener === 'function') {
        marker.addEventListener('click', handler)
      }
    } catch (e) {
      console.warn('[trackRenderer] attachClick failed', e)
    }
  }

  function renderTrack(points, options = {}) {
    return new Promise((resolve) => {
      console.debug('[trackRenderer] renderTrack input count', Array.isArray(points) ? points.length : 0)
      const { points: clean, discarded } = _preprocess(points || [])
      console.debug('[trackRenderer] cleaned points', clean.length, 'discarded', discarded)

      if (clean.length === 0) {
        clearTrack()
        console.warn('[trackRenderer] no valid points after cleaning, discarded', discarded)
        resolve({ rendered: false, reason: 'no-data', discarded })
        return
      }

      // idempotent: clear previous
      clearTrack()

      // register panel-close listener to ensure selection is cleared
      try {
        if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
          window.addEventListener('pointPanel:close', _handlePanelCloseEvent)
        }
      } catch (e) { /* ignore */ }

      // compute segments (by time gap) for navigation restrictions
      try {
        lastSegments = splitByGap(clean, options.gapMs || 30 * 60 * 1000)
      } catch (e) { lastSegments = [] }

      if (clean.length === 1) {
        const singleStyle = { size: 12, color: '#ff8800', border: '#ffffff', borderWidth: 2 }
        singleMarker = _createCircleMarkerAtPoint(clean[0], singleStyle)
        lastPoints = clean
        console.debug('[trackRenderer] rendered single marker')
        resolve({ rendered: true, type: 'single', points: clean })
        return
      }

      // compute per-segment paths and draw each segment separately so different segments are not connected
      const fullPath = clean.map(p => [Number(p.lng), Number(p.lat)])
      try {
        const polylineOpts = Object.assign({ strokeColor: '#ff8800', strokeWeight: 2, strokeOpacity: 1 }, options.polyline || {})
        currentPolylines = []
        // draw each segment (segments computed earlier by splitByGap)
        if (Array.isArray(lastSegments) && lastSegments.length) {
          for (const seg of lastSegments) {
            if (!Array.isArray(seg.points) || seg.points.length < 2) continue
            const segPath = seg.points.map(p => [Number(p.lng), Number(p.lat)])
            try {
              const pl = addPolyline(map, segPath, polylineOpts)
              currentPolylines.push(pl)
            } catch (eSeg) {
              console.warn('[trackRenderer] addPolyline for segment failed', eSeg)
            }
          }
        } else {
          // fallback: draw all points as a single polyline
          try { const pl = addPolyline(map, fullPath, polylineOpts); currentPolylines.push(pl) } catch (eAll) { console.warn('[trackRenderer] addPolyline fallback failed', eAll) }
        }

        // try fitting map view to the drawn polylines; fall back to bbox-based center/zoom
        try {
          if (map && typeof map.setFitView === 'function' && currentPolylines.length) {
            map.setFitView(currentPolylines)
          } else {
            // no polylines (maybe only isolated points) -> fallback to bbox fit using full path
            throw new Error('no-polylines')
          }
        } catch (e2) {
          console.warn('[trackRenderer] setFitView failed or no polylines, falling back to bbox fit', e2)
          try {
            // compute bounding box
            let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity
            for (const pt of fullPath) {
              const lng = Number(pt[0])
              const lat = Number(pt[1])
              if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
              if (lng < minLng) minLng = lng
              if (lng > maxLng) maxLng = lng
              if (lat < minLat) minLat = lat
              if (lat > maxLat) maxLat = lat
            }
            if (minLng !== Infinity && minLat !== Infinity && maxLng !== -Infinity && maxLat !== -Infinity) {
              const centerLng = (minLng + maxLng) / 2
              const centerLat = (minLat + maxLat) / 2
              const lngDiff = maxLng - minLng
              const latDiff = maxLat - minLat
              const maxDiff = Math.max(lngDiff, latDiff)
              let zoom = 14
              if (maxDiff < 0.0005) zoom = 19
              else if (maxDiff < 0.001) zoom = 18
              else if (maxDiff < 0.005) zoom = 17
              else if (maxDiff < 0.01) zoom = 16
              else if (maxDiff < 0.02) zoom = 15
              else if (maxDiff < 0.05) zoom = 14
              else if (maxDiff < 0.1) zoom = 13
              else if (maxDiff < 0.5) zoom = 11
              else if (maxDiff < 1) zoom = 9
              else zoom = 8
              try { map.setCenter([centerLng, centerLat]) } catch (e3) { console.warn('[trackRenderer] setCenter failed', e3) }
              try { map.setZoom(zoom) } catch (e4) { console.warn('[trackRenderer] setZoom failed', e4) }
            }
          } catch (eBbox) {
            console.warn('[trackRenderer] bbox fit failed', eBbox)
          }
        }
      } catch (e) {
        console.error('[trackRenderer] addPolyline failed', e)
      }

      // start / end markers (larger)
      const startStyle = { size: 16, color: '#2ecc71', border: '#ffffff', borderWidth: 2 }
      const endStyle = { size: 16, color: '#e74c3c', border: '#ffffff', borderWidth: 2 }
      startMarker = _createCircleMarkerAtPoint(clean[0], startStyle)
      endMarker = _createCircleMarkerAtPoint(clean[clean.length - 1], endStyle)

      // per-point small markers (exclude first and last so start/end keep larger size)
      const smallStyle = { size: 10, color: '#ff8800', border: '#ffffff', borderWidth: 1 }
      pointMarkers = []
      if (clean.length > 2) {
        for (let i = 1; i < clean.length - 1; i++) {
          try {
            const m = _createCircleMarkerAtPoint(clean[i], smallStyle)
            if (m) pointMarkers.push(m)
          } catch (e) {
            console.warn('[trackRenderer] create point marker failed', e)
          }
        }
      }

      lastPoints = clean
      console.debug('[trackRenderer] rendered polyline points', fullPath.length)
      resolve({ rendered: true, type: 'polyline', points: clean })
    })
  }

  function appendPoints(points) {
    // Simple merge: concatenate and re-render (keeps idempotence)
    const merged = (lastPoints || []).concat(points || [])
    return renderTrack(merged)
  }

  return {
    renderTrack,
    clearTrack,
    appendPoints,
    // expose lastPoints for debugging/tests
    _internal: { getLastPoints: () => lastPoints, getLastSegments: () => lastSegments }
  }
}

export default initTrackRenderer
