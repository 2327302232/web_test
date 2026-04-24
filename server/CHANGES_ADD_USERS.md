# CHANGES_ADD_USERS.md

此文档由本地修改脚本生成，记录在 `server` 中新增 `users` 表、DB 层 API 以及本地测试的步骤与结果。

## 修改/新增文件（相对路径）
- server/src/schema.sql  （新增 `users` 表）
- server/src/db.js      （新增 users 相关 prepared statements 与导出函数：addUser, getUserByUsername, getUserById, listUsers, updateUser, removeUser）
- server/src/api/users.js  （新增测试用路由：/api/test/register, /api/test/login, /api/test/users）
- server/src/server.js  （挂载上述 users 路由）
- server/CHANGES_ADD_USERS.md （本文件）

## 新增 DB API 函数契约

1. `addUser({ username, password, displayName, createdAt } = {})`
   - 必填：`username` (string), `password` (string)
   - 行为：尝试插入 users 表；使用 `createdAt` 或 `Date.now()`。
   - 返回：若成功 -> `{ lastInsertRowid, createdAt }`；若 username 已存在 -> `{ existing: true, row }`（row 为已有行）。
   - 错误：缺少必填字段时抛错；DB 错误抛出异常供调用者捕获。对 UNIQUE 违例进行了捕获并返回 `existing=true`，不会抛出未捕获异常。

2. `getUserByUsername(username)`
   - 输入：`username`（必填）
   - 返回：若存在返回用户对象 `{ id, username, password_hash, display_name, created_at }`，否则返回 `null`。

3. `getUserById(id)`
   - 输入：`id`（必填）
   - 返回：用户对象或 `null`。

4. `listUsers({ limit = 100, offset = 0 } = {})`
   - 返回：用户数组，按 `created_at` DESC 排序。每项包含 `{ id, username, password_hash, display_name, created_at }`。

5. `updateUser(username, updates = {})`
   - 输入：`username`（必填），`updates`: `{ password?, displayName? }`
   - 行为：只更新提供的字段（动态构建 SQL）。返回 `{ changes }`（受影响行数）。若 `updates` 为空则抛错。

6. `removeUser(username)`
   - 输入：`username`（必填）
   - 返回：`{ changes }`。

注意：`password` 被直接存入 `password_hash` 列（明文存储，按任务要求保留该行为）。

## 测试/验证步骤（将按下述流程执行并记录结果）

1. 启动后端（通过 VS Code 的 NPM Scripts 或 Run/Debug）并观察控制台，确认 `initDb()` 执行成功。
   - 记录包含 `initDb success` 或类似的启动日志行。

2. POST /api/test/register
   - 请求：`{ "username": "testuser", "password": "plain123", "displayName": "Test User" }`
   - 期望：HTTP 201 或 200（若已存在），响应 body 包含 `username`, `displayName`, `createdAt`（不包含 password）。

3. POST /api/test/login
   - 请求：`{ "username": "testuser", "password": "plain123" }`
   - 期望：HTTP 200 返回用户信息；若失败返回 401。

4. 使用 VS Code SQLite 扩展打开 `server/data/tracks.sqlite` 并执行查询验证：
   - `SELECT id, username, password_hash, display_name, created_at FROM users WHERE username = 'testuser';`
   - 验证 `password_hash` 包含刚才提交的明文密码。

5. 幂等性测试：重复调用注册接口，期望返回 `existing=true` 或 200（不抛致命错误）。

6. （可选）调用更新/删除接口并验证 DB 变化。

---

后续步骤：我将启动本地 server 并执行上述测试，随后把实际的控制台日志、HTTP 请求与响应、以及 SQLite 查询结果粘贴到本文件中。

## 实际测试结果与日志

注意：在尝试启动默认端口 8787 时，发现该端口已被占用（EADDRINUSE）。因此我将服务在备用端口 8788 启动以便进行 HTTP 测试。下面为关键输出节选。

1) 启动/DB 初始化日志（来自 `node src/server.js`，端口 8788）：

```
src/server.js: starting...
src/server.js: initializing DB...
Using DB path: D:\PERSONAL\Project\26_4\web\ride_helmet_web\server\data\tracks.sqlite
PRAGMA journal_mode: [ { journal_mode: 'wal' } ]
PRAGMA busy_timeout: [ { timeout: 5000 } ]
PRAGMA synchronous: [ { synchronous: 1 } ]
src/server.js: DB initialized.
src/server.js: starting MQTT client...
src/server.js: MQTT client started (see mqtt logs for subscriptions).
src/server.js: ready. Waiting for MQTT messages. Press Ctrl+C to stop.
HTTP server listening on port 8788
```

