# 家庭收支記錄

家庭收支記錄以 Windows 家用電腦為主機，近期目標是將信用卡 PDF 解鎖、解析與核對後，更新每月支出 Excel。SQLite 保留可追溯資料；Web 用於設定、核對確認與處理例外，完整 Dashboard 不是交付前置。

**目前狀態：** 已有文件匣、通用 CSV 匯入、總覽/搜尋/工作紀錄、Codex MCP Gmail 收件邊界、個人資料輔助的加密 PDF 預覽、帳單分析／核對／確認及專用 Excel；解鎖設定不要求銀行或家庭成員。郵件明確描述完整證號與字母大小寫，或明確區分本國籍證號/外籍生日格式時，可先本機解鎖，不需 AI。中國信託已完成真實 Finance/Excel；2026-09-30 新下載的中國信託、國泰世華、永豐加密帳單均通過逐列/合計核對及冪等，後兩家草稿尚待人工確認。支援上述已驗證文字版型及受限台新零交易，未知版型仍待處理；Codex 排程真實/跨日收件尚未驗收。

未列交易日期的利息依使用者批准按帳單明示結帳日認列，明細顯示「結帳日認列」；保留原始缺日期與認列依據。普通消費/費用/繳款缺日期，或利息缺明示結帳日，仍待處理，不拿郵件日猜日期。

**分類功能已正式部署：** 原私有網址已有消費分類、Donut、Category → Merchant → Transaction 下鑽、未分類整理與 Excel 分類投影；既有 18 筆交易與來源保留。V1 採 read-time Effective Category，不改 FinanceTransaction identity，也不做 AI 分類、Budget、Tag 或多層 subcategory。完整設計及測試對照見 [CATEGORY_SPENDING_PLAN.md](CATEGORY_SPENDING_PLAN.md)。

