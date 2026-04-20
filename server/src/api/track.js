import express from 'express'
import { getTrack } from '../db.js'

const router = express.Router()

// GET /api/track?deviceId=dev-001&from=...&to=...&limit=...
router.get('/api/track', async (req, res) => {
  try {
    const { deviceId, from, to, limit } = req.query || {}
    if (!deviceId) return res.status(400).json({ error: 'deviceId is required' })
    const opt = { deviceId }
    if (from !== undefined) opt.from = Number(from)
    if (to !== undefined) opt.to = Number(to)
    if (limit !== undefined) opt.limit = Number(limit)
    const rows = getTrack(opt)
    return res.json({ deviceId: String(deviceId), points: rows })
  } catch (err) {
    console.error('GET /api/track error', err)
    return res.status(500).json({ error: err?.message || String(err) })
  }
})

export default router