2) 直接 DB 函数测试（`node test_add_users.js`）输出：

```
TEST: initDb
Using DB path: D:\PERSONAL\Project\26_4\web\ride_helmet_web\server\data\tracks.sqlite
PRAGMA journal_mode: [ { journal_mode: 'wal' } ]
PRAGMA busy_timeout: [ { timeout: 5000 } ]
PRAGMA synchronous: [ { synchronous: 1 } ]
TEST: initDb done
TEST: addUser testuser
addUser result: {"lastInsertRowid":2,"createdAt":1777032601258}
TEST: getUserByUsername testuser
getUserByUsername: {"id":2,"username":"testuser","password_hash":"plain123","display_name":"Test User","created_at":1777032601258}
TEST: addUser duplicate
addUser unique constraint: UNIQUE constraint failed: users.username
addUser duplicate result: {"existing":true,"row":{"id":2,"username":"testuser","password_hash":"plain123","display_name":"Test User","created_at":1777032601258}}
TEST: listUsers
listUsers: [{"id":2,"username":"testuser","password_hash":"plain123","display_name":"Test User","created_at":1777032601258}]
TEST: login check
login: success
TEST: updateUser displayName
updateUser result: {"changes":1}
after update: {"id":2,"username":"testuser","password_hash":"plain123","display_name":"Updated Name","created_at":1777032601258}
TEST: removeUser
removeUser result: {"changes":1}
after remove: null
TEST: done
```

3) HTTP 接口测试（`node test_http_users.js`，对 `/api/test/*` 的请求与响应）：

- 请求：POST http://localhost:8788/api/test/register
   - Body: { "username": "testuser_http", "password": "plain123", "displayName": "HTTP User" }
   - 响应状态: 201
   - 响应 Body:

```
{"id":3,"username":"testuser_http","displayName":"HTTP User","createdAt":1777032681350}
```

- 请求：POST http://localhost:8788/api/test/login
   - Body: { "username": "testuser_http", "password": "plain123" }
   - 响应状态: 200
   - 响应 Body:

```
{"id":3,"username":"testuser_http","displayName":"HTTP User"}
```

- 请求：GET http://localhost:8788/api/test/users
   - 响应状态: 200
   - 响应 Body:

```
{"users":[{"id":3,"username":"testuser_http","password_hash":"plain123","display_name":"HTTP User","created_at":1777032681350}]}
```

- 幂等性测试：再次 POST /api/test/register（同一 username）
   - 响应状态: 200
   - 响应 Body:

```
{"existing":true,"id":3,"username":"testuser_http","displayName":"HTTP User","createdAt":1777032681350}
```

（注：上面 `password_hash` 字段确实包含明文 `plain123`，这与任务约定一致，请勿在真实环境中采用）

## 变更回滚 / 撤销说明

若需撤销本次本地更改并删除用户表/数据，可手动在 VS Code 的 SQLite 扩展中运行以下 SQL：

```
DROP TABLE IF EXISTS users;
```

若需恢复代码状态（本地更改未提交至 git），手动删除或还原以下代码：

- 从 `server/src/schema.sql` 中移除 `users` 表定义。
- 从 `server/src/db.js` 中移除 `users` 相关的 prepared statements 与导出函数（`addUser`, `getUserByUsername`, `getUserById`, `listUsers`, `updateUser`, `removeUser`）。
- 删除 `server/src/api/users.js` 与测试脚本 `server/test_add_users.js`, `server/test_http_users.js`，并在 `server/src/server.js` 中移除对 `users.js` 的 `import` 与 `app.use(usersRouter)`。

执行以上步骤后，手动启动服务（或使用 SQLite 扩展）确认 `users` 表与相关数据已被删除。

## 安全与注意事项（必须阅读）

- 本次实现按要求将密码以明文形式存入 `password_hash` 列。请注意：这会造成严重安全风险。切勿将此测试数据库或包含明文密码的文件推送到公共仓库或分享给他人。
- 若要在真实项目中使用，请务必改为使用经过验证的哈希算法（例如 bcrypt / argon2），并对敏感数据进行严格访问控制与加密传输。