日常開啟 [家庭收支記錄](https://desktop-vcgfqnq.tailb47104.ts.net/)，在總覽選月份並查看「分類支出」。既有消費尚未設分類，因此圓環會顯示「未分類」；點「待分類商家」指定分類，可選擇記住商家，讓後續同商家交易套用規則。點分類、商家可一路查看交易與原始文件。「設定 → 消費分類」管理類別與規則。

**目前分類限制與下一步：** V1 有分類工具，但沒有內建商家辨識或消費 AI。2026-09-30 唯讀實測為 14 個類別、商家規則與有效单筆 override 均 0，九月 6 筆支出皆未分類。使用者已核准下一版 taxonomy 建议写入规划：饮食、日常采购、交通、购物、居家／水电通讯、家庭／育儿、医疗／健康、娱乐／数位服务、旅游、图书、课程／教育、保险、金融费用、未分类，另保留收入／转帐系统类别；并建议 Donut 最多 6 slices 且未分类保持可见。详细边界与 A1-A6 见 [CATEGORY_SPENDING_PLAN.md](CATEGORY_SPENDING_PLAN.md#18-逐筆自動分類研究與後續流程規劃未實作)。当前正式 0012 尚未因此新增 books／insurance 或改写分类规则；程式 migration／部署仍需另行授权。

## 分類功能隔離預覽

```powershell
.\scripts\start_category_preview.ps1 -MobileHostname desktop-vcgfqnq.tailb47104.ts.net
```

隔離 [分類預覽](https://desktop-vcgfqnq.tailb47104.ts.net:8443/?month=2026-09) 僅供測試，不是日常入口。其獨立 `data/category-preview/synthetic.db` 的合成來源已撤銷，目前有效交易 0 筆；不可自行恢復以補圖。SecretStore 與 Excel 關閉。服務須保持執行、裝置須加入同一 Tailscale；實體手機尚未驗收。

2026-09-30 授權部署後，程式與正式 `data/family-finance-hub-live.db` 均為 `0012_transaction_categories`；正式 3000／HTTPS 443 已同步新版 `frontend/dist` 及 owned Excel。成對備份與副本還原／migration 驗證證據在本機 `data/backups/20260930-categories-1845/`，不進 Git。未來 schema 不同仍須當次授權、成對備份及副本驗證，不能將新版 API 直接搭配舊 DB。隔離 preview 腳本不是正式啟動器。

在「總覽」選月份與單一幣別，點分類清單或圓環進入商家，再點商家看逐筆交易。「修改分類」可選單筆或同商家現在／未來；「待分類商家」集中整理，「設定 → 分類」管理分類及 exact／contains 規則。分類代碼不可重複，顯示名稱可相同；停用類別保留引用但不再作有效分類。

密碼規則 provider-neutral/Groq adapter 與 safe-switch 已完成：可先做不落盤的 synthetic 連線測試，保存時會再次 preflight，失敗不會覆蓋舊設定；狀態 API 也會分開回報 profile 與 credential 是否可用。2026-09-30 修正 Windows 啟動帳戶後，Active Provider 仍是 OpenAI / `gpt-4.1-mini`，既有 key 已可從 Windows Credential Manager 讀取（`credential_available=true`）；這只確認本機憑證可讀，未重新驗證供應商授權或額度。Groq runtime activation 與真實 Groq request 仍需使用者提供 Groq API key 後驗收。相關 Active Provider、preflight 與安全切換規格見 [GROQ_RUNTIME_REVIEW.md](GROQ_RUNTIME_REVIEW.md)。Excel 優先的逐步實作與驗收見 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)，下列操作說明描述現有功能。

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

相同 SHA-256 內容再次上傳或由 Codex MCP 重送時，會保持已撤銷，不新增交易；來自新郵件的相同內容也適用。若重新輸出後檔案 bytes 不同，會被視為另一份文件，目前尚未做跨文件的語意去重。預覽後若關聯交易或文件狀態改變，系統會要求重新確認；重複確認同一動作不會重複計算或增加操作紀錄。

此功能最初由 `0009_document_revocation` migration 加入；目前程式 Alembic head 為 `0012_transaction_categories`。既有使用者須先取得正式升級授權、停止 API、成對備份資料庫／文件／專用工作簿，再升級與同步 build；正式啟動器不會自動改動資料庫。

## Gmail、Codex MCP 與加密 PDF

Gmail 的授權、搜尋與執行排程由 Codex 的 Gmail MCP／自動化管理，網站不再要求匯入 Google OAuth JSON，也不保存 Gmail access token 或 refresh token。Codex 找到 PDF 附件後，只把附件、來源識別及密碼關鍵字附近的必要文字送到本機 `POST /api/integrations/codex-mcp/gmail/import`；網站立即遮罩並擷取提示，原始 message/attachment ID 只用來計算不可逆來源 key，主旨、寄件者與完整郵件本文都不寫入 SQLite。

Codex MCP 匯入的附件會透過 `StoragePort` 保存到 Windows 本機文件匣，先做 SHA-256 去重，再建立 `codex_mcp_gmail` 來源關聯。相同來源重跑是冪等操作；同一來源識別若突然對應不同 bytes 會拒絕並要求人工檢查。舊的網站內建 Gmail OAuth API 預設回應 410，且內建 scheduler 不會啟動；`FAMILY_FINANCE_HUB_LEGACY_GMAIL_OAUTH=true` 只保留給既有資料相容與測試，不是產品主流程。

Gmail 網頁替代下載採 `scripts/gmail_attachment_download.py` 的「下載前 prepare、指定附件下載、collect 驗證」流程。下載事件逾時但新 `.tmp` 是完整 PDF 時仍可取得檔案；舊檔、寫入中／不完整檔、多檔歧義與失效 receipt 不當成功。工具保存原始加密 bytes 與 SHA-256 證據，不刪改 Downloads 原檔；完整操作及三銀行隔離驗收見 [IMPLEMENTATION_PLAN.md 第 4.1 節](IMPLEMENTATION_PLAN.md#41-必測e2e-gmail-3bank-三銀行真實-gmail-驗收)。此流程修正完成判定，不保證外部 Gmail／瀏覽器永不故障，也不是 MCP 排程已驗收。

PDF 進入共用文件匣後，由文件詳情的「分析帳單」進入銀行 parser；只有顯示交易列、且帳單合計核對成功，才會在使用者按「確認匯入」後寫入 Finance。要查看加密 PDF，先到「設定 → 文件解鎖」保存身分證字號、出生日期或其中一項，不需要填銀行、機構或家庭成員。Codex 提供的來源郵件提示會先遮罩再保存為受限 context；非 Gmail 文件才可由使用者手動提供不含實際密碼的提示。

解鎖資料保存在執行服務的 Windows 使用者帳戶下，可從「認證管理員 → Windows 認證」查看 `family-finance-hub` 相關項目；SQLite 只保存隨機參照。此主機服務應由 `FamilyFinanceHub` 互動式登入排程啟動。`start_server.ps1` 現在會先以獨立隨機測試項目確認保管庫可寫入、讀取及清除，再開啟網站；不可用時拒絕啟動。從 Codex 沙箱帳戶啟動可能回報 Windows 1312，或因讀不到原帳戶的憑證而誤顯示「未保存」。

郵件若明確寫出密碼是完整身分證字號及英文字母大小寫，系統會先在本機確認這個格式，再從 Windows Credential Manager 取值並只嘗試該單一密碼，不需要 AI。若同一封郵件明確區分本國籍使用身分證、外籍使用西元生日 `YYYYMMDD`，系統只依郵件列出的兩種格式依序嘗試，成功後只保存真正命中的規則。郵件沒有說明格式時不會輸入證號或生日試猜；所有明確候選仍解不開時也會直接回報密碼不符，不擴張其他排列。其他局部或多欄位組合只有在提示可用且允許 AI 時，才讓 AI 解讀遮罩後的規則，再由本機組合最多三個候選。身分證字號、生日及實際密碼不送給 AI，只留在 Windows Credential Manager/本機記憶體；解密預覽不改寫原始 PDF。

PDF 內嵌文字不足時，系統才會嘗試使用本機 OCR；PDFium 在記憶體渲染，Tesseract 透過 stdin 處理，不建立臨時帳單影像。OCR 需要另外安裝 Tesseract 及 `chi_tra`、`eng`；亦可用 `FAMILY_FINANCE_HUB_TESSERACT` 指定執行檔、`FAMILY_FINANCE_HUB_OCR_LANG` 指定語言。執行前會檢查語言資料，尚未就緒時仍可檢視 PDF。OCR 文字不寫 DB；本主機 OCR runtime 未驗收。目前 parser 涵蓋已驗證中國信託/國泰/永豐文字版型及受限台新零交易，未知版型仍待處理。

AI API 設定在「設定 → 進階設定」，屬可選功能；目前 UI 對新設定預設 Groq Free + `openai/gpt-oss-20b`，也可由使用者明確選擇 OpenAI。先輸入 API key 與模型按「測試連線」；成功只代表 synthetic 規則可解析，尚不會保存或切換。按「保存並切換」時 backend 會再次 preflight，成功才更新 Windows Credential Manager 與 Active Provider，失敗會保留舊設定。畫面會分別顯示作用中 Provider、模型與安全憑證狀態。既有 OpenAI 不會因升級自動改 Groq；供應商額度與模型可能調整，不宣稱永久免費。未設定 provider credential 時不呼叫 AI。若提示只藏在尚未解鎖的 PDF 內，仍需由郵件或使用者提供提示。真實身分證、生日、實際 PDF 密碼及帳單全文不會送給 provider；Groq 失敗或 429 不會自動切換到 OpenAI。Codex 自動化只負責收錄附件，不會繞過帳單核對與確認閘門直接建立財務交易。

## Excel 自動更新

「設定 → 連線服務」可啟用專用 Excel 自動更新。預設關閉；啟用後 Backend 每 30 秒檢查一次已提交的 SQLite 資料，並將所有有效交易完整重建到 `data\exports\家庭收支記錄.xlsx`。可用 `FAMILY_FINANCE_HUB_EXCEL_PATH` 指定其他 `.xlsx` 路徑。

工作簿包含「月份幣別摘要」、「交易明細」、「文件狀態」、「信用卡月支出」及「分類支出」；交易明細在原欄位後新增「分類」。分類與 Web 共用 resolver，按月／幣別分開，付款不進分類支出，退款沖抵。分類或規則修改也會讓輸出待更新；此主機正式工作簿已重建並核對 18 筆交易、分類與每期合計。日期／金額保留為可計算類型，穩定 ID 保留；撤銷／恢復及重跑仍不複製交易。

SQLite 仍是唯一事實來源，Excel 是可重建的輸出。應用程式只會替換自己建立且帶有內部標記的工作簿；若目標位置已有其他 Excel，會停止並提示，不會覆蓋。直接修改專用工作簿後，下載會先停用並標示待更新，下一次更新會以 SQLite 內容重建。Excel 正在開啟、檔案無法寫入或更新失敗時保留上一版並繼續重試；錯誤摘要不會包含底層路徑或敏感內容。

「文件狀態」會列出尚未建立交易或尚未核對的 PDF。現有 parser 只涵蓋上述已驗證版型；未知版型、解鎖失敗、交易列缺失或帳單合計不符，都會保留待處理，不會因為 PDF 進入文件匣就被視為已入帳。文件詳情會載入完整帳單列供核對；確認匯入後，SQLite 交易會在下一次 Excel 更新時出現在「交易明細」及「信用卡月支出」。

## 信用卡帳單匯入流程

1. 在「新增資料」手動收錄 PDF，或由 Codex Gmail 自動化匯入；PDF 先進共用文件匣，SHA-256 相同的檔案不會重複收錄。
2. 打開文件詳情，按「分析帳單」。系統只在本機解鎖，使用來源郵件的密碼提示及 Windows Credential Manager 內的個人資料。
3. 對支援的版型，畫面會顯示日期、項目與金額；確認交易列與帳單核對狀態後按「確認匯入」。
4. 確認後才建立 Finance 交易；再到「設定 → 連線服務」啟用 Excel，或按「立即更新」，輸出到 `data\exports\家庭收支記錄.xlsx`。

Codex MCP 自動化負責發現並收錄 Gmail 附件；「收錄 PDF」與「確認帳單入帳」仍是兩個有意分開的步驟。這可避免錯誤版型或錯誤密碼把資料直接寫進家庭收支。未知銀行會停在待處理，不能以成功解鎖代替交易解析。

## 測試與建置

```powershell
$testRoot = Join-Path 'C:/Users/brad/Documents/Codex' ('pt-' + [guid]::NewGuid().ToString('N').Substring(0,8))
.\.venv\Scripts\python.exe -m pytest backend/tests --basetemp $testRoot -q --tb=short
cd frontend
$testRoot = Join-Path 'C:/Users/brad/Documents/Codex' ('vt-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$env:TEMP = $testRoot
$env:TMP = $testRoot
npm test
npm run build -- --outDir dist-category-preview
```

以上短暫存路徑適用此 Windows 主機，其他主機改為自己可寫的短路徑。本輪重新跑 backend **326 passed**（含 16 項下載回歸，2 warnings）、frontend **29 passed**、TypeScript／Vite production build 成功。正式部署後從 Gmail 新下載中國信託／國泰／永豐帳單，隔離解析 1／19／31 列、獨立逐列／摘要及冪等通過；正式 Finance 18 → 18。Recharts 使用 lazy chunk；UI unit tests mock chart，正式實際 SVG／下鑽及桌面、320px／390px 瀏覽器另驗證。實體手機、screen reader、重開機與冷啟動效能目標仍未完成；完整證據與限制見 HANDOFF／CATEGORY_SPENDING_PLAN。

每次交付另外必跑 **E2E-GMAIL-3BANK**：從 Gmail 重新下載三家不同銀行的真實信用卡對帳單，先確認郵件密碼格式，再完成本機解鎖、交易解析/核對與冪等重跑。三家全部通過才算真實驗收完成；unit tests/build、舊結果或只解鎖不算替代。完整步驟見 [實作流程第 4.1 節](IMPLEMENTATION_PLAN.md#41-必測e2e-gmail-3bank-三銀行真實-gmail-驗收)，本次結果與阻塞見 [交接](HANDOFF.md)。測試不得自動確認正式入帳。

本次純文件與既有成果 Git 封存重新跑 backend 326／frontend 29 passed 及隔離 production build，沒有新程式部署或帳本寫入。上述 Gmail 三銀行 PASS 是前次 `retest-20260930-1903` 的部署驗收，本次未重新下載，不能稱為新一輪 PASS。未來逐筆自動分類實作交付仍须當次重新驗收；本次唯讀本機／私有 HTTPS 首頁、實際 JS／CSS、health／分類 API 正常，實體手機未測。

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
- [消費分類、支出 Donut 與下鑽規劃](CATEGORY_SPENDING_PLAN.md)
