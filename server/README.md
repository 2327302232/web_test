# Server (Windows)

1) 安装依赖：

```powershell
cd server
npm install
```

2) 运行：

```powershell
npm run dev
```

3) 验证（在浏览器或 PowerShell 中）：

- `GET http://localhost:8787/api/health`  -> { ok: true }
- `POST http://localhost:8787/api/test/seed` -> seeds 20 gps points
- `GET http://localhost:8787/api/devices` -> list devices with lastTs
- `GET http://localhost:8787/api/track?deviceId=dev-001` -> track points

注意：不要提交 `.env` 或 `server/data/*.sqlite`。

## 长期后端入口（`src/server.js`）

本仓库新增了 `src/server.js` 作为长期运行的后端入口（ESM 风格）。职责仅限于：初始化数据库、启动 MQTT 客户端并注册优雅退出逻辑；不包含 HTTP 路由或其它业务实现。

启动（文档说明，agent 未执行任何命令）：

```powershell
cd server
npm run start
```

主要环境变量（在仓库中被发现并使用）：
- `MQTT_URL`（必需）
- `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_CLIENT_ID`
- `MQTT_TOPIC_PREFIX`（默认 `v1/devices`）
- `MQTT_CA_PATH`（可选，用于 TLS）
- `MQTT_QOS_TELEMETRY`, `MQTT_QOS_CMD`
- `COMMAND_ACK_TIMEOUT_MS`, `RECONNECT_PERIOD_MS`
- `DB_PATH`（可选，覆盖默认的 `server/data/tracks.sqlite`）

本地手动验证检查点（仅文档）：
1) 启动后应看到 `DB initialized.` 或类似日志，表示 `initDb()` 成功执行。
2) 启动后应看到 MQTT client 相关日志，例如 `MQTT connected` 与 `subscribed`，表示已订阅设备主题。
3) 当设备发送 telemetry 时，`[MQTT EVENT] telemetry` 日志会打印接收到的 payload；同时可使用 sqlite3 或 DB 浏览器检查数据是否写入：

示例 sqlite3 查询（仅示例，手动在 server 目录下使用 sqlite3 CLI 或 DB 浏览器运行）：

```
sqlite3 server/data/tracks.sqlite "SELECT * FROM gps_points ORDER BY ts DESC LIMIT 10;"
sqlite3 server/data/tracks.sqlite "SELECT * FROM device_commands ORDER BY ts DESC LIMIT 10;"
```

说明：仓库中仍保留 `test-start.mjs` 作为调试/测试脚本（位于仓库根目录），它也会初始化 DB 并启动 MQTT，用于临时调试。长期运行的服务建议使用 `src/server.js`（并通过 `npm run start` 启动）。
