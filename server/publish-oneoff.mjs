// server/publish-oneoff.mjs
import 'dotenv/config';
import { initDb } from './src/db.js';
import { startMqtt, publishCommand, stopMqtt } from './src/mqtt.js';

async function main() {
  try {
    await initDb();
    await startMqtt();
    const id = await publishCommand({
      deviceId: 'dev001',
      type: 'control',
      action: 'vibrate',
      value: { strength: 2 }
    });
    console.log('published cmdId', id);
    // 等待一小会儿让 publish 完成并触发回调
    await new Promise(r => setTimeout(r, 500));
    await stopMqtt();
    process.exit(0);
  } catch (err) {
    console.error('publish failed', err);
    process.exit(1);
  }
}

main();