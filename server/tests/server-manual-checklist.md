# Server 手动检查清单（server/tests/server-manual-checklist.md）

此文件包含手动验证长期入口 `src/server.js` 的清单与排错提示（仅文档，不执行）。

1) 启动服务

```powershell
cd server
npm run start
```

2) 启动后应观察到日志：
- `DB initialized.` —— 表示 `initDb()` 成功
- `MQTT connected` 与若干 `subscribed` 日志 —— 表示 MQTT 已连接并订阅主题
- 若收到设备数据，会看到 `[MQTT EVENT] telemetry` 或其它事件日志

3) 使用 sqlite3 验证数据写入（示例命令，手动运行）：

```
sqlite3 server/data/tracks.sqlite "SELECT device_id, ts, lng, lat FROM gps_points ORDER BY ts DESC LIMIT 10;"
sqlite3 server/data/tracks.sqlite "SELECT cmd_id, device_id, status, ts FROM device_commands ORDER BY ts DESC LIMIT 10;"
```

4) 常见问题与排查
- 未看到 `MQTT connected`：确认 `MQTT_URL` 环境变量是否设置正确，检查网络与 TLS（若使用 `MQTT_CA_PATH`）。
- 订阅失败或被踢下线：检查 `MQTT_CLIENT_ID` 是否与其他客户端冲突（重复 clientId 会被 broker 踢）。
- DB 初始化失败：检查 `DB_PATH` 指向是否有效；确认 `server/data` 目录具有写权限。
- 收到 telemetry 但未写入 DB：查看运行日志中的错误（`[MQTT EVENT] error`），并确认 payload 格式是否包含经纬度字段（`lng`/`lat` 或 `lon`/`lat`）。

5) 其它建议
- 使用 `test-start.mjs`（根目录）做快速调试，但 `src/server.js` 为长期运行入口并已在 `package.json` 中添加 `start` 脚本。
