#!/usr/bin/env node
import { initDb, insertGpsPoint } from '../src/db.js'

async function main() {
  await initDb()
  const now = Date.now()
  const baseLng = 113.3931
  const baseLat = 23.0394
  const deviceId = process.argv[2] || 'dev-001'

  const points = [
    { ts: now - 60000, lng: baseLng, lat: baseLat, speed: 0, battery: 100 },
    { ts: now - 30000, lng: baseLng + 0.001, lat: baseLat + 0.001, speed: 2, battery: 99 },
    { ts: now, lng: baseLng + 0.002, lat: baseLat + 0.0015, speed: 3, battery: 98 }
  ]

  for (const p of points) {
    try {
      const res = insertGpsPoint({ deviceId, ts: p.ts, lng: p.lng, lat: p.lat, speed: p.speed, battery: p.battery, status: 'ok', source: 'script', rawJson: JSON.stringify(p), createdAt: Date.now() })
      console.log('inserted', p, '->', res)
    } catch (e) {
      console.error('insert failed', e && e.message ? e.message : e)
    }
  }

  console.log('done')
}

main().catch((e) => { console.error(e); process.exit(1) })
