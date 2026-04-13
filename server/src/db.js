import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import Database from 'better-sqlite3';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const defaultDataDir = path.join(__dirname, '..', 'data');

let db = null;

export function initDb() {
  const dbPath = process.env.DB_PATH ? path.resolve(process.env.DB_PATH) : path.join(defaultDataDir, 'tracks.sqlite');

  if (!fs.existsSync(defaultDataDir)) {
    fs.mkdirSync(defaultDataDir, { recursive: true });
  }

  db = new Database(dbPath);

  const schemaPath = path.join(__dirname, 'schema.sql');
  if (fs.existsSync(schemaPath)) {
    const sql = fs.readFileSync(schemaPath, 'utf8');
    db.exec(sql);
  }

  return db;
}

export function insertGpsPoint({ deviceId, ts, lng, lat, source = 'raw' }) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  const stmt = db.prepare('INSERT INTO gps_points (device_id, ts, lng, lat, source) VALUES (?, ?, ?, ?, ?)');
  const info = stmt.run(deviceId, ts, lng, lat, source);
  return info.lastInsertRowid;
}

export function listDevices({ limit = 100 } = {}) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  const stmt = db.prepare('SELECT device_id AS deviceId, MAX(ts) AS lastTs FROM gps_points GROUP BY device_id ORDER BY lastTs DESC LIMIT ?');
  return stmt.all(limit);
}

export function getTrack({ deviceId, from, to, limit = 5000 } = {}) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  if (!deviceId) return [];

  const parts = ['device_id = ?'];
  const params = [deviceId];

  if (typeof from === 'number') {
    parts.push('ts >= ?');
    params.push(from);
  }
  if (typeof to === 'number') {
    parts.push('ts <= ?');
    params.push(to);
  }

  const where = parts.length ? ('WHERE ' + parts.join(' AND ')) : '';
  const sql = `SELECT ts, lng, lat FROM gps_points ${where} ORDER BY ts ASC LIMIT ?`;
  params.push(limit);
  const stmt = db.prepare(sql);
  return stmt.all(...params);
}
