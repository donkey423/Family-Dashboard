# 操作與部署

## Windows 本機

請依 README 建立 Python venv、安裝 backend 及 frontend 依賴、執行 Alembic migration，然後啟動 FastAPI 與 Vite。預設資料放在啟動目錄下的 `data/family-finance-hub.db` 與 `data/documents/`；可用 `FAMILY_FINANCE_HUB_DATABASE_URL`、`FAMILY_FINANCE_HUB_STORAGE_ROOT`、`FAMILY_FINANCE_HUB_MAX_UPLOAD_BYTES` 覆寫。上傳大小預設 25 MiB。

開發時兩個服務預設綁定 `127.0.0.1`。要從家庭其他裝置連線，需在 API 視窗設定 Web UI 的來源與 Tailscale IP：

```powershell
$env:FAMILY_FINANCE_HUB_CORS_ORIGINS = "http://<Windows-Tailscale-IP>:5173"
python -m uvicorn family_finance_hub.main:app --app-dir backend\src --host <Windows-Tailscale-IP> --port 8000
```

Web 視窗則執行：

```powershell
$env:VITE_API_BASE_URL = "http://<Windows-Tailscale-IP>:8000"
npm run dev -- --host <Windows-Tailscale-IP>
```

將 `<Windows-Tailscale-IP>` 替換為 Windows 主機在 Tailscale 顯示的位址。Windows Defender Firewall 僅允許 Tailscale 私有網路介面及可信家庭裝置。Vite 開發伺服器僅供開發；常態部署應建置靜態前端並由受控本機服務提供。

不得設定路由器埠轉送或將 API 綁定到公開網路介面。v0.1 沒有登入/權限系統，存取控制依賴 Windows 主機防火牆與 Tailscale 裝置授權。

## 備份

停止 API 後，一併備份 SQLite database 和完整 `data/documents/` 目錄。還原時保持兩者來自同一時間點，再執行應用程式。v0.1 尚未提供自動備份、加密備份或還原檢查工具。

## 秘密管理

目前沒有外部服務 secret。新增 OAuth/provider secret 時不得放入普通 SQLite table、log、`.env`、repository 或明文設定檔；Windows 整合應使用 Credential Manager/SecretStore。
