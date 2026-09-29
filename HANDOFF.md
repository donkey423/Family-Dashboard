# 交接

## 2026-09-29 免費 AI provider 與真實流程狀態

- GitHub `main` 已包含 Groq 實作 commit `eeb6883`；2026-09-29 使用者已確認本機 push 回覆 `Everything up-to-date` 且工作區乾淨。後續模型不可再把 Groq 描述成「只在本機未提交」。

- 已完成第一階段 provider-neutral 實作：Groq Free 預設 `openai/gpt-oss-20b`、既有 OpenAI 相容路徑、設定 API/UI provider 選擇，以及不送 `store` 的 Groq Responses payload。兩者共用既有 `PasswordRule` DSL、遮罩後提示、verified rule cache、SecretStore 與本機 PasswordComposer。
- Groq 失敗、429、schema/網路錯誤會留在 pending/manual 路徑，不會自動呼叫可能付費的 OpenAI；API key 不進 repo、SQLite、log 或前端持久化。這次完整驗證為 backend 187 passed、frontend production build 成功，另有 2 個既有相依套件棄用警告。
- 最後一次有證據的 runtime smoke check 仍回報 Active Provider=`openai`、Model=`gpt-4.1-mini`。Groq 程式已在 `main`，但 Git 狀態不代表 runtime 已切換；設定頁的 Groq 預設也不會覆寫既有 Active Provider。切換後必須重新讀取 `/api/security/ai-provider` 才能確認真正使用的 provider/model。
- 本次已從使用者授權的 Gmail 網頁下載一份信用卡 PDF，收錄到 FamilyHub 文件匣；同一 bytes 再次收錄回報 `duplicate=true`。FamilyHub 內建 Gmail OAuth 仍未授權，所以這次不是內建 Gmail scheduler 的驗收。
- 該 PDF 的 AI 預覽實際使用既有 OpenAI profile，因額度不足停止；系統沒有自動切 Groq，也沒有建立 Finance transaction。結果是文件已收錄但仍未解鎖、未解析、未入帳，避免誤匯入。
- 尚未完成：S3F-C safe-switch preflight、S3F-B Groq runtime activation、Groq 解鎖真實 PDF、銀行專用 PDF transaction parser、逐筆核對及 PDF → Excel 入帳；不要把文件收錄/去重視為帳單解析完成。
- 下一步順序：**先 S3F-C，再 S3F-B，再 S4**。先补 `Test Connection`/preflight，确保新 provider 设定验证失败时旧 Active Provider 不变；之后才切到 Groq，用 synthetic prompt 验证真实 request 与 cache，再重新跑授权 PDF。

本次執行遇到的 Git 分支同步、Windows pytest 暫存權限、runtime provider 未切換、Gmail OAuth 邊界、OpenAI 額度及文件狀態漂移，已逐項記錄在 [EXECUTION_ISSUES.md](EXECUTION_ISSUES.md)。

Groq 的最新深度審查與執行規格見 [GROQ_RUNTIME_REVIEW.md](GROQ_RUNTIME_REVIEW.md)；`FREE_AI_PASSWORD_RULE_PLAN.md` 保留 provider 設計與安全邊界。

## 目前接手入口

2026-09-29 文件解鎖操作已簡化：設定頁只需保存身分證字號及/或生日，系統內部建立固定個人 profile；開啟加密 PDF 時，若有 AI key 與可用的 Gmail/手動提示，AI 僅解析遮罩規則，由本機使用 SecretStore 值組合密碼。舊銀行/成員 profile API 保留相容，但不是新 UI 的前置。這次完整 backend 187 passed、frontend build 成功；真實 Gmail PDF 已收錄並驗證重複 bytes 不新增文件，但目前 OpenAI profile 額度不足，沒有建立交易。實體 MacBook/手機未驗收，銀行 PDF transaction parser 與 PDF→Excel 自動入帳仍未完成。

近期目標已收斂為「信用卡 PDF 解鎖、解析、核對後更新每月支出 Excel」。Web 只補設定、核對確認及例外處理，不先擴充平台或完整 Dashboard。2026-09-28 已依本機程式更新 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) 的 S0-S9 詳細工作包、檔案落點、驗收數值及 Luna max 啟動指示；本輪接續實作了版型無關的 Statement 正規化與入帳閘門，但尚未建立銀行專用 parser。

