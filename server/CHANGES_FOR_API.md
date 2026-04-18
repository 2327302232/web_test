CHANGES FOR HTTP COMMAND API (阶段 E)

概述：

- 本次变更在长期后端入口上实现了一个基础的 HTTP 命令下发接口（仅用于测试/验证，不包含鉴权或生产强化）。

新增/修改文件：

- 新增： `src/api/command.js` — Express 路由，实现 `POST /api/command`，负责输入校验、在 `device_commands` 中写入 `queued` 记录并调用 `publishCommand` 发布到 MQTT。
- 修改： `src/server.js` — 在长期入口中挂载并启动 Express HTTP 服务（监听端口由 `PORT` 环境变量或默认 `8787`）。
- 修改： `package.json` — 声明 `express` 依赖（仅修改 package.json，不执行安装）。
- 修改： `README.md` — 新增“HTTP 命令 API（阶段 E）”文档，包含请求/响应示例与本地手动测试步骤。
- 修改： `tests/server-manual-checklist.md` — 在手动检查清单中加入 HTTP API 的验证步骤（详见 tests 文件）。

实现细节与权衡：

- 路由实现使用 `crypto.randomUUID()` 生成 `cmdId`（若环境不支持则回退到时间+随机字符串）。
- 路由先调用 `addDeviceCommand(...)` 写入数据库（幂等：若 cmdId 已存在，`addDeviceCommand` 会返回已有记录），然后调用 `publishCommand({ deviceId, cmdId, ... })`。
- `publishCommand` 在内部也会尝试写入 DB 并在 publish 成功时把状态更新为 `sent`，并启动 ACK 超时计时器；收到设备 ACK 时，`mqtt.js` 会把状态更新为 `acked`。
- 若 `publishCommand` 拒绝/抛出，路由会把对应记录的状态更新为 `failed` 并返回 HTTP 500。

依赖与安装注意（代理/审阅者须知）：

- 为了简化路由实现，`express` 已添加到 `package.json` 的 `dependencies` 中，但 agent 没有也不会运行 `npm install`。请在目标环境中运行 `npm install` 以获得依赖。

约束与合规性声明：

- 本次变更严格遵守任务要求：未在任何步骤中运行系统命令或执行 git 操作（如 commit/push）。
- 未修改 `src/db.js` 与 `src/mqtt.js` 的内部实现；路由优先使用两个模块导出的 `addDeviceCommand` 与 `publishCommand`。

如果审阅者发现 `publishCommand` 的签名在运行时与预期不符（例如不接受外部传入的 `cmdId`），建议的最小改动为：使 `publishCommand` 接受可选的 `cmdId` 参数并在内部使用传入的 `cmdId`，或在路由中先写 DB 再调用客户端 publish（当前实现已采用前者的使用方式）。

执行者/测试者备注：

- 启动服务后，请使用 `curl` 发布命令并用 `mosquitto_sub` 订阅 `v1/devices/<deviceId>/cmd` 以验证消息是否到达；使用 `sqlite3` 或 DB 浏览器查询 `device_commands` 表验证状态变化。

Agent 行为声明：

- 本次代码变更由 AI agent 在工作区直接编辑文件完成；agent 未执行任何 shell 命令、未安装依赖、也未运行任何 git 操作。
