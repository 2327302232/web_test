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
  // playback manager (autoplay within current segment)
  let _playTimer = null
  let _isPlaying = false
  let _playSpeed = 5 // default 5x
  let _playCurrentIndex = -1
  let _playSegment = null
  // segmentId -> { polylines: [], markers: [] }
  const segmentLayers = {}
  /**
   * 渲染单个分段
   * @param {string} segmentId
   * @param {Array} points
   * @param {object} options
   * @returns {Promise<{segmentId, rendered, info}>}
   */
  function renderSegment(segmentId, points, options = {}) {
    return new Promise((resolve) => {
      if (!segmentId || !Array.isArray(points) || points.length === 0) {
        resolve({ segmentId, rendered: false, info: 'no-points' });
        return;
      }
      // 幂等：先清理
      clearSegment(segmentId);
      const { points: clean } = _preprocess(points);
      if (clean.length === 0) {
        resolve({ segmentId, rendered: false, info: 'no-valid-points' });
        return;
      }
      // polyline
      const polylineOpts = Object.assign({ strokeColor: '#8400ff', strokeWeight: 3, strokeOpacity: 1 }, options.polyline || {});
      const segPath = clean.map(p => [Number(p.lng), Number(p.lat)]);
      let pl = null;
      try {
        pl = addPolyline(map, segPath, polylineOpts);
      } catch (e) {
        console.warn('[trackRenderer] addPolyline failed', e);
      }
      // start/end markers
      let startM = null, endM = null;
      try {
        if (clean.length > 0) {
          startM = _createCircleMarkerAtPoint(clean[0], { size: 14, color: '#2ecc71', border: '#fff', borderWidth: 2 });
        }
        if (clean.length > 1) {
          endM = _createCircleMarkerAtPoint(clean[clean.length - 1], { size: 14, color: '#e74c3c', border: '#fff', borderWidth: 2 });
        }
      } catch (e) { /* ignore */ }

      // 中间点小marker
      const midMarkers = [];
      if (clean.length > 2) {
        for (let i = 1; i < clean.length - 1; i++) {
          try {
            const m = _createCircleMarkerAtPoint(clean[i], { size: 10, color: '#ff8800', border: '#fff', borderWidth: 1 });
            if (m) midMarkers.push(m);
          } catch (e) { /* ignore */ }
        }
      }

      segmentLayers[segmentId] = {
        polylines: pl ? [pl] : [],
        markers: [startM, endM, ...midMarkers].filter(Boolean),
      };
      resolve({ segmentId, rendered: true, info: { points: clean.length } });
    });
  }

  /**
   * 清理单个分段
   * @param {string} segmentId
   */
  function clearSegment(segmentId) {
    const entry = segmentLayers[segmentId];
    if (!entry) return;
    if (Array.isArray(entry.polylines)) {
      for (const pl of entry.polylines) {
        try { if (pl && typeof pl.setMap === 'function') pl.setMap(null); } catch (e) { }
      }
    }
    if (Array.isArray(entry.markers)) {
      for (const m of entry.markers) {
        try { if (m && typeof m.setMap === 'function') m.setMap(null); } catch (e) { }
      }
    }
    delete segmentLayers[segmentId];
  }

  /**
   * 清理所有分段
   */
  function clearAll() {
    for (const id of Object.keys(segmentLayers)) {
      clearSegment(id);
    }
  }

  // panel close handler (will be registered on window)
  function _handlePanelCloseEvent(e) {
    try { _clearSelection() } catch (err) { /* ignore */ }
    try { _stopAutoPlay() } catch (err) { /* ignore */ }
  }

  function _clearAutoPlayTimer() {
    try { if (_playTimer) { clearTimeout(_playTimer); _playTimer = null } } catch (e) { /* ignore */ }
  }

  function _stopAutoPlay() {
    _clearAutoPlayTimer()
    _isPlaying = false
    _playCurrentIndex = -1
    _playSegment = null
  }

  function _scheduleNextInSegment() {
    try {
      if (!_isPlaying || !Array.isArray(lastPoints) || lastPoints.length === 0) { _stopAutoPlay(); return }
      if (!_playSegment) {
        _playSegment = Array.isArray(lastSegments) ? lastSegments.find(s => _playCurrentIndex >= s.startIndex && _playCurrentIndex <= s.endIndex) : null
      }
      if (!_playSegment) { _stopAutoPlay(); return }
      if (_playCurrentIndex >= _playSegment.endIndex) { _stopAutoPlay(); return }
      const cur = lastPoints[_playCurrentIndex]
      const nxt = lastPoints[_playCurrentIndex + 1]
      if (!cur || !nxt) { _stopAutoPlay(); return }
      const delta = Math.max(1, Number(nxt.ts) - Number(cur.ts))
      const delay = Math.max(0, Math.round(delta / (_playSpeed || 1)))
      _clearAutoPlayTimer()
      _playTimer = setTimeout(() => {
        _playTimer = null
        // advance index and open panel for next
        _playCurrentIndex = Math.min(_playSegment.endIndex, _playCurrentIndex + 1)
        try { openForIndex(_playCurrentIndex) } catch (e) { /* ignore */ }
        // schedule further unless stopped
        _scheduleNextInSegment()
      }, delay)
    } catch (e) {
      console.warn('[trackRenderer] autoplay schedule error', e)
      _stopAutoPlay()
    }
  }

  function _startAutoPlayFrom(index) {
    try {
      _stopAutoPlay()
      if (!Array.isArray(lastPoints) || lastPoints.length === 0) return
      const i = Math.max(0, Math.min(index, lastPoints.length - 1))
      _playCurrentIndex = i
      _isPlaying = true
      _playSegment = Array.isArray(lastSegments) ? lastSegments.find(s => i >= s.startIndex && i <= s.endIndex) : null
      if (!_playSegment) { _stopAutoPlay(); return }
      // ensure panel shows current index
      try { openForIndex(_playCurrentIndex) } catch (e) { /* ignore */ }
      // schedule subsequent steps
      _scheduleNextInSegment()
    } catch (e) {
      console.warn('[trackRenderer] startAutoPlay failed', e)
      _stopAutoPlay()
    }
  }

  // open panel for a given index (global helper so autoplay can reuse it)
  function openForIndexGlobal(i) {
    try {
      if (!Array.isArray(lastPoints) || lastPoints.length === 0) {
        return
      }
      const idx = Math.max(0, Math.min(i, lastPoints.length - 1))
      try { const m = _getMarkerForIndex(idx); if (m) _selectMarker(m) } catch (e) { /* ignore */ }

      let onPrevFn = null
      let onNextFn = null
      try {
        if (Array.isArray(lastSegments) && lastSegments.length) {
          const seg = lastSegments.find(s => idx >= s.startIndex && idx <= s.endIndex)
          if (seg) {
            if (idx > seg.startIndex) onPrevFn = () => { _stopAutoPlay(); openForIndexGlobal(idx - 1) }
            if (idx < seg.endIndex) onNextFn = () => { _stopAutoPlay(); openForIndexGlobal(idx + 1) }
          } else {
            onPrevFn = () => { _stopAutoPlay(); openForIndexGlobal(idx - 1) }
            onNextFn = () => { _stopAutoPlay(); openForIndexGlobal(idx + 1) }
          }
        } else {
          onPrevFn = () => { _stopAutoPlay(); openForIndexGlobal(idx - 1) }
          onNextFn = () => { _stopAutoPlay(); openForIndexGlobal(idx + 1) }
        }
      } catch (e) { onPrevFn = () => { _stopAutoPlay(); openForIndexGlobal(idx - 1) }; onNextFn = () => { _stopAutoPlay(); openForIndexGlobal(idx + 1) } }

      const p = showPointPanel({
        title: '轨迹点信息',
        data: lastPoints[idx],
        isPlaying: !!_isPlaying,
        onPrev: onPrevFn,
        onNext: onNextFn,
        onTogglePlay: (playing) => { if (playing) _startAutoPlayFrom(idx); else _stopAutoPlay() }
      })
      if (p && typeof p.finally === 'function') p.finally(() => { try { _clearSelection() } catch (e) {} })
    } catch (e) {
      console.warn('[trackRenderer] openForIndexGlobal failed', e)
    }
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
            // delegate to global implementation that also supports autoplay
            try { openForIndexGlobal(i) } catch (e) { console.warn('[trackRenderer] openForIndex delegate failed', e) }
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
    renderSegment,
    clearSegment,
    clearAll,
    // expose lastPoints for debugging/tests
    _internal: { getLastPoints: () => lastPoints, getLastSegments: () => lastSegments, segmentLayers }
  }
}

export default initTrackRenderer
