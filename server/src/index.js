import http from 'http';
import { URL } from 'url';
import { fileURLToPath } from 'url';
import path from 'path';
import { initDb, insertGpsPoint, listDevices, getTrack } from './db.js';

const PORT = process.env.PORT ? Number(process.env.PORT) : 8787;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const defaultDbPath = process.env.DB_PATH ? path.resolve(process.env.DB_PATH) : path.join(__dirname, '..', 'data', 'tracks.sqlite');

initDb();

console.log(`Server starting on port ${PORT}`);
console.log(`Using DB path: ${defaultDbPath}`);

function jsonResponse(res, statusCode, obj) {
  res.statusCode = statusCode;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(obj));
}

const server = http.createServer(async (req, res) => {
  try {
    const base = `http://${req.headers.host || 'localhost'}`;
    const url = new URL(req.url, base);

    if (req.method === 'GET' && url.pathname === '/api/health') {
      return jsonResponse(res, 200, { ok: true });
    }

    if (req.method === 'POST' && url.pathname === '/api/test/seed') {
      const now = Date.now();
      const baseLng = 116.397428;
      const baseLat = 39.90923;
      for (let i = 0; i < 20; i++) {
        const ts = now + i * 1000;
        const lng = baseLng + (Math.random() - 0.5) * 0.002;
        const lat = baseLat + (Math.random() - 0.5) * 0.002;
        insertGpsPoint({ deviceId: 'dev-001', ts, lng, lat, source: 'seed' });
      }
      return jsonResponse(res, 200, { inserted: 20 });
    }

    if (req.method === 'GET' && url.pathname === '/api/devices') {
      const limit = Number(url.searchParams.get('limit')) || 100;
      const devices = listDevices({ limit });
      return jsonResponse(res, 200, devices);
    }

    if (req.method === 'GET' && url.pathname === '/api/track') {
      const deviceId = url.searchParams.get('deviceId');
      if (!deviceId) {
        return jsonResponse(res, 400, { error: 'deviceId is required' });
      }
      const fromParam = url.searchParams.get('from');
      const toParam = url.searchParams.get('to');
      const limit = Number(url.searchParams.get('limit')) || 5000;

      const now = Date.now();
      const from = fromParam ? Number(fromParam) : now - 3600 * 1000;
      const to = toParam ? Number(toParam) : now;

      if (Number.isNaN(from) || Number.isNaN(to)) {
        return jsonResponse(res, 400, { error: 'from/to must be unix ms integers' });
      }

      const rows = getTrack({ deviceId, from, to, limit });
      return jsonResponse(res, 200, rows);
    }

    jsonResponse(res, 404, { error: 'Not found' });
  } catch (err) {
    console.error(err);
    jsonResponse(res, 500, { error: err.message });
  }
});

server.listen(PORT, () => {
  console.log(`Listening on http://localhost:${PORT}`);
});
