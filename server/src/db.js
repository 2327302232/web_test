/*
 * server/src/db.js
 * SQLite helper for the backend. Provides initDb and DB operations used by mqtt/http layers.
 *
 * Usage example:
 * import { initDb, insertGpsPoint, addDeviceCommand } from './db.js';
 * await initDb();
 * insertGpsPoint({ deviceId: 'dev-001', ts: Date.now(), lng: 116.3, lat: 39.9 });
 * addDeviceCommand({ cmdId: 'uuid-1', deviceId: 'dev-001', ts: Date.now(), type: 'cmd', action: 'beep', valueJson: '{}' });
 *
 * 测试验证指引（在终端手动执行）：
 * 1) 确保在 server 目录依赖已安装（better-sqlite3）。
 * 2) 在 Node 中运行：
 *    import { initDb, insertGpsPoint, listDevices, getTrack, addDeviceCommand, updateCommandStatus } from './src/db.js';
 *    await initDb();
 *    insertGpsPoint({ deviceId: 'dev-001', ts: Date.now(), lng: 116.3, lat: 39.9 });
 *    console.log(await listDevices());
 *    console.log(await getTrack({ deviceId: 'dev-001' }));
 *    addDeviceCommand({ cmdId: 'uuid-1', deviceId: 'dev-001', ts: Date.now(), type: 'cmd', action: 'do', valueJson: '{}' });
 *    updateCommandStatus({ cmdId: 'uuid-1', status: 'sent', sentTs: Date.now() });
 * 3) 使用 sqlite3 CLI 或 DB 浏览器打开 server/data/tracks.sqlite 验证表结构与数据。
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import Database from 'better-sqlite3';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let db = null;
const stmts = {};

function prepareStatements() {
  stmts.insertGps = db.prepare(`INSERT INTO gps_points (device_id, ts, lng, lat, speed, heading, altitude, accuracy, battery, status, source, raw_json, created_at)
    VALUES (@device_id, @ts, @lng, @lat, @speed, @heading, @altitude, @accuracy, @battery, @status, @source, @raw_json, @created_at)`);

  stmts.listDevices = db.prepare(`SELECT device_id AS deviceId, MAX(ts) AS lastTs FROM gps_points GROUP BY device_id ORDER BY lastTs DESC LIMIT @limit`);

  stmts.getTrack = db.prepare(`SELECT ts, lng, lat, speed, battery, status FROM gps_points
    WHERE device_id = @device_id AND ts >= @from AND ts <= @to ORDER BY ts ASC LIMIT @limit`);

  stmts.insertCmd = db.prepare(`INSERT INTO device_commands (cmd_id, device_id, ts, type, action, value_json, status, retries)
    VALUES (@cmd_id, @device_id, @ts, @type, @action, @value_json, @status, @retries)`);

  stmts.getCmdById = db.prepare(`SELECT * FROM device_commands WHERE cmd_id = @cmd_id`);

  stmts.getPending = db.prepare(`SELECT * FROM device_commands WHERE device_id = @device_id AND status IN ('queued','sent') ORDER BY ts ASC`);
}

/**
 * Initialize the database.
 * - 使用 process.env.DB_PATH（若无则使用 server/data/tracks.sqlite）
 * - 确保 data 目录存在
 * - 设置 PRAGMA 并执行 server/src/schema.sql（如存在）
 * @param {Object} [options] Optional options forwarded to better-sqlite3 constructor as second arg (not required)
 * @returns {Database} better-sqlite3 Database 实例
 */
