# 家庭收支記錄

家庭收支記錄以 Windows 家用電腦為主機，近期目標是將信用卡 PDF 解鎖、解析與核對後，更新每月支出 Excel。SQLite 保留可追溯資料；Web 用於設定、核對確認與處理例外，完整 Dashboard 不是交付前置。

**目前狀態：** 已有文件匣、通用 CSV 匯入、總覽/搜尋/工作紀錄、Gmail 同步、個人資料輔助的加密 PDF 預覽及專用 Excel 輸出；解鎖設定不再要求銀行或家庭成員。密碼規則 provider-neutral/Groq adapter 已完成並通過合成驗證。2026-09-29 最後一次有證據的 runtime smoke check 仍使用 OpenAI / `gpt-4.1-mini`；Groq 程式已在 `main`，但 runtime activation 與真實 Groq request 尚未驗收。最近一份授權 Gmail PDF 已完成收錄與 SHA-256 去重，當時 AI 預覽因 OpenAI 額度問題停止，沒有建立交易；銀行專用 PDF 交易 parser 尚未完成，不能宣稱信用卡 PDF 已自動入帳。Excel 優先的逐步實作與驗收見 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)；Groq 已實作後的 Active Provider / runtime activation / safe-switch 深度審查見 [GROQ_RUNTIME_REVIEW.md](GROQ_RUNTIME_REVIEW.md)。下列操作說明描述現有功能。

## 開發環境

- Windows 10/11
- Python 3.11 或更新版本（需先安裝 Windows Python runtime）
- Node.js 22.12+（或 20.19+）與 npm

## 啟動

在 repository 根目錄開啟兩個 PowerShell 視窗：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e "backend[dev,ocr]"
alembic -c backend\alembic.ini upgrade head
uvicorn family_finance_hub.main:app --app-dir backend\src --host 127.0.0.1 --port 8000
```

`alembic upgrade head` 會更新資料庫結構。若你已有舊資料庫，先停止 API 並備份 SQLite 檔與 `data\documents`，再執行 migration；不要刪除或重建舊資料庫。

若以 `FAMILY_FINANCE_HUB_DATABASE_URL` 指定 SQLite 路徑，API 與 Alembic migration 會使用同一個值。

另一個視窗：

```powershell
cd frontend
$env:NODE_OPTIONS = "--use-system-ca"
npm --cache .npm-cache install
npm run dev -- --host 127.0.0.1
```

開啟 Vite 顯示的網址。開發時 Vite 會將同網域的 `/api` 轉送到 `http://127.0.0.1:8000`；設定 `VITE_API_BASE_URL` 可覆寫 API 位址。

## 此 Windows 主機的網站網址

目前此主機的 Tailscale Serve 將私有 HTTPS 網址轉送至 `localhost:3000`，此入口目前由家庭收支記錄使用；它不是未來所有新專案各自的網址。要讓本專案的網頁與 API 使用同一網址，先在 repository 根目錄建置前端，再啟動單一服務：

```powershell
npm --prefix frontend run build
.\scripts\start_server.ps1 -DatabasePath data/family-finance-hub-live.db
```

`data/family-finance-hub-live.db` 是此主機由舊版資料庫的線上一致性快照升級而來的新版資料庫；舊 `data/family-finance-hub.db` 保留未改動，不可直接用新版程式啟動。啟動腳本不會自動執行 migration。其他新安裝環境應先依上方步驟建立資料庫並升級至 Alembic head，再用預設的 `data/family-finance-hub.db` 啟動。

本站僅限同一 Tailscale 網路的已授權裝置，不是公開網站。Windows 必須開機且服務正在執行；此主機已設定使用者登入時自動啟動。請只用新的 Tailscale 網址操作，其他舊開發連接埠可能仍指向舊資料庫，兩者不會自動同步。部署細節見 [操作與部署](docs/operations.md)。

新 Web 專案的手機預覽應按全域 Codex 指引，使用未占用的本機連接埠及獨立的 Tailscale Serve HTTPS 埠，並實測新專案畫面。此主機的全域 `register-mobile-preview.ps1` 可在新專案啟動後註冊其私有網址；已以兩個隔離測試服務驗證可同時使用不同埠且不改動本站的根網址。家庭收支記錄持續占用 `3000` 時，其他專案不會自動出現在本站網址，也不應為了預覽而停掉本專案。各專案須自行保持其服務執行。