前輪 S1-S3 已完成補強及隔離合成測試；S4 現在已有版型無關的 Statement 契約、月支出語意與正規化閘門，銀行 parser 仍需樣本。接手收到開始指示後重驗基線，再從真正未完成處繼續，不重做已有功能、不把規格當程式完成。

- 本機 `master` 已包含 `ARCHITECTURE_REVIEW_BRIEF.md`。Tailscale Serve 既有設定為私有 HTTPS → `localhost:3000`，網頁與 API 現由同一 FastAPI 服務提供；個人解鎖及單一服務部署已在此主機驗證。此主機使用 `data/family-finance-hub-live.db`，由舊資料庫的一致性快照升級至 `0010_workbook_export`；原始舊 DB 與 `data/backups/2026-09-29-pre-deploy/` 保留。先前 19 份文件、17 筆交易、23 筆工作紀錄及 19 筆文件來源均經核對。舊 DB 不可直接用新版程式啟動。
- `FamilyFinanceHub` Windows 排程在使用者登入後啟動 `scripts/start_server.ps1 -DatabasePath data/family-finance-hub-live.db`，目前由手動觸發的排程執行中。Tailscale HTTPS 首頁與 `/api/dashboard` 均驗證成功；重新開機後的自動觸發及實體 iPhone 尚未驗證。其他舊開發連接埠可能仍寫入舊 DB，兩者不自動同步，應只用新的 Tailscale 網址操作。
- 此主機的跨專案手機預覽工具位於全域 Codex 設定，不屬於本 repository。2026-09-29 以兩個只回傳測試文字的服務驗證 `3001 -> HTTPS 8443`、`3002 -> HTTPS 8444` 可並行、重複註冊保持原路由、錯誤首頁文字與覆蓋 `443` 均被拒絕；測試路由及服務已移除。最後再驗證 Serve 僅剩 `443 -> localhost:3000`、本站 `/api/health` 回傳 200。未以實體手機驗收，也未替尚不存在的新專案預先建立網址。
- 前輪 S0 基線：backend 128 passed、2 個既有棄用警告，frontend production build 成功，Alembic head 為 `0010_workbook_export`。變更後聚焦測試見下方；不是本次文件修改重跑的結果。接手 S0 與 S6/S7/S9 各有完整 backend/build 關卡。
- 固定取捨：S4 一家銀行 parser → S5 最小模型 → S6 原子入帳與正確 Excel → S7 最小設定/待處理 → S8 沿用 Gmail 的受控自動入帳 → S9 固定 Windows 入口。保留 Documents 1:N、SecretStore、撤銷/恢復及 Excel 安全投影；不擴充 DSL/OCR/domain。
- 舊計畫的完整月報/分類、90 天新掃描水位、每日新排程與移除 History 不再是本輪要求。現有 Gmail 引擎/30 分鐘 opt-in 排程及 Excel 背景檢查先沿用；Excel 從選配改為主要交付，不代表現有輸出已具正確信用卡語意。
- 外部關卡：S4 至少兩個期別的真實樣本及逐筆核對；S6 人工確認的真實入帳；S8/S9 才在授權下做 Gmail/正式環境驗收。缺件不可猜測，不回填聊天中的個人秘密，不以合成測試代替外部驗收。
- 下一步：S4 仍需兩個期別的授權本機 PDF 樣本；一份用於 parser 開發，另一份只作未參與調整的驗證。原始文件不進 repo、聊天或外部 AI；可先提供版面與欄位保留、個資/卡號已替換的合成副本。收到前不建立臆測 parser，也不進行依賴樣本契約的 S5 schema。本次未修改正式 DB schema、FamilyHub Gmail OAuth、秘密或 Tailscale 路由；Gmail 網頁下載僅用於文件收錄/去重及預覽錯誤驗證。

## 目前狀態

