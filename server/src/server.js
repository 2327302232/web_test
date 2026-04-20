/*
 * server/src/server.js
 * 长期后端入口（ESM）
 * 职责：
 *  - 在进程启动时调用并等待 `initDb()` 完成；
 *  - 启动 MQTT 客户端（`startMqtt()`）；
 *  - 打印启动日志（DB 初始化成功、MQTT 启动提示）；
 *  - 注册优雅退出（SIGINT / SIGTERM），在退出时停止 MQTT 并关闭 DB 连接。
 *
 * 注意：此文件不实现 HTTP 路由或其它业务逻辑，仅作为长期运行入口。
 */

import 'dotenv/config';
import { initDb, db } from './db.js';
import { startMqtt, stopMqtt, on as onMqtt } from './mqtt.js';
import express from 'express';
import commandRouter from './api/command.js';
import trackRouter from './api/track.js';

let shuttingDown = false;
let httpServer = null;

async function start() {
  try {
    console.log('src/server.js: starting...');

    console.log('src/server.js: initializing DB...');
    await initDb();
    console.log('src/server.js: DB initialized.');

    console.log('src/server.js: starting MQTT client...');
    await startMqtt();
    console.log('src/server.js: MQTT client started (see mqtt logs for subscriptions).');

    // 挂载并启动内置 HTTP 接口（若需要使用 express）
    try {
      const app = express();
      // Simple CORS middleware to allow frontend dev server access.
      app.use((req, res, next) => {
        const allowed = process.env.CORS_ORIGIN || '*';
        res.setHeader('Access-Control-Allow-Origin', allowed);
        res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
        // If you need to support credentials, set Access-Control-Allow-Credentials accordingly and avoid '*'
        if (req.method === 'OPTIONS') return res.sendStatus(204);
        next();
      });
      app.use(express.json({ limit: '1mb' }));
      // 健康检查
      app.get('/api/health', (req, res) => res.json({ ok: true }));
      // mount command router and track router
      app.use(commandRouter);
      app.use(trackRouter);

      const port = process.env.PORT ? Number(process.env.PORT) : 8787;
      httpServer = app.listen(port, () => console.log(`HTTP server listening on port ${port}`));
    } catch (e) {
      console.warn('src/server.js: failed to start HTTP server', e && e.message ? e.message : e);
    }

    // 订阅 MQTT 事件用于运行时日志观察
    onMqtt('telemetry', (p) => console.log('[MQTT EVENT] telemetry', JSON.stringify(p)));
    onMqtt('cmd_ack', async (payload) => {
      console.log('[MQTT EVENT] cmd_ack', JSON.stringify(payload));
      try {
        const cmdId = payload.cmdId || payload.cmd_id || payload.cmd;
        if (!cmdId) {
          console.warn('[ACK] Missing cmdId in payload:', payload);
          return;
        }
        // 幂等策略：若 DB 已有 status='acked'，则忽略后续失败/超时更新，但允许 ok=true 覆盖
        let shouldUpdate = true;
        let currentStatus = null;
        try {
          if (db && typeof db.prepare === 'function') {
            const row = db.prepare('SELECT status FROM device_commands WHERE cmd_id = ?').get(cmdId);
            currentStatus = row ? row.status : null;
            if (currentStatus === 'acked' && payload.ok !== true) {
              shouldUpdate = false;
              console.log(`[ACK] cmdId ${cmdId} 已为 acked，忽略本次 status=${payload.ok ? 'acked' : 'failed'}`);
            }
          }
        } catch (e) {
          console.warn('[ACK] 查询当前命令状态失败:', e);
        }
        if (!shouldUpdate) return;
        // 状态判定
        let status = 'acked';
        if (payload.ok === true) {
          status = 'acked';
        } else if (payload.ok === false && payload.message === 'ack timeout') {
          status = 'failed';
        } else if (payload.ok === false) {
          status = 'failed';
        }
        // ack_ts
        const ackTs = payload.ts != null ? Number(payload.ts) : Date.now();
        // ack_payload
        const ackPayload = JSON.stringify(payload.raw || payload);
        // last_error
        const lastError = payload.ok === false ? (payload.message || 'ACK failed') : undefined;
        // DB 更新
        const { updateCommandStatus } = await import('./db.js');
        try {
          const res = updateCommandStatus({
            cmdId,
            status,
            ackTs,
            ackPayload,
            lastError
          });
          console.log(`[ACK] DB updated for cmdId ${cmdId} -> status ${status}, changes: ${res.changes}`);
        } catch (err) {
          console.error(`[ACK] DB update failed for cmdId ${cmdId}:`, err);
        }
      } catch (e) {
        console.error('[ACK] handler error:', e);
      }
    });
    onMqtt('status', (s) => console.log('[MQTT EVENT] status', JSON.stringify(s)));
    onMqtt('event', (e) => console.log('[MQTT EVENT] event', JSON.stringify(e)));
    onMqtt('error', (err) => console.error('[MQTT EVENT] error', err && err.error ? err.error : err));

    console.log('src/server.js: ready. Waiting for MQTT messages. Press Ctrl+C to stop.');
  } catch (err) {
    console.error('src/server.js: failed to start:', err);
    await shutdown(1);
  }
}

async function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log('src/server.js: shutting down...');

  try {
    // 停止 MQTT
    try {
      const res = stopMqtt();
      if (res && typeof res.then === 'function') await res;
      console.log('src/server.js: MQTT client stopped.');
    } catch (e) {
      console.warn('src/server.js: error while stopping MQTT client:', e);
    }

    // 关闭数据库连接（better-sqlite3 的 close 是同步方法）
    try {
      if (db && typeof db.close === 'function') {
        db.close();
        console.log('src/server.js: database connection closed.');
      } else {
        console.log('src/server.js: no DB connection to close.');
      }
    } catch (e) {
      console.warn('src/server.js: error while closing DB:', e);
    }

    // 关闭 HTTP server（若存在）
    try {
      if (httpServer && typeof httpServer.close === 'function') {
        await new Promise((resolve) => httpServer.close(() => resolve()));
        console.log('src/server.js: HTTP server closed.');
      }
    } catch (e) {
      console.warn('src/server.js: error while closing HTTP server:', e);
    }
  } catch (err) {
    console.error('src/server.js: error during shutdown:', err);
    exitCode = exitCode || 1;
  } finally {
    console.log('src/server.js: exit now.');
    // 确保进程退出
    process.exit(exitCode);
  }
}

process.on('SIGINT', () => { console.log('src/server.js: SIGINT received'); shutdown(0); });
process.on('SIGTERM', () => { console.log('src/server.js: SIGTERM received'); shutdown(0); });
process.on('uncaughtException', (err) => { console.error('src/server.js: uncaughtException', err); shutdown(1); });
process.on('unhandledRejection', (reason) => { console.error('src/server.js: unhandledRejection', reason); shutdown(1); });

// 启动
start();
