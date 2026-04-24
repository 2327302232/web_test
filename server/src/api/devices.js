import express from 'express'
import { addDevice, getDevice, listRegisteredDevices, updateDevice, removeDevice } from '../db.js'

const router = express.Router()

// GET /api/devices?limit=100&offset=0
router.get('/api/devices', async (req, res) => {
  try {
    const { limit, offset } = req.query || {}
    const opt = {}
    if (limit !== undefined) opt.limit = Number(limit)
    if (offset !== undefined) opt.offset = Number(offset)
    const rows = listRegisteredDevices(opt)
    return res.json({ devices: rows })
  } catch (err) {
    console.error('GET /api/devices error', err)
    return res.status(500).json({ error: err?.message || String(err) })
  }
})

// GET /api/devices/:deviceId
router.get('/api/devices/:deviceId', async (req, res) => {
  try {
    const { deviceId } = req.params
    const row = getDevice(deviceId)
    if (!row) return res.status(404).json({ error: 'not_found' })
    return res.json({ device: row })
  } catch (err) {
    console.error('GET /api/devices/:deviceId error', err)
    return res.status(500).json({ error: err?.message || String(err) })
  }
})

// POST /api/devices
router.post('/api/devices', async (req, res) => {
  try {
    const body = req.body || {}
    const { deviceId, serial, name, userId, metadata } = body
    if (!deviceId || typeof deviceId !== 'string') return res.status(400).json({ error: 'deviceId (string) is required' })
    const added = addDevice({ deviceId, serial, name, userId, metadata, createdAt: Date.now() })
    if (added && added.existing) return res.status(200).json({ device: added.row, existing: true })
    const row = getDevice(deviceId)
    return res.status(201).json({ device: row })
  } catch (err) {
    console.error('POST /api/devices error', err)
    return res.status(500).json({ error: err?.message || String(err) })
  }
})

// PUT /api/devices/:deviceId
router.put('/api/devices/:deviceId', async (req, res) => {
  try {
    const { deviceId } = req.params
    const updates = req.body || {}
    const result = updateDevice(deviceId, updates)
    return res.json(result)
  } catch (err) {
    console.error('PUT /api/devices/:deviceId error', err)
    return res.status(500).json({ error: err?.message || String(err) })
  }
})

// DELETE /api/devices/:deviceId
router.delete('/api/devices/:deviceId', async (req, res) => {
  try {
    const { deviceId } = req.params
    const result = removeDevice(deviceId)
    return res.json(result)
  } catch (err) {
    console.error('DELETE /api/devices/:deviceId error', err)
    return res.status(500).json({ error: err?.message || String(err) })
  }
})

export default router
