# CHANGES_FOR_ACK.md

## 1. 修改文件与职责

- 修改：src/server.js — 在 'cmd_ack' 事件 handler 中新增对 DB 更新的逻辑。
- 新增/更新：CHANGES_FOR_ACK.md — 变更说明与调用签名记录。
- 修改：tests/server-manual-checklist.md — 新增 ACK 验证步骤。

## 2. DB 更新函数签名

- 使用 db.js 导出的 `updateCommandStatus({ cmdId, status, ackTs, ackPayload, lastError })`
  - 参数：
    - cmdId: string
    - status: string
    - ackTs: number (ACK 时间戳)
    - ackPayload: string (JSON 字符串，记录原始 payload)
    - lastError: string (可选，错误信息)

## 3. 事件 payload 结构

- mqtt.js emit 的 'cmd_ack' payload 结构：
  - { deviceId, cmdId, ok, message, ts, raw }

## 4. 处理位置与理由

- 采用优先做法：在 src/server.js 的 onMqtt('cmd_ack', ...) handler 内调用 updateCommandStatus。
- 理由：server.js 已订阅事件且有 DB 可用，改动最小、可控性最好。

## 5. 状态与幂等策略

- status 取值：
  - ok === true → status = 'acked'
  - ok === false 且 message === 'ack timeout' → status = 'failed'
  - ok === false 且 message 其它 → status = 'failed'
- ack_ts 取 payload.ts（如无则 Date.now()）
- ack_payload 取 JSON.stringify(payload.raw || payload)
- last_error 取 payload.message（仅 ok=false 时）
- 幂等策略：
  - 真实设备后续到达的 ACK（ok=true）会覆盖先前的 failed/expired 记录，优先使用最新到达的 ACK 信息。
  - 若 DB 已有 status='acked'，则忽略后续相同 cmdId 的超时/失败更新。
  - 若 updateCommandStatus 已内建幂等逻辑则直接调用，否则先查当前状态。

## 6. 容错与日志

- DB 更新操作前后均有日志，异常被捕获并打印，不阻断主流程。

## 7. agent 操作声明

- agent 未运行任何 shell/PowerShell/Node/npm/git/任何命令。
- agent 未对 db.js 或 mqtt.js 的核心逻辑做任何修改。

## 8. 测试与文档

- tests/server-manual-checklist.md 已新增 ACK 验证步骤。
- README.md 可选补充说明。

---

如遇下列情况已停止自动修改并等待人工确认：
- db.js 无 updateCommandStatus 导出（已确认存在）。
- updateCommandStatus 签名与预期差异较大（已确认兼容）。
- 需更改 db 层幂等/覆盖规则（当前无需 DB schema 变更）。
