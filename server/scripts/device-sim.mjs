/**
 * server/scripts/device-sim.mjs
 * 模拟开发板：订阅 v1/devices/{DEVICE_ID}/cmd，收到命令后等待处理延迟再发送 ACK 到 v1/devices/{DEVICE_ID}/ack
 *
 * NOTE:
 * - 配置已直接写入本文件（无需环境变量）。
 * - 把此文件保存到仓库的 server/scripts/ 目录下（若该目录不存在，请创建）。
 * - 运行前请在 server 目录安装依赖（你本地执行：npm install），运行示例见下方说明。
 *
 * 不要在此处运行任何命令；这是交付给你在本机运行的脚本文件内容。
 */

import fs from 'fs';
import path from 'path';
import mqtt from 'mqtt';

// ---------------------------
// 直接内置的配置信息（按你的环境填写）
// ---------------------------
const CONFIG = {
  MQTT_URL: 'mqtts://101.37.104.185:48825',
  MQTT_USERNAME: 'quectel',
  MQTT_PASSWORD: '12345678',
  // 请确保此路径指向存在的 CA 证书文件（Windows 路径示例）
  MQTT_CA_PATH: 'D:\\Downloads\\connectlab_test_certificates (2)\\rsa\\connectlab_rsa_ca.cer',
  MQTT_TOPIC_PREFIX: 'v1/devices',
  DEVICE_ID: 'dev-001',
  PROCESSING_DELAY_MS: 1200, // 收到命令后等待多久再发 ACK（毫秒）
  MQTT_REJECT_UNAUTHORIZED: true // 若使用自签名证书并想忽略验证可改为 false（不建议）
};
// ---------------------------

const {
  MQTT_URL,
  MQTT_USERNAME,
  MQTT_PASSWORD,
  MQTT_CA_PATH,
  MQTT_TOPIC_PREFIX,
  DEVICE_ID,
  PROCESSING_DELAY_MS,
  MQTT_REJECT_UNAUTHORIZED
} = CONFIG;

if (!MQTT_URL) {
  console.error('MQTT_URL 未配置，请在脚本顶部填写 CONFIG 对象。');
  process.exit(1);
}

// 读取 CA（如果提供）
let caBuffer = null;
try {
  if (MQTT_CA_PATH && fs.existsSync(MQTT_CA_PATH)) {
    caBuffer = fs.readFileSync(MQTT_CA_PATH);
    console.log('Loaded CA from', MQTT_CA_PATH);
  } else if (MQTT_CA_PATH) {
    console.warn('CA file not found at', MQTT_CA_PATH);
  }
} catch (e) {
  console.warn('Failed to read CA file:', e && e.message ? e.message : e);
}

const clientId = `device-sim-${DEVICE_ID}-${Date.now()}`;
const mqttOpts = {
  clientId,
  clean: true,
  reconnectPeriod: 2000,
  keepalive: 30,
  rejectUnauthorized: MQTT_REJECT_UNAUTHORIZED
};
if (MQTT_USERNAME) mqttOpts.username = MQTT_USERNAME;
if (MQTT_PASSWORD) mqttOpts.password = MQTT_PASSWORD;
if (caBuffer) mqttOpts.ca = caBuffer;

console.log(`Device simulator config:
  MQTT_URL: ${MQTT_URL}
  DEVICE_ID: ${DEVICE_ID}
  TOPIC PREFIX: ${MQTT_TOPIC_PREFIX}
  PROCESSING_DELAY_MS: ${PROCESSING_DELAY_MS}
  clientId: ${clientId}
`);

const client = mqtt.connect(MQTT_URL, mqttOpts);

client.on('connect', () => {
  console.log('MQTT connected');
  const cmdTopic = `${MQTT_TOPIC_PREFIX}/${DEVICE_ID}/cmd`;
  client.subscribe(cmdTopic, { qos: 1 }, (err, granted) => {
    if (err) {
      console.error('Subscribe error:', err);
    } else {
      console.log('Subscribed to', cmdTopic, 'granted=', granted);
    }
  });
});

client.on('message', (topic, payloadBuf) => {
  let payloadStr = null;
  try {
    payloadStr = payloadBuf && payloadBuf.toString ? payloadBuf.toString() : String(payloadBuf);
  } catch (e) {
    console.warn('Failed to stringify payload buffer:', e && e.message ? e.message : e);
    payloadStr = null;
  }

  let parsed = null;
  try {
    parsed = payloadStr ? JSON.parse(payloadStr) : null;
  } catch (e) {
    console.warn('Received non-JSON payload:', payloadStr);
  }

  console.log('Received message on', topic, 'payload=', parsed ?? payloadStr);

  // 尝试从 payload 中拿到 cmdId
  const cmdId = parsed && (parsed.cmdId ?? parsed.cmd_id ?? parsed.cmd) ? (parsed.cmdId ?? parsed.cmd_id ?? parsed.cmd) : null;
  const deviceIdFromTopic = topic.split('/')[2] || DEVICE_ID;

  // 模拟处理耗时后发送 ACK
  const delay = Number(PROCESSING_DELAY_MS) || 1000;
  setTimeout(() => {
    const ackPayload = {
      deviceId: deviceIdFromTopic,
      cmdId: cmdId,
      ok: true,
      message: 'done',
      ts: Date.now()
    };
    const ackTopic = `${MQTT_TOPIC_PREFIX}/${deviceIdFromTopic}/ack`;
    client.publish(ackTopic, JSON.stringify(ackPayload), { qos: 1 }, (err) => {
      if (err) console.error('Failed to publish ACK:', err && err.message ? err.message : err);
      else console.log('Published ACK to', ackTopic, 'payload=', ackPayload);
    });
  }, delay);
});

client.on('error', (err) => {
  console.error('MQTT client error:', err && err.message ? err.message : err);
});

client.on('close', () => {
  console.log('MQTT connection closed');
});

process.on('SIGINT', () => {
  console.log('SIGINT received: closing MQTT client');
  client.end(true, () => process.exit(0));
});
process.on('SIGTERM', () => {
  console.log('SIGTERM received: closing MQTT client');
  client.end(true, () => process.exit(0));
});