export async function initDb(options = {}) {
  if (db) return db;

  const envPath = process.env.DB_PATH;
  const dbPath = envPath ? (path.isAbsolute(envPath) ? envPath : path.resolve(envPath)) : path.resolve(__dirname, '..', 'data', 'tracks.sqlite');
  const dataDir = path.dirname(dbPath);
  fs.mkdirSync(dataDir, { recursive: true });

  db = new Database(dbPath, options.openOptions || {});

  try {
    db.pragma('journal_mode = WAL');
    db.pragma('busy_timeout = 5000');
    db.pragma('synchronous = NORMAL');
  } catch (err) {
    console.warn('Failed to apply PRAGMA:', err && err.message ? err.message : err);
  }

  const schemaPath = path.resolve(__dirname, 'schema.sql');
  if (fs.existsSync(schemaPath)) {
    const sql = fs.readFileSync(schemaPath, 'utf8');
    try {
      db.exec(sql);
    } catch (err) {
      console.error('Failed to execute schema.sql:', err && err.message ? err.message : err);
      throw err;
    }
  } else {
    console.warn('schema.sql not found at', schemaPath);
  }

  prepareStatements();

  try {
    const jm = db.pragma('journal_mode');
    const bt = db.pragma('busy_timeout');
    const sync = db.pragma('synchronous');
    console.log(`Using DB path: ${dbPath}`);
    console.log('PRAGMA journal_mode:', jm);
    console.log('PRAGMA busy_timeout:', bt);
    console.log('PRAGMA synchronous:', sync);
  } catch (err) {
    console.log(`Using DB path: ${dbPath}`);
  }

  return db;
}

/**
 * Insert a GPS point into gps_points.
 * @param {Object} param
 * @param {string} param.deviceId
 * @param {number} param.ts
 * @param {number} param.lng
 * @param {number} param.lat
 * @param {number} [param.speed]
 * @param {number} [param.heading]
 * @param {number} [param.altitude]
 * @param {number} [param.accuracy]
 * @param {number} [param.battery]
 * @param {string} [param.status]
 * @param {string} [param.source]
 * @param {string} [param.rawJson]
 * @param {number} [param.createdAt]
 * @returns {{lastInsertRowid:number,changes:number}} 返回插入信息。发生错误时抛出异常。
 */
export function insertGpsPoint({ deviceId, ts, lng, lat, speed = null, heading = null, altitude = null, accuracy = null, battery = null, status = 'ok', source = 'raw', rawJson = null, createdAt = null } = {}) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  if (!deviceId || ts == null || lng == null || lat == null) {
    throw new Error('Missing required fields: deviceId, ts, lng, lat');
  }
  try {
    const info = stmts.insertGps.run({
      device_id: String(deviceId),
      ts: Number(ts),
      lng: Number(lng),
      lat: Number(lat),
      speed: speed == null ? null : Number(speed),
      heading: heading == null ? null : Number(heading),
      altitude: altitude == null ? null : Number(altitude),
      accuracy: accuracy == null ? null : Number(accuracy),
      battery: battery == null ? null : Number(battery),
      status: status == null ? 'ok' : String(status),
      source: source == null ? 'raw' : String(source),
      raw_json: rawJson == null ? null : String(rawJson),
      created_at: createdAt == null ? null : Number(createdAt)
    });
    return { lastInsertRowid: info.lastInsertRowid, changes: info.changes };
  } catch (err) {
    throw err;
  }
}

/**
 * List devices with their latest timestamp.
 * @param {Object} [opt]
 * @param {number} [opt.limit=100]
 * @returns {Array<{deviceId:string,lastTs:number}>}
 */
export function listDevices({ limit = 100 } = {}) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  const rows = stmts.listDevices.all({ limit: Number(limit) });
  return rows.map(r => ({ deviceId: r.deviceId, lastTs: r.lastTs }));
}

/**
 * Get track points for a device in a time range [from, to]
 * @param {Object} opt
 * @param {string} opt.deviceId
 * @param {number} [opt.from=0]
 * @param {number} [opt.to=Number.MAX_SAFE_INTEGER]
 * @param {number} [opt.limit=5000]
 * @returns {Array<object>} rows
 */