## CSV 格式

使用 UTF-8、逗號分隔並含標題列的 CSV。日期欄可用 `date`、`posted_at` 或 `transaction_date`；描述欄可用 `description`、`memo`、`name`、`payee` 或 `merchant`。金額欄可用 `amount` 或 `transaction amount`，支出請用負數、收入用正數；也可提供 `debit`/`withdrawal` 與 `credit`/`deposit` 欄，前者會記為支出。`currency` 選填，未提供時使用 TWD。原始列會保留在本機資料庫，且每筆交易都連回匯入的 CSV 文件。

匯入會拒絕無效日期、非有限或超過兩位小數的金額、非三字母幣別，以及與標題欄數不符的資料列；失敗會記入匯入紀錄，不會留下部分交易。總覽以資料庫聚合金額，完整交易明細可按月份篩選並分頁。

## 撤銷誤匯入的帳單

1. 在「文件」或首頁最近文件，按該份文件的「撤銷匯入」。
2. 核對檔名、關聯交易筆數及各幣別收入／支出，選擇原因後確認。
3. 需要恢復時，到「文件 → 已撤銷」選擇「恢復」，再次核對影響範圍。

撤銷後，該文件的交易會立即退出 Dashboard、交易列表及搜尋；其他文件的交易不受影響。原始文件、交易與操作歷史仍保留，不是永久刪除，也不是刪除本機 PDF 副本。恢復只重新啟用既有紀錄，不會重新解析文件；原本沒有交易的文件恢復後仍沒有交易。

相同 SHA-256 內容再次上傳或從 Gmail 同步時，會保持已撤銷，不新增交易；來自新郵件的相同內容也適用。若重新輸出後檔案 bytes 不同，會被視為另一份文件，目前尚未做跨文件的語意去重。預覽後若關聯交易或文件狀態改變，系統會要求重新確認；重複確認同一動作不會重複計算或增加操作紀錄。

此功能最初由 `0009_document_revocation` migration 加入；目前版本 Alembic head 為 `0010_workbook_export`。既有使用者須先停止 API、成對備份資料庫與文件，再依上方啟動步驟升級；程式不會在啟動時自動改動資料庫。

## Gmail 與加密 PDF

在「設定」頁匯入 Google Cloud 的 Gmail API OAuth 桌面應用程式 JSON，然後按「連接 Google 帳戶」及「立即同步 Gmail」。同步使用唯讀權限；預設查詢 `in:anywhere has:attachment {filename:pdf filename:csv}`，不限制日期。垃圾郵件/垃圾桶的完整涵蓋仍待補強與驗收，不能只憑查詢字串宣稱全部掃描完成。初次同步超過單次上限時，再按一次同步即可接續。OAuth 設定與 token 僅放 Windows Credential Manager。連線後可手動同步；定時同步需另外勾選啟用，預設關閉，每 30 分鐘同步一次。Windows 關機時不會執行，重新啟動後會補跑已到期的同步。替換 OAuth 設定會關閉定時同步，需重新授權及手動啟用。

Gmail CSV 會使用通用欄位解析匯入交易；解析失敗的 CSV 仍會保存在共用文件匣並留下失敗紀錄，不會阻止後續郵件同步。PDF 會先進共用文件匣，不會把抽取文字猜成交易。要查看加密 PDF，先到「設定 → 文件解鎖」保存身分證字號、出生日期或其中一項，不需要填銀行、機構或家庭成員。系統會即時讀取 Gmail 郵件的主旨、寄件者與文字本文，擷取並遮罩密碼提示；非 Gmail 文件可在預覽視窗手動提供提示。已設定 AI key 時，開啟加密 PDF 會嘗試讓 AI 解讀遮罩後的提示，再由本機依規則組合最多三個候選密碼。身分證字號、生日及實際密碼不送給 AI，只留在 Windows Credential Manager/本機記憶體；解密預覽不改寫原始 PDF。

