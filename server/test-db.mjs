import { initDb, insertGpsPoint, listDevices, getTrack, addDeviceCommand, updateCommandStatus } from './src/db.js';
await initDb();
console.log(await insertGpsPoint({ deviceId: 'dev-001', ts: Date.now(), lng: 116.3, lat: 39.9 }));
console.log(await listDevices());
console.log(await getTrack({ deviceId: 'dev-001' }));
console.log(await addDeviceCommand({ cmdId: 'uuid-test-1', deviceId: 'dev-001', ts: Date.now(), type: 'control', action: 'vibrate', valueJson: {strength:2} }));
console.log(await updateCommandStatus({ cmdId: 'uuid-test-1', status: 'sent', sentTs: Date.now() }));