產品「家庭收支記錄」v0.1 為 Windows 主機上的 local-first Modular Monolith。M1-M5.4 的共用平台與既定流程已實作：Documents/1:N source records、SHA-256 冪等匯入、通用 Finance CSV、Dashboard/Search/Jobs、密碼規則安全邊界、加密 PDF transient preview、Gmail 手動/增量同步與 opt-in 每 30 分鐘 scheduler。M7.1-M7.5 的搜尋、來源追溯、月份／幣別總覽、設定分組、PDF 預覽體驗及手機排版，以及 M8 第一階段的專用 Excel 投影也已實作；銀行專用 PDF parser 與外部環境驗收尚未完成。

PDF 文字抽取不足時才走 `OcrProvider`；目前 Tesseract adapter 會先以 `--list-langs` 確認設定所需 traineddata，再使用 PDFium 在記憶體渲染、透過 stdin 傳頁面影像，最多 20 頁、每頁約 8 MP、總逾時 120 秒。缺少語言資料會回報獨立狀態；OCR 文字僅保留於此次處理記憶體，不寫 DB/log/文件暫存；OCR 失敗不影響原始/解密 PDF 預覽。OCR 執行檔和 `chi_tra`/`eng` 語言資料尚未在此 Windows 主機安裝/驗收。銀行專用 PDF statement parser 尚未實作；PDF 仍只屬於共用 Document，不會猜測或自動建立 Finance transaction。

前輪程式測試使用 FakeGmail，尚未驗收真實帳戶授權狀態；接手時確認現場設定，不推定未設定而重設既有連線。自動同步預設關閉，需使用者在 UI 完成 readonly OAuth 後明確啟用。排程與手動按鈕共用 `GmailSyncUseCase` 及鎖，PDF 只收錄文件，CSV 才走通用匯入。替換 OAuth client 設定會關閉排程。

通用 CSV 匯入會拒絕無效日期、非有限/超精度金額、格式不合的幣別與欄位數異常，失敗資料不會留下部分交易。Gmail 先保存 CSV 文件；單份財務解析失敗會保留文件與失敗工作紀錄，並繼續處理後續郵件。完整交易頁提供月份／幣別篩選和分頁；首頁只讀選定期間最近 8 筆，Dashboard 金額由 SQLite 依期間與幣別聚合。Alembic 與 API 共用 `FAMILY_FINANCE_HUB_DATABASE_URL`。

S1 已驗證自訂 Gmail 查詢走 message search、不借用 history 範圍，且保留預設增量 cursor；涵蓋自訂 A/B 查詢、無既有 cursor、分頁中途改查詢及附件暫時失敗重試。S2 已驗證 HTML table row/cell、inline 空白、重疊上下文保序，以及先遮罩再套輸出上限；測試使用合成值。S3 已把 PDF 來源讀取、寄件者唯一匹配、已驗證規則重用、本機密碼組合、解密與文字抽取協調移到可直接測試的 application use case；格式錯誤／多地址不自動匹配，明確手動 profile 優先。測試確認歧義時不讀秘密、匹配失敗不遍歷其他家庭成員秘密、`/content` 保持原始 bytes、`/preview` 維持 no-store。前輪此處未連線真實 Gmail；本次另完成 Gmail 網頁手動下載與文件收錄/去重，FamilyHub 內建 Gmail OAuth 仍未授權。

S4 新增 `finance/statements/contracts.py`：銀行 parser 的純輸入/輸出型別、帶原因碼的 unsupported 結果、列帳金額符號限制、對帳狀態，以及按消費日期/幣別彙總消費、退款、淨消費、費用、利息與繳款；未知列與缺日期列明確標示，不猜消費。相同行以不同 `line_index` 保留；帳戶線索拒絕長數字串，只接受末四碼或受限遮罩值。另新增 `finance/statements/normalization.py`，以 `statement_id + line_index` 產生穩定 SHA-256 row hash，保留合法相同交易，並只讓 `ready` 結果進入後續入帳；未知列、缺日期、未核對或對帳不符會保留為 `pending` 並帶原因碼。此層不讀 PDF、Gmail、DB 或秘密，也不代表已有銀行專用 parser、真實樣本或銀行核對公式，不能稱解析/入帳完成。

## 帳單撤銷／恢復已完成

