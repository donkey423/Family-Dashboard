# 操作與部署

## Windows 本機

請依 README 建立 Python venv、安裝 backend 及 frontend 依賴、執行 Alembic migration，然後啟動 FastAPI 與 Vite。預設資料放在啟動目錄下的 `data/family-finance-hub.db` 與 `data/documents/`；可用 `FAMILY_FINANCE_HUB_DATABASE_URL`、`FAMILY_FINANCE_HUB_STORAGE_ROOT`、`FAMILY_FINANCE_HUB_MAX_UPLOAD_BYTES` 覆寫。上傳大小預設 25 MiB。

可選 OCR 依賴以 `python -m pip install -e "backend[ocr]"` 安裝；Tesseract OCR 執行檔及繁體中文/英文語言資料需另外安裝。可用 `FAMILY_FINANCE_HUB_TESSERACT` 指定執行檔，`FAMILY_FINANCE_HUB_OCR_LANG` 指定語言，預設為 `chi_tra+eng`。OCR 僅在 PDF 文字抽取不足時啟動，最多處理 20 頁、每頁限制約 8 百萬像素，總逾時 120 秒；失敗不會阻止 PDF 預覽。PDF 渲染及 OCR 內容只在記憶體處理，不保存辨識文字或臨時頁面影像。未安裝 Tesseract 或語言資料時，UI 仍可檢視 PDF 並顯示辨識狀態。

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

`backend/tests/test_backup_restore.py` 以隔離合成資料驗證成對備份/還原可恢復文件 bytes、交易與搜尋結果；尚未對使用中的家庭資料庫進行實際還原演練。

## 秘密管理

家庭成員身分資料、OpenAI API key 與 Gmail OAuth client/token 均透過 Windows Credential Manager 保存；SQLite 只存隨機 credential reference。不要將 secrets 寫入普通 SQLite table、log、`.env`、repository 或明文設定檔。若 Windows Credential Manager 不可用，相關設定/操作會失敗，不會降級至明文儲存。

Gmail OAuth 授權會在執行 API 的 Windows 主機開啟瀏覽器並使用 loopback callback，因此首次連線需要互動式桌面 session。授權完成後可手動同步；定時同步預設關閉，必須在 UI 明確啟用後才每 30 分鐘觸發一次，並且只呼叫既有 Gmail sync use case。它可匯入通用 CSV 與收錄 PDF 文件，但不會將 PDF 猜成交易。Windows 關機時排程暫停；重新啟動後若已到期，會在 scheduler 下一次檢查時補跑。替換 OAuth client 設定會自動關閉排程。
