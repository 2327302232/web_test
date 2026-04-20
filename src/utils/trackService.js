// Track service: fetches points from backend and delegates rendering to trackRenderer
import initTrackRenderer from './trackRenderer.js'

export function initTrackService(map) {
  if (!map) throw new Error('map is required')
  const renderer = initTrackRenderer(map)

  async function loadTrack({ deviceId = 'dev-001', from, to, limit } = {}) {
    const backendBase = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8787'
    const params = new URLSearchParams()
    params.set('deviceId', deviceId)
    if (from !== undefined) params.set('from', String(from))
    if (to !== undefined) params.set('to', String(to))
    if (limit !== undefined) params.set('limit', String(limit))
    const url = `${backendBase.replace(/\/$/, '')}/api/track?${params.toString()}`
    console.debug('[trackService] fetching track', url)

    const resp = await fetch(url)
    if (!resp.ok) {
      const err = new Error(`HTTP ${resp.status}`)
      err.status = resp.status
      throw err
    }
    const data = await resp.json()
    const pts = Array.isArray(data.points) ? data.points : []
    const result = await renderer.renderTrack(pts)
    return { result, raw: data }
  }

  function clearTrack() { renderer.clearTrack() }
  function appendPoints(points) { return renderer.appendPoints(points) }

  return { loadTrack, clearTrack, appendPoints, renderer }
}

export default initTrackService
