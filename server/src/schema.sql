-- Schema for GPS points
CREATE TABLE IF NOT EXISTS gps_points (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  lng REAL NOT NULL,
  lat REAL NOT NULL,
  source TEXT DEFAULT 'raw'
);

CREATE INDEX IF NOT EXISTS idx_gps_device_ts ON gps_points(device_id, ts);

-- Table reserved for device commands
CREATE TABLE IF NOT EXISTS device_commands (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cmd_id TEXT NOT NULL UNIQUE,
  device_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  type TEXT NOT NULL,
  action TEXT NOT NULL,
  value_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued'
);

CREATE INDEX IF NOT EXISTS idx_cmd_device_ts ON device_commands(device_id, ts);