PDF 內嵌文字不足時，系統才會嘗試使用本機 OCR；PDFium 會在記憶體中渲染，Tesseract 透過標準輸入處理影像，不建立臨時帳單影像。OCR 需要另外安裝 Tesseract 及 `chi_tra`、`eng` 語言資料；亦可用 `FAMILY_FINANCE_HUB_TESSERACT` 指向執行檔，並以 `FAMILY_FINANCE_HUB_OCR_LANG` 指定語言。執行 OCR 前會檢查設定所需的語言資料；引擎尚未就緒或缺少語言資料時仍可檢視 PDF，介面會分別顯示狀態。OCR 文字只在此次處理的記憶體中使用，不寫入資料庫；銀行專用 PDF 交易 parser 尚未實作。

AI API 設定在「設定 → 進階設定」保存，屬可選功能；目前 UI 對新設定預設 Groq Free + `openai/gpt-oss-20b`，也可由使用者明確選擇 OpenAI。請區分：Groq 是目前 Recommended / new-setup Default，真正 Active Provider 仍以 backend 已保存的 profile + Windows Credential Manager 為準；既有 OpenAI 不會因升級自動改 Groq。切換後應重新讀取設定狀態確認 provider/model，並先以 synthetic prompt 驗證真實 Groq，再測帳單。供應商額度與模型可能調整，不宣稱永久免費。未設定 provider credential 時不呼叫 AI。若提示只藏在尚未解鎖的 PDF 內，仍需由郵件或使用者提供提示。真實身分證、生日、實際 PDF 密碼及帳單全文不會送給 provider；Groq 失敗或 429 不會自動切換到 OpenAI。定時同步只會處理 CSV 與建立 PDF 文件來源，不會將 PDF 自動解析為財務交易。

## Excel 自動更新

「設定 → 連線服務」可啟用專用 Excel 自動更新。預設關閉；啟用後 Backend 每 30 秒檢查一次已提交的 SQLite 資料，並將所有有效交易完整重建到 `data\exports\家庭收支記錄.xlsx`。可用 `FAMILY_FINANCE_HUB_EXCEL_PATH` 指定其他 `.xlsx` 路徑。

工作簿包含「月份幣別摘要」、「交易明細」與「文件狀態」；日期、金額保留為可排序及計算的 Excel 類型，交易與文件穩定 ID 留在明細中。撤銷帳單後，對應交易會從下一版工作簿移除；恢復後會重新出現。重複 Gmail/CSV 同步不會重複列出同一筆交易。

SQLite 仍是唯一事實來源，Excel 是可重建的輸出。應用程式只會替換自己建立且帶有內部標記的工作簿；若目標位置已有其他 Excel，會停止並提示，不會覆蓋。直接修改專用工作簿後，下載會先停用並標示待更新，下一次更新會以 SQLite 內容重建。Excel 正在開啟、檔案無法寫入或更新失敗時保留上一版並繼續重試；錯誤摘要不會包含底層路徑或敏感內容。

「文件狀態」會列出尚未建立交易的 PDF，但目前沒有經真實銀行帳單驗證的 `BankStatementParser`，所以 PDF 不會因為進入 Excel 清單就被視為已入帳。

## 測試與建置

```powershell
python -m pytest backend\tests
cd frontend
npm run build
```

## 家用網路使用

先讓 Web 與 API 只監聽 Windows 主機，再依 [部署說明](docs/operations.md) 使用 Tailscale 私有網路連線。不要將服務公開到網際網路或設定路由器連接埠轉送。

## 文件

- [專案目標](PROJECT.md)
- [架構](ARCHITECTURE.md)
- [里程碑與待辦](TASKS.md)
- [Excel 優先實作流程與 Luna max 交接](IMPLEMENTATION_PLAN.md)
- [維護交接](HANDOFF.md)
- [操作與部署](docs/operations.md)
- [執行問題與處理紀錄](EXECUTION_ISSUES.md)
- [免費 AI 密碼規則 Provider 規格](FREE_AI_PASSWORD_RULE_PLAN.md)
- [Groq Runtime 深度審查與切換方案](GROQ_RUNTIME_REVIEW.md)