- 文件頁提供「有效／已撤銷」與撤銷／恢復操作，確認前顯示關聯交易筆數、各幣別收入／支出／淨額及撤銷原因。
- 撤銷會讓對應交易退出 Dashboard、交易列表與搜尋；保留來源、交易與工作紀錄，可恢復既有交易而不重新解析。沒有交易的文件恢復後仍為零筆。
- 本機上傳與 Gmail 同步均保留相同 SHA-256 文件的撤銷狀態；不同內容仍視為新文件，尚無語意層級帳單去重。保存本機副本不會恢復收支。
- 狀態更新與工作紀錄在同一 transaction；重複操作不新增紀錄，預覽後狀態或影響金額改變則要求重新確認。
- `0009_document_revocation` 已在隔離 SQLite 升級驗證；既有文件預設有效。使用中的資料庫尚未遷移。

## 使用體驗評估與待辦

2026-09-27 已完成 M7.1-M7.5 程式修改及隔離合成資料的桌面與 390px／320px 操作驗證。M7 的前端自動化測試基礎設施及更大規模合成資料矩陣仍待補強；實作順序及驗收條件見 `TASKS.md` 的 M7。

- 搜尋與導覽：搜尋獨立為結果頁，文件／交易各自有總數與分頁，搜尋字詞及分頁保留在 URL，且具備獨立載入、空結果、錯誤與舊請求防護。
- 新增資料與入帳：統一入口區分只收錄文件、CSV 建立交易及 Gmail 同步；文件詳情集中顯示來源、有效狀態、關聯交易與匯入歷史。PDF 收錄仍明示尚未建立交易。
- 來源追溯：交易與 Jobs 只有在有 `source_document_id`／`document_id` 時提供文件連結；文件詳情可回看本機／遠端來源及所有關聯處理結果。
- 月份／幣別總覽：首頁預設本月，Dashboard 由資料庫依月份與幣別聚合；不同幣別不相加，連往交易頁會保留同一組條件，空月份顯示明確空狀態。
- 設定目前依「文件解鎖／連線服務／進階設定」分組，預設顯示個人解鎖資料；不再要求使用者建立銀行或家庭成員設定。舊 profile schema/API 保留相容。
- PDF 開啟後會先自動預覽；只有需要密碼或密碼規則錯誤時才展開解鎖設定。來源不可用、需要密碼、密碼不符及 OCR 未就緒都有獨立提示，且明示預覽不會建立交易。
- PDF 與撤銷／恢復對話框已補焦點移入、Tab 循環、Escape 關閉及回到觸發按鈕；若已設定 AI key，加密 PDF 預覽可分析遮罩後提示（預覽視窗可關閉）；不啟用 Gmail 同步、不保存遠端附件。
- M7.5 已完成：主要字級層級與多幣別摘要、手機交易兩行排列、單排導覽、長內容縮排／換行及共用 `EmptyState`／`TransactionTable` 元件已整理。
- 待處理：M7 前端行為測試基礎設施與更大規模長檔名／失敗狀態矩陣，銀行 PDF parser 也仍未完成。

下一步依 `IMPLEMENTATION_PLAN.md` 完成 S4：等待銀行名稱及兩期 PDF 樣本，保存在使用者授權的私有位置，或以欄位/版面相同的合成副本提供；一份用來開發，一份盲測。缺樣本期間不推測銀行格式、不建多銀行 framework，也不先建立依賴實際 parser 契約的 Statement schema。前端行為測試隨 S7 需要補強，不為完成舊清單而重排非核心功能，不全面重寫 `App.tsx`。

M7 `2b21333`、M8 `488cee7`、免費 API 文件與 Groq 程式 `eeb6883` 均已包含於目前 `main` 歷史；後續接手只以最新 Git HEAD 為準，不再使用 `4f9bfb5` 當最新遠端。

## M8 第一階段：Excel 自動投影已完成

