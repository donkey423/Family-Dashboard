# 操作與部署

## Windows 本機

請依 README 建立 Python venv、安裝 backend 及 frontend 依賴、執行 Alembic migration，然後啟動 FastAPI 與 Vite。預設資料放在啟動目錄下的 `data/family-finance-hub.db`、`data/documents/` 與 `data/exports/家庭收支記錄.xlsx`；可用 `FAMILY_FINANCE_HUB_DATABASE_URL`、`FAMILY_FINANCE_HUB_STORAGE_ROOT`、`FAMILY_FINANCE_HUB_MAX_UPLOAD_BYTES`、`FAMILY_FINANCE_HUB_EXCEL_PATH` 覆寫。上傳大小預設 25 MiB。設定 `FAMILY_FINANCE_HUB_DATABASE_URL` 後，Alembic 與 API 都會使用同一個資料庫位址。

可選 OCR 依賴以 `python -m pip install -e "backend[ocr]"` 安裝；Tesseract OCR 執行檔及繁體中文/英文語言資料需另外安裝。可用 `FAMILY_FINANCE_HUB_TESSERACT` 指定執行檔，`FAMILY_FINANCE_HUB_OCR_LANG` 指定語言，預設為 `chi_tra+eng`。OCR 僅在 PDF 文字抽取不足時啟動，先以 `tesseract --list-langs` 確認所需語言資料，再開始渲染；最多處理 20 頁、每頁限制約 8 百萬像素，總逾時 120 秒。缺少引擎或語言資料時，UI 會顯示不同狀態且不阻止 PDF 預覽。PDF 渲染及 OCR 內容只在記憶體處理，不保存辨識文字或臨時頁面影像。

開發時兩個服務預設綁定 `127.0.0.1`，Vite 會將 `/api` 轉送到本機的 API。此 Windows 主機的常用入口是先執行 `npm --prefix frontend run build`，再執行 `.\scripts\start_server.ps1 -DatabasePath data/family-finance-hub-live.db`，由單一 FastAPI 服務在 `127.0.0.1:3000` 提供靜態網頁及 `/api`。Tailscale Serve 已將此主機的私有 HTTPS 網址轉送到 `localhost:3000`；不要為手機預覽改綁 `0.0.0.0` 或重設既有 Serve。

`data/family-finance-hub-live.db` 是這台主機的新版資料庫。舊 `data/family-finance-hub.db` 仍是舊 revision `0003_gmail_sync_state`，不要將新版 API 或 Alembic 直接指向舊檔。升級前的一致性資料庫備份 `data/backups/2026-09-29-pre-deploy/family-finance-hub-online.db` 與文件備份保存在本機，不進 Git。舊開發連接埠可能仍寫入舊資料庫，請只用新網址操作；兩份資料庫不會自動同步。此主機的 `FamilyFinanceHub` 排程使用目前 Windows 使用者的互動式登入，不會保存密碼；登出或關機後需再次登入才能服務。排程已經由手動觸發測試，但尚未實際重開機驗證。

若不用 Tailscale Serve，而是要直接連到開發用的 Vite/API 連接埠，才需在 API 視窗設定 Web UI 的來源與 Tailscale IP：

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

## 資料庫版本升級

本版本 Alembic head 為 `0010_workbook_export`。停止 API 並成對備份 DB 與文件後，在確認 `FAMILY_FINANCE_HUB_DATABASE_URL` 指向正確資料庫的環境執行 `python -m alembic -c backend/alembic.ini upgrade head`，再啟動新版 API 與前端。`0009` 增加撤銷狀態／原因／版本欄位，`0010` 增加 Excel 投影設定與狀態；兩者都不刪除文件或交易。

回退時不要讓舊版 API 讀取仍有已撤銷文件的資料庫，否則舊查詢會重新把交易算入。migration downgrade 因此在還有撤銷文件時拒絕執行；需先透過正常恢復流程處理，或成對還原升級前備份並回到相符版本。不可直接清空撤銷欄位規避檢查。

