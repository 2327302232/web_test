// Track renderer helper for drawing GPS tracks on AMap map instances.
// Exports: initTrackRenderer(map) -> { renderTrack, clearTrack, appendPoints }
import { addPolyline, createMarker } from './amap.js'

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

  let currentPolyline = null
  let startMarker = null
  let endMarker = null
  let singleMarker = null
  let lastPoints = []

  function clearTrack() {
    try {
      if (currentPolyline && typeof currentPolyline.setMap === 'function') currentPolyline.setMap(null)
      if (startMarker && typeof startMarker.setMap === 'function') startMarker.setMap(null)
      if (endMarker && typeof endMarker.setMap === 'function') endMarker.setMap(null)
      if (singleMarker && typeof singleMarker.setMap === 'function') singleMarker.setMap(null)
    } catch (e) {
      console.warn('[trackRenderer] clear error', e)
    } finally {
      currentPolyline = null
      startMarker = null
      endMarker = null
      singleMarker = null
      lastPoints = []
    }
  }

  function _createMarkerAtPoint(p, opts = {}) {
    try {
      return createMarker(map, [p.lng, p.lat], opts)
    } catch (e) {
      console.warn('[trackRenderer] createMarker failed', e)
      return null
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

      if (clean.length === 1) {
        singleMarker = _createMarkerAtPoint(clean[0], { title: 'track point' })
        lastPoints = clean
        console.debug('[trackRenderer] rendered single marker')
        resolve({ rendered: true, type: 'single', points: clean })
        return
      }

      // use array pairs ([lng, lat]) which AMap reliably accepts
      const path = clean.map(p => [Number(p.lng), Number(p.lat)])

      try {
        const polylineOpts = Object.assign({ strokeColor: '#ff8800', strokeWeight: 2, strokeOpacity: 1 }, options.polyline || {})
        currentPolyline = addPolyline(map, path, polylineOpts)
        // try fitting map view to the drawn polyline; fall back to bbox-based center/zoom
        try {
          if (map && typeof map.setFitView === 'function') {
            map.setFitView([currentPolyline])
          }
        } catch (e2) {
          console.warn('[trackRenderer] setFitView failed, falling back to bbox fit', e2)
          try {
            // compute bounding box
            let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity
            for (const pt of path) {
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

      // start / end markers
      startMarker = _createMarkerAtPoint(clean[0], { title: 'start' })
      endMarker = _createMarkerAtPoint(clean[clean.length - 1], { title: 'end' })

      lastPoints = clean
      console.debug('[trackRenderer] rendered polyline points', path.length)
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
    _internal: { getLastPoints: () => lastPoints }
  }
}

export default initTrackRenderer
