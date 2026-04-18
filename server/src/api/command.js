/*
 * server/src/api/command.js
 * Express router: POST /api/command
 *
 * 行为：
 *  - 验证请求体（deviceId, type, action 必需）
 *  - 生成 cmdId（UUIDv4 via crypto.randomUUID）
 *  - 调用 addDeviceCommand 写入 device_commands（status=queued）
 *  - 调用 publishCommand 发布到 MQTT（传入 cmdId）并等待结果
 *  - 根据 publish 结果返回 { cmdId, status }，并在失败时更新 DB status->failed
 */

import express from 'express';
import crypto from 'crypto';
import { addDeviceCommand, updateCommandStatus } from '../db.js';
import { publishCommand } from '../mqtt.js';

const router = express.Router();

router.post('/api/command', async (req, res) => {
  console.log('HTTP POST /api/command received');
  const body = req.body || {};
  const { deviceId, type, action, value } = body;
  const errors = [];
  if (!deviceId || typeof deviceId !== 'string') errors.push('deviceId (string) is required');
  if (!type || typeof type !== 'string') errors.push('type (string) is required');
  if (!action || typeof action !== 'string') errors.push('action (string) is required');
  if (errors.length) return res.status(400).json({ error: 'validation', details: errors });

  const cmdId = (crypto && typeof crypto.randomUUID === 'function') ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const ts = Date.now();

  try {
    const addRes = addDeviceCommand({ cmdId, deviceId, ts, type, action, valueJson: value });
    console.log('addDeviceCommand result', addRes && addRes.existing ? 'existing' : 'inserted', cmdId);
  } catch (err) {
    console.error('Failed to addDeviceCommand', err && err.message ? err.message : err);
    try { updateCommandStatus({ cmdId, status: 'failed', lastError: err && err.message ? err.message : String(err) }); } catch (e) {}
    return res.status(500).json({ cmdId, status: 'failed', error: 'db write failed' });
  }

  // 使用 mqtt.publishCommand 发布（publishCommand 内部也会处理 DB 状态更新为 sent/failed）
  try {
    const publishedCmdId = await publishCommand({ deviceId, cmdId, type, action, value });
    return res.status(200).json({ cmdId: publishedCmdId, status: 'sent' });
  } catch (err) {
    console.error('publishCommand failed', err && err.message ? err.message : err);
    try { updateCommandStatus({ cmdId, status: 'failed', lastError: err && err.message ? err.message : String(err) }); } catch (e) {}
    return res.status(500).json({ cmdId, status: 'failed', error: err && err.message ? err.message : String(err) });
  }
});

export default router;