## 資料備份

停止 API 後，一併備份 SQLite database 和完整 `data/documents/` 目錄。還原時保持兩者來自同一時間點，再執行應用程式。`data/exports/家庭收支記錄.xlsx` 是可重建輸出，不取代 DB 與 Documents 備份；可一起備份供立即查閱，但不能只備份 Excel。v0.1 尚未提供自動備份、加密備份或還原檢查工具。

`backend/tests/test_backup_restore.py` 以隔離合成資料驗證成對備份/還原可恢復文件 bytes、交易與搜尋結果；尚未對使用中的家庭資料庫進行實際還原演練。

## 秘密管理

家庭成員身分資料、Groq/OpenAI API key 與 Gmail OAuth client/token 均透過 Windows Credential Manager 保存；SQLite 只存隨機 credential reference。不要將 secrets 寫入普通 SQLite table、log、`.env`、repository 或明文設定檔。若 Windows Credential Manager 不可用，相關設定/操作會失敗，不會降級至明文儲存。

AI 密碼規則設定可在「設定 → 進階設定」選擇 Groq（免費優先）或 OpenAI。Groq 目前使用 `openai/gpt-oss-20b` 與 Responses JSON Schema；Groq Responses 不接受 `store`，程式不會送出。只有遮罩後的密碼提示與必要非敏感 context 會送出，provider 失敗/429 會保留待處理，不會自動切換到可能付費的 provider。免費額度、模型及 Structured Outputs 支援需以供應商當下官方文件為準。

切換 provider 後必須按保存；設定頁的 Groq 預設值只提供新設定的預填，不會自動改寫既有的 Windows Credential Manager profile。可用設定頁重新讀取的實際 provider/model 確認目前服務使用哪一條路徑。2026-09-29 的現場服務仍是既有 OpenAI profile；Groq adapter 已部署於程式但尚未保存 Groq key。這次授權 Gmail 網頁下載的 PDF 已完成本機收錄與重複 bytes 去重，AI 預覽因 OpenAI 額度不足停止且沒有建立交易；要驗證 Groq，需先在本機保存 key，再用合成提示測試。

Gmail OAuth 授權會在執行 API 的 Windows 主機開啟瀏覽器並使用 loopback callback，因此首次連線需要互動式桌面 session。授權完成後可手動同步；定時同步預設關閉，必須在 UI 明確啟用後才每 30 分鐘觸發一次，並且只呼叫既有 Gmail sync use case。它可匯入通用 CSV 與收錄 PDF 文件，但不會將 PDF 猜成交易。Windows 關機時排程暫停；重新啟動後若已到期，會在 scheduler 下一次檢查時補跑。替換 OAuth client 設定會自動關閉排程。

若 Google OAuth consent screen 使用 External + Testing，refresh token 一般會在 7 天後過期；長期自動同步應依 Google 官方規則完成應用程式發布狀態與測試使用者設定，並在真實 Windows 主機驗證重新開機後仍可刷新 token。不要把 refresh token 移出 Credential Manager 來繞過到期。

## Excel 輸出操作

Excel 自動更新預設關閉。啟用後，每 30 秒比對 SQLite 快照；Backend 啟動時也會立即檢查一次。目標檔案只能是 `.xlsx`，預設為 `data/exports/家庭收支記錄.xlsx`。指定 `FAMILY_FINANCE_HUB_EXCEL_PATH` 時應使用受目前 Windows 使用者控制的本機路徑，不建議放在會同時同步／改寫檔案的雲端目錄。

應用程式只覆蓋自己建立且帶有 ownership marker 的工作簿。若目標已有其他檔案，會顯示 `unowned_workbook` 並停止；請移動該檔案或改用新路徑。使用 Excel 開啟導致寫入失敗時會保留上一版並定時重試。直接編輯專用工作簿後，系統會偵測輸出 SHA-256 不一致、暫停下載，並在下一次更新以 SQLite 內容重建。
