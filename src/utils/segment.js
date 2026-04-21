// Utilities to preprocess points and split a track into segments by time gap

function _normalizeTs(raw) {
  const n = Number(raw)
  if (!Number.isFinite(n)) return NaN
  return n < 1e12 ? Math.round(n * 1000) : Math.round(n)
}

function preprocessPoints(points) {
  const out = []
  if (!Array.isArray(points)) return out
  for (const pt of points) {
    if (!pt) continue
    const ts = _normalizeTs(pt.ts)
    const lng = Number(pt.lng)
    const lat = Number(pt.lat)
    if (!Number.isFinite(ts) || !Number.isFinite(lng) || !Number.isFinite(lat)) continue
    if (lng < -180 || lng > 180 || lat < -90 || lat > 90) continue
    out.push(Object.assign({}, pt, { ts: ts, lng: Number(lng), lat: Number(lat) }))
  }
  // sort by ts asc
  out.sort((a, b) => a.ts - b.ts)
  // minimal adjacent dedupe: same lng/lat and ts diff < 1 ms
  const dedup = []
  for (const p of out) {
    const prev = dedup[dedup.length - 1]
    if (prev && prev.lng === p.lng && prev.lat === p.lat && Math.abs(p.ts - prev.ts) < 1) {
      continue
    }
    dedup.push(p)
  }
  return dedup
}

/**
 * Split preprocessed points into segments when time gap between adjacent points > gapMs.
 * Returns array of { startIndex, endIndex, points }
 */
export function splitByGap(preprocessedPoints, gapMs = 30 * 60 * 1000) {
  const segments = []
  if (!Array.isArray(preprocessedPoints) || preprocessedPoints.length === 0) return segments
  let startIdx = 0
  let curr = [preprocessedPoints[0]]
  for (let i = 1; i < preprocessedPoints.length; i++) {
    const prev = preprocessedPoints[i - 1]
    const cur = preprocessedPoints[i]
    if (cur.ts - prev.ts > gapMs) {
      segments.push({ startIndex: startIdx, endIndex: startIdx + curr.length - 1, points: curr.slice() })
      startIdx += curr.length
      curr = [cur]
    } else {
      curr.push(cur)
    }
  }
  segments.push({ startIndex: startIdx, endIndex: startIdx + curr.length - 1, points: curr.slice() })
  return segments
}

/**
 * Convenience: take raw points, preprocess them, then split into segments.
 * Returns { cleanPoints, segments }
 */
export function segmentTrack(rawPoints, gapMs = 30 * 60 * 1000) {
  const clean = preprocessPoints(rawPoints)
  const segments = splitByGap(clean, gapMs)
  return { cleanPoints: clean, segments }
}

export default { preprocessPoints, splitByGap, segmentTrack }
