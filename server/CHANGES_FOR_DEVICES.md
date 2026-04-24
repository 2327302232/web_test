变更说明：新增设备信息表与设备级序号表（device_sequences）

目的
- 在后端数据库中新增 `devices` 表用于存放设备元信息（device_id、serial、name、user_id、metadata、created_at）。
- 新增 `device_sequences` 表用于应用层按 `(table_name, device_id)` 管理自定义序号（替代直接修改 sqlite_sequence）。

已修改文件
- `server/src/schema.sql`：追加 `devices` 与 `device_sequences` 表定义与索引（使用 IF NOT EXISTS，安全执行）。
- `server/src/db.js`：增加 prepared statements 与导出函数，包含：
  - `addDevice`, `getDevice`, `listRegisteredDevices`, `updateDevice`, `removeDevice`
  - `getDeviceSequence`, `setDeviceSequence`, `incDeviceSequence`
- `server/src/api/devices.js`：新增 HTTP CRUD 接口，路径以 `/api/devices` 开头。
- `server/src/server.js`：挂载 `devices` 路由。

安全与回滚
1. 已经建议并完成数据库备份（`server/data/tracks.sqlite.bak`）。如需回滚：停止服务并把该备份文件复制回 `server/data/tracks.sqlite`。

如何验证（手动步骤示例）
1. 启动前请先停止正在运行的后端（如有）。
2. 在 `server` 目录（或使用合适的 NODE 环境）运行：
```
node -e "import('./src/db.js').then(async m=>{await m.initDb(); console.log('initDb done'); process.exit()})"
```
3. 用 sqlite CLI 或 DB 浏览器检查表结构：
   - 查看 `devices` 表：`PRAGMA table_info('devices');`
   - 查看 `device_sequences` 表：`PRAGMA table_info('device_sequences');`
4. 使用 HTTP 接口（若后端已启动）进行测试：
   - POST /api/devices  创建设备：{ "deviceId":"dev-001","serial":"S123","name":"Test" }
   - GET /api/devices  列表设备
   - GET /api/devices/dev-001  查看设备详情
   - PUT /api/devices/dev-001  更新设备字段
   - DELETE /api/devices/dev-001  删除设备

注意事项
- 我没有修改 sqlite 的内部系统表 `sqlite_sequence`。如需设备级自增序号，请使用 `device_sequences` 表（已实现 `incDeviceSequence` 等函数）。
- 我没有启动或停止任何服务、也没有执行数据库迁移命令；请在本地按上述验证步骤运行并确认。
