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

本版本 Alembic head 為 `0011_statement_import`。停止 API 並成對備份 DB 與文件後，在確認 `FAMILY_FINANCE_HUB_DATABASE_URL` 指向正確資料庫的環境執行 `python -m alembic -c backend/alembic.ini upgrade head`，再啟動新版 API 與前端。`0009` 增加撤銷狀態／原因／版本欄位，`0010` 增加 Excel 投影設定與狀態，`0011` 增加可核對的信用卡帳單、帳單列與冪等入帳狀態；migration 不刪除文件或交易。

回退時不要讓舊版 API 讀取仍有已撤銷文件的資料庫，否則舊查詢會重新把交易算入。migration downgrade 因此在還有撤銷文件時拒絕執行；需先透過正常恢復流程處理，或成對還原升級前備份並回到相符版本。不可直接清空撤銷欄位規避檢查。

## 資料備份

停止 API 後，一併備份 SQLite database 和完整 `data/documents/` 目錄。還原時保持兩者來自同一時間點，再執行應用程式。`data/exports/家庭收支記錄.xlsx` 是可重建輸出，不取代 DB 與 Documents 備份；可一起備份供立即查閱，但不能只備份 Excel。v0.1 尚未提供自動備份、加密備份或還原檢查工具。

`backend/tests/test_backup_restore.py` 以隔離合成資料驗證成對備份/還原可恢復文件 bytes、交易與搜尋結果；尚未對使用中的家庭資料庫進行實際還原演練。

## 秘密管理

家庭成員身分資料與 Groq/OpenAI API key 透過 Windows Credential Manager 保存；SQLite 只存隨機 credential reference。Gmail connector credential 由 Codex 管理，不交給 FamilyHub。不要將 secrets 寫入普通 SQLite table、log、`.env`、repository 或明文設定檔。若 Windows Credential Manager 不可用，相關設定/操作會失敗，不會降級至明文儲存。

憑證屬於執行服務的 Windows 使用者，從「認證管理員 → Windows 認證」查看 `family-finance-hub` 或 `<隨機參照>@family-finance-hub` 項目。請透過設定頁保存，不要手動修改參照。此主機須以原有 `FamilyFinanceHub` 互動式登入排程啟動服務；可在該使用者的 PowerShell 執行 `Start-ScheduledTask -TaskName FamilyFinanceHub`。排程不會停止已占用 3000 的程序，遇到占用時應先核對原程序所屬專案與帳戶。

`start_server.ps1` 在監聽前，以獨立隨機 service 及合成值測試 Windows Credential Manager 的寫入、讀取與清除。失敗時拒絕啟動。已確認 `CodexSandboxOffline` 環境寫入會回報 Windows 1312；缺少有效憑證登入工作階段時，即使讀取不存在的項目未報錯，也不能宣稱安全保管庫可用。2026-09-30 已改由使用者排程提供服務，設定頁保存與重新讀取均成功。

AI 密碼規則設定可在「設定 → 進階設定」選擇 Groq（免費優先）或 OpenAI。Groq 目前使用 `openai/gpt-oss-20b` 與 Responses JSON Schema；Groq Responses 不接受 `store`，程式不會送出。只有遮罩後的密碼提示與必要非敏感 context 會送出，provider 失敗/429 會保留待處理，不會自動切換到可能付費的 provider。免費額度、模型及 Structured Outputs 支援需以供應商當下官方文件為準。

切換 provider 後必須按保存；設定頁的 Groq 預設值只提供新設定的預填，不會自動改寫既有的 Windows Credential Manager profile。可用設定頁重新讀取的實際 provider/model 確認目前服務使用哪一條路徑。2026-09-30 修正啟動帳戶後，現場服務仍是 OpenAI / `gpt-4.1-mini`，既有 credential 已可讀；本次未發出 provider request，未確認授權或額度。Groq adapter 與 safe-switch 已完成，但 Groq runtime activation 及真實 request 尚未驗收。來源郵件明示的完整格式不需要 AI；實際中國信託帳單已完成本機解鎖、parser、合計核對、Finance 匯入與 Excel 重建。