M8 第一階段已完成專用 Excel 輸出、背景重試與設定介面；新目標以 Excel 為主要使用成果，但目前仍須 S6C 補正信用卡退款/繳款分類、自然月摘要及 Statement 狀態。SQLite 仍是唯一事實來源；啟用後會立即並每 30 秒檢查快照與輸出，只有需要更新時才重建應用程式擁有的工作簿，只輸出有效交易，另列待處理 PDF。撤銷/恢復反映在下一次輸出；Excel 佔用時保留舊版並重試；外部修改由 SHA-256 偵測，暫停下載後從 SQLite 重建。手寫內容會被重建覆蓋；下載為當次副本，持續更新的是設定的本機檔。預設路徑為 `data/exports/家庭收支記錄.xlsx`（由 storage_root 上層衍生），可由 `FAMILY_FINANCE_HUB_EXCEL_PATH` 覆寫。

密碼規則另修正候選值去重後規則索引錯位：預覽成功時會保存原始、真正命中的規則，不會因空白或重複候選值記錯規則。尚無經驗證的真實銀行 PDF parser，因此不能宣稱 PDF 已自動入帳。程式測試使用隔離合成 DB／PDF／Excel；本次另以使用者授權的 Gmail 網頁手動下載一份 PDF 做文件收錄/去重及預覽錯誤驗證，沒有建立財務交易。

## 前一輪文件更新的驗證

前一輪只更新 7 份 MD 的 S0-S9 規格及產品/交接說明，不執行業務功能、不連線 Gmail/AI、不操作正式 DB/SecretStore。當時契約測試 collection 為 18 項（未執行測試）；7 份文件的 12 個本機連結、11 個既有測試路徑及 code fences 檢查通過，`git diff --check` 通過。更新前後的 14 份既有已修改/未追蹤程式檔 SHA-256 完全相同，沒有新增或遺失程式變更。未重跑 backend suite 或 frontend build，不沿用前輪結果冒稱本次通過。

## 前輪程式驗證

- 2026-09-28 S0 基線（S1-S3 修改前）：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests -q -p no:cacheprovider`，128 passed、2 個既有 FastAPI TestClient／Starlette anyio deprecation warnings；`npm --prefix frontend run build` 成功。此結果是修改前基線，不代表本輪程式改動後完整 backend suite 已通過。
- 2026-09-28 S1-S4 契約聚焦測試：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_gmail_sync.py backend/tests/test_password_rules.py backend/tests/test_pdf_api.py backend/tests/test_pdf_processor.py backend/tests/test_pdf_processing.py backend/tests/test_statement_contracts.py -q -p no:cacheprovider`，74 passed、2 個既有 FastAPI TestClient／Starlette anyio deprecation warnings；僅使用合成資料。覆蓋 Gmail 自訂 query 與 history 隔離、密碼提示上下文／遮罩、寄件者 profile 唯一匹配及加密 PDF 預覽整合、Statement 契約與月報語意。
- 前輪 S1-S4 修改後 `git diff --check` 通過；當時未重跑完整 backend suite 或 frontend build。接手須重驗 S0，並依新計畫在 S6/S7/S9 跑完整關卡。

## 本輪程式驗證

- 2026-09-29 免費 AI provider 實作回歸：`.\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider --basetemp .pytest-tmp\free-ai-status`，187 passed、2 個既有 FastAPI/anyio 相依套件棄用警告。
- 2026-09-29 Frontend production build：`npm --prefix frontend run build` 成功；`git diff --check` 通過。
- 合成測試覆蓋 Groq/OpenAI dispatch、legacy profile、遮罩 payload、verified cache、失敗不 fallback、設定 API/UI 與 PDF preview contract；未把真實 Groq key 或真實帳單內容放進測試。
- 實際服務 smoke check 顯示已保存 provider 仍為 OpenAI；授權 Gmail 網頁下載的 PDF 已收錄，重複 bytes 回報 `duplicate=true`，AI 預覽因 OpenAI 額度不足停止，Finance transaction 維持 0。

## 目前產品方向的重新審查 Gate

2026-09-28 使用者重新確認：近期核心需求不是繼續擴張「家庭資料平台」，而是**每月信用卡帳單自動分析**。最新詳細需求、疑似 Overdesign 清單、建議簡化方向與交給高階模型的 12 個審查問題，集中在 `ARCHITECTURE_REVIEW_BRIEF.md`。

