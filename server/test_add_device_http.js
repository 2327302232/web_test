#!/usr/bin/env node
const base = 'http://localhost:8788';

async function run() {
  try {
    // 请根据当前登录的用户 id 调整 userId。测试中我使用 testuser_http 的 id=3（如已创建）。
    const body = { deviceId: 'dev-frontend-1', name: 'Frontend Device 1', serial: 'SN-FFF-1', userId: 3 };
    console.log('POST /api/devices ->', JSON.stringify(body));
    const res = await fetch(`${base}/api/devices`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    console.log('status:', res.status);
    const j = await res.json();
    console.log('body:', JSON.stringify(j));
  } catch (err) {
    console.error('error', err);
    process.exit(1);
  }
}

run();