export function getTrack({ deviceId, from = 0, to = Number.MAX_SAFE_INTEGER, limit = 5000 } = {}) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  if (!deviceId) throw new Error('deviceId is required.');
  const rows = stmts.getTrack.all({ device_id: String(deviceId), from: Number(from), to: Number(to), limit: Number(limit) });
  return rows;
}

/**
 * Add a device command. 对重复 cmdId 返回已有记录以保证幂等性。
 * @param {Object} param
 * @param {string} param.cmdId
 * @param {string} param.deviceId
 * @param {number} param.ts
 * @param {string} param.type
 * @param {string} param.action
 * @param {string} param.valueJson
 * @returns {{lastInsertRowid?:number,cmdId?:string,existing?:boolean,row?:object}}
 */
export function addDeviceCommand({ cmdId, deviceId, ts, type, action, valueJson } = {}) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  if (!cmdId || !deviceId || ts == null || !type || !action || valueJson == null) {
    throw new Error('Missing required fields for addDeviceCommand: cmdId, deviceId, ts, type, action, valueJson');
  }
  try {
    const info = stmts.insertCmd.run({ cmd_id: String(cmdId), device_id: String(deviceId), ts: Number(ts), type: String(type), action: String(action), value_json: String(valueJson), status: 'queued', retries: 0 });
    return { lastInsertRowid: info.lastInsertRowid, cmdId };
  } catch (err) {
    // 约定：若为唯一约束冲突，则返回已有记录，便于幂等。
    if (err && err.message && (err.message.includes('UNIQUE') || err.message.includes('constraint'))) {
      const row = stmts.getCmdById.get({ cmd_id: String(cmdId) });
      return { existing: true, row };
    }
    throw err;
  }
}

/**
 * Update command status fields by cmdId. 只更新提供的字段。
 * @param {Object} param
 * @param {string} param.cmdId
 * @param {string} [param.status]
 * @param {number} [param.sentTs]
 * @param {number} [param.ackTs]
 * @param {string} [param.ackPayload]
 * @param {number} [param.retries]
 * @param {string} [param.lastError]
 * @returns {{changes:number}} 返回受影响行数。
 */
export function updateCommandStatus({ cmdId, status, sentTs, ackTs, ackPayload, retries, lastError } = {}) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  if (!cmdId) throw new Error('cmdId is required.');
  const sets = [];
  const params = { cmd_id: String(cmdId) };
  if (status !== undefined) { sets.push('status = @status'); params.status = String(status); }
  if (sentTs !== undefined) { sets.push('sent_ts = @sent_ts'); params.sent_ts = sentTs == null ? null : Number(sentTs); }
  if (ackTs !== undefined) { sets.push('ack_ts = @ack_ts'); params.ack_ts = ackTs == null ? null : Number(ackTs); }
  if (ackPayload !== undefined) { sets.push('ack_payload = @ack_payload'); params.ack_payload = ackPayload == null ? null : String(ackPayload); }
  if (retries !== undefined) { sets.push('retries = @retries'); params.retries = retries == null ? null : Number(retries); }
  if (lastError !== undefined) { sets.push('last_error = @last_error'); params.last_error = lastError == null ? null : String(lastError); }
  if (sets.length === 0) throw new Error('No fields to update provided.');
  const sql = `UPDATE device_commands SET ${sets.join(', ')} WHERE cmd_id = @cmd_id`;
  const stmt = db.prepare(sql);
  const info = stmt.run(params);
  return { changes: info.changes };
}

/**
 * Get pending commands for a device (status IN ('queued','sent')).
 * @param {Object} param
 * @param {string} param.deviceId
 * @returns {Array<object>}
 */
export function getPendingCommands({ deviceId } = {}) {
  if (!db) throw new Error('Database not initialized. Call initDb() first.');
  if (!deviceId) throw new Error('deviceId is required.');
  return stmts.getPending.all({ device_id: String(deviceId) });
}

export { db };

// 我已完成：server/src/schema.sql 和 server/src/db.js（不包含 git 操作）