在高階模型重新審查前，不要因該文件的候選方案直接刪除 Gmail incremental sync、Documents 1:N、revocation、OCR 或 Excel safety；它們是「需判斷是否值得簡化」而不是「已決定移除」。同時也不要新增 Drive、其他家庭 domain、通用 AI、Push/PubSub 等非核心能力。

近期開發優先序應暫時指向：
1. 第一份真實信用卡帳單與 bank-specific parser。
2. 密碼規則上下文擷取的真實郵件可靠性。
3. sender/profile 自動匹配。
4. 再由高階審查結果決定 Gmail scheduler/incremental sync 與 Excel background projection 是否收斂。


## 最近程式驗證

- M8 Backend：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m8-full`，120 passed、2 個既有 FastAPI TestClient／Starlette anyio deprecation warnings。覆蓋 Excel 完整重建、冪等、撤銷／恢復、檔案佔用、重新啟動、外部修改偵測、下載保護，以及 PDF 密碼規則原始索引回歸。
- M8 Frontend：`npm run build` 成功；以 `http://127.0.0.1:5190/?view=settings` 搭配隔離合成 DB 驗證 Excel 啟用、立即更新、4 筆交易、1 份待處理 PDF 與下載入口。桌面及 390px／320px 均無水平溢出，console error 為空。
- M8 Migration：空白隔離 SQLite 由 `0001` 完整升級至 `0010_workbook_export`，Alembic version 查詢為 `0010_workbook_export`。使用中的資料庫尚未遷移。
- M7.1-M7.2 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-2`，69 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。
- M7.1-M7.2 Frontend：`npm run build` 成功；隔離合成資料瀏覽器驗證搜尋結果頁、URL／上一頁、分頁、新增資料入口、未授權 Gmail 下一步、文件詳情、來源連結與匯入歷史，沒有目前頁面的 console error。
- M7.3 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-3-final`，70 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。覆蓋 Dashboard 跨月、多幣別、空期間、幣別／月份格式錯誤、有效文件條件及撤銷／恢復回歸。
- M7.3 Frontend：`npm run build` 成功；以 `http://127.0.0.1:5188/` 搭配隔離合成 DB/storage 驗證本月總覽、空月份、月份／幣別控制，以及「查看全部交易」保留 `month` URL 條件；新分頁沒有 console error。
- M7.4 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-4-full`，70 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings；PDF focused suite 為 10 passed。新增 PDF 錯誤分類的 CORS header 暴露驗證。
- M7.4 Frontend：`npm run build` 成功；以 `http://127.0.0.1:5189/` 搭配隔離合成 DB/storage 驗證設定四組分頁、一般 PDF 自動預覽、OCR 未就緒提示、加密 PDF 需要解鎖提示、PDF／撤銷對話框 Escape 回到觸發按鈕及 Shift+Tab 焦點循環；目前頁面 console error 為空。
- M7.5 Frontend：`npm run build` 成功；以隔離合成資料驗證交易頁桌面回歸，並用 Chromium device metrics 實際量測 390px／320px：`body.scrollWidth` 與 viewport 相等、交易表格 `scrollWidth` 等於內容寬度、項目／金額／日期／來源均在列內，五個主導覽維持單排。交易表格已抽至 `frontend/src/TransactionTable.tsx`，空狀態抽至 `frontend/src/EmptyState.tsx`；目前未建立獨立 frontend test runner。

