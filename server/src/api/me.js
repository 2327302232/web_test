import express from 'express'
import { getUserById, listUsers } from '../db.js'

const router = express.Router()

// GET /api/me
// Behavior:
// - If request contains header `X-User-Id` or query `userId`, try to return that user.
// - Otherwise return the first user from DB (development convenience) or 404 when none.

router.get('/api/me', (req, res) => {
  try {
    const uidHeader = req.get('X-User-Id')
    const qid = req.query && req.query.userId ? req.query.userId : null
    const uid = uidHeader || qid
    if (uid) {
      const id = Number(uid)
      if (!Number.isFinite(id)) return res.status(400).json({ error: 'invalid_user_id' })
      const u = getUserById(id)
      if (!u) return res.status(404).json({ error: 'user_not_found' })
      return res.json({ id: u.id, username: u.username, displayName: u.display_name })
    }

    // fallback: return first user for dev convenience
    const users = listUsers({ limit: 1 })
    if (users && users.length > 0) {
      const u = users[0]
      return res.json({ id: u.id, username: u.username, displayName: u.display_name })
    }

    return res.status(404).json({ error: 'no_users' })
  } catch (err) {
    console.error('GET /api/me error', err)
    return res.status(500).json({ error: err?.message || String(err) })
  }
})

export default router
