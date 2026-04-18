// test-start.mjs
// 用法：在 server 目录运行 `npm install dotenv`（若尚未安装），然后 `node test-start.mjs`
// 脚本功能：初始化 DB、启动 MQTT 客户端，并把常见事件输出到控制台，便于调试。

import 'dotenv/config'; // 如果不想用 dotenv，可以通过 shell export 环境变量再运行本文件
import { initDb } from './src/db.js';
import { startMqtt, stopMqtt, on as onMqtt } from './src/mqtt.js';

async function main() {
  try {
    console.log('Initializing DB...');
    await initDb();
    console.log('DB initialized.');

    console.log('Starting MQTT client...');
    await startMqtt();
    console.log('MQTT client started.');

    // 订阅事件并打印，便于观察
    onMqtt('telemetry', (p) => {
      console.log('[EVENT] telemetry', JSON.stringify(p));
    });
    onMqtt('cmd_ack', (a) => {
      console.log('[EVENT] cmd_ack', JSON.stringify(a));
    });
    onMqtt('status', (s) => {
      console.log('[EVENT] status', JSON.stringify(s));
    });
    onMqtt('event', (e) => {
      console.log('[EVENT] device event', JSON.stringify(e));
    });
    onMqtt('error', (err) => {
      console.error('[EVENT] mqtt error', err && err.error ? err.error : err);
    });

    console.log('Ready. Waiting for MQTT messages. Press Ctrl+C to stop.');
  } catch (err) {
    console.error('Failed to start test script:', err);
    process.exit(1);
  }
}

// 优雅关闭
async function shutdown() {
  try {
    console.log('Shutting down...');
    await stopMqtt();
    console.log('MQTT client stopped.');
    process.exit(0);
  } catch (err) {
    console.error('Error during shutdown', err);
    process.exit(1);
  }
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

main();