- Backend：`.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/revocation-final`，67 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。覆蓋撤銷範圍、多幣別、恢復、冪等、過期預覽、失敗回滾、Gmail 已撤銷文件保護及備份／migration。
- OCR/PDF processor focused tests：10 passed；含加密 PDF 解密後才呼叫 provider、OCR 錯誤不阻斷預覽、Tesseract 語言資料預檢及 stdin 資料流測試。
- 使用目前 Codex Python runtime 的 PDFium 對合成 PDF 實際渲染一頁至記憶體，Tesseract 子程序以 stub 驗證 PNG stdin/output；不是實際辨識品質驗收。
- Frontend：`npm run build` 成功。
- 瀏覽器以隔離合成帳單驗證桌面及 390px／320px 手機版撤銷、恢復、取消、摘要更新與過期預覽 409 後重新確認；沒有頁面水平溢出。撤銷後僅剩另一份文件的交易，恢復後精確回到原有四筆與各幣別金額。正常流程無 console 錯誤。
- 上一輪驗證預覽為 `http://127.0.0.1:5177/`，API 為 8018；DB/storage 位於忽略的 `backend/.test-tmp/lifecycle-preview-20260926/`。僅含合成資料，與正式資料隔離；此處記錄驗證環境，不保證服務持續執行。
- 修正 PDF OCR 狀態標頭未透過 CORS 暴露的整合問題；跨來源 API 測試通過，瀏覽器以合成 PDF 驗證「OCR 尚未就緒」提示出現且仍可預覽。
- Alembic head 為 `0010_workbook_export`；`0009_document_revocation` 的既有資料保留與 downgrade 防護仍由測試覆蓋。OCR 無 schema migration。
- `backend/tests/test_backup_restore.py` 以有效／已撤銷兩種合成 DB + documents storage 演練備份／還原，恢復 PDF bytes、Finance transaction、撤銷狀態及工作紀錄；已撤銷交易需明確恢復才重新計入。
- Tesseract executable 與 `chi_tra`/`eng` runtime 尚未完成真實 OCR 驗收。較早的「Tailscale CLI/service 未找到」已被後續部署結果取代：Tailscale 私有 HTTPS → `localhost:3000` 已驗證可用；仍待重新開機自動觸發與實體 iPhone/MacBook 驗收。

## 正式使用與外部驗收

此主機已使用成對備份後升級至 `0010_workbook_export` 的 `data/family-finance-hub-live.db`；舊 DB 仍保留且不可直接用新版程式啟動。其他主機若尚未升級，仍須先停止 API、成對備份 DB/storage、確認位址後依 `docs/operations.md` 操作。

1. OCR 為條件式待辦，不是下一步前置：僅當 S4 真實帳單證明文字抽取不足，才安裝/驗收 Tesseract 及 `chi_tra`/`eng` traineddata。缺語言資料的提早檢查已有合成測試，真實 runtime 尚未驗收；近期順序依 S0-S9，不先擴充 OCR。
2. 由使用者設定 Google Cloud OAuth 桌面 client 並在家庭主機互動授權；以真實台灣信用卡帳單在本機核對解密和 OCR 結果，不把帳單放入 repository。
3. 根據核對過的真實格式定義 bank-specific `BankStatementParser`/profile，補日期、幣別、金額、退款與冪等映射；通過人工核對前不自動寫交易。
4. 完成 Windows 開機啟動與背景常駐包裝，並確認 Gmail OAuth refresh token 在選定發布狀態下可長期使用；不要用測試中的短效授權宣稱已可長期自動化。
5. 安裝/登入 Tailscale 並確認家庭裝置與 Windows Firewall 規則後，再做遠端 Web 使用檢查。不要公開服務或設 router port forwarding。
6. 尚未驗證真實資料庫的生產備份/還原；目前只完成隔離合成 rehearsal。未提供自動或加密備份。
7. 搜尋分頁已列入 M7.1，不再等資料量增長才處理；工作歷史目前最多 100 筆，其分頁與匯入批次大小另依使用量評估。

## 安全界線

- 不讀取或回填先前對話裡曾提供的個人秘密；SQLite、log、repository 與 plaintext config 不可存 secrets。身分資料、PDF password、OAuth token 只透過使用者明確操作的本機 SecretStore/Credential Manager。
- 程式測試與 restore rehearsal 僅用合成資料及隔離 SQLite/storage；本次真實 Gmail 操作限於使用者授權的網頁手動下載與本機文件收錄，FamilyHub 內建 Gmail OAuth 仍未設定，不據此宣稱自動同步已完成。
- 正式升級前先確認 DB 與 storage 路徑，停止 API 並成對備份 DB 和 `data/documents`，再明確執行 migration；禁止刪除/重建舊 DB 或讓 app 靜默升級 schema。
- 不自動 commit、push 或覆蓋其他既有修改。
