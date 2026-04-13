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