Provider 切換已採 safe-switch：先以固定 synthetic 密碼提示與現有 PasswordRule schema 做 Test Connection / preflight，不讀 Gmail 或個資，也不持久化新設定；只有驗證成功後才保存並切換 Active Provider。驗證失敗時舊 provider 維持不變，且不會自動 fallback 到其他付費 provider。最新執行順序與驗收條件見 `GROQ_RUNTIME_REVIEW.md`。

Gmail 授權、搜尋與排程由 Codex Gmail MCP／Codex 自動化管理。FamilyHub 設定頁不接收 OAuth JSON 或 token；網站內建 Gmail API 與 scheduler 預設停用，舊端點回 410。`FAMILY_FINANCE_HUB_LEGACY_GMAIL_OAUTH=true` 只供既有 remote source 相容與測試，不應在新部署中開啟。

Codex 任務取得 PDF 後，將附件、Gmail message/attachment ID 及密碼規則附近的必要文字，以 multipart 送到本機 `POST /api/integrations/codex-mcp/gmail/import`。Backend 不保存原始 Gmail ID、subject、sender 或完整本文；來源 ID 只用來計算不可逆 key，提示先遮罩才保存。附件會持久化到 Documents storage，因此備份時必須連同 `data/documents/` 保存。

此主機已在 Codex 應用程式建立並啟用「家庭收支 Gmail 帳單收錄」自動化，使用 `gpt-6-luna` 的 Max reasoning，每 30 分鐘搜尋最近 45 天的 PDF 帳單。排程沒有新附件時不通知；新匯入、失敗或需要人工處理時才通知。自動化可收錄並觸發分析，但不會自動確認入帳。排程設定屬於 Codex 應用程式，不存於 repository；首次真實 Gmail 執行及至少一次冪等重跑仍須另行驗收。

## Excel 輸出操作

Excel 自動更新預設關閉。啟用後，每 30 秒比對 SQLite 快照；Backend 啟動時也會立即檢查一次。目標檔案只能是 `.xlsx`，預設為 `data/exports/家庭收支記錄.xlsx`。指定 `FAMILY_FINANCE_HUB_EXCEL_PATH` 時應使用受目前 Windows 使用者控制的本機路徑，不建議放在會同時同步／改寫檔案的雲端目錄。信用卡 PDF 必須先在文件詳情分析並按確認匯入；待處理或未知版型不會自動出現在有效交易明細。

## 信用卡 PDF 到家庭收支

支援版型的流程固定為：文件收錄 → 本機解鎖 → `BankStatementParser` 解析交易列 → 帳單合計核對 → UI 顯示待確認列 → 使用者確認 → Finance transaction → Excel rebuild。此版本已驗證中國信託版型，並保留受限台新零交易判斷；其他版型會回傳待處理原因，不猜測欄位或金額。重複確認同一帳單會重用既有交易，不新增第二份。

Codex MCP Gmail 來源會保存遮罩後的郵件規則提示供解鎖流程使用；一般本機上傳可由 UI 輸入不含實際密碼的規則提示。實際身分證、生日與組合密碼只從 Windows Credential Manager／本機記憶體使用，不寫入 SQLite、log 或 Excel。Codex 排程只收錄附件，仍需在文件詳情完成核對與確認，不把收件視為自動入帳。

應用程式只覆蓋自己建立且帶有 ownership marker 的工作簿。若目標已有其他檔案，會顯示 `unowned_workbook` 並停止；請移動該檔案或改用新路徑。使用 Excel 開啟導致寫入失敗時會保留上一版並定時重試。直接編輯專用工作簿後，系統會偵測輸出 SHA-256 不一致、暫停下載，並在下一次更新以 SQLite 內容重